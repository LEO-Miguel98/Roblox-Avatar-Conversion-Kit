import unittest
from collections import defaultdict

from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import _analyze_face_regions, _reconstructed_face_morphs


class FacialBoundaryRigTests(unittest.TestCase):
    def _build_mesh(self):
        mesh = ObjMesh()

        def triangle(points, material="FaceMtl"):
            start = len(mesh.vertices)
            mesh.vertices.extend(points)
            mesh.faces.append(Face(
                [(start, None, None), (start + 1, None, None), (start + 2, None, None)],
                "RigHead",
                material,
            ))
            return {start, start + 1, start + 2}

        # Head bounds / rear shell references.
        triangle([(-1.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 2.0, 0.5)])
        triangle([(-1.0, 0.0, -0.1), (1.0, 0.0, -0.1), (0.0, 2.0, -0.1)])

        # Visible eye feature islands.
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            for y in (0.76, 0.84, 0.92, 1.00):
                triangle([
                    (cx - 0.035, y - 0.02, -0.49),
                    (cx + 0.035, y - 0.02, -0.49),
                    (cx, y + 0.025, -0.49),
                ])

        # Thin brows so face analysis does not confuse them with the eye surface.
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            start = len(mesh.vertices)
            pts = [
                (cx - 0.09, 1.08, -0.49), (cx - 0.06, 1.115, -0.49),
                (cx - 0.03, 1.09, -0.49), (cx, 1.12, -0.49),
                (cx + 0.03, 1.09, -0.49), (cx + 0.06, 1.115, -0.49),
                (cx + 0.09, 1.08, -0.49), (cx, 1.075, -0.49),
            ]
            mesh.vertices.extend(pts)
            for a, b, c in ((0, 1, 7), (1, 2, 7), (2, 3, 7), (3, 4, 7), (4, 5, 7), (5, 6, 7)):
                mesh.faces.append(Face(
                    [(start + a, None, None), (start + b, None, None), (start + c, None, None)],
                    "RigHead", "FaceMtl",
                ))

        # The eye-socket skin triangles are all boundary edges by construction.
        eye_skin = {}
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            eye_skin[side] = triangle([
                (cx - 0.13, 0.73, -0.46),
                (cx + 0.13, 0.73, -0.46),
                (cx, 1.03, -0.46),
            ], material="FaceMtl__RACK_SKIN")

        mouth_skin = triangle([
            (-0.16, 0.20, -0.47),
            (0.16, 0.20, -0.47),
            (0.0, 0.34, -0.47),
        ], material="FaceMtl__RACK_SKIN")

        mouth = set()
        for x in (-0.12, -0.04, 0.04, 0.12):
            mouth |= triangle([
                (x - 0.03, 0.20, -0.49),
                (x + 0.03, 0.20, -0.49),
                (x, 0.28, -0.49),
            ])
        return mesh, eye_skin, mouth_skin, mouth

    def _morphs(self):
        mesh, eye_skin, mouth_skin, mouth = self._build_mesh()
        mapping = {"RigHead": "head"}
        regions = _analyze_face_regions(mesh, mapping)
        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)
        morphs = _reconstructed_face_morphs(
            mesh, mapping, source_to_pmx, regions=regions
        )
        return mesh, eye_skin, mouth_skin, mouth, regions, {m.name_en: m for m in morphs}

    def test_blink_pins_socket_boundary_to_eye_closure_line(self):
        mesh, eye_skin, _mouth_skin, _mouth, regions, morphs = self._morphs()
        blink = dict(morphs["BlinkLeft"].offsets)
        driver = regions.left_eye_surface
        line = sum(mesh.vertices[index][1] for index in driver) / len(driver)
        left_skin = eye_skin[1.0]
        moved = [index for index in left_skin if index in blink]
        self.assertEqual(set(moved), left_skin)
        for index in moved:
            final_y = mesh.vertices[index][1] + blink[index][1]
            self.assertAlmostEqual(final_y, line, places=5)

    def test_smile_pins_lip_boundary_corners_outward_and_up(self):
        mesh, _eye_skin, mouth_skin, _mouth, _regions, morphs = self._morphs()
        smile = dict(morphs["Smile"].offsets)
        left = min(mouth_skin, key=lambda index: mesh.vertices[index][0])
        right = max(mouth_skin, key=lambda index: mesh.vertices[index][0])
        self.assertIn(left, smile)
        self.assertIn(right, smile)
        self.assertLess(smile[left][0], 0.0)
        self.assertGreater(smile[right][0], 0.0)
        self.assertGreater(smile[left][1], 0.0)
        self.assertGreater(smile[right][1], 0.0)


if __name__ == "__main__":
    unittest.main()
