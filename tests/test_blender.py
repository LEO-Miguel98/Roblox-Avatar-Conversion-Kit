import ast
import tempfile
import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.blender import write_blender_script
from roblox_avatar_conversion_kit.features import DynamicAccessory, EyeRig, FeaturePlan
from roblox_avatar_conversion_kit.rig import Bone


class BlenderScriptTests(unittest.TestCase):
    def test_generated_script_contains_vrm_expressions_lookat_and_springbones(self):
        bones = [
            Bone("hips", None, (0, 0, 0)),
            Bone("spine", "hips", (0, 1, 0)),
            Bone("chest", "spine", (0, 2, 0)),
            Bone("head", "chest", (0, 3, 0)),
        ]
        features = FeaturePlan(
            eyes=EyeRig((0, 3.1, -0.4), (-0.1, 3.1, -0.4), (0.1, 3.1, -0.4), (0, 3, 0)),
            dynamics=(
                DynamicAccessory(
                    "Hair", "Handle1", "head", "rackDynamic_Handle1_Hair", "rackDynamic_Handle1_Hair_end",
                    (0, 3, 0), (0, 3.3, 0), (0, 3.6, 0), (0.5, 0.8, 0.3),
                    0.5, 0.55, 0.15, 0.4,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "build_in_blender.py"
            write_blender_script(
                output,
                obj_path=Path(td) / "avatar.obj",
                bones=bones,
                group_to_bone={"Rig1": "spine", "Handle1": "head"},
                smooth_weights=True,
                glb_path=Path(td) / "avatar.glb",
                vrm_path=Path(td) / "avatar.vrm",
                features=features,
                model_name="Avatar",
            )
            source = output.read_text(encoding="utf-8")
            ast.parse(source)
            self.assertIn("morph_target_binds.add", source)
            self.assertIn("add_spring_bone1_spring", source)
            self.assertIn('look_at.type = "bone"', source)
            self.assertIn("export_scene.vrm", source)
            self.assertIn("zero-delta editable scaffolds", source)


if __name__ == "__main__":
    unittest.main()
