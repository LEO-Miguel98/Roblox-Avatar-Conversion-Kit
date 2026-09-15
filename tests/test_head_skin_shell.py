import unittest

from roblox_avatar_conversion_kit.geometry_only import _GroupInfo, _restore_animated_head_skin
from roblox_avatar_conversion_kit.obj import Face, ObjMesh


class HeadSkinShellTests(unittest.TestCase):
    def test_splits_broad_head_shell_from_small_face_overlay(self):
        vertices = []
        for y in range(5):
            for x in range(5):
                xx = -1.0 + x * 0.5
                yy = y * 0.5
                zz = 0.08 * ((x - 2) ** 2 + (y - 2) ** 2)
                vertices.append((xx, yy, zz))
        faces = []
        for y in range(4):
            for x in range(4):
                a = y * 5 + x
                b = a + 1
                c = a + 5
                d = c + 1
                faces.append(Face([(a, None, None), (b, None, None), (d, None, None)], "Rig7", "HeadMtl"))
                faces.append(Face([(a, None, None), (d, None, None), (c, None, None)], "Rig7", "HeadMtl"))

        base = len(vertices)
        vertices += [(-0.35, 1.15, -0.25), (-0.05, 1.15, -0.25), (-0.20, 1.30, -0.25)]
        faces.append(Face([(base, None, None), (base + 1, None, None), (base + 2, None, None)], "Rig7", "HeadMtl"))
        mesh = ObjMesh(vertices=vertices, faces=faces)
        lo, hi = mesh.bounds(range(25))
        head = _GroupInfo(
            "Rig7",
            lo,
            hi,
            tuple((lo[i] + hi[i]) * 0.5 for i in range(3)),
            tuple(hi[i] - lo[i] for i in range(3)),
        )

        vertex_count, component_count, face_count = _restore_animated_head_skin(mesh, head)
        self.assertEqual(vertex_count, 25)
        self.assertEqual(component_count, 1)
        self.assertEqual(face_count, 32)
        shell_materials = {face.material for face in mesh.faces[:32]}
        self.assertEqual(shell_materials, {"HeadMtl__RACK_SKIN"})
        self.assertEqual(mesh.faces[-1].material, "HeadMtl")


if __name__ == "__main__":
    unittest.main()
