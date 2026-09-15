from __future__ import annotations

from collections import defaultdict


def _scale_offsets(offsets, scale: float):
    return [
        (index, tuple(float(value) * scale for value in delta))
        for index, delta in offsets
    ]


def _combine_offsets(weighted_offsets):
    """Combine multiple vertex-morph fields by PMX vertex index."""

    merged = defaultdict(lambda: [0.0, 0.0, 0.0])
    for offsets, weight in weighted_offsets:
        for index, delta in offsets:
            for axis in range(3):
                merged[index][axis] += float(delta[axis]) * float(weight)
    return [
        (index, tuple(values))
        for index, values in sorted(merged.items())
        if max(abs(value) for value in values) >= 1e-7
    ]


def _frown_offsets(smile_offsets):
    """Turn the reconstructed mouth-smile field into a conservative corner-down field."""

    output = []
    for index, delta in smile_offsets:
        # Keep most horizontal widening, but reverse the vertical smile lift.  Z stays untouched.
        output.append((index, (delta[0] * 0.70, -delta[1], delta[2])))
    return output


def install(pmx):
    """Install standard MMD facial names/aliases after geometric face reconstruction.

    MMD VMD files match morphs by their Japanese names.  Earlier RACK versions accidentally used
    ``笑い`` for a mouth smile and ``にこり`` for happy eyes.  In common MMD models ``笑い`` is an
    eye expression, ``にこり`` is an eyebrow expression, while mouth smiles use names such as
    ``にやり`` / ``口角上げ``.  A motion can therefore look broken even when every PMX vertex
    offset is geometrically correct, because the VMD is driving the wrong part of the face.

    This finalizer fixes those semantic collisions and adds a small compatibility set for common
    Tda/Animasa-style expression tracks.  The aliases reuse the already reconstructed skin-aware
    morph fields, so they do not reintroduce detached eye/mouth motion.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def compatible_face_morphs(
        mesh,
        group_to_bone,
        source_to_pmx,
        *,
        regions=None,
        mouth_hidden_at_neutral=False,
    ):
        morphs = base_reconstructed_face_morphs(
            mesh,
            group_to_bone,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=mouth_hidden_at_neutral,
        )
        if not morphs:
            return morphs

        by_en = {morph.name_en: morph for morph in morphs}
        output = []

        # Correct the two semantic name collisions from <= v0.3.25.
        for morph in morphs:
            if morph.name_en == "HappyEyes":
                output.append(pmx._VertexMorph("笑い", morph.name_en, 2, list(morph.offsets)))
            elif morph.name_en == "Smile":
                output.append(pmx._VertexMorph("にやり", morph.name_en, 3, list(morph.offsets)))
            else:
                output.append(morph)

        by_en = {morph.name_en: morph for morph in output}
        used_jp = {morph.name_jp for morph in output}

        def add_copy(jp, en, source_en, *, panel=None, scale=1.0):
            source = by_en.get(source_en)
            if source is None or jp in used_jp:
                return
            output.append(pmx._VertexMorph(
                jp,
                en,
                source.panel if panel is None else panel,
                _scale_offsets(source.offsets, scale),
            ))
            used_jp.add(jp)

        def add_combined(jp, en, panel, parts):
            if jp in used_jp:
                return
            weighted = []
            for source_en, weight in parts:
                source = by_en.get(source_en)
                if source is not None:
                    weighted.append((source.offsets, weight))
            offsets = _combine_offsets(weighted)
            if offsets:
                output.append(pmx._VertexMorph(jp, en, panel, offsets))
                used_jp.add(jp)

        # Eye aliases frequently used by public VMD motions.
        add_copy("ウィンク２", "BlinkLeft2", "BlinkLeft", panel=2)
        add_copy("ｳｨﾝｸ２右", "BlinkRight2", "BlinkRight", panel=2)
        add_copy("ウィンク右2", "BlinkRight2Alt", "BlinkRight", panel=2)
        add_copy("なごみ", "RelaxedEyes", "HalfLid", panel=2, scale=0.58)
        add_copy("ｷﾘｯ", "SharpEyes", "HalfLid", panel=2, scale=0.36)
        add_copy("はぅ", "HauEyes", "HappyEyes", panel=2, scale=0.88)

        # The standard eyebrow ``にこり`` is distinct from eye ``笑い``.
        add_combined(
            "にこり",
            "BrowSmile",
            1,
            (("BrowRaise", 0.55), ("BrowSad", 0.35)),
        )

        # Common mouth aliases/shapes.  These are conservative approximations built from the
        # skin-bound mouth fields, but crucially they let VMD tracks reach the mouth at all.
        add_copy("口角上げ", "MouthCornerUp", "Smile", panel=3, scale=0.82)
        smile = by_en.get("Smile")
        if smile is not None and "口角下げ" not in used_jp:
            output.append(pmx._VertexMorph(
                "口角下げ",
                "MouthCornerDown",
                3,
                _frown_offsets(smile.offsets),
            ))
            used_jp.add("口角下げ")

        add_copy("にっこり", "MouthSmileSoft", "Smile", panel=3, scale=0.88)
        add_copy("にやり２", "MouthSmile2", "Smile", panel=3, scale=1.05)
        add_combined("あ２", "MouthA2", 3, (("MouthOpen", 0.78), ("MouthWide", 0.22)))
        add_combined("▲", "MouthTriangle", 3, (("MouthU", 0.58), ("MouthOpen", 0.34)))
        add_combined("□", "MouthSquare", 3, (("MouthOpen", 1.0), ("MouthWide", 0.34)))

        closed = by_en.get("MouthClosed")
        if closed is not None and smile is not None and "∧" not in used_jp:
            frown = _frown_offsets(smile.offsets)
            output.append(pmx._VertexMorph(
                "∧",
                "MouthCaret",
                3,
                _combine_offsets(((closed.offsets, 0.72), (frown, 0.62))),
            ))
            used_jp.add("∧")

        return output

    pmx._reconstructed_face_morphs = compatible_face_morphs
