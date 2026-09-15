import tempfile
import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import write_pmx
from roblox_avatar_conversion_kit.rig import Bone


class PmxTests(unittest.TestCase):
    def test_writes_pmx_signature(self):
        mesh = ObjMesh(
            vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
            faces=[Face([(0, None, None), (1, None, None), (2, None, None)], "Rig1", None)],
        )
        bones = [Bone("hips", None, (0, 0, 0)), Bone("spine", "hips", (0, 1, 0))]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.pmx"
            stats = write_pmx(out, model_name="A", mesh=mesh, materials={}, bones=bones, group_to_bone={"Rig1": "spine"})
            self.assertEqual(out.read_bytes()[:4], b"PMX ")
            self.assertEqual(stats["triangles"], 1)


if __name__ == "__main__":
    unittest.main()
