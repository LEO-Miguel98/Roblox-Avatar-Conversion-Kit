import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from roblox_avatar_conversion_kit.face_vmd_compat import install


@dataclass(frozen=True)
class VertexMorph:
    name_jp: str
    name_en: str
    panel: int
    offsets: list


class FaceVmdCompatibilityTests(unittest.TestCase):
    def _pmx(self):
        base_morphs = [
            VertexMorph("まばたき", "Blink", 2, [(1, (0.0, 1.0, 0.0))]),
            VertexMorph("ウィンク", "BlinkLeft", 2, [(2, (0.0, 1.0, 0.0))]),
            VertexMorph("ウィンク右", "BlinkRight", 2, [(3, (0.0, 1.0, 0.0))]),
            VertexMorph("びっくり", "EyeWide", 2, [(4, (0.0, 1.0, 0.0))]),
            VertexMorph("じと目", "HalfLid", 2, [(5, (0.0, -1.0, 0.0))]),
            # These two names are deliberately the pre-v0.3.26 incorrect assignments.
            VertexMorph("にこり", "HappyEyes", 2, [(6, (0.0, 1.0, 0.0))]),
            VertexMorph("上", "BrowRaise", 1, [(20, (0.0, 1.0, 0.0))]),
            VertexMorph("困る", "BrowSad", 1, [(21, (0.0, 0.5, 0.0))]),
            VertexMorph("笑い", "Smile", 3, [(30, (0.4, 0.8, 0.0))]),
            VertexMorph("あ", "MouthOpen", 3, [(31, (0.0, -1.0, 0.0))]),
            VertexMorph("う", "MouthU", 3, [(32, (-0.2, -0.4, 0.0))]),
            VertexMorph("ん", "MouthClosed", 3, [(33, (0.0, 0.2, 0.0))]),
            VertexMorph("口横広げ", "MouthWide", 3, [(34, (0.5, 0.0, 0.0))]),
        ]

        def base(*_args, **_kwargs):
            return [VertexMorph(m.name_jp, m.name_en, m.panel, list(m.offsets)) for m in base_morphs]

        return SimpleNamespace(_VertexMorph=VertexMorph, _reconstructed_face_morphs=base)

    def test_standard_names_route_to_correct_face_regions(self):
        pmx = self._pmx()
        install(pmx)
        morphs = pmx._reconstructed_face_morphs(None, None, None)
        by_jp = {m.name_jp: m for m in morphs}

        # Standard MMD: eye smile is 笑い, brow smile is にこり, mouth smile is にやり.
        self.assertEqual({i for i, _ in by_jp["笑い"].offsets}, {6})
        self.assertTrue({20, 21}.intersection({i for i, _ in by_jp["にこり"].offsets}))
        self.assertEqual({i for i, _ in by_jp["にやり"].offsets}, {30})

        self.assertNotIn(30, {i for i, _ in by_jp["笑い"].offsets})
        self.assertNotIn(6, {i for i, _ in by_jp["にこり"].offsets})
        self.assertEqual(len([m.name_jp for m in morphs]), len({m.name_jp for m in morphs}))

    def test_common_tda_animasa_aliases_are_present(self):
        pmx = self._pmx()
        install(pmx)
        morphs = pmx._reconstructed_face_morphs(None, None, None)
        names = {m.name_jp for m in morphs}

        expected = {
            "ウィンク２", "ｳｨﾝｸ２右", "ウィンク右2", "なごみ", "ｷﾘｯ", "はぅ",
            "あ２", "▲", "∧", "□", "口角上げ", "口角下げ", "にっこり", "にやり２",
        }
        self.assertTrue(expected.issubset(names))

    def test_mouth_aliases_only_reuse_mouth_vertices(self):
        pmx = self._pmx()
        install(pmx)
        morphs = pmx._reconstructed_face_morphs(None, None, None)
        by_jp = {m.name_jp: m for m in morphs}
        mouth_vertices = {30, 31, 32, 33, 34}

        for name in ("あ２", "▲", "∧", "□", "口角上げ", "口角下げ"):
            self.assertTrue({i for i, _ in by_jp[name].offsets}.issubset(mouth_vertices))


if __name__ == "__main__":
    unittest.main()
