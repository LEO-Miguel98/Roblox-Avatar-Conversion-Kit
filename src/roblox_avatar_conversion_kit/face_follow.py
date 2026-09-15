from __future__ import annotations


def install(pmx):
    """Add low-amplitude face-shell deformation around reconstructed facial feature morphs.

    Roblox dynamic-head OBJ exports split eyes/lips/brows from the opaque head shell. The v0.3.13
    reconstruction correctly animates those feature pieces, but a rigid shell can make them look
    like stickers sliding over the face. This wrapper keeps the existing feature morphs and adds
    smooth companion offsets to nearby *front-facing* skin vertices.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def coordinated_face_morphs(
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
        width, height, depth = regions.size
        by_name = {morph.name_en: morph for morph in morphs}

        skin = {
            corner[0]
            for face in mesh.faces
            if face.group == group and (face.material or "").endswith("__RACK_SKIN")
            for corner in face.corners
        }
        # Only deform the visible front half. Back-of-head shell vertices must stay rigid during
        # facial animation or the whole skull can visibly breathe with speech/blinks.
        front_skin = frozenset(
            index
            for index in skin
            if mesh.vertices[index][2] <= center[2] - 0.08 * depth
        )
        if not front_skin:
            return morphs

        def feature_center(source):
            points = [mesh.vertices[index] for index in source]
            if not points:
                return center
            return tuple(
                sum(point[axis] for point in points) / len(points)
                for axis in range(3)
            )

        def skin_support(source, radius_x, radius_y, *, y_bias=0.0):
            if not source:
                return {}
            anchor = feature_center(source)
            ax = anchor[0]
            ay = anchor[1] + y_bias
            rx = max(radius_x, 1e-6)
            ry = max(radius_y, 1e-6)
            support = {}
            for index in front_skin:
                point = mesh.vertices[index]
                nx = (point[0] - ax) / rx
                ny = (point[1] - ay) / ry
                r2 = nx * nx + ny * ny
                if r2 >= 1.0:
                    continue
                # Quadratic falloff avoids a visible border where the companion deformation ends.
                support[index] = (1.0 - r2) ** 2
            return support

        def append_skin(name, support, delta_fn):
            morph = by_name.get(name)
            if morph is None:
                return
            for vertex_index, influence in support.items():
                point = mesh.vertices[vertex_index]
                delta = delta_fn(point, influence)
                if max(abs(value) for value in delta) < 1e-6:
                    continue
                for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                    morph.offsets.append((pmx_index, pmx._mmd_vec3(delta)))

        def add_eye_side(source, blink_name):
            if len(source) < 12:
                return
            ys = [mesh.vertices[index][1] for index in source]
            line = sum(ys) / len(ys)
            support = skin_support(source, 0.25 * width, 0.17 * height)
            append_skin(
                blink_name,
                support,
                lambda point, influence: (
                    0.0,
                    (line - point[1]) * 0.14 * influence,
                    0.0,
                ),
            )

        add_eye_side(regions.left_eye, "BlinkLeft")
        add_eye_side(regions.right_eye, "BlinkRight")

        # Blink is a standalone PMX morph, so give it the same shell offsets as both winks rather
        # than relying on MMD to compose the two side morphs.
        if "Blink" in by_name:
            for source in (regions.left_eye, regions.right_eye):
                if len(source) < 12:
                    continue
                ys = [mesh.vertices[index][1] for index in source]
                line = sum(ys) / len(ys)
                support = skin_support(source, 0.25 * width, 0.17 * height)
                append_skin(
                    "Blink",
                    support,
                    lambda point, influence, _line=line: (
                        0.0,
                        (_line - point[1]) * 0.14 * influence,
                        0.0,
                    ),
                )

        for source in (regions.left_eye, regions.right_eye):
            if len(source) < 12:
                continue
            ys = [mesh.vertices[index][1] for index in source]
            line = sum(ys) / len(ys)
            support = skin_support(source, 0.25 * width, 0.18 * height)
            append_skin(
                "EyeWide",
                support,
                lambda point, influence, _line=line: (
                    0.0,
                    (point[1] - _line) * 0.035 * influence,
                    0.0,
                ),
            )
            append_skin(
                "HalfLid",
                support,
                lambda point, influence, _line=line: (
                    0.0,
                    (_line - point[1]) * 0.075 * influence if point[1] > _line else 0.0,
                    0.0,
                ),
            )
            append_skin(
                "HappyEyes",
                support,
                lambda point, influence, _line=line: (
                    0.0,
                    0.012 * height * influence * (1.0 if point[1] <= _line else 0.35),
                    0.0,
                ),
            )

        for source in (regions.left_brow, regions.right_brow):
            if len(source) < 6:
                continue
            support = skin_support(
                source,
                0.24 * width,
                0.15 * height,
                y_bias=0.015 * height,
            )
            append_skin(
                "BrowRaise", support,
                lambda _point, influence: (0.0, 0.010 * height * influence, 0.0),
            )
            append_skin(
                "BrowLower", support,
                lambda _point, influence: (0.0, -0.008 * height * influence, 0.0),
            )
            append_skin(
                "BrowSad", support,
                lambda point, influence: (
                    0.0,
                    (0.014 if abs(point[0] - center[0]) < 0.22 * width else -0.004)
                    * height * influence,
                    0.0,
                ),
            )
            append_skin(
                "BrowAngry", support,
                lambda point, influence: (
                    0.0,
                    (-0.013 if abs(point[0] - center[0]) < 0.22 * width else 0.004)
                    * height * influence,
                    0.0,
                ),
            )
            append_skin(
                "BrowSerious", support,
                lambda _point, influence: (0.0, -0.006 * height * influence, 0.0),
            )

        mouth = regions.mouth
        if len(mouth) < 12:
            return morphs
        mouth_support = skin_support(
            mouth,
            0.34 * width,
            0.30 * height,
            y_bias=-0.015 * height,
        )
        mouth_anchor = feature_center(mouth)

        def mouth_skin_delta(kind, point, influence):
            rel_x = point[0] - mouth_anchor[0]
            sign_x = 1.0 if rel_x >= 0 else -1.0
            xnorm = min(abs(rel_x) / max(0.34 * width, 1e-6), 1.0)
            below = max(
                0.0,
                min((mouth_anchor[1] - point[1]) / max(0.26 * height, 1e-6), 1.0),
            )
            if kind == "a":
                return (
                    0.004 * width * xnorm * sign_x * influence,
                    -0.026 * height * (0.45 + 0.55 * below) * influence,
                    0.0,
                )
            if kind == "i":
                return (
                    0.010 * width * xnorm * sign_x * influence,
                    -0.003 * height * influence,
                    0.0,
                )
            if kind == "u":
                return (
                    -0.010 * width * xnorm * sign_x * influence,
                    -0.004 * height * influence,
                    0.0,
                )
            if kind == "e":
                return (
                    0.008 * width * xnorm * sign_x * influence,
                    -0.012 * height * influence,
                    0.0,
                )
            if kind == "o":
                return (
                    -0.007 * width * xnorm * sign_x * influence,
                    -0.016 * height * influence,
                    0.0,
                )
            if kind == "n":
                return (
                    0.0,
                    (mouth_anchor[1] - point[1]) * 0.035 * influence,
                    0.0,
                )
            if kind == "wide":
                return (
                    0.012 * width * xnorm * sign_x * influence,
                    -0.002 * height * influence,
                    0.0,
                )
            if kind == "smile":
                return (
                    0.008 * width * xnorm * sign_x * influence,
                    0.018 * height * (0.35 + 0.65 * xnorm) * influence,
                    0.0,
                )
            return (0.0, 0.0, 0.0)

        for name, kind in (
            ("MouthOpen", "a"),
            ("MouthI", "i"),
            ("MouthU", "u"),
            ("MouthE", "e"),
            ("MouthO", "o"),
            ("MouthClosed", "n"),
            ("MouthWide", "wide"),
            ("Smile", "smile"),
        ):
            append_skin(
                name,
                mouth_support,
                lambda point, influence, _kind=kind: mouth_skin_delta(
                    _kind, point, influence
                ),
            )

        return morphs

    pmx._reconstructed_face_morphs = coordinated_face_morphs
