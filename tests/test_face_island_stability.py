import unittest
from collections import defaultdict

from roblox_avatar_conversion_kit.face_island_stability import _is_fragmented_surface
from roblox_avatar_conversion_kit.face_runtime import _coherent_surface_components
from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import _analyze_face_regions, _reconstructed_face_morphs


class FaceIslandStabilityTests(unittest.TestCase):
    def test_coherent_mouth_surface_rejects_tiny_fragments(self):
        components = []
        cursor = 0
        for size in (66, 52, 10, 8, 4, 4, 3):
            component = set(range(cursor, cursor + size))
            cursor += size
            components.append(component)
        kept = _coherent_surface_components(components)
        self.assertEqual([len(component) for component in kept], [66, 52])

        simple = [
            {0, 1, 2},
            {3, 4, 5},
            {6, 7, 8},
            {9, 10, 11},
        ]
        self.assertEqual(len(_coherent_surface_components(simple)), 4)

    def test_fragmented_eye_overlay_surface_binds_while_socket_skin_blinks(self):
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

        eye_skin = set()
        for side in (-1.0, 1.0):
            cx = 0.35 * side
            eye_skin |= triangle([
                (cx - 0.14, 0.72, -0.46),
                (cx + 0.14, 0.72, -0.46),
                (cx, 1.04, -0.46),
            ], material="FaceMtl__RACK_SKIN")

            for island in range(15):
                y = 0.78 + 0.012 * (island % 5)
                x = cx + 0.018 * ((island // 5) - 1)
                triangle([
                    (x - 0.012, y - 0.008, -0.49),
                    (x + 0.012, y - 0.008, -0.49),
                    (x, y + 0.010, -0.49),
                ])

        source_to_pmx = defaultdict(list)
        for index in range(len(mesh.vertices)):
            source_to_pmx[("RigHead", index)].append(index)

        mapping = {"RigHead": "head"}
        regions = _analyze_face_regions(mesh, mapping)
        self.assertIsNotNone(regions)
        self.assertTrue(_is_fragmented_surface(mesh, "RigHead", regions.left_eye_surface))
        self.assertTrue(_is_fragmented_surface(mesh, "RigHead", regions.right_eye_surface))

        morphs = _reconstructed_face_morphs(
            mesh,
            mapping,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=False,
        )
        by_name = {morph.name_en: morph for morph in morphs}
        self.assertIn("Blink", by_name)
        blink_indices = {index for index, _ in by_name["Blink"].offsets}

        # v0.3.23 intentionally removed all fragmented eye artwork from the morph. v0.3.24 keeps
        # deeper eye pieces rigid but re-adds only the visible/front overlay surface, bound to the
        # local opaque skin triangle so it cannot drift away from the socket during VMD playback.
        self.assertTrue(set(regions.left_eye_surface).issubset(blink_indices))
        self.assertTrue(set(regions.right_eye_surface).issubset(blink_indices))
        left_deep = set(regions.left_eye) - set(regions.left_eye_surface)
        right_deep = set(regions.right_eye) - set(regions.right_eye_surface)
        self.assertTrue(left_deep.isdisjoint(blink_indices))
        self.assertTrue(right_deep.isdisjoint(blink_indices))
        self.assertTrue(eye_skin.intersection(blink_indices))


if __name__ == "__main__":
    unittest.main()
