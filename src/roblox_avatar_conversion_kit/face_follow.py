from __future__ import annotations


def install(pmx):
    """Couple reconstructed facial features to the nearby opaque head shell.

    Roblox dynamic-head OBJ exports split eyes/lips/brows from the opaque head shell. Moving those
    disconnected feature islands without transferring their *actual* motion into the nearby skin
    makes them look like stickers sliding over a rigid face. This wrapper samples each feature
    morph's real displacement field and transfers a clamped, lower-strength version to nearby
    front-facing skin vertices.
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
        # Keep the skull/back-of-head rigid. Only the visible facial shell participates.
        front_skin = frozenset(
            index
            for index in skin
            if mesh.vertices[index][2] <= center[2] - 0.08 * depth
        )
        if not front_skin:
            return morphs

        def source_motion(name, source):
            """Recover source-space feature deltas from the already-authored PMX morph."""
            morph = by_name.get(name)
            if morph is None or not source:
                return {}
            by_pmx = {vertex_index: delta for vertex_index, delta in morph.offsets}
            motion = {}
            for source_index in source:
                values = [
                    by_pmx[pmx_index]
                    for pmx_index in source_to_pmx.get((group, source_index), ())
                    if pmx_index in by_pmx
                ]
                if not values:
                    continue
                count = float(len(values))
                # _mmd_vec3 is its own inverse: it only flips Z.
                average = tuple(sum(value[axis] for value in values) / count for axis in range(3))
                motion[source_index] = (average[0], average[1], -average[2])
            return motion

        def _clamp(value, limit):
            return max(-limit, min(limit, value))

        def append_motion_coupled_skin(
            name,
            source,
            *,
            radius_x,
            radius_y,
            gain,
            max_x,
            max_y,
            max_z=0.0,
            z_gain=0.0,
        ):
            """Transfer local feature motion to nearby shell vertices.

            The nearest few feature vertices define the local displacement direction. Inverse-
            distance blending avoids hard seams between disconnected eye/lip components while a
            distance falloff and explicit component clamps keep the head silhouette stable.
            """
            morph = by_name.get(name)
            motion = source_motion(name, source)
            if morph is None or not motion:
                return

            rx = max(float(radius_x), 1e-6)
            ry = max(float(radius_y), 1e-6)
            movers = [
                (mesh.vertices[index], delta)
                for index, delta in motion.items()
                if abs(delta[0]) + abs(delta[1]) + abs(delta[2]) > 1e-9
            ]
            if not movers:
                return

            min_x = min(point[0] for point, _delta in movers) - rx
            max_x_bound = max(point[0] for point, _delta in movers) + rx
            min_y = min(point[1] for point, _delta in movers) - ry
            max_y_bound = max(point[1] for point, _delta in movers) + ry

            for skin_index in front_skin:
                point = mesh.vertices[skin_index]
                if not (min_x <= point[0] <= max_x_bound and min_y <= point[1] <= max_y_bound):
                    continue

                nearest = []
                for feature_point, delta in movers:
                    nx = (point[0] - feature_point[0]) / rx
                    ny = (point[1] - feature_point[1]) / ry
                    distance2 = nx * nx + ny * ny
                    if distance2 >= 1.0:
                        continue
                    nearest.append((distance2, delta))
                if not nearest:
                    continue
                nearest.sort(key=lambda item: item[0])
                nearest = nearest[:6]

                total = 0.0
                blended = [0.0, 0.0, 0.0]
                for distance2, delta in nearest:
                    # Strongly favor the closest feature samples so upper/lower lids and opposite
                    # mouth edges do not cancel each other across the facial opening.
                    weight = ((1.0 - distance2) ** 2) / (0.025 + distance2)
                    total += weight
                    for axis in range(3):
                        blended[axis] += delta[axis] * weight
                if total <= 1e-12:
                    continue
                blended = [value / total for value in blended]

                nearest_distance2 = nearest[0][0]
                falloff = (1.0 - nearest_distance2) ** 1.5
                delta = (
                    _clamp(blended[0] * gain * falloff, max_x),
                    _clamp(blended[1] * gain * falloff, max_y),
                    _clamp(blended[2] * z_gain * falloff, max_z) if max_z > 0.0 else 0.0,
                )
                if max(abs(value) for value in delta) < 1e-6:
                    continue
                for pmx_index in source_to_pmx.get((group, skin_index), ()):
                    morph.offsets.append((pmx_index, pmx._mmd_vec3(delta)))

        # Eyes need the strongest coupling because an 88%-closing eye island against a nearly rigid
        # socket is the most obvious source of the floating/sticker look.
        for name, source in (
            ("BlinkLeft", regions.left_eye),
            ("BlinkRight", regions.right_eye),
        ):
            append_motion_coupled_skin(
                name,
                source,
                radius_x=0.14 * width,
                radius_y=0.11 * height,
                gain=0.72,
                max_x=0.018 * width,
                max_y=0.055 * height,
            )

        if "Blink" in by_name:
            for source in (regions.left_eye, regions.right_eye):
                append_motion_coupled_skin(
                    "Blink",
                    source,
                    radius_x=0.14 * width,
                    radius_y=0.11 * height,
                    gain=0.72,
                    max_x=0.018 * width,
                    max_y=0.055 * height,
                )

        for name, gain in (("EyeWide", 0.60), ("HalfLid", 0.68), ("HappyEyes", 0.68)):
            for source in (regions.left_eye, regions.right_eye):
                append_motion_coupled_skin(
                    name,
                    source,
                    radius_x=0.14 * width,
                    radius_y=0.115 * height,
                    gain=gain,
                    max_x=0.018 * width,
                    max_y=0.050 * height,
                )

        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            for source in (regions.left_brow, regions.right_brow):
                append_motion_coupled_skin(
                    name,
                    source,
                    radius_x=0.13 * width,
                    radius_y=0.095 * height,
                    gain=0.55,
                    max_x=0.015 * width,
                    max_y=0.030 * height,
                )

        # The neutral-mouth reveal can contain a large Z displacement because the mouth cavity is
        # hidden inside the head. Never transfer that reveal into the skin shell; only X/Y lip/jaw
        # motion is coupled. This makes speech deform the face without making the cheek shell pop.
        mouth = regions.mouth
        if len(mouth) >= 12:
            for name in (
                "MouthOpen",
                "MouthI",
                "MouthU",
                "MouthE",
                "MouthO",
                "MouthClosed",
                "MouthWide",
                "Smile",
            ):
                append_motion_coupled_skin(
                    name,
                    mouth,
                    radius_x=0.18 * width,
                    radius_y=0.145 * height,
                    gain=0.66,
                    max_x=0.030 * width,
                    max_y=0.048 * height,
                    z_gain=0.0,
                )

        return morphs

    pmx._reconstructed_face_morphs = coordinated_face_morphs
