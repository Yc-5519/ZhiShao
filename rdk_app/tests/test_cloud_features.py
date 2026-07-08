import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

class FakeSerialConn:
    is_open = True

    def write(self, _data):
        return None

    def close(self):
        self.is_open = False


sys.modules.setdefault("serial", SimpleNamespace(Serial=lambda *args, **kwargs: FakeSerialConn()))

from services.app_service import AppService
from services.store import Store
import services.web_dashboard as web_dashboard


class FakeRuntime:
    def __init__(self, **overrides):
        self.overrides = overrides

    def snapshot(self):
        data = {
            "running": True,
            "camera_ok": True,
            "camera_message": "正常",
            "monitor_url": "https://care.example.com",
            "public_monitor_url": "https://care.example.com",
            "lan_monitor_url": "http://10.0.0.2:5000",
            "raw_video_allowed": False,
            "raw_video_seconds_left": 0,
            "care_mode": "边界看护",
            "follow_enabled": True,
            "ptz_mode": "跟随/待命",
            "fall_mode": "保守",
            "fall_state": "NORMAL",
            "target_count": 1,
            "raw_pose_count": 1,
            "last_seen_time": "刚刚",
        }
        data.update(self.overrides)
        return data


class FakeStore:
    def __init__(self, **metric_overrides):
        self.metric_overrides = metric_overrides

    def get_metrics(self):
        metrics = {
            "seen_seconds": 600,
            "active_seconds": 300,
            "suspect_fall_count": 0,
            "confirmed_fall_count": 0,
            "last_seen_time": "刚刚",
        }
        metrics.update(self.metric_overrides)
        return metrics

    def list_events(self, limit=8, date=None):
        return []

    def today(self):
        return "2026-06-24"

    def access_summary(self, date=None):
        return "今日公网访问 2 次，最近一次 20:01 /health 200。"

    def record_event(self, *args, **kwargs):
        return None


class FakeFrameHub:
    def get_skeleton(self):
        return None

    def raw_age(self):
        return 999.0

    def skeleton_age(self):
        return 999.0


class FakeVision:
    is_moving = False

    def lock_status_text(self):
        return "锁定状态测试"


class FakePtz:
    def serial_ok(self):
        return True


class FakeReport:
    def send_report(self):
        return None


class FakeBrain:
    def ask(self, *args, **kwargs):
        return None

    def health_check(self):
        return {"ok": True, "label": "VLM 大脑", "detail": "http://127.0.0.1:9000/health"}


