import os
import sys
import unittest
from types import SimpleNamespace

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

from main import send_fall_alert


class FakeBot:
    def __init__(self):
        self.uploads = []
        self.webhooks = []

    def upload_image(self, path):
        self.uploads.append(path)
        return "img_v2_test"

    def send_webhook(self, title, content, image_key=""):
        self.webhooks.append((title, content, image_key))
        return {"code": 0}


class FakeStore:
    def __init__(self):
        self.metrics = []

    def now_text(self):
        return "2026-07-07 16:00:00"

    def add_metrics(self, **kwargs):
        self.metrics.append(kwargs)


class FallAlertTests(unittest.TestCase):
    def test_confirmed_fall_alert_includes_skeleton_evidence_when_available(self):
        bot = FakeBot()
        store = FakeStore()
        alert = send_fall_alert(bot, store)

        alert("检测到疑似摔倒", "卧室", evidence_path="/tmp/critical_evidence.jpg")

        self.assertEqual(bot.uploads, ["/tmp/critical_evidence.jpg"])
        self.assertEqual(bot.webhooks[0][2], "img_v2_test")
        self.assertEqual(store.metrics, [{"alerts_sent_count": 1}])


if __name__ == "__main__":
    unittest.main()
