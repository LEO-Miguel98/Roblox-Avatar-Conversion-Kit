import unittest
from collections import defaultdict

from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import _analyze_face_regions, _reconstructed_face_morphs


class FaceMorphTests(unittest.TestCase):
    def _build_face(self):
        mesh = ObjMesh()

        def triangle(points):
            start = len(mesh.vertices)
            mesh.vertices.extend(points)
            mesh.faces.append(Face(
                [(start, None, None), (start + 1, None, None), (start + 2, None, None)],
                "RigHead",
                "FaceMtl",
            ))

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

        # Four disconnected mouth triangles provide a deformable lip/mouth region.
        for x in (-0.12, -0.04, 0.04, 0.12):
            triangle([
                (x - 0.03, 0.20, -0.49),
                (x + 0.03, 0.20, -0.49),
                (x, 0.28, -0.49),
            ])
        return mesh

    def test_reconstructs_blinks_vowels_and_smile_from_face_geometry(self):
        mesh = self._build_face()
        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)

        morphs = _reconstructed_face_morphs(
            mesh,
            {"RigHead": "head"},
            source_to_pmx,
        )
        by_name = {m.name_en: m for m in morphs}

        self.assertEqual(
            set(by_name),
            {
                "Blink", "BlinkLeft", "BlinkRight",
                "MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO",
                "Smile",
            },
        )
        self.assertGreater(len(by_name["Blink"].offsets), 20)
        self.assertGreater(len(by_name["MouthOpen"].offsets), 10)
        self.assertEqual(by_name["Blink"].panel, 2)
        for name in ("MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO", "Smile"):
            self.assertEqual(by_name[name].panel, 3)

    def test_hidden_neutral_mouth_is_revealed_by_mouth_morphs(self):
        mesh = self._build_face()
        mapping = {"RigHead": "head"}
        regions = _analyze_face_regions(mesh, mapping)
        self.assertIsNotNone(regions)
        self.assertGreaterEqual(len(regions.mouth), 12)
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
        # Source mouth vertices are tucked deeper (+Z in Roblox space), then morph deltas restore
        # them toward the MMD camera (+Z after Roblox->MMD depth inversion).
        self.assertTrue(any(delta[2] > 0.05 for _, delta in mouth_open.offsets))


if __name__ == "__main__":
    unittest.main()
