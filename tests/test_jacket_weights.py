import unittest

from roblox_avatar_conversion_kit.rig import Bone
from roblox_avatar_conversion_kit.weights import weights_for_layered_point


class JacketWeightTests(unittest.TestCase):
    def setUp(self):
        self.bones = [
            Bone("hips", None, (0.0, 0.0, 0.0)),
            Bone("spine", "hips", (0.0, 1.0, 0.0)),
            Bone("chest", "spine", (0.0, 2.0, 0.0)),
            Bone("leftUpperArm", "chest", (1.0, 2.0, 0.0)),
            Bone("leftLowerArm", "leftUpperArm", (2.0, 2.0, 0.0)),
            Bone("leftHand", "leftLowerArm", (3.0, 2.0, 0.0)),
            Bone("rightUpperArm", "chest", (-1.0, 2.0, 0.0)),
            Bone("rightLowerArm", "rightUpperArm", (-2.0, 2.0, 0.0)),
            Bone("rightHand", "rightLowerArm", (-3.0, 2.0, 0.0)),
        ]

    def _by_name(self, point):
        values = weights_for_layered_point(point, self.bones, profile="upper_body")
        self.assertAlmostEqual(sum(value.weight for value in values), 1.0, places=6)
        self.assertLessEqual(len(values), 4)
        return {value.bone: value.weight for value in values}

    def test_jacket_torso_does_not_leak_into_limbs(self):
        values = self._by_name((0.0, 1.2, 0.0))
        self.assertTrue(set(values) <= {"hips", "spine", "chest"})

    def test_left_sleeve_is_side_locked(self):
        values = self._by_name((1.6, 2.0, 0.0))
        self.assertIn("leftUpperArm", values)
        self.assertIn("leftLowerArm", values)
        self.assertFalse(any(name.startswith("right") for name in values))

    def test_cuff_has_small_wrist_influence_not_hand_dominance(self):
        values = self._by_name((2.9, 2.0, 0.0))
        self.assertLessEqual(values.get("leftHand", 0.0), 0.15 + 1e-8)
        self.assertGreater(values.get("leftLowerArm", 0.0), values.get("leftHand", 0.0))

    def test_right_sleeve_never_crosses_to_left_arm(self):
        values = self._by_name((-2.4, 2.0, 0.0))
        self.assertFalse(any(name.startswith("left") for name in values))
        self.assertIn("rightLowerArm", values)


if __name__ == "__main__":
    unittest.main()
