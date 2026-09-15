import unittest

from roblox_avatar_conversion_kit.geometry_only import _GroupInfo, _restore_animated_head_skin
from roblox_avatar_conversion_kit.obj import Face, ObjMesh


class HeadSkinShellTests(unittest.TestCase):
    def test_splits_broad_and_small_same_atlas_skin_from_face_overlay(self):
        vertices = []
        uvs = []

        # Broad disconnected 5x5 shell with real depth.
        for y in range(5):
            for x in range(5):
                xx = -1.0 + x * 0.5
                yy = y * 0.5
                zz = 0.08 * ((x - 2) ** 2 + (y - 2) ** 2)
                vertices.append((xx, yy, zz))
                # Seed shell UV island.
                uvs.append((0.10 + x * 0.03, 0.20 + y * 0.05))

        faces = []
        for y in range(4):
            for x in range(4):
                a = y * 5 + x
                b = a + 1
                c = a + 5
                d = c + 1
                faces.append(Face([(a, a, None), (b, b, None), (d, d, None)], "Rig7", "HeadMtl"))
                faces.append(Face([(a, a, None), (d, d, None), (c, c, None)], "Rig7", "HeadMtl"))

        # Small disconnected nose/philtrum-like skin fragment uses the same UV island and should
        # be recovered even though it is too small to pass the broad 3D shell thresholds.
        small = len(vertices)
        vertices += [
            (-0.06, 0.54, -0.20), (0.00, 0.52, -0.20), (0.06, 0.54, -0.20),
            (0.07, 0.64, -0.16), (0.00, 0.72, -0.15), (-0.07, 0.64, -0.16),
        ]
        ubase = len(uvs)
        uvs += [
            (0.15, 0.27), (0.17, 0.26), (0.19, 0.27),
            (0.19, 0.31), (0.17, 0.34), (0.15, 0.31),
        ]
        for a, b, c in ((0, 1, 5), (1, 4, 5), (1, 2, 4), (2, 3, 4)):
            faces.append(Face(
                [(small + a, ubase + a, None), (small + b, ubase + b, None), (small + c, ubase + c, None)],
                "Rig7",
                "HeadMtl",
            ))

        # Textured facial overlay sits outside the inferred skin UV island and must remain textured.
        overlay = len(vertices)
        vertices += [(-0.35, 1.15, -0.25), (-0.05, 1.15, -0.25), (-0.20, 1.30, -0.25)]
        ou = len(uvs)
        uvs += [(0.72, 0.80), (0.78, 0.80), (0.75, 0.86)]
        faces.append(Face(
            [(overlay, ou, None), (overlay + 1, ou + 1, None), (overlay + 2, ou + 2, None)],
            "Rig7",
            "HeadMtl",
        ))

        mesh = ObjMesh(vertices=vertices, uvs=uvs, faces=faces)
        lo, hi = mesh.bounds(range(25))
        head = _GroupInfo(
            "Rig7",
            lo,
            hi,
            tuple((lo[i] + hi[i]) * 0.5 for i in range(3)),
            tuple(hi[i] - lo[i] for i in range(3)),
        )

        vertex_count, component_count, face_count = _restore_animated_head_skin(mesh, head)
        self.assertEqual(vertex_count, 31)
        self.assertEqual(component_count, 2)
        self.assertEqual(face_count, 36)
        self.assertTrue(all(
            (face.material or "").endswith("__RACK_SKIN")
            for face in mesh.faces[:36]
        ))
        self.assertEqual(mesh.faces[-1].material, "HeadMtl")


if __name__ == "__main__":
    unittest.main()
