import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

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
    def snapshot(self):
        return {
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


class FakeStore:
    def get_metrics(self):
        return {
            "seen_seconds": 600,
            "active_seconds": 300,
            "suspect_fall_count": 0,
            "confirmed_fall_count": 0,
            "last_seen_time": "刚刚",
        }

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
    def make_app(self, brain=None):
        return AppService(
            FakeStore(),
            FakeRuntime(),
            FakeFrameHub(),
            FakeVision(),
            FakePtz(),
            FakeReport(),
            brain or FakeBrain(),
            SimpleNamespace(),
        )

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

    def test_ask_brain_falls_back_to_local_status_when_vlm_unavailable(self):
        answer = self.make_app().ask_brain("现在安全吗")
        self.assertFalse(answer["need_image"])
        self.assertIn("云端大脑暂时连接不上", answer["answer"])
        self.assertIn("本地看护仍在运行", answer["answer"])
        self.assertIn("安心状态", answer["answer"])


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
