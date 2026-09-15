from __future__ import annotations


def install(pmx):
    """Make reconstructed face morphs safe for ordinary additive VMD animation.

    PMX vertex morphs are additive. Earlier reconstructed vowels reused the same large mouth-cavity
    reveal offset in every standard vowel morph, so normal VMD crossfades could add those reveals
    together and push teeth/tongue/cavity geometry through the face. Eye morphs also deformed the
    full detected eye region even though only the visible eyelid/lash surface should change shape.

    This finalizer keeps standard VMD morphs surface-driven: visible eye/lip surfaces and the facial
    skin cage deform together, while deeper eyeball and hidden mouth-cavity components stay rigidly
    attached to the head. The hidden cavity therefore remains safely tucked away instead of being
    repeatedly translated by あ/い/う/え/お blends.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def motion_safe_face_morphs(
        mesh,
        group_to_bone,
        source_to_pmx,
        *,
        regions=None,
        mouth_hidden_at_neutral=False,
    ):
        regions = regions or pmx._analyze_face_regions(mesh, group_to_bone)
        morphs = base_reconstructed_face_morphs(
            mesh,
            group_to_bone,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=mouth_hidden_at_neutral,
        )
        if regions is None or not morphs:
            return morphs

        group = regions.group
        center = regions.center
        width, height, _depth = regions.size
        by_name = {morph.name_en: morph for morph in morphs}

        def source_pmx_indices(source):
            return {
                pmx_index
                for source_index in source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }

        def replace_feature_offsets(name, remove_source, source_deltas):
            """Replace only feature-island offsets, preserving the already-authored skin cage."""
            morph = by_name.get(name)
            if morph is None:
                return
            remove_pmx = source_pmx_indices(remove_source)
            if remove_pmx:
                morph.offsets[:] = [
                    (vertex_index, delta)
                    for vertex_index, delta in morph.offsets
                    if vertex_index not in remove_pmx
                ]
            for source_index in sorted(source_deltas):
                delta = source_deltas[source_index]
                if max(abs(value) for value in delta) < 1e-6:
                    continue
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, pmx._mmd_vec3(delta)))

        left_eye_surface = (
            regions.left_eye_surface
            if len(regions.left_eye_surface) >= 12 else regions.left_eye
        )
        right_eye_surface = (
            regions.right_eye_surface
            if len(regions.right_eye_surface) >= 12 else regions.right_eye
        )
        all_eye = frozenset(set(regions.left_eye) | set(regions.right_eye))

        def eye_surface_field(source, kind):
            if len(source) < 12:
                return {}
            points = [mesh.vertices[index] for index in source]
            line = sum(point[1] for point in points) / len(points)
            xmid = sum(point[0] for point in points) / len(points)
            xspan = max(max(point[0] for point in points) - min(point[0] for point in points), 1e-6)
            output = {}
            for index in source:
                point = mesh.vertices[index]
                rel_y = point[1] - line
                rel_x = (point[0] - xmid) / xspan
                if kind == "blink":
                    # Full closure: the visible eyelid/lash surface finishes on the same line as
                    # the hard-bound eye-socket border authored by face_boundary.py.
                    delta = (0.0, line - point[1], 0.0)
                elif kind == "wide":
                    delta = (0.0, rel_y * 0.28, 0.0)
                elif kind == "half":
                    delta = (0.0, (line - point[1]) * 0.78 if rel_y > 0.0 else 0.0, 0.0)
                elif kind == "happy":
                    arch = 0.022 * height * (1.0 - min(abs(rel_x) * 2.0, 1.0))
                    delta = (0.0, (line + arch - point[1]) * 0.90, 0.0)
                else:
                    continue
                if max(abs(value) for value in delta) >= 1e-6:
                    output[index] = delta
            return output

        replace_feature_offsets(
            "BlinkLeft", regions.left_eye, eye_surface_field(left_eye_surface, "blink")
        )
        replace_feature_offsets(
            "BlinkRight", regions.right_eye, eye_surface_field(right_eye_surface, "blink")
        )
        combined_blink = {}
        combined_blink.update(eye_surface_field(left_eye_surface, "blink"))
        combined_blink.update(eye_surface_field(right_eye_surface, "blink"))
        replace_feature_offsets("Blink", all_eye, combined_blink)

        for name, kind in (
            ("EyeWide", "wide"),
            ("HalfLid", "half"),
            ("HappyEyes", "happy"),
        ):
            values = {}
            values.update(eye_surface_field(left_eye_surface, kind))
            values.update(eye_surface_field(right_eye_surface, kind))
            replace_feature_offsets(name, all_eye, values)

        mouth_all = getattr(regions, "mouth_all", regions.mouth)
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        mouth_surface = mouth_surface if len(mouth_surface) >= 12 else mouth_all

        def mouth_surface_field(kind):
            if len(mouth_surface) < 12:
                return {}
            points = [mesh.vertices[index] for index in mouth_surface]
            xmid = sum(point[0] for point in points) / len(points)
            line = sum(point[1] for point in points) / len(points)
            output = {}
            for index in mouth_surface:
                point = mesh.vertices[index]
                rel_x = point[0] - xmid
                sign_x = 1.0 if rel_x >= 0.0 else -1.0
                xnorm = min(abs(rel_x) / max(0.21 * width, 1e-6), 1.0)
                rel_y = point[1] - line
                if kind == "open":
                    dx = 0.0
                    dy = (
                        (-0.080 * height if rel_y <= 0.0 else 0.022 * height)
                        * (0.60 + 0.40 * min(abs(rel_y) / max(0.11 * height, 1e-6), 1.0))
                    )
                elif kind == "i":
                    dx = 0.028 * width * xnorm * sign_x
                    dy = -0.010 * height * (1.0 - xnorm)
                elif kind == "u":
                    dx = -0.038 * width * xnorm * sign_x
                    dy = -0.020 * height if rel_y <= 0.0 else 0.007 * height
                elif kind == "e":
                    dx = 0.021 * width * xnorm * sign_x
                    dy = -0.048 * height if rel_y <= 0.0 else 0.014 * height
                elif kind == "o":
                    dx = -0.025 * width * xnorm * sign_x
                    dy = -0.055 * height if rel_y <= 0.0 else 0.012 * height
                elif kind == "closed":
                    dx = 0.0
                    dy = (line - point[1]) * 0.90
                elif kind == "wide":
                    dx = 0.034 * width * xnorm * sign_x
                    dy = -0.006 * height
                elif kind == "smile":
                    dx = 0.021 * width * xnorm * sign_x
                    dy = 0.060 * height * (xnorm ** 1.12)
                else:
                    continue
                delta = (dx, dy, 0.0)
                if max(abs(value) for value in delta) >= 1e-6:
                    output[index] = delta
            return output

        # Standard VMD mouth tracks now move only the visible mouth surface. The internal cavity is
        # deliberately absent from these morphs, preventing additive vowel crossfades from stacking
        # a large Z reveal and exploding teeth/tongue geometry through the face.
        for name, kind in (
            ("MouthOpen", "open"),
            ("MouthI", "i"),
            ("MouthU", "u"),
            ("MouthE", "e"),
            ("MouthO", "o"),
            ("MouthClosed", "closed"),
            ("MouthWide", "wide"),
            ("Smile", "smile"),
        ):
            replace_feature_offsets(name, mouth_all, mouth_surface_field(kind))

        return morphs

    pmx._reconstructed_face_morphs = motion_safe_face_morphs
