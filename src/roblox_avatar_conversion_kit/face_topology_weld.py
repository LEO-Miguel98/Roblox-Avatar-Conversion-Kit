from __future__ import annotations

from collections import Counter, defaultdict, deque

from .face_island_stability import _subset_components


def _skin_topology(mesh, group):
    """Return skin vertices, adjacency and true material-boundary components."""
    edge_counts = Counter()
    adjacency = defaultdict(set)
    skin_vertices = set()
    for face in mesh.faces:
        if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
            continue
        ids = [corner[0] for corner in face.corners]
        skin_vertices.update(ids)
        for index, first in enumerate(ids):
            second = ids[(index + 1) % len(ids)]
            edge = tuple(sorted((first, second)))
            edge_counts[edge] += 1
            adjacency[first].add(second)
            adjacency[second].add(first)

    boundary_adjacency = defaultdict(set)
    for (first, second), count in edge_counts.items():
        if count == 1:
            boundary_adjacency[first].add(second)
            boundary_adjacency[second].add(first)

    components = []
    seen = set()
    for start in boundary_adjacency:
        if start in seen:
            continue
        queue = [start]
        seen.add(start)
        component = set()
        while queue:
            current = queue.pop()
            component.add(current)
            for neighbor in boundary_adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(frozenset(component))
    return frozenset(skin_vertices), adjacency, tuple(components)


def _center(mesh, vertices):
    points = [mesh.vertices[index] for index in vertices]
    count = max(float(len(points)), 1.0)
    return tuple(sum(point[axis] for point in points) / count for axis in range(3))


def _choose_eye_loop(mesh, components, driver, center, size):
    """Choose the actual closed skin aperture nearest one detected eye."""
    if len(driver) < 6:
        return frozenset()
    width, height, _depth = size
    target = _center(mesh, driver)
    best = None
    best_score = float("inf")
    for component in components:
        if not (12 <= len(component) <= 120):
            continue
        points = [mesh.vertices[index] for index in component]
        lo = tuple(min(point[axis] for point in points) for axis in range(3))
        hi = tuple(max(point[axis] for point in points) for axis in range(3))
        span_x = hi[0] - lo[0]
        span_y = hi[1] - lo[1]
        if not (0.10 * width <= span_x <= 0.48 * width):
            continue
        if not (0.04 * height <= span_y <= 0.28 * height):
            continue
        candidate = _center(mesh, component)
        score = (
            ((candidate[0] - target[0]) / max(0.20 * width, 1e-6)) ** 2
            + ((candidate[1] - target[1]) / max(0.15 * height, 1e-6)) ** 2
        )
        if score < best_score:
            best_score = score
            best = component
    return best if best is not None and best_score <= 2.25 else frozenset()


def _eye_pair_targets(mesh, loop):
    """Pair upper/lower socket vertices by X and return one shared closure curve."""
    if len(loop) < 8:
        return {}
    points = {index: mesh.vertices[index] for index in loop}
    ys = [point[1] for point in points.values()]
    mid_y = (min(ys) + max(ys)) * 0.5
    upper = [index for index, point in points.items() if point[1] >= mid_y]
    lower = [index for index, point in points.items() if point[1] < mid_y]
    if not upper or not lower:
        return {index: mid_y for index in loop}

    targets = {}
    for index, point in points.items():
        opposite = lower if index in upper else upper
        partner = min(
            opposite,
            key=lambda other: (
                abs(points[other][0] - point[0]),
                abs(points[other][1] - point[1]),
            ),
        )
        targets[index] = (point[1] + points[partner][1]) * 0.5
    return targets


