import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from roblox_avatar_conversion_kit.face_runtime import FaceRegions
from roblox_avatar_conversion_kit.face_visible_layers import (
    _promote_dominant_lip_component,
    install,
)
from roblox_avatar_conversion_kit.obj import Face, ObjMesh


class FaceVisibleLayerTests(unittest.TestCase):
    @staticmethod
    def _connected_component(mesh, count, *, group="RigHead", material="FaceMtl"):
        start = len(mesh.vertices)
        mesh.vertices.extend((float(index), 0.0, 0.0) for index in range(count))
        for offset in range(1, count - 1):
            mesh.faces.append(Face(
                [
                    (start, None, None),
                    (start + offset, None, None),
                    (start + offset + 1, None, None),
                ],
                group,
                material,
            ))
        return set(range(start, start + count))

    def test_dominant_colored_lip_layer_is_not_left_in_hidden_cavity(self):
        mesh = ObjMesh()
        dominant_lips = self._connected_component(mesh, 30)
        thin_line = self._connected_component(mesh, 10)
        regions = FaceRegions(
            group="RigHead",
            center=(0.0, 0.0, 0.0),
            size=(1.0, 1.0, 1.0),
            left_eye=frozenset(),
            right_eye=frozenset(),
            left_eye_surface=frozenset(),
            right_eye_surface=frozenset(),
            left_brow=frozenset(),
            right_brow=frozenset(),
            mouth=frozenset(dominant_lips),
            mouth_all=frozenset(dominant_lips | thin_line),
            mouth_surface=frozenset(thin_line),
            mouth_components=2,
            hide_depth=0.36,
        )

        promoted = _promote_dominant_lip_component(mesh, regions)
        self.assertTrue(dominant_lips.issubset(promoted.mouth_surface))
        self.assertTrue(dominant_lips.isdisjoint(promoted.mouth))
        self.assertTrue(thin_line.issubset(promoted.mouth_surface))

    def test_similarly_sized_mouth_parts_keep_conservative_classification(self):
        mesh = ObjMesh()
        first = self._connected_component(mesh, 24)
        second = self._connected_component(mesh, 20)
        regions = FaceRegions(
            group="RigHead",
            center=(0.0, 0.0, 0.0),
            size=(1.0, 1.0, 1.0),
            left_eye=frozenset(),
            right_eye=frozenset(),
            left_eye_surface=frozenset(),
            right_eye_surface=frozenset(),
            left_brow=frozenset(),
            right_brow=frozenset(),
            mouth=frozenset(first),
            mouth_all=frozenset(first | second),
            mouth_surface=frozenset(second),
            mouth_components=2,
            hide_depth=0.36,
        )
        unchanged = _promote_dominant_lip_component(mesh, regions)
        self.assertEqual(unchanged.mouth, regions.mouth)
        self.assertEqual(unchanged.mouth_surface, regions.mouth_surface)

    def test_deep_eye_component_follows_socket_as_one_rigid_island(self):
        mesh = ObjMesh()
        # Opaque front skin triangle. Source OBJ front is -Z.
        mesh.vertices.extend([
            (-0.20, 0.00, -0.30),
            (0.20, 0.00, -0.30),
            (0.00, 0.30, -0.30),
        ])
        mesh.faces.append(Face(
            [(0, None, None), (1, None, None), (2, None, None)],
            "RigHead",
            "FaceMtl__RACK_SKIN",
        ))

        deep_eye = self._connected_component(mesh, 6, group="RigHead", material="FaceMtl")
        for index in deep_eye:
            x, _, _ = mesh.vertices[index]
            mesh.vertices[index] = (x * 0.01, 0.10, -0.20)

        regions = FaceRegions(
            group="RigHead",
            center=(0.0, 0.10, 0.0),
            size=(1.0, 1.0, 1.0),
            left_eye=frozenset(deep_eye),
            right_eye=frozenset(),
            left_eye_surface=frozenset(),
            right_eye_surface=frozenset(),
            left_brow=frozenset(),
            right_brow=frozenset(),
            mouth=frozenset(),
            mouth_all=frozenset(),
            mouth_surface=frozenset(),
            mouth_components=0,
            hide_depth=0.36,
        )

        @dataclass
        class Morph:
            name_en: str
            offsets: list

        def base_analyze(_mesh, _mapping):
            return regions

        def base_morphs(_mesh, _mapping, _source_to_pmx, **_kwargs):
            # All three skin vertices move down by the same amount.
            return [Morph("BlinkLeft", [(0, (0.0, -0.12, 0.0)), (1, (0.0, -0.12, 0.0)), (2, (0.0, -0.12, 0.0))])]

        fake_pmx = SimpleNamespace(
            _analyze_face_regions=base_analyze,
            _reconstructed_face_morphs=base_morphs,
        )
        install(fake_pmx)

        source_to_pmx = {
            ("RigHead", index): [index]
            for index in range(len(mesh.vertices))
        }
        morphs = fake_pmx._reconstructed_face_morphs(
            mesh,
            {"RigHead": "head"},
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=False,
        )
        blink = next(morph for morph in morphs if morph.name_en == "BlinkLeft")
        offsets = dict(blink.offsets)
        deltas = [offsets[index] for index in sorted(deep_eye)]
        self.assertTrue(all(delta == deltas[0] for delta in deltas))
        self.assertAlmostEqual(deltas[0][1], -0.12, places=7)


if __name__ == "__main__":
    unittest.main()
