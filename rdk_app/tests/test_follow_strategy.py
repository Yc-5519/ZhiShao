import os
import sys
import time
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

from services.target_tracker import TargetTracker
import services.ptz_service as ptz_service
import settings
from services.ptz_service import PTZService


def target(cx, cy=240, area=16000, track_id=None, appearance=None):
    appearance = np.array(appearance or [1.0, 0.0, 0.0], dtype=np.float32)
    appearance = appearance / max(float(np.linalg.norm(appearance)), 1e-6)
    width = area ** 0.5
    box = (cx - width / 2, cy - width / 2, cx + width / 2, cy + width / 2)
    data = {
        "cx": cx,
        "cy": cy,
        "area": area,
        "box": box,
        "appearance": appearance,
        "kpts": np.zeros((17, 3), dtype=np.float32),
    }
    if track_id is not None:
        data["track_id"] = track_id
    return data


class TargetTrackerFollowTests(unittest.TestCase):
    def test_default_follow_tuning_prefers_smooth_demo_behavior(self):
        self.assertEqual(settings.VISION_INFERENCE_MAX_FPS, 8.0)
        self.assertEqual(settings.PTZ_DEADZONE_X, 90)
        self.assertEqual(settings.PTZ_DEADZONE_Y, 75)
        self.assertEqual(settings.PTZ_MAX_STEP_X, 6.0)
        self.assertEqual(settings.PTZ_MAX_STEP_Y, 4.0)
        self.assertEqual(settings.TARGET_LOCK_REACQUIRE_SECONDS, 18.0)

    def test_lock_reacquires_same_person_after_short_disappearance(self):
        tracker = TargetTracker()
        first = target(320, appearance=[0.9, 0.1, 0.0])
        active, _reason = tracker.choose([first])
        self.assertIsNotNone(active)
        ok, _reply = tracker.lock_current()
        self.assertTrue(ok)

        tracker.tracks = {}
        tracker.last_locked_seen = time.time() - 3.0
        candidate = target(340, appearance=[0.88, 0.12, 0.0])
        active, _reason = tracker.choose([candidate])

        self.assertIsNotNone(active)
        self.assertEqual(tracker.lock_state, "短时重识别锁定")
        self.assertEqual(tracker.ptz_follow_target.get("track_id"), tracker.locked_track_id)

    def test_competition_mode_does_not_follow_unlocked_person(self):
        tracker = TargetTracker()
        tracker.require_lock_for_follow = True

        active, reason = tracker.choose([target(360)])

        self.assertIsNotNone(active)
        self.assertIsNone(tracker.ptz_follow_target)
        self.assertIn("锁定", reason)


    def test_locked_target_loss_message_does_not_call_returning_target_stranger(self):
        tracker = TargetTracker()
        first = target(320, appearance=[0.9, 0.1, 0.0])
        tracker.choose([first])
        ok, _reply = tracker.lock_current()
        self.assertTrue(ok)

        tracker.last_locked_seen = time.time() - 4.0
        active, reason = tracker.choose([])

        self.assertIsNone(active)
        self.assertNotIn("陌生人", reason)
        self.assertNotIn("生人", reason)


    def test_locked_single_person_keeps_original_id_after_brief_gap(self):
        tracker = TargetTracker()
        tracker.choose([target(320, appearance=[0.8, 0.2, 0.0])])
        ok, _reply = tracker.lock_current()
        self.assertTrue(ok)
        locked_id = tracker.locked_track_id

        tracker.choose([])
        tracker.tracks = {}
        tracker.last_locked_seen = time.time() - 2.0
        active, _reason = tracker.choose([target(500, appearance=[0.7, 0.3, 0.0])])

        self.assertIsNotNone(active)
        self.assertEqual(active.get("track_id"), locked_id)
        self.assertEqual(tracker.locked_track_id, locked_id)

    def test_different_person_is_not_reused_as_locked_id_after_brief_gap(self):
        tracker = TargetTracker()
        tracker.choose([target(120, appearance=[1.0, 0.0, 0.0])])
        ok, _reply = tracker.lock_current()
        self.assertTrue(ok)
        locked_id = tracker.locked_track_id

        tracker.choose([])
        tracker.tracks = {}
        tracker.last_locked_seen = time.time() - 2.0
        active, _reason = tracker.choose([target(560, appearance=[0.0, 1.0, 0.0])])

        self.assertIsNone(active)
        self.assertIsNone(tracker.ptz_follow_target)
        self.assertEqual(tracker.locked_track_id, locked_id)