def _eye_loop_field(mesh, loop, kind, scale=1.0):
    targets = _eye_pair_targets(mesh, loop)
    if not targets:
        return {}
    points = [mesh.vertices[index] for index in loop]
    xmid = sum(point[0] for point in points) / len(points)
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    xspan = max(max_x - min_x, 1e-6)
    output = {}
    for index in loop:
        point = mesh.vertices[index]
        close_y = targets[index]
        rel_y = point[1] - close_y
        rel_x = (point[0] - xmid) / xspan
        if kind == "blink":
            dy = close_y - point[1]
        elif kind == "wide":
            dy = rel_y * 0.26
        elif kind == "half":
            dy = (close_y - point[1]) * 0.72 if rel_y > 0.0 else 0.0
        elif kind == "happy":
            arch = 0.020 * xspan * (1.0 - min(abs(rel_x) * 2.0, 1.0))
            target_y = close_y + arch
            dy = (target_y - point[1]) * 0.92
        else:
            continue
        dy *= scale
        if abs(dy) >= 1e-7:
            output[index] = (0.0, dy, 0.0)
    return output


def _propagate_skin_field(mesh, adjacency, anchors, *, rings=2):
    """Carry hard aperture motion into nearby connected flesh without soft-layer drift."""
    if not anchors:
        return {}
    output = dict(anchors)
    distance = {index: 0 for index in anchors}
    queue = deque(anchors)
    while queue:
        current = queue.popleft()
        d = distance[current]
        if d >= rings:
            continue
        for neighbor in adjacency.get(current, ()):
            if neighbor in distance:
                continue
            distance[neighbor] = d + 1
            queue.append(neighbor)

    anchor_indices = tuple(anchors)
    falloff = {1: 0.68, 2: 0.34, 3: 0.17}
    for index, ring in distance.items():
        if ring == 0:
            continue
        point = mesh.vertices[index]
        nearest = min(
            anchor_indices,
            key=lambda other: sum(
                (mesh.vertices[other][axis] - point[axis]) ** 2 for axis in range(3)
            ),
        )
        factor = falloff.get(ring, 0.0)
        delta = tuple(value * factor for value in anchors[nearest])
        if max(abs(value) for value in delta) >= 1e-7:
            output[index] = delta
    return output


def _nearest_delta(mesh, source, anchors):
    if not anchors:
        return (0.0, 0.0, 0.0)
    point = mesh.vertices[source]
    nearest = min(
        anchors,
        key=lambda other: sum(
            (mesh.vertices[other][axis] - point[axis]) ** 2 for axis in range(3)
        ),
    )
    return anchors[nearest]


def _mouth_anchor_vertices(mesh, boundary_components, driver, center, size):
    """Select the real skin seam immediately surrounding the visible mouth layers."""
    if len(driver) < 8:
        return frozenset()
    width, height, depth = size
    points = [mesh.vertices[index] for index in driver]
    ymid = sum(point[1] for point in points) / len(points)
    min_x, max_x = min(point[0] for point in points), max(point[0] for point in points)
    candidates = set().union(*boundary_components) if boundary_components else set()
    output = {
        index
        for index in candidates
        if min_x - 0.055 * width <= mesh.vertices[index][0] <= max_x + 0.055 * width
        and abs(mesh.vertices[index][1] - ymid) <= 0.105 * height
        and mesh.vertices[index][2] <= center[2] - 0.02 * depth
    }
    return frozenset(output)


