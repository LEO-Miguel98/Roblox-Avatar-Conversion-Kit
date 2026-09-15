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

        # A small skin seam in the mouth area must never be included in mouth morphs.
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
        return mesh, skin_seam, mouth_vertices

    def test_reconstructs_separate_eye_brow_and_mouth_controls(self):
        mesh, skin_seam, mouth_vertices = self._build_face()
        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)

        regions = _analyze_face_regions(mesh, {"RigHead": "head"})
        self.assertIsNotNone(regions)
        self.assertTrue(skin_seam.isdisjoint(regions.mouth))
        self.assertTrue(mouth_vertices.issubset(regions.mouth))
        self.assertGreaterEqual(len(regions.left_brow), 6)
        self.assertGreaterEqual(len(regions.right_brow), 6)

        morphs = _reconstructed_face_morphs(
            mesh,
            {"RigHead": "head"},
            source_to_pmx,
            regions=regions,
        )
        by_name = {m.name_en: m for m in morphs}

        expected = {
            "Blink", "BlinkLeft", "BlinkRight",
            "EyeWide", "HalfLid", "HappyEyes",
            "BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious",
            "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
            "MouthClosed", "MouthWide", "Smile",
        }
        self.assertEqual(set(by_name), expected)
        self.assertGreater(len(by_name["Blink"].offsets), 20)
        self.assertGreater(len(by_name["MouthOpen"].offsets), 10)
        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            self.assertEqual(by_name[name].panel, 1)
        for name in ("Blink", "EyeWide", "HalfLid", "HappyEyes"):
            self.assertEqual(by_name[name].panel, 2)
        for name in (
            "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
            "MouthClosed", "MouthWide", "Smile",
        ):
            self.assertEqual(by_name[name].panel, 3)

    def test_hidden_neutral_mouth_reveals_only_actual_mouth_not_skin_shell(self):
        mesh, skin_seam, _ = self._build_face()
        mapping = {"RigHead": "head"}
        regions = _analyze_face_regions(mesh, mapping)
        self.assertIsNotNone(regions)
        self.assertGreaterEqual(len(regions.mouth), 12)
        self.assertTrue(skin_seam.isdisjoint(regions.mouth))
        self.assertGreater(regions.hide_depth, 0.0)

        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)
        morphs = _reconstructed_face_morphs(
            mesh,
            mapping,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=True,
        )
        mouth_open = next(morph for morph in morphs if morph.name_en == "MouthOpen")
        moved_indices = {index for index, _ in mouth_open.offsets}
        self.assertTrue(skin_seam.isdisjoint(moved_indices))
        self.assertTrue(any(delta[2] > 0.05 for _, delta in mouth_open.offsets))


if __name__ == "__main__":
    unittest.main()
