import unittest
from collections import defaultdict

from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import _analyze_face_regions, _reconstructed_face_morphs


class FaceMorphTests(unittest.TestCase):
    def _build_face(self):
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

        triangle([(-1.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 2.0, 0.5)])
        triangle([(-1.0, 0.0, -0.1), (1.0, 0.0, -0.1), (0.0, 2.0, -0.1)])

        for side in (-1.0, 1.0):
            cx = 0.35 * side
            for y in (0.76, 0.84, 0.92, 1.00):
                triangle([
                    (cx - 0.035, y - 0.02, -0.49),
                    (cx + 0.035, y - 0.02, -0.49),
                    (cx, y + 0.025, -0.49),
                ])

        for side in (-1.0, 1.0):
            cx = 0.35 * side
            start = len(mesh.vertices)
            points = [
                (cx - 0.09, 1.08, -0.49),
                (cx - 0.06, 1.115, -0.49),
                (cx - 0.03, 1.09, -0.49),
                (cx, 1.12, -0.49),
                (cx + 0.03, 1.09, -0.49),
                (cx + 0.06, 1.115, -0.49),
                (cx + 0.09, 1.08, -0.49),
                (cx, 1.075, -0.49),
            ]
            mesh.vertices.extend(points)
            for a, b, c in ((0, 1, 7), (1, 2, 7), (2, 3, 7), (3, 4, 7), (4, 5, 7), (5, 6, 7)):
                mesh.faces.append(Face(
                    [(start + a, None, None), (start + b, None, None), (start + c, None, None)],
                    "RigHead",
                    "FaceMtl",
                ))

        eye_skin = set()
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            eye_skin |= triangle([
                (cx - 0.12, 0.72, -0.46),
                (cx + 0.12, 0.72, -0.46),
                (cx, 1.04, -0.46),
            ], material="FaceMtl__RACK_SKIN")

        skin_seam = triangle([
            (-0.025, 0.22, -0.49),
            (0.025, 0.22, -0.49),
            (0.0, 0.34, -0.49),
        ], material="FaceMtl__RACK_SKIN")

        mouth_vertices = set()
        for x in (-0.12, -0.04, 0.04, 0.12):
            mouth_vertices |= triangle([
                (x - 0.03, 0.20, -0.49),
                (x + 0.03, 0.20, -0.49),
                (x, 0.28, -0.49),
            ])

        internal_mouth = set()
        for x in (-0.10, -0.03, 0.03, 0.10):
            internal_mouth |= triangle([
                (x - 0.025, 0.205, -0.32),
                (x + 0.025, 0.205, -0.32),
                (x, 0.27, -0.32),
            ])
        return mesh, skin_seam, mouth_vertices, internal_mouth, eye_skin

    def _morphs(self, mesh, *, mouth_hidden=False):
        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)
        mapping = {"RigHead": "head"}
        regions = _analyze_face_regions(mesh, mapping)
        morphs = _reconstructed_face_morphs(
            mesh,
            mapping,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=mouth_hidden,
        )
        return regions, {morph.name_en: morph for morph in morphs}

    def test_reconstructs_separate_eye_brow_and_mouth_controls(self):
        mesh, skin_seam, mouth_vertices, internal_mouth, eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh)
        self.assertIsNotNone(regions)
        self.assertTrue(skin_seam.isdisjoint(regions.mouth_all))
        self.assertTrue(mouth_vertices.issubset(regions.mouth_surface))
        self.assertTrue(internal_mouth.issubset(regions.mouth))
        self.assertTrue((mouth_vertices | internal_mouth).issubset(regions.mouth_all))
        self.assertTrue(regions.mouth_surface.isdisjoint(regions.mouth))
        self.assertGreaterEqual(len(regions.left_eye_surface), 12)
        self.assertGreaterEqual(len(regions.right_eye_surface), 12)
        self.assertGreaterEqual(len(regions.left_brow), 6)
        self.assertGreaterEqual(len(regions.right_brow), 6)

        expected = {
            "Blink", "BlinkLeft", "BlinkRight",
            "EyeWide", "HalfLid", "HappyEyes",
            "BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious",
            "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
            "MouthClosed", "MouthWide", "Smile",
        }
        self.assertEqual(set(by_name), expected)
        self.assertTrue(eye_skin.issubset({index for index, _ in by_name["Blink"].offsets}))
        self.assertTrue(skin_seam.issubset({index for index, _ in by_name["MouthOpen"].offsets}))
        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            self.assertEqual(by_name[name].panel, 1)
        for name in ("Blink", "EyeWide", "HalfLid", "HappyEyes"):
            self.assertEqual(by_name[name].panel, 2)
        for name in (
            "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
            "MouthClosed", "MouthWide", "Smile",
        ):
            self.assertEqual(by_name[name].panel, 3)

    def test_skin_cage_closes_socket_and_shapes_mouth_with_features(self):
        mesh, skin_seam, mouth_vertices, _internal_mouth, eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh)

        blink = dict(by_name["BlinkLeft"].offsets)
        eye_feature_peak = max(
            abs(blink[index][1]) for index in regions.left_eye_surface if index in blink
        )
        left_eye_skin = {index for index in eye_skin if mesh.vertices[index][0] >= 0.0}
        eye_shell_peak = max(abs(blink[index][1]) for index in left_eye_skin if index in blink)
        self.assertGreater(eye_feature_peak, 0.0)
        self.assertGreater(eye_shell_peak, eye_feature_peak * 0.65)

        eye_line = sum(mesh.vertices[index][1] for index in regions.left_eye_surface) / len(
            regions.left_eye_surface
        )
        upper_socket = [
            index for index in left_eye_skin
            if mesh.vertices[index][1] > eye_line and index in blink
        ]
        lower_socket = [
            index for index in left_eye_skin
            if mesh.vertices[index][1] < eye_line and index in blink
        ]
        self.assertTrue(upper_socket)
        self.assertTrue(lower_socket)
        self.assertTrue(all(blink[index][1] < 0.0 for index in upper_socket))
        self.assertTrue(all(blink[index][1] > 0.0 for index in lower_socket))

        mouth_open = dict(by_name["MouthOpen"].offsets)
        mouth_feature_peak = max(
            abs(mouth_open[index][1]) for index in mouth_vertices if index in mouth_open
        )
        mouth_shell_peak = max(abs(mouth_open[index][1]) for index in skin_seam if index in mouth_open)
        self.assertGreater(mouth_feature_peak, 0.0)
        self.assertGreater(mouth_shell_peak, mouth_feature_peak * 0.60)

        lower_skin = [index for index in skin_seam if mesh.vertices[index][1] < 0.30]
        upper_skin = [index for index in skin_seam if mesh.vertices[index][1] >= 0.30]
        self.assertTrue(all(mouth_open[index][1] < 0.0 for index in lower_skin))
        self.assertTrue(all(mouth_open[index][1] > 0.0 for index in upper_skin))

        smile = dict(by_name["Smile"].offsets)
        left_corner = min(skin_seam, key=lambda index: mesh.vertices[index][0])
        right_corner = max(skin_seam, key=lambda index: mesh.vertices[index][0])
        self.assertLess(smile[left_corner][0], 0.0)
        self.assertGreater(smile[right_corner][0], 0.0)
        self.assertGreater(smile[left_corner][1], 0.0)
        self.assertGreater(smile[right_corner][1], 0.0)

        self.assertLessEqual(eye_shell_peak, regions.size[1] * 0.12 + 1e-8)
        self.assertLessEqual(mouth_shell_peak, regions.size[1] * 0.075 + 1e-8)

    def test_hidden_neutral_mouth_keeps_surface_attached_and_cavity_internal(self):
        mesh, skin_seam, mouth_vertices, internal_mouth, _eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh, mouth_hidden=True)
        self.assertIsNotNone(regions)
        self.assertTrue(mouth_vertices.issubset(regions.mouth_surface))
        self.assertTrue(internal_mouth.issubset(regions.mouth))
        self.assertGreater(regions.hide_depth, 0.0)

        mouth_open = dict(by_name["MouthOpen"].offsets)
        self.assertTrue(skin_seam.issubset(mouth_open))
        self.assertTrue(all(abs(mouth_open[index][2]) < 1e-6 for index in skin_seam))
        self.assertTrue(all(abs(mouth_open[index][2]) < 1e-6 for index in mouth_vertices))
        self.assertTrue(any(mouth_open[index][2] > 0.05 for index in internal_mouth))

        for name in ("MouthClosed", "Smile"):
            offsets = dict(by_name[name].offsets)
            self.assertTrue(all(abs(offsets[index][2]) < 1e-6 for index in internal_mouth))


if __name__ == "__main__":
    unittest.main()
