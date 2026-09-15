import tempfile
import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.obj import parse_obj


class ObjTests(unittest.TestCase):
    def test_triangulates_quad(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.obj"
            p.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\ng Rig1\nf 1 2 3 4\n", encoding="utf-8")
            mesh = parse_obj(p)
            self.assertEqual(len(mesh.faces), 2)
            self.assertIn("Rig1", mesh.group_vertex_indices())


if __name__ == "__main__":
    unittest.main()
