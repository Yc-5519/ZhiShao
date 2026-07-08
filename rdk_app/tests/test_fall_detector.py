import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.fall_detector import FallDetector
from services.pose_validator import PoseValidator


class StoreStub:
    def set_metrics(self, **_kwargs):
        pass

    def add_metrics(self, **_kwargs):
        pass

    def record_event(self, *_args, **_kwargs):
        pass


class BrainStub:
    pass


def fallen_target_without_head_or_legs():
    kpts = np.zeros((17, 3), dtype=np.float32)
    kpts[5] = [180, 360, 0.82]
    kpts[6] = [220, 360, 0.82]
    kpts[11] = [360, 365, 0.82]
    kpts[12] = [400, 365, 0.82]
    return {
        "track_id": 7,
        "cx": 320,
        "cy": 395,
        "area": 66000,
        "box": (100, 320, 540, 470),
        "kpts": kpts,
        "fall_eligible": True,
    }


class FallDetectorRiskTests(unittest.TestCase):
    def test_validator_keeps_low_horizontal_torso_as_fall_eligible_target(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        box = np.array([[100, 320, 540, 470]], dtype=np.float32)
        scores = np.array([0.88], dtype=np.float32)
        kpts = fallen_target_without_head_or_legs()["kpts"]
        validator = PoseValidator()

        targets = validator.validate(frame, box, scores, [kpts])

        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0]["fall_eligible"])

    def test_low_horizontal_torso_can_be_fall_risk_even_with_missing_head_or_legs(self):
        detector = FallDetector(StoreStub(), BrainStub(), lambda *_args, **_kwargs: None)

        risky = detector.quick_risk_targets([fallen_target_without_head_or_legs()])

        self.assertEqual(len(risky), 1)


if __name__ == "__main__":
    unittest.main()
