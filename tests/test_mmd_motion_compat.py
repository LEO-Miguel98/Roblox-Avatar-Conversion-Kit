import unittest

from roblox_avatar_conversion_kit.pmx import MMD_JP, _pmx_bones
from roblox_avatar_conversion_kit.rig import Bone


class MmdMotionCompatibilityTests(unittest.TestCase):
    def test_builds_classic_mmd_body_hierarchy_and_semistandard_helpers(self):
        bones = [
            Bone("hips", None, (0.0, 1.6, 0.0)),
            Bone("spine", "hips", (0.0, 2.0, 0.0)),
            Bone("chest", "spine", (0.0, 2.4, 0.0)),
            Bone("neck", "chest", (0.0, 2.8, 0.0)),
            Bone("head", "neck", (0.0, 3.2, 0.0)),
            Bone("leftUpperArm", "chest", (0.4, 2.4, 0.0)),
            Bone("leftLowerArm", "leftUpperArm", (0.8, 2.0, 0.0)),
            Bone("leftHand", "leftLowerArm", (1.1, 1.7, 0.0)),
            Bone("rightUpperArm", "chest", (-0.4, 2.4, 0.0)),
            Bone("rightLowerArm", "rightUpperArm", (-0.8, 2.0, 0.0)),
            Bone("rightHand", "rightLowerArm", (-1.1, 1.7, 0.0)),
            Bone("leftUpperLeg", "hips", (0.2, 1.3, 0.0)),
            Bone("leftLowerLeg", "leftUpperLeg", (0.2, 0.7, 0.0)),
            Bone("leftFoot", "leftLowerLeg", (0.2, 0.15, 0.0)),
            Bone("rightUpperLeg", "hips", (-0.2, 1.3, 0.0)),
            Bone("rightLowerLeg", "rightUpperLeg", (-0.2, 0.7, 0.0)),
            Bone("rightFoot", "rightLowerLeg", (-0.2, 0.15, 0.0)),
        ]
        output = _pmx_bones(bones, None)
        by_name = {bone.name: bone for bone in output}

        self.assertIsNone(by_name["allParent"].parent)
        self.assertEqual(by_name["center"].parent, "allParent")
        self.assertEqual(by_name["groove"].parent, "center")
        # Upper/lower body are siblings under groove/center motion, matching classic PMD behavior.
        self.assertEqual(by_name["hips"].parent, "groove")
        self.assertEqual(by_name["spine"].parent, "groove")
        self.assertEqual(by_name["chest"].parent, "spine")

        self.assertEqual(by_name["leftShoulderP"].parent, "chest")
        self.assertEqual(by_name["leftShoulder"].parent, "leftShoulderP")
        self.assertEqual(by_name["leftUpperArm"].parent, "leftShoulder")
        self.assertEqual(by_name["leftArmTwist"].parent, "leftUpperArm")
        self.assertEqual(by_name["leftLowerArm"].parent, "leftArmTwist")
        self.assertEqual(by_name["leftWristTwist"].parent, "leftLowerArm")
        self.assertEqual(by_name["leftHand"].parent, "leftWristTwist")

        self.assertEqual(by_name["leftLegIK"].parent, "allParent")
        self.assertEqual(by_name["leftLegIK"].ik_target, "leftFoot")
        self.assertEqual(by_name["leftLegIK"].ik_links, ("leftLowerLeg", "leftUpperLeg"))
        self.assertEqual(by_name["leftToeIK"].parent, "leftLegIK")
        self.assertEqual(by_name["leftToeIK"].ik_target, "leftToe")
        self.assertEqual(by_name["leftToeIK"].ik_links, ("leftFoot",))
        self.assertEqual(by_name["leftToeIK"].ik_iterations, 3)
        self.assertEqual(by_name["leftToeIK"].ik_weight, 1.0)

        self.assertEqual(MMD_JP["allParent"], "全ての親")
        self.assertEqual(MMD_JP["groove"], "グルーブ")
        self.assertEqual(MMD_JP["leftShoulderP"], "左肩P")
        self.assertEqual(MMD_JP["leftArmTwist"], "左腕捩")
        self.assertEqual(MMD_JP["leftWristTwist"], "左手捩")
        self.assertEqual(MMD_JP["leftToeIK"], "左つま先ＩＫ")


if __name__ == "__main__":
    unittest.main()
