import tempfile
import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.features import DynamicAccessory, EyeRig, FeaturePlan
from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import write_pmx
from roblox_avatar_conversion_kit.rig import Bone


class PmxTests(unittest.TestCase):
    def test_writes_pmx_with_gaze_ik_and_accessory_physics(self):
        mesh = ObjMesh(
            vertices=[
                (0, 0, 0), (1, 0, 0), (0, 1, 0),
                (0, 1, 0), (0.5, 1.5, 0), (-0.5, 1.5, 0),
            ],
            faces=[
                Face([(0, None, None), (1, None, None), (2, None, None)], "Rig1", None),
                Face([(3, None, None), (4, None, None), (5, None, None)], "Handle1", None),
            ],
        )
        bones = [
            Bone("hips", None, (0, 0, 0)),
            Bone("spine", "hips", (0, 1, 0)),
            Bone("head", "spine", (0, 2, 0)),
            Bone("leftUpperLeg", "hips", (-0.2, -0.5, 0)),
            Bone("leftLowerLeg", "leftUpperLeg", (-0.2, -1.2, 0)),
            Bone("leftFoot", "leftLowerLeg", (-0.2, -1.8, 0)),
            Bone("rightUpperLeg", "hips", (0.2, -0.5, 0)),
            Bone("rightLowerLeg", "rightUpperLeg", (0.2, -1.2, 0)),
            Bone("rightFoot", "rightLowerLeg", (0.2, -1.8, 0)),
        ]
        dynamic = DynamicAccessory(
            name="Hair",
            group="Handle1",
            parent_bone="head",
            bone_name="rackDynamic_Handle1_Hair",
            terminal_name="rackDynamic_Handle1_Hair_end",
            root_position=(0, 2.0, 0),
            center_position=(0, 2.3, 0),
            tail_position=(0, 2.6, 0),
            size=(0.6, 0.8, 0.3),
            stiffness=0.5,
            drag_force=0.55,
            gravity_power=0.15,
            angular_limit=0.4,
        )
        features = FeaturePlan(
            eyes=EyeRig(
                master_position=(0, 2.1, -0.4),
                left_position=(-0.1, 2.1, -0.4),
                right_position=(0.1, 2.1, -0.4),
                head_position=(0, 2.0, 0),
            ),
            dynamics=(dynamic,),
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.pmx"
            stats = write_pmx(
                out,
                model_name="A",
                mesh=mesh,
                materials={},
                bones=bones,
                group_to_bone={"Rig1": "spine", "Handle1": "head"},
                features=features,
            )
            data = out.read_bytes()
            self.assertEqual(data[:4], b"PMX ")
            self.assertEqual(data[9], 0)  # PMX global encoding flag: 0 = UTF-16LE
            self.assertEqual(stats["triangles"], 2)
            self.assertEqual(stats["ik_bones"], 2)
            self.assertEqual(stats["gaze_morphs"], 4)
            self.assertEqual(stats["dynamic_accessory_bones"], 1)
            self.assertGreaterEqual(stats["rigid_bodies"], 2)
            self.assertEqual(stats["physics_joints"], 1)
            self.assertNotIn(b"LookLeft", data)
            self.assertIn("LookLeft".encode("utf-16-le"), data)
            self.assertIn("表情".encode("utf-16-le"), data)
            self.assertEqual(stats["text_encoding"], "utf-16-le")
            self.assertIn("rackJoint_Handle1".encode("utf-16-le"), data)


if __name__ == "__main__":
    unittest.main()
