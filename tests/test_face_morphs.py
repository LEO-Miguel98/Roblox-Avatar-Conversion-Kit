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

        # Two shell triangles establish a 2 x 2 x 1 head box without looking like eye/mouth parts.
        triangle([(-1.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 2.0, 0.5)])
        triangle([(-1.0, 0.0, -0.1), (1.0, 0.0, -0.1), (0.0, 2.0, -0.1)])

        # Four disconnected triangles per eye provide >= 12 vertices on the front quarter.
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            for y in (0.76, 0.84, 0.92, 1.00):
                triangle([
                    (cx - 0.035, y - 0.02, -0.49),
                    (cx + 0.035, y - 0.02, -0.49),
                    (cx, y + 0.025, -0.49),
                ])

        # One connected thin eyebrow strip per side, with enough vertices to avoid confusing tiny
        # eye highlights for eyebrows.
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

        # Small opaque shell patches around each eye represent the eyelid/cheek surface. They are
        # not eye geometry, but coordinated morphs should move them with the actual nearby eye field.
        eye_skin = set()
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            eye_skin |= triangle([
                (cx - 0.12, 0.72, -0.46),
                (cx + 0.12, 0.72, -0.46),
                (cx, 1.04, -0.46),
            ], material="FaceMtl__RACK_SKIN")

        # A small skin seam in the mouth area must remain skin, while coordinated mouth morphs are
        # allowed to deform it so the lips do not look detached from the face.
        skin_seam = triangle([
            (-0.025, 0.22, -0.49),
            (0.025, 0.22, -0.49),
            (0.0, 0.34, -0.49),
        ], material="FaceMtl__RACK_SKIN")

        # Four disconnected mouth triangles provide a deformable lip/mouth region.
        mouth_vertices = set()
        for x in (-0.12, -0.04, 0.04, 0.12):
            mouth_vertices |= triangle([
                (x - 0.03, 0.20, -0.49),
                (x + 0.03, 0.20, -0.49),
                (x, 0.28, -0.49),
            ])
        return mesh, skin_seam, mouth_vertices, eye_skin

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
        mesh, skin_seam, mouth_vertices, eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh)
        self.assertIsNotNone(regions)
        self.assertTrue(skin_seam.isdisjoint(regions.mouth))
        self.assertTrue(mouth_vertices.issubset(regions.mouth))
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
        self.assertGreater(len(by_name["Blink"].offsets), 20)
        blink_indices = {index for index, _ in by_name["Blink"].offsets}
        self.assertTrue(eye_skin.issubset(blink_indices))
        self.assertGreater(len(by_name["MouthOpen"].offsets), 10)
        mouth_open_indices = {index for index, _ in by_name["MouthOpen"].offsets}
        self.assertTrue(skin_seam.issubset(mouth_open_indices))
        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            self.assertEqual(by_name[name].panel, 1)
        for name in ("Blink", "EyeWide", "HalfLid", "HappyEyes"):
            self.assertEqual(by_name[name].panel, 2)
        for name in (
            "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
            "MouthClosed", "MouthWide", "Smile",
        ):
            self.assertEqual(by_name[name].panel, 3)

    def test_shell_tracks_actual_eye_and_mouth_motion_at_useful_strength(self):
        mesh, skin_seam, mouth_vertices, eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh)

        blink = dict(by_name["BlinkLeft"].offsets)
        eye_feature_peak = max(abs(blink[index][1]) for index in regions.left_eye if index in blink)
        eye_shell_peak = max(abs(blink[index][1]) for index in eye_skin if index in blink)
        self.assertGreater(eye_feature_peak, 0.0)
        self.assertGreater(eye_shell_peak, eye_feature_peak * 0.30)

        mouth_open = dict(by_name["MouthOpen"].offsets)
        mouth_feature_peak = max(abs(mouth_open[index][1]) for index in mouth_vertices if index in mouth_open)
        mouth_shell_peak = max(abs(mouth_open[index][1]) for index in skin_seam if index in mouth_open)
        self.assertGreater(mouth_feature_peak, 0.0)
        self.assertGreater(mouth_shell_peak, mouth_feature_peak * 0.25)

        # Coupling is intentionally local and clamped; it must never drag the whole head silhouette.
        self.assertLessEqual(eye_shell_peak, regions.size[1] * 0.055 + 1e-8)
        self.assertLessEqual(mouth_shell_peak, regions.size[1] * 0.048 + 1e-8)

    def test_hidden_neutral_mouth_reveals_only_actual_mouth_not_skin_shell(self):
        mesh, skin_seam, _, _eye_skin = self._build_face()
        regions, by_name = self._morphs(mesh, mouth_hidden=True)
        self.assertIsNotNone(regions)
        self.assertGreaterEqual(len(regions.mouth), 12)
        self.assertTrue(skin_seam.isdisjoint(regions.mouth))
        self.assertGreater(regions.hide_depth, 0.0)

        mouth_open = by_name["MouthOpen"]
        moved_indices = {index for index, _ in mouth_open.offsets}
        self.assertTrue(skin_seam.issubset(moved_indices))
        skin_deltas = [delta for index, delta in mouth_open.offsets if index in skin_seam]
        self.assertTrue(skin_deltas)
        self.assertTrue(all(abs(delta[2]) < 1e-6 for delta in skin_deltas))
        self.assertTrue(any(delta[2] > 0.05 for index, delta in mouth_open.offsets if index not in skin_seam))


if __name__ == "__main__":
    unittest.main()