class FakePTZ:
    def __init__(self):
        self.current_pan = 90
        self.current_tilt = 90
        self.pan_commands = []
        self.tilt_commands = []
        self.center_calls = 0

    def ensure_connected(self):
        return True

    def is_open(self):
        return True

    def set_pan(self, angle):
        self.current_pan = int(angle)
        self.pan_commands.append(self.current_pan)
        return True

    def set_tilt(self, angle):
        self.current_tilt = int(angle)
        self.tilt_commands.append(self.current_tilt)
        return True

    def center(self):
        self.center_calls += 1
        self.current_pan = 90
        self.current_tilt = 90
        return True


class RuntimeStub:
    def __init__(self):
        self.values = {}

    def update(self, **kwargs):
        self.values.update(kwargs)


class PTZFollowControlTests(unittest.TestCase):
    def setUp(self):
        self.fake_ptz = FakePTZ()
        self.original_ptz = ptz_service.ptz
        self.original_values = {
            "PTZ_DEADZONE_X": ptz_service.PTZ_DEADZONE_X,
            "PTZ_DEADZONE_Y": ptz_service.PTZ_DEADZONE_Y,
            "PTZ_KP_X": ptz_service.PTZ_KP_X,
            "PTZ_KP_Y": ptz_service.PTZ_KP_Y,
        }
        self.original_optional = {
            name: getattr(ptz_service, name, None)
            for name in (
                "PTZ_MAX_STEP_X",
                "PTZ_MAX_STEP_Y",
                "PTZ_MIN_STEP_X",
                "PTZ_MIN_STEP_Y",
                "PTZ_COMMAND_INTERVAL",
                "PTZ_NO_TARGET_SEARCH_DELAY_SECONDS",
                "PTZ_NO_TARGET_SEARCH_DURATION_SECONDS",
            )
        }
        ptz_service.ptz = self.fake_ptz
        ptz_service.PTZ_DEADZONE_X = 40
        ptz_service.PTZ_DEADZONE_Y = 40
        ptz_service.PTZ_KP_X = 0.05
        ptz_service.PTZ_KP_Y = 0.04
        ptz_service.PTZ_MAX_STEP_X = 5
        ptz_service.PTZ_MAX_STEP_Y = 4
        ptz_service.PTZ_MIN_STEP_X = 1
        ptz_service.PTZ_MIN_STEP_Y = 1
        ptz_service.PTZ_COMMAND_INTERVAL = 0.0
        ptz_service.PTZ_NO_TARGET_SEARCH_DELAY_SECONDS = 60.0
        ptz_service.PTZ_NO_TARGET_SEARCH_DURATION_SECONDS = 20.0

    def tearDown(self):
        ptz_service.ptz = self.original_ptz
        for name, value in self.original_values.items():
            setattr(ptz_service, name, value)
        for name, value in self.original_optional.items():
            if value is None and hasattr(ptz_service, name):
                delattr(ptz_service, name)
            elif value is not None:
                setattr(ptz_service, name, value)

    def test_follow_uses_configured_deadzone_and_gain(self):
        service = PTZService(RuntimeStub())

        service.follow(target(370))

        self.assertTrue(self.fake_ptz.pan_commands)
        self.assertEqual(self.fake_ptz.pan_commands[-1], 87)

    def test_follow_caps_large_single_step(self):
        service = PTZService(RuntimeStub())

        service.follow(target(620))

        self.assertEqual(self.fake_ptz.pan_commands[-1], 85)

    def test_no_target_waits_one_minute_before_searching(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        service.last_seen = 100.0
        service.kf_enabled = False

        with mock.patch("services.ptz_service.time.time", return_value=159.0):
            service.on_no_target()

        self.assertFalse(self.fake_ptz.pan_commands)
        self.assertEqual(self.fake_ptz.center_calls, 0)
        self.assertEqual(runtime.values["ptz_mode"], "等待目标经过")

    def test_no_target_searches_after_one_minute_then_centers(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        service.last_seen = 100.0
        service.kf_enabled = False

        with mock.patch("services.ptz_service.time.time", return_value=161.0):
            service.on_no_target()

        self.assertTrue(self.fake_ptz.pan_commands)
        self.assertEqual(runtime.values["ptz_mode"], "无人搜索")

        with mock.patch("services.ptz_service.time.time", return_value=182.0):
            service.on_no_target()

        self.assertEqual(self.fake_ptz.center_calls, 1)
        self.assertEqual(runtime.values["ptz_mode"], "回中等待")


    def test_lost_target_immediately_continues_last_seen_direction(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        service.last_calc = 100.0
        service.last_cmd = 0.0
        service.kf_enabled = False

        with mock.patch("services.ptz_service.time.time", return_value=100.0):
            service.follow(target(620))

        first_pan = self.fake_ptz.current_pan
        with mock.patch("services.ptz_service.time.time", return_value=104.0):
            service.on_no_target()

        self.assertLess(self.fake_ptz.current_pan, first_pan)

    def test_lost_target_uses_last_screen_side_even_before_servo_moved(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        service.last_calc = 100.0
        service.last_cmd = 0.0
        service.kf_enabled = False

        with mock.patch("services.ptz_service.time.time", return_value=100.0):
            service.follow(target(350))

        self.assertFalse(self.fake_ptz.pan_commands)
        first_pan = self.fake_ptz.current_pan
        with mock.patch("services.ptz_service.time.time", return_value=101.0):
            service.on_no_target()

        self.assertLess(self.fake_ptz.current_pan, first_pan)

    def test_fall_focus_tilts_down_without_horizontal_switch(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        start_pan = self.fake_ptz.current_pan
        start_tilt = self.fake_ptz.current_tilt

        service.focus_fall_target(target(600, cy=430))

        self.assertEqual(self.fake_ptz.current_pan, start_pan)
        self.assertGreater(self.fake_ptz.current_tilt, start_tilt)

    def test_fall_focus_does_not_keep_tilting_when_target_is_not_low(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        start_pan = self.fake_ptz.current_pan
        start_tilt = self.fake_ptz.current_tilt

        service.focus_fall_target(target(330, cy=230))

        self.assertEqual(self.fake_ptz.current_pan, start_pan)
        self.assertEqual(self.fake_ptz.current_tilt, start_tilt)
        self.assertEqual(runtime.values["ptz_mode"], "摔倒风险观察")

    def test_fall_focus_temporarily_blocks_no_target_side_search(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)
        service.last_target_direction = 1

        with mock.patch("services.ptz_service.time.time", return_value=100.0):
            service.focus_fall_target(target(330, cy=430))
        pan_after_focus = self.fake_ptz.current_pan

        with mock.patch("services.ptz_service.time.time", return_value=101.0):
            service.on_no_target()

        self.assertEqual(self.fake_ptz.current_pan, pan_after_focus)
        self.assertEqual(runtime.values["ptz_mode"], "摔倒风险保持")

    def test_fall_focus_temporarily_blocks_normal_follow_pan(self):
        runtime = RuntimeStub()
        service = PTZService(runtime)

        with mock.patch("services.ptz_service.time.time", return_value=100.0):
            service.focus_fall_target(target(330, cy=430))
        pan_after_focus = self.fake_ptz.current_pan

        with mock.patch("services.ptz_service.time.time", return_value=101.0):
            service.follow(target(620, cy=260))

        self.assertEqual(self.fake_ptz.current_pan, pan_after_focus)
        self.assertEqual(runtime.values["ptz_mode"], "摔倒风险保持")


if __name__ == "__main__":
    unittest.main()