def _mouth_base_field(mesh, anchors, driver, kind):
    if not anchors or len(driver) < 8:
        return {}
    points = [mesh.vertices[index] for index in driver]
    xmid = sum(point[0] for point in points) / len(points)
    line = sum(point[1] for point in points) / len(points)
    min_x, max_x = min(point[0] for point in points), max(point[0] for point in points)
    xspan = max(max_x - min_x, 1e-6)
    output = {}
    for index in anchors:
        point = mesh.vertices[index]
        rel_x = point[0] - xmid
        xnorm = min(abs(rel_x) / max(xspan * 0.5, 1e-6), 1.0)
        sign_x = 1.0 if rel_x >= 0.0 else -1.0
        rel_y = point[1] - line
        if kind == "open":
            dx = 0.0
            dy = -0.070 * xspan if rel_y <= 0.0 else 0.024 * xspan
        elif kind == "i":
            dx = 0.055 * xspan * xnorm * sign_x
            dy = -0.014 * xspan * (1.0 - xnorm)
        elif kind == "u":
            dx = -0.060 * xspan * xnorm * sign_x
            dy = -0.020 * xspan if rel_y <= 0.0 else 0.008 * xspan
        elif kind == "e":
            dx = 0.045 * xspan * xnorm * sign_x
            dy = -0.052 * xspan if rel_y <= 0.0 else 0.015 * xspan
        elif kind == "o":
            dx = -0.048 * xspan * xnorm * sign_x
            dy = -0.060 * xspan if rel_y <= 0.0 else 0.014 * xspan
        elif kind == "closed":
            dx = 0.0
            dy = (line - point[1]) * 0.94
        elif kind == "wide":
            dx = 0.068 * xspan * xnorm * sign_x
            dy = -0.008 * xspan
        elif kind == "smile":
            dx = 0.050 * xspan * xnorm * sign_x
            dy = 0.085 * xspan * (xnorm ** 1.10)
        elif kind == "frown":
            dx = 0.035 * xspan * xnorm * sign_x
            dy = -0.070 * xspan * (xnorm ** 1.10)
        else:
            continue
        if max(abs(dx), abs(dy)) >= 1e-7:
            output[index] = (dx, dy, 0.0)
    return output


def _combine_fields(parts):
    merged = defaultdict(lambda: [0.0, 0.0, 0.0])
    for field, weight in parts:
        for index, delta in field.items():
            for axis in range(3):
                merged[index][axis] += delta[axis] * weight
    return {
        index: tuple(values)
        for index, values in merged.items()
        if max(abs(value) for value in values) >= 1e-7
    }


