import unittest
from collections import defaultdict

from roblox_avatar_conversion_kit.obj import Face, ObjMesh
from roblox_avatar_conversion_kit.pmx import _analyze_face_regions, _reconstructed_face_morphs


class FaceApertureLockTests(unittest.TestCase):
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

        # Broad head bounds used by the geometry-only face analyzer.
        triangle([(-1.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 2.0, 0.5)])
        triangle([(-1.0, 0.0, -0.1), (1.0, 0.0, -0.1), (0.0, 2.0, -0.1)])

        eye_surface = {"left": set(), "right": set()}
        for side_name, side in (("right", -1.0), ("left", 1.0)):
            cx = 0.35 * side
            for y in (0.76, 0.84, 0.92, 1.00):
                eye_surface[side_name] |= triangle([
                    (cx - 0.035, y - 0.02, -0.49),
                    (cx + 0.035, y - 0.02, -0.49),
                    (cx, y + 0.025, -0.49),
                ])

        # Small brow strips keep the synthetic head representative of a dynamic Roblox face.
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

        eye_skin = {"left": set(), "right": set()}
        for side_name, side in (("right", -1.0), ("left", 1.0)):
            cx = 0.35 * side
            eye_skin[side_name] |= triangle([
                (cx - 0.12, 0.72, -0.46),
                (cx + 0.12, 0.72, -0.46),
                (cx, 1.04, -0.46),
            ], material="FaceMtl__RACK_SKIN")

        mouth_skin = triangle([
            (-0.14, 0.19, -0.49),
            (0.14, 0.19, -0.49),
            (0.0, 0.35, -0.49),
        ], material="FaceMtl__RACK_SKIN")

        mouth_surface = set()
        for x in (-0.12, -0.04, 0.04, 0.12):
            mouth_surface |= triangle([
                (x - 0.03, 0.20, -0.49),
                (x + 0.03, 0.20, -0.49),
                (x, 0.28, -0.49),
            ])

        return mesh, eye_surface, eye_skin, mouth_surface, mouth_skin

    def _morphs(self, mesh):
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
            mouth_hidden_at_neutral=False,
        )
        return regions, {morph.name_en: morph for morph in morphs}

    @staticmethod
    def _nearest(mesh, source_index, candidates, sx, sy):
        point = mesh.vertices[source_index]
        return min(
            candidates,
            key=lambda index: (
                ((point[0] - mesh.vertices[index][0]) / sx) ** 2
                + ((point[1] - mesh.vertices[index][1]) / sy) ** 2
            ),
        )

    def test_blink_surface_finishes_on_paired_skin_socket(self):
        mesh, _eye_surface, eye_skin, _mouth_surface, _mouth_skin = self._build_face()
        regions, by_name = self._morphs(mesh)
        self.assertIsNotNone(regions)

        blink = dict(by_name["BlinkLeft"].offsets)
        sx = 0.16 * regions.size[0]
        sy = 0.13 * regions.size[1]
        for source_index in regions.left_eye_surface:
            boundary_index = self._nearest(mesh, source_index, eye_skin["left"], sx, sy)
            self.assertIn(source_index, blink)
            self.assertIn(boundary_index, blink)
            feature_target_y = mesh.vertices[source_index][1] + blink[source_index][1]
            boundary_target_y = mesh.vertices[boundary_index][1] + blink[boundary_index][1]
            self.assertAlmostEqual(feature_target_y, boundary_target_y, places=7)

    def test_mouth_surface_inherits_exact_lip_skin_delta_under_vmd_blends(self):
        mesh, _eye_surface, _eye_skin, mouth_surface, mouth_skin = self._build_face()
        regions, by_name = self._morphs(mesh)
        self.assertIsNotNone(regions)
        sx = 0.12 * regions.size[0]
        sy = 0.08 * regions.size[1]

        pairs = {
            source_index: self._nearest(mesh, source_index, mouth_skin, sx, sy)
            for source_index in mouth_surface
        }
        for name in ("MouthOpen", "MouthI", "MouthU", "MouthE", "MouthO", "Smile"):
            offsets = dict(by_name[name].offsets)
            for source_index, boundary_index in pairs.items():
                self.assertIn(source_index, offsets)
                self.assertIn(boundary_index, offsets)
                for axis in range(3):
                    self.assertAlmostEqual(
                        offsets[source_index][axis],
                        offsets[boundary_index][axis],
                        places=7,
                    )

        # Additive VMD crossfades must preserve the neutral feature-to-lip relative vector exactly.
        open_offsets = dict(by_name["MouthOpen"].offsets)
        o_offsets = dict(by_name["MouthO"].offsets)
        w_open, w_o = 0.65, 0.35
        for source_index, boundary_index in pairs.items():
            feature = mesh.vertices[source_index]
            boundary = mesh.vertices[boundary_index]
            for axis in (0, 1):
                feature_target = (
                    feature[axis]
                    + w_open * open_offsets[source_index][axis]
                    + w_o * o_offsets[source_index][axis]
                )
                boundary_target = (
                    boundary[axis]
                    + w_open * open_offsets[boundary_index][axis]
                    + w_o * o_offsets[boundary_index][axis]
                )
                self.assertAlmostEqual(
                    feature_target - boundary_target,
                    feature[axis] - boundary[axis],
                    places=7,
                )


if __name__ == "__main__":
    unittest.main()
