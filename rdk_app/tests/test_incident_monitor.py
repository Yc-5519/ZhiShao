import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.incident_monitor import IncidentMonitorService


class FakeClock:
    def __init__(self, value=1000.0):
        self.value = value

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeBot:
    def __init__(self, response=None):
        self.messages = []
        self.response = {"ok": True} if response is None else response

    def send_webhook(self, title, content):
        self.messages.append((title, content))
        return self.response


class FakeStore:
    def __init__(self):
        self.events = []
        self.metrics = []

    def now_text(self):
        return "2026-07-01 10:00:00"

    def record_event(self, event_type, message, level="info", data=None, handled=False, action=""):
        self.events.append(
            {
                "type": event_type,
                "message": message,
                "level": level,
                "data": data or {},
                "handled": handled,
                "action": action,
            }
        )

    def add_metrics(self, **increments):
        self.metrics.append(increments)


class FakeRuntime:
    def __init__(self, **state):
        self.state = {
            "running": True,
            "camera_ok": True,
            "camera_message": "ok",
            "target_count": 1,
            "last_seen_time": "2026-07-01 09:59:00",
            "public_monitor_url": "http://public.example",
        }
        self.state.update(state)

    def snapshot(self):
        return dict(self.state)


class FakeFrameHub:
    def __init__(self, raw_age=1.0, skeleton_age=1.0):
        self._raw_age = raw_age
        self._skeleton_age = skeleton_age

    def raw_age(self):
        return self._raw_age

    def skeleton_age(self):
        return self._skeleton_age


class FakeBrain:
    def __init__(self, ok=True, detail="healthy"):
        self.ok = ok
        self.detail = detail

    def health_check(self):
        return {"ok": self.ok, "label": "VLM", "detail": self.detail}


def make_service(clock, runtime=None, frame_hub=None, brain=None, public_ok=True, bot=None):
    return IncidentMonitorService(
        FakeStore(),
        runtime or FakeRuntime(),
        frame_hub or FakeFrameHub(),
        brain or FakeBrain(),
        bot or FakeBot(),
        now=clock.now,
        sleep=lambda seconds: None,
        check_interval_seconds=1.0,
        alert_cooldown_seconds=60.0,
        camera_bad_seconds=5.0,
        frame_stale_seconds=5.0,
        brain_bad_seconds=5.0,
        public_bad_seconds=5.0,
        no_person_seconds=30.0,
        public_check=lambda _url: public_ok,
    )


class IncidentMonitorTests(unittest.TestCase):
    def test_camera_failure_sends_alert_after_threshold(self):
        clock = FakeClock()
        service = make_service(clock, runtime=FakeRuntime(camera_ok=False, camera_message="read failed"))

        service.check_once()
        clock.advance(6)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 1)
        title, content = service.bot.messages[0]
        self.assertIn("突发情况", title)
        self.assertIn("摄像头", content)
        self.assertIn("read failed", content)
        self.assertEqual(service.store.events[-1]["type"], "incident_camera")

    def test_cooldown_prevents_duplicate_alerts(self):
        clock = FakeClock()
        service = make_service(clock, runtime=FakeRuntime(camera_ok=False, camera_message="read failed"))

        service.check_once()
        clock.advance(6)
        service.check_once()
        clock.advance(10)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 1)

    def test_recovery_sends_resolved_message_after_alert(self):
        clock = FakeClock()
        runtime = FakeRuntime(camera_ok=False, camera_message="read failed")
        service = make_service(clock, runtime=runtime)

        service.check_once()
        clock.advance(6)
        service.check_once()
        runtime.state.update(camera_ok=True, camera_message="ok")
        service.check_once()

        self.assertEqual(len(service.bot.messages), 2)
        self.assertIn("已恢复", service.bot.messages[-1][0])
        self.assertEqual(service.store.events[-1]["type"], "incident_camera_recovered")

    def test_brain_unavailable_sends_alert_after_threshold(self):
        clock = FakeClock()
        service = make_service(clock, brain=FakeBrain(ok=False, detail="timeout"))

        service.check_once()
        clock.advance(6)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 1)
        self.assertIn("VLM", service.bot.messages[0][1])
        self.assertIn("timeout", service.bot.messages[0][1])
        self.assertEqual(service.store.events[-1]["type"], "incident_brain")

    def test_public_gateway_unavailable_sends_alert_after_threshold(self):
        clock = FakeClock()
        service = make_service(clock, public_ok=False)

        service.check_once()
        clock.advance(6)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 1)
        self.assertIn("公网", service.bot.messages[0][1])
        self.assertEqual(service.store.events[-1]["type"], "incident_public_gateway")

    def test_no_person_for_long_time_sends_camera_position_advice(self):
        clock = FakeClock()
        runtime = FakeRuntime(target_count=0, last_seen_time="2026-07-01 09:50:00")
        service = make_service(clock, runtime=runtime)

        service.check_once()
        clock.advance(31)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 1)
        self.assertIn("长时间没有看到人", service.bot.messages[0][1])
        self.assertIn("摄像头", service.bot.messages[0][1])
        self.assertEqual(service.store.events[-1]["type"], "incident_no_person")

    def test_no_person_recovery_sends_resolved_message(self):
        clock = FakeClock()
        runtime = FakeRuntime(target_count=0, last_seen_time="2026-07-01 09:50:00")
        service = make_service(clock, runtime=runtime)

        service.check_once()
        clock.advance(31)
        service.check_once()
        runtime.state.update(target_count=1)
        service.check_once()

        self.assertEqual(len(service.bot.messages), 2)
        self.assertEqual(service.store.events[-1]["type"], "incident_no_person_recovered")

    def test_alert_event_records_webhook_success(self):
        clock = FakeClock()
        service = make_service(clock, runtime=FakeRuntime(camera_ok=False, camera_message="read failed"))

        service.check_once()
        clock.advance(6)
        service.check_once()

        self.assertEqual(service.store.events[-1]["data"]["notify_ok"], True)
        self.assertEqual(service.store.events[-1]["data"]["notify_detail"], "ok")

    def test_alert_event_records_webhook_failure_summary(self):
        clock = FakeClock()
        bot = FakeBot(response={"code": 19001, "msg": "bad webhook"})
        service = make_service(clock, runtime=FakeRuntime(camera_ok=False, camera_message="read failed"), bot=bot)

        service.check_once()
        clock.advance(6)
        service.check_once()

        self.assertEqual(service.store.events[-1]["data"]["notify_ok"], False)
        self.assertIn("19001", service.store.events[-1]["data"]["notify_detail"])
        self.assertIn("bad webhook", service.store.events[-1]["data"]["notify_detail"])

    def test_default_no_person_threshold_is_practical_for_camera_movement(self):
        import settings

        self.assertLessEqual(settings.INCIDENT_NO_PERSON_SECONDS, 60.0)


if __name__ == "__main__":
    unittest.main()
