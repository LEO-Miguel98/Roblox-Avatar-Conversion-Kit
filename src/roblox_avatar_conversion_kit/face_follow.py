from __future__ import annotations


def install(pmx):
    """Couple reconstructed facial features to a local front-face skin cage.

    v0.3.18 uses the visible/front feature layer as the motion driver where possible. This prevents
    deeper eyeball/cavity geometry from steering the skin shell and expands the deformation through
    one or two connected skin rings so the eyelid, cheek and jaw transition reads as one face.
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
        front_skin = frozenset(
            index
            for index in skin
            if mesh.vertices[index][2] <= center[2] - 0.08 * depth
        )
        if not front_skin:
            return morphs

        # Topology propagation is restricted to already-recognized front-face skin. It therefore
        # cannot leak through glasses/hair or around the rear skull even when they are spatially
        # close to an eye or mouth feature.
        skin_adjacency = {index: set() for index in front_skin}
        for face in mesh.faces:
            if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
                continue
            ids = [corner[0] for corner in face.corners if corner[0] in front_skin]
            for i, vertex in enumerate(ids):
                for neighbor in ids[i + 1:]:
                    skin_adjacency[vertex].add(neighbor)
                    skin_adjacency[neighbor].add(vertex)

        def source_motion(name, source):
            """Recover source-space feature deltas from the authored PMX morph."""
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
                average = tuple(sum(value[axis] for value in values) / count for axis in range(3))
                motion[source_index] = (average[0], average[1], -average[2])
            return motion

        def _clamp(value, limit):
            return max(-limit, min(limit, value))

        def _magnitude(delta):
            return sum(value * value for value in delta)

        def motion_coupled_skin(
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
            propagate=True,
        ):
            morph = by_name.get(name)
            motion = source_motion(name, source)
            if morph is None or not motion:
                return {}

            rx = max(float(radius_x), 1e-6)
            ry = max(float(radius_y), 1e-6)
            movers = [
                (mesh.vertices[index], delta)
                for index, delta in motion.items()
                if abs(delta[0]) + abs(delta[1]) + abs(delta[2]) > 1e-9
            ]
            if not movers:
                return {}

            min_x = min(point[0] for point, _delta in movers) - rx
            max_x_bound = max(point[0] for point, _delta in movers) + rx
            min_y = min(point[1] for point, _delta in movers) - ry
            max_y_bound = max(point[1] for point, _delta in movers) + ry
            direct = {}

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
                    weight = ((1.0 - distance2) ** 2) / (0.025 + distance2)
                    total += weight
                    for axis in range(3):
                        blended[axis] += delta[axis] * weight
                if total <= 1e-12:
                    continue
                blended = [value / total for value in blended]

                # Slightly broader than v0.3.17, but still local. The strongest inner socket/lip
                # vertices can follow most of the visible feature motion while the outer face fades.
                falloff = (1.0 - nearest[0][0]) ** 1.25
                delta = (
                    _clamp(blended[0] * gain * falloff, max_x),
                    _clamp(blended[1] * gain * falloff, max_y),
                    _clamp(blended[2] * z_gain * falloff, max_z) if max_z > 0.0 else 0.0,
                )
                if max(abs(value) for value in delta) >= 1e-6:
                    direct[skin_index] = delta

            if not propagate or not direct:
                return direct

            # Carry a smaller amount of motion through connected facial skin. This fills the sparse
            # gaps between restored shell fragments and gives cheeks/jaw/eyelids a continuous cage
            # response without dragging the head silhouette.
            output = dict(direct)
            frontier = dict(direct)
            for decay in (0.42, 0.22):
                expanded = {}
                for skin_index in front_skin:
                    if skin_index in output:
                        continue
                    neighbor_deltas = [
                        frontier[neighbor]
                        for neighbor in skin_adjacency.get(skin_index, ())
                        if neighbor in frontier
                    ]
                    if not neighbor_deltas:
                        continue
                    count = float(len(neighbor_deltas))
                    average = tuple(
                        sum(delta[axis] for delta in neighbor_deltas) / count
                        for axis in range(3)
                    )
                    delta = tuple(value * decay for value in average)
                    if max(abs(value) for value in delta) >= 1e-6:
                        expanded[skin_index] = delta
                output.update(expanded)
                frontier = expanded
                if not expanded:
                    break

            # A small topology average removes single-vertex spikes while preserving the direct
            # feature-follow direction at the inner eyelid/lip border.
            for skin_index, delta in direct.items():
                neighbors = [
                    output[neighbor]
                    for neighbor in skin_adjacency.get(skin_index, ())
                    if neighbor in output
                ]
                if not neighbors:
                    continue
                count = float(len(neighbors))
                average = tuple(
                    sum(value[axis] for value in neighbors) / count
                    for axis in range(3)
                )
                output[skin_index] = tuple(
                    0.88 * delta[axis] + 0.12 * average[axis]
                    for axis in range(3)
                )
            return output

        pending = {name: {} for name in by_name}

        def merge_skin(name, values):
            if name not in pending:
                return
            target = pending[name]
            for source_index, delta in values.items():
                current = target.get(source_index)
                # Left/right support can meet at the nose. Choose the stronger local field instead
                # of emitting duplicate PMX offsets, whose behavior varies between consumers.
                if current is None or _magnitude(delta) > _magnitude(current):
                    target[source_index] = delta

        left_eye_driver = (
            regions.left_eye_surface
            if len(regions.left_eye_surface) >= 12 else regions.left_eye
        )
        right_eye_driver = (
            regions.right_eye_surface
            if len(regions.right_eye_surface) >= 12 else regions.right_eye
        )

        for name, source in (
            ("BlinkLeft", left_eye_driver),
            ("BlinkRight", right_eye_driver),
        ):
            merge_skin(name, motion_coupled_skin(
                name,
                source,
                radius_x=0.15 * width,
                radius_y=0.125 * height,
                gain=0.82,
                max_x=0.020 * width,
                max_y=0.060 * height,
            ))

        for source in (left_eye_driver, right_eye_driver):
            merge_skin("Blink", motion_coupled_skin(
                "Blink",
                source,
                radius_x=0.15 * width,
                radius_y=0.125 * height,
                gain=0.82,
                max_x=0.020 * width,
                max_y=0.060 * height,
            ))

        for name, gain in (("EyeWide", 0.68), ("HalfLid", 0.75), ("HappyEyes", 0.75)):
            for source in (left_eye_driver, right_eye_driver):
                merge_skin(name, motion_coupled_skin(
                    name,
                    source,
                    radius_x=0.15 * width,
                    radius_y=0.13 * height,
                    gain=gain,
                    max_x=0.020 * width,
                    max_y=0.055 * height,
                ))

        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            for source in (regions.left_brow, regions.right_brow):
                merge_skin(name, motion_coupled_skin(
                    name,
                    source,
                    radius_x=0.14 * width,
                    radius_y=0.10 * height,
                    gain=0.62,
                    max_x=0.016 * width,
                    max_y=0.032 * height,
                ))

        mouth_all = getattr(regions, "mouth_all", regions.mouth)
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        mouth_driver = mouth_surface if len(mouth_surface) >= 12 else mouth_all
        if len(mouth_driver) >= 12:
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
                merge_skin(name, motion_coupled_skin(
                    name,
                    mouth_driver,
                    radius_x=0.20 * width,
                    radius_y=0.17 * height,
                    gain=0.76,
                    max_x=0.035 * width,
                    max_y=0.055 * height,
                    z_gain=0.0,
                ))

        for name, source_offsets in pending.items():
            morph = by_name.get(name)
            if morph is None or not source_offsets:
                continue
            for source_index in sorted(source_offsets):
                delta = source_offsets[source_index]
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, pmx._mmd_vec3(delta)))

        return morphs

    pmx._reconstructed_face_morphs = coordinated_face_morphs