class CloudFeatureTests(unittest.TestCase):
    def make_app(self, brain=None, store=None, runtime=None):
        return AppService(
            store or FakeStore(),
            runtime or FakeRuntime(),
            FakeFrameHub(),
            FakeVision(),
            FakePtz(),
            FakeReport(),
            brain or FakeBrain(),
            SimpleNamespace(),
        )

    def test_family_summary_reports_current_state_before_today_high_risk(self):
        app = self.make_app(store=FakeStore(confirmed_fall_count=1), runtime=FakeRuntime(target_count=1))

        text = app.family_summary()

        first_line, second_line, *_ = text.splitlines()
        self.assertIn("当前能看到可信人体目标", first_line)
        self.assertIn("今天出现过高风险提醒", second_line)

    def test_monitor_url_prefers_configured_public_url(self):
        with mock.patch.object(web_dashboard, "PUBLIC_MONITOR_URL", "https://care.example.com/"):
            self.assertEqual(web_dashboard.get_monitor_url(5000), "https://care.example.com")
            self.assertEqual(web_dashboard.get_public_monitor_url(), "https://care.example.com")

    def test_self_check_reports_public_and_vlm_connectivity(self):
        fake_response = SimpleNamespace(status_code=200)
        with mock.patch("services.app_service.requests.get", return_value=fake_response):
            text = self.make_app().self_check()
        self.assertIn("公网入口", text)
        self.assertIn("https://care.example.com", text)
        self.assertIn("VLM 大脑", text)
        self.assertIn("通过", text)

    def test_self_check_treats_public_auth_challenge_as_reachable(self):
        fake_response = SimpleNamespace(status_code=401)
        with mock.patch("services.app_service.requests.get", return_value=fake_response):
            text = self.make_app().self_check()
        self.assertIn("通过 - 公网入口", text)
        self.assertIn("需要登录", text)

    def test_ask_brain_falls_back_to_local_status_when_vlm_unavailable(self):
        answer = self.make_app().ask_brain("现在安全吗")
        self.assertFalse(answer["need_image"])
        self.assertIn("云端大脑暂时连接不上", answer["answer"])
        self.assertIn("本地看护仍在运行", answer["answer"])
        self.assertIn("安心状态", answer["answer"])

    def test_web_status_route_uses_compact_payload(self):
        app = SimpleNamespace(status_payload=mock.Mock(return_value={"ok": True}))
        dashboard = web_dashboard.WebDashboard(app)

        with dashboard.flask.test_client() as client:
            response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        app.status_payload.assert_called_once_with(compact=True)

    def test_video_stream_reuses_cached_jpeg_frame(self):
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        app = SimpleNamespace(get_video_frame=mock.Mock(return_value=frame))
        dashboard = web_dashboard.WebDashboard(app)

        with mock.patch.object(web_dashboard.time, "time", return_value=1000.0):
            first = dashboard._jpeg_bytes("skeleton")
            second = dashboard._jpeg_bytes("skeleton")

        self.assertTrue(first.startswith(b"\xff\xd8"))
        self.assertEqual(first, second)
        app.get_video_frame.assert_called_once_with("skeleton")

    def test_dashboard_pauses_video_stream_when_page_hidden(self):
        app = SimpleNamespace(status_payload=mock.Mock(return_value={"ok": True}))
        dashboard = web_dashboard.WebDashboard(app)
        html = dashboard._html()

        self.assertIn("document.addEventListener('visibilitychange'", html)
        self.assertIn("removeAttribute('src')", html)
        self.assertIn("startSnapshotLoop();", html)
        self.assertNotIn('src="/video/skeleton"', html)

    def test_dashboard_uses_snapshot_endpoint_for_default_lightweight_video(self):
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        app = SimpleNamespace(get_video_frame=mock.Mock(return_value=frame), status_payload=mock.Mock(return_value={"ok": True}))
        dashboard = web_dashboard.WebDashboard(app)

        with dashboard.flask.test_client() as client:
            response = client.get("/snapshot/skeleton.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/jpeg")
        self.assertTrue(response.data.startswith(b"\xff\xd8"))
        self.assertIn("/snapshot/", dashboard._html())

    def test_mobile_dashboard_stacks_sections_in_single_column(self):
        app = SimpleNamespace(status_payload=mock.Mock(return_value={"ok": True}))
        dashboard = web_dashboard.WebDashboard(app)
        html = dashboard._html()

        self.assertIn("@media(max-width:900px)", html)
        self.assertIn("overflow-x:hidden", html)
        self.assertIn(".side{display:flex;flex-direction:column", html)
        self.assertIn(".buttons{grid-template-columns:repeat(3,minmax(0,1fr))", html)
        self.assertIn(".events{max-height:220px", html)


class StoreAccessLogTests(unittest.TestCase):
    def test_access_summary_uses_existing_events_without_sensitive_values(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = Store(os.path.join(tmp, "zhishao.db"))
            store.record_web_access("GET", "/", 200, "1.2.3.4", "Mozilla/5.0")
            store.record_web_access("POST", "/api/command", 200, "1.2.3.4", "secret-token")
            summary = store.access_summary()
        self.assertIn("今日公网访问 2 次", summary)
        self.assertIn("/api/command", summary)
        self.assertNotIn("secret-token", summary)
        self.assertNotIn("1.2.3.4", summary)


if __name__ == "__main__":
    unittest.main()
