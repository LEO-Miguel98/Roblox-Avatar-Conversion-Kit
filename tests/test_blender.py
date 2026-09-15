import ast
import tempfile
import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.blender import write_blender_script
from roblox_avatar_conversion_kit.rig import Bone


class BlenderScriptTests(unittest.TestCase):
    def test_generated_script_is_valid_python(self):
        bones = [
            Bone("hips", None, (0, 0, 0)),
            Bone("spine", "hips", (0, 1, 0)),
            Bone("chest", "spine", (0, 2, 0)),
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "build_in_blender.py"
            write_blender_script(
                output,
                obj_path=Path(td) / "avatar.obj",
                bones=bones,
                group_to_bone={"Rig1": "spine"},
                smooth_weights=True,
                glb_path=Path(td) / "avatar.glb",
            )
            source = output.read_text(encoding="utf-8")
            ast.parse(source)
            self.assertIn("point_weights", source)
            self.assertIn("export_scene.gltf", source)


if __name__ == "__main__":
    unittest.main()
