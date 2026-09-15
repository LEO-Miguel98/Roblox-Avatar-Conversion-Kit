from __future__ import annotations


def install(pmx):
    """Make the opaque facial skin an explicit participant in reconstructed expressions.

    v0.3.17/v0.3.18 transferred feature motion into nearby skin. That improved attachment but could
    still leave an eye socket visibly open while the eye island closed, or leave the lip/cheek skin
    neutral while the mouth surface smiled. v0.3.19 authors the facial skin cage from the same shape
    rules as the eye and mouth morphs themselves: eyelid/socket skin converges on the blink line and
    lip/corner/cheek/chin skin receives the matching mouth expression field.
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

        skin_adjacency = {index: set() for index in front_skin}
        for face in mesh.faces:
            if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
                continue
            ids = [corner[0] for corner in face.corners if corner[0] in front_skin]
            for i, vertex in enumerate(ids):
                for neighbor in ids[i + 1:]:
                    skin_adjacency[vertex].add(neighbor)
                    skin_adjacency[neighbor].add(vertex)

        def _clamp(value, limit):
            return max(-limit, min(limit, value))

        def _magnitude(delta):
            return sum(value * value for value in delta)

        def propagate(direct, decays):
            """Carry a smaller expression through connected recognized facial skin only."""
            if not direct:
                return {}
            output = dict(direct)
            frontier = dict(direct)
            for decay in decays:
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
            return output

        def nearest_influence(point, source_points, radius_x, radius_y, power=0.72):
            rx = max(radius_x, 1e-6)
            ry = max(radius_y, 1e-6)
            nearest = min(
                ((point[0] - other[0]) / rx) ** 2
                + ((point[1] - other[1]) / ry) ** 2
                for other in source_points
            )
            if nearest >= 1.0:
                return 0.0
            return (1.0 - nearest) ** power

        pending = {name: {} for name in by_name}

        def merge_skin(name, values):
            if name not in pending:
                return
            target = pending[name]
            for source_index, delta in values.items():
                current = target.get(source_index)
                if current is None or _magnitude(delta) > _magnitude(current):
                    target[source_index] = delta

        def eye_skin_field(source, kind):
            if len(source) < 12:
                return {}
            points = [mesh.vertices[index] for index in source]
            ys = [point[1] for point in points]
            xs = [point[0] for point in points]
            line = sum(ys) / len(ys)
            xmid = sum(xs) / len(xs)
            xspan = max(max(xs) - min(xs), 1e-6)
            direct = {}
            radius_x = 0.15 * width
            radius_y = 0.125 * height

            for skin_index in front_skin:
                point = mesh.vertices[skin_index]
                influence = nearest_influence(point, points, radius_x, radius_y)
                if influence <= 0.0:
                    continue
                rel_y = point[1] - line
                rel_x = (point[0] - xmid) / xspan
                if kind == "blink":
                    # Socket/eyelid skin itself closes toward the same line as the eye surface.
                    dy = (line - point[1]) * 0.94 * influence
                    dx = 0.0
                    max_y = 0.12 * height
                elif kind == "wide":
                    dx = 0.0
                    dy = rel_y * 0.22 * influence
                    max_y = 0.040 * height
                elif kind == "half":
                    dx = 0.0
                    dy = (line - point[1]) * 0.58 * influence if rel_y > 0 else 0.0
                    max_y = 0.070 * height
                elif kind == "happy":
                    arch = 0.020 * height * (1.0 - min(abs(rel_x) * 2.0, 1.0))
                    dx = 0.0
                    dy = (line + arch - point[1]) * 0.76 * influence
                    max_y = 0.080 * height
                else:
                    continue
                dy = _clamp(dy, max_y)
                if max(abs(dx), abs(dy)) >= 1e-6:
                    direct[skin_index] = (dx, dy, 0.0)
            return propagate(direct, (0.28, 0.12))

        left_eye_driver = (
            regions.left_eye_surface
            if len(regions.left_eye_surface) >= 12 else regions.left_eye
        )
        right_eye_driver = (
            regions.right_eye_surface
            if len(regions.right_eye_surface) >= 12 else regions.right_eye
        )

        merge_skin("BlinkLeft", eye_skin_field(left_eye_driver, "blink"))
        merge_skin("BlinkRight", eye_skin_field(right_eye_driver, "blink"))
        merge_skin("Blink", eye_skin_field(left_eye_driver, "blink"))
        merge_skin("Blink", eye_skin_field(right_eye_driver, "blink"))
        for source in (left_eye_driver, right_eye_driver):
            merge_skin("EyeWide", eye_skin_field(source, "wide"))
            merge_skin("HalfLid", eye_skin_field(source, "half"))
            merge_skin("HappyEyes", eye_skin_field(source, "happy"))

        def feature_motion_field(name, source, radius_x, radius_y, gain, max_y):
            # Brows have no opening that needs to close, so a local copy of their real motion is OK.
            morph = by_name.get(name)
            if morph is None or not source:
                return {}
            by_pmx = {vertex_index: delta for vertex_index, delta in morph.offsets}
            movers = []
            for source_index in source:
                values = [
                    by_pmx[pmx_index]
                    for pmx_index in source_to_pmx.get((group, source_index), ())
                    if pmx_index in by_pmx
                ]
                if not values:
                    continue
                count = float(len(values))
                average = tuple(sum(value[a] for value in values) / count for a in range(3))
                movers.append((mesh.vertices[source_index], (average[0], average[1], -average[2])))
            if not movers:
                return {}
            direct = {}
            source_points = [point for point, _ in movers]
            for skin_index in front_skin:
                point = mesh.vertices[skin_index]
                influence = nearest_influence(point, source_points, radius_x, radius_y, 0.9)
                if influence <= 0.0:
                    continue
                nearest = sorted(
                    movers,
                    key=lambda item: (
                        ((point[0] - item[0][0]) / max(radius_x, 1e-6)) ** 2
                        + ((point[1] - item[0][1]) / max(radius_y, 1e-6)) ** 2
                    ),
                )[:4]
                delta = tuple(sum(item[1][a] for item in nearest) / len(nearest) for a in range(3))
                out = (
                    _clamp(delta[0] * gain * influence, 0.016 * width),
                    _clamp(delta[1] * gain * influence, max_y),
                    0.0,
                )
                if max(abs(value) for value in out) >= 1e-6:
                    direct[skin_index] = out
            return propagate(direct, (0.24,))

        for name in ("BrowRaise", "BrowLower", "BrowSad", "BrowAngry", "BrowSerious"):
            for source in (regions.left_brow, regions.right_brow):
                merge_skin(name, feature_motion_field(
                    name, source, 0.14 * width, 0.10 * height, 0.70, 0.036 * height
                ))

        mouth_all = getattr(regions, "mouth_all", regions.mouth)
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        mouth_driver = mouth_surface if len(mouth_surface) >= 12 else mouth_all

        def mouth_skin_field(kind):
            if len(mouth_driver) < 12:
                return {}
            points = [mesh.vertices[index] for index in mouth_driver]
            xmid = sum(point[0] for point in points) / len(points)
            line = sum(point[1] for point in points) / len(points)
            radius_x = 0.21 * width
            radius_y = 0.17 * height
            direct = {}

            for skin_index in front_skin:
                point = mesh.vertices[skin_index]
                nx = (point[0] - xmid) / max(radius_x, 1e-6)
                ny = (point[1] - line) / max(radius_y, 1e-6)
                r2 = nx * nx + ny * ny
                if r2 >= 1.0:
                    continue
                near = nearest_influence(
                    point, points, 0.13 * width, 0.10 * height, power=0.65
                )
                broad = (1.0 - r2) ** 1.15
                influence = min(1.0, 0.30 * broad + 0.85 * near)
                rel_x = point[0] - xmid
                sign_x = 1.0 if rel_x >= 0 else -1.0
                xnorm = min(abs(rel_x) / max(0.21 * width, 1e-6), 1.0)
                rel_y = point[1] - line

                if kind == "open":
                    dx = 0.0
                    dy = (
                        (-0.075 * height if rel_y <= 0 else 0.018 * height)
                        * (0.55 + 0.45 * min(abs(rel_y) / max(0.11 * height, 1e-6), 1.0))
                        * influence
                    )
                elif kind == "i":
                    dx = 0.025 * width * xnorm * sign_x * influence
                    dy = -0.010 * height * (1.0 - xnorm) * influence
                elif kind == "u":
                    dx = -0.035 * width * xnorm * sign_x * influence
                    dy = (-0.018 * height if rel_y <= 0 else 0.006 * height) * influence
                elif kind == "e":
                    dx = 0.018 * width * xnorm * sign_x * influence
                    dy = (-0.045 * height if rel_y <= 0 else 0.012 * height) * influence
                elif kind == "o":
                    dx = -0.022 * width * xnorm * sign_x * influence
                    dy = (-0.052 * height if rel_y <= 0 else 0.010 * height) * influence
                elif kind == "closed":
                    dx = 0.0
                    dy = (line - point[1]) * 0.74 * influence
                elif kind == "wide":
                    dx = 0.030 * width * xnorm * sign_x * influence
                    dy = -0.006 * height * influence
                elif kind == "smile":
                    dx = 0.017 * width * xnorm * sign_x * influence
                    dy = (
                        0.052 * height
                        * (xnorm ** 1.18)
                        * (0.55 + 0.45 * near)
                        * influence
                    )
                else:
                    continue
                dx = _clamp(dx, 0.040 * width)
                dy = _clamp(dy, 0.075 * height)
                if max(abs(dx), abs(dy)) >= 1e-6:
                    direct[skin_index] = (dx, dy, 0.0)
            return propagate(direct, (0.34, 0.16))

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
            merge_skin(name, mouth_skin_field(kind))

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