def install(pmx):
    """Morph-space weld visible face layers to real skin aperture topology.

    This is intentionally installed after VMD compatibility aliases: aliases are welded too, so a
    differently named VMD morph cannot reintroduce eye/socket or lip/mouth drift.
    """
    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def topology_welded_face_morphs(
        mesh, group_to_bone, source_to_pmx, *, regions=None, mouth_hidden_at_neutral=False,
    ):
        regions = regions or pmx._analyze_face_regions(mesh, group_to_bone)
        morphs = base_reconstructed_face_morphs(
            mesh, group_to_bone, source_to_pmx, regions=regions,
            mouth_hidden_at_neutral=mouth_hidden_at_neutral,
        )
        if regions is None or not morphs:
            return morphs

        group = regions.group
        _skin_vertices, skin_adjacency, boundary_components = _skin_topology(mesh, group)
        if not boundary_components:
            return morphs

        left_driver = regions.left_eye_surface if len(regions.left_eye_surface) >= 12 else regions.left_eye
        right_driver = regions.right_eye_surface if len(regions.right_eye_surface) >= 12 else regions.right_eye
        left_loop = _choose_eye_loop(mesh, boundary_components, left_driver, regions.center, regions.size)
        right_loop = _choose_eye_loop(mesh, boundary_components, right_driver, regions.center, regions.size)
        mouth_driver = regions.mouth_surface if len(regions.mouth_surface) >= 12 else regions.mouth_all
        mouth_anchors = _mouth_anchor_vertices(mesh, boundary_components, mouth_driver, regions.center, regions.size)
        by_en = {morph.name_en: morph for morph in morphs}

        def source_pmx(source):
            return {
                pmx_index for source_index in source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }

        def replace_source_field(morph, field):
            if not field:
                return
            remove = source_pmx(field)
            if remove:
                morph.offsets[:] = [item for item in morph.offsets if item[0] not in remove]
            for source_index in sorted(field):
                delta = pmx._mmd_vec3(field[source_index])
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, delta))

        def replace_source_with_nearest(morph, source, field):
            if not source or not field:
                return
            remove = source_pmx(source)
            if remove:
                morph.offsets[:] = [item for item in morph.offsets if item[0] not in remove]
            for source_index in sorted(source):
                delta = _nearest_delta(mesh, source_index, field)
                if max(abs(value) for value in delta) < 1e-7:
                    continue
                converted = pmx._mmd_vec3(delta)
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, converted))

        def rigid_follow_components(morph, source, field):
            if not source or not field:
                return
            components = _subset_components(mesh, group, source)
            remove = source_pmx(source)
            if remove:
                morph.offsets[:] = [item for item in morph.offsets if item[0] not in remove]
            for component in components:
                samples = [_nearest_delta(mesh, index, field) for index in component]
                if not samples:
                    continue
                count = float(len(samples))
                delta = tuple(sum(item[axis] for item in samples) / count for axis in range(3))
                if max(abs(value) for value in delta) < 1e-7:
                    continue
                converted = pmx._mmd_vec3(delta)
                for source_index in component:
                    for pmx_index in source_to_pmx.get((group, source_index), ()):
                        morph.offsets.append((pmx_index, converted))

        eye_specs = {
            "Blink": ("both", "blink", 1.0), "BlinkLeft": ("left", "blink", 1.0),
            "BlinkRight": ("right", "blink", 1.0), "BlinkLeft2": ("left", "blink", 1.0),
            "BlinkRight2": ("right", "blink", 1.0), "BlinkRight2Alt": ("right", "blink", 1.0),
            "EyeWide": ("both", "wide", 1.0), "HalfLid": ("both", "half", 1.0),
            "RelaxedEyes": ("both", "half", 0.58), "SharpEyes": ("both", "half", 0.36),
            "HappyEyes": ("both", "happy", 1.0), "HauEyes": ("both", "happy", 0.88),
        }
        for name, (side, kind, scale) in eye_specs.items():
            morph = by_en.get(name)
            if morph is None:
                continue
            side_fields = []
            if side in ("left", "both") and left_loop:
                field = _propagate_skin_field(mesh, skin_adjacency, _eye_loop_field(mesh, left_loop, kind, scale), rings=2)
                side_fields.append((field, regions.left_eye_surface, set(regions.left_eye) - set(regions.left_eye_surface)))
            if side in ("right", "both") and right_loop:
                field = _propagate_skin_field(mesh, skin_adjacency, _eye_loop_field(mesh, right_loop, kind, scale), rings=2)
                side_fields.append((field, regions.right_eye_surface, set(regions.right_eye) - set(regions.right_eye_surface)))
            for field, surface, deep in side_fields:
                replace_source_field(morph, field)
                replace_source_with_nearest(morph, surface, field)
                rigid_follow_components(morph, deep, field)

        base_mouth = {
            kind: _mouth_base_field(mesh, mouth_anchors, mouth_driver, kind)
            for kind in ("open", "i", "u", "e", "o", "closed", "wide", "smile", "frown")
        }
        mouth_specs = {
            "MouthOpen": (("open", 1.0),), "MouthI": (("i", 1.0),),
            "MouthU": (("u", 1.0),), "MouthE": (("e", 1.0),),
            "MouthO": (("o", 1.0),), "MouthClosed": (("closed", 1.0),),
            "MouthWide": (("wide", 1.0),), "Smile": (("smile", 1.0),),
            "MouthCornerUp": (("smile", 0.82),), "MouthCornerDown": (("frown", 1.0),),
            "MouthSmileSoft": (("smile", 0.88),), "MouthSmile2": (("smile", 1.05),),
            "MouthA2": (("open", 0.78), ("wide", 0.22)),
            "MouthTriangle": (("u", 0.58), ("open", 0.34)),
            "MouthSquare": (("open", 1.0), ("wide", 0.34)),
            "MouthCaret": (("closed", 0.72), ("frown", 0.62)),
        }
        for name, parts in mouth_specs.items():
            morph = by_en.get(name)
            if morph is None:
                continue
            field = _combine_fields((base_mouth[kind], weight) for kind, weight in parts)
            if field:
                replace_source_field(morph, field)
                replace_source_with_nearest(morph, mouth_driver, field)

        return morphs

    pmx._reconstructed_face_morphs = topology_welded_face_morphs
