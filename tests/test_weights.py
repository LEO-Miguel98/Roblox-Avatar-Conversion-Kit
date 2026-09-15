import unittest

from roblox_avatar_conversion_kit.rig import Bone
from roblox_avatar_conversion_kit.weights import weights_for_point


class WeightTests(unittest.TestCase):
    def setUp(self):
        self.bones = [
            Bone("hips", None, (0, 0, 0)),
            Bone("spine", "hips", (0, 1, 0)),
            Bone("chest", "spine", (0, 2, 0)),
            Bone("leftUpperArm", "chest", (1, 2, 0)),
            Bone("leftLowerArm", "leftUpperArm", (2, 2, 0)),
            Bone("leftHand", "leftLowerArm", (3, 2, 0)),
        ]

    def test_weights_normalize_and_blend(self):
        weights = weights_for_point((1.9, 2, 0), "leftUpperArm", self.bones)
        self.assertAlmostEqual(sum(weight.weight for weight in weights), 1.0, places=6)
        self.assertGreaterEqual(len(weights), 2)
        self.assertIn("leftLowerArm", {weight.bone for weight in weights})

    def test_max_four_influences(self):
        self.assertLessEqual(len(weights_for_point((0, 1, 0), "spine", self.bones)), 4)


if __name__ == "__main__":
    unittest.main()
