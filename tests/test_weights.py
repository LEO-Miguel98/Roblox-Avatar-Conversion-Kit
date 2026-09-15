import unittest

from roblox_avatar_conversion_kit.rig import Bone
from roblox_avatar_conversion_kit.weights import PRIMARY_WEIGHT_FLOORS, weights_for_point


class WeightTests(unittest.TestCase):
    def setUp(self):
        self.bones = [
            Bone("hips", None, (0, 0, 0)),
            Bone("spine", "hips", (0, 1, 0)),
            Bone("chest", "spine", (0, 2, 0)),
            Bone("neck", "chest", (0, 2.5, 0)),
            Bone("head", "neck", (0, 3, 0)),
            Bone("leftUpperArm", "chest", (1, 2, 0)),
            Bone("leftLowerArm", "leftUpperArm", (2, 2, 0)),
            Bone("leftHand", "leftLowerArm", (3, 2, 0)),
        ]

    def test_weights_normalize_blend_and_keep_primary_floor(self):
        weights = weights_for_point((1.9, 2, 0), "leftUpperArm", self.bones)
        self.assertAlmostEqual(sum(weight.weight for weight in weights), 1.0, places=6)
        self.assertGreaterEqual(len(weights), 2)
        by_name = {weight.bone: weight.weight for weight in weights}
        self.assertIn("leftLowerArm", by_name)
        self.assertGreaterEqual(by_name["leftUpperArm"], PRIMARY_WEIGHT_FLOORS["leftUpperArm"])

    def test_head_stays_almost_rigid(self):
        weights = weights_for_point((0, 2.6, 0), "head", self.bones)
        by_name = {weight.bone: weight.weight for weight in weights}
        self.assertGreaterEqual(by_name["head"], 0.97)

    def test_max_four_influences(self):
        self.assertLessEqual(len(weights_for_point((0, 1, 0), "spine", self.bones)), 4)


if __name__ == "__main__":
    unittest.main()
