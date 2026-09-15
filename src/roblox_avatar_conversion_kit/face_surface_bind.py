from __future__ import annotations

from math import inf

from .face_island_stability import _is_fragmented_surface


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _closest_point_barycentric(point, a, b, c):
    """Return squared distance and barycentric weights for the closest point on triangle ABC."""

    ab = _sub(b, a)
    ac = _sub(c, a)
    ap = _sub(point, a)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        closest = a
        weights = (1.0, 0.0, 0.0)
    else:
        bp = _sub(point, b)
        d3 = _dot(ab, bp)
        d4 = _dot(ac, bp)
        if d3 >= 0.0 and d4 <= d3:
            closest = b
            weights = (0.0, 1.0, 0.0)
        else:
            vc = d1 * d4 - d3 * d2
            if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
                v = d1 / max(d1 - d3, 1e-12)
                closest = (
                    a[0] + v * ab[0],
                    a[1] + v * ab[1],
                    a[2] + v * ab[2],
                )
                weights = (1.0 - v, v, 0.0)
            else:
                cp = _sub(point, c)
                d5 = _dot(ab, cp)
                d6 = _dot(ac, cp)
                if d6 >= 0.0 and d5 <= d6:
                    closest = c
                    weights = (0.0, 0.0, 1.0)
                else:
                    vb = d5 * d2 - d1 * d6
                    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
                        w = d2 / max(d2 - d6, 1e-12)
                        closest = (
                            a[0] + w * ac[0],
                            a[1] + w * ac[1],
                            a[2] + w * ac[2],
                        )
                        weights = (1.0 - w, 0.0, w)
                    else:
                        va = d3 * d6 - d5 * d4
                        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
                            denom = max((d4 - d3) + (d5 - d6), 1e-12)
                            w = (d4 - d3) / denom
                            bc = _sub(c, b)
                            closest = (
                                b[0] + w * bc[0],
                                b[1] + w * bc[1],
                                b[2] + w * bc[2],
                            )
                            weights = (0.0, 1.0 - w, w)
                        else:
                            denom = va + vb + vc
                            if abs(denom) < 1e-12:
                                closest = a
                                weights = (1.0, 0.0, 0.0)
                            else:
                                inv = 1.0 / denom
                                v = vb * inv
                                w = vc * inv
                                u = 1.0 - v - w
                                closest = (
                                    u * a[0] + v * b[0] + w * c[0],
                                    u * a[1] + v * b[1] + w * c[1],
                                    u * a[2] + v * b[2] + w * c[2],
                                )
                                weights = (u, v, w)

    delta = _sub(point, closest)
    return _dot(delta, delta), weights


def _skin_triangles(mesh, group, center, size):
    """Triangulate the restored opaque front-face skin for surface binding."""

    _width, _height, depth = size
    front_limit = center[2] - 0.035 * depth
    triangles = []
    for face in mesh.faces:
        if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
            continue
        ids = [corner[0] for corner in face.corners]
        if len(ids) < 3:
            continue
        for offset in range(1, len(ids) - 1):
            tri = (ids[0], ids[offset], ids[offset + 1])
            points = [mesh.vertices[index] for index in tri]
            centroid_z = sum(point[2] for point in points) / 3.0
            # Source OBJ front is -Z. Keep the front shell and reject the rear/side head.
            if centroid_z <= front_limit:
                triangles.append(tri)
    return triangles


def _surface_bindings(mesh, group, feature_vertices, center, size):
    """Pair feature vertices to the closest point on the real opaque skin surface."""

    triangles = _skin_triangles(mesh, group, center, size)
    if not triangles:
        return {}

    width, height, depth = size
    max_distance2 = (0.18 * max(width, height, depth)) ** 2
    output = {}
    for source_index in feature_vertices:
        point = mesh.vertices[source_index]
        best_distance2 = inf
        best = None
        for tri in triangles:
            a, b, c = (mesh.vertices[index] for index in tri)
            distance2, weights = _closest_point_barycentric(point, a, b, c)
            if distance2 < best_distance2:
                best_distance2 = distance2
                best = (tri, weights)
        if best is not None and best_distance2 <= max_distance2:
            output[source_index] = best
    return output


def install(pmx):
    """Bind detailed dynamic-head overlay art to the actual deforming face surface.

    The Roblox animated-head OBJ stores facial artwork as disconnected overlay geometry. Even when
    eye/lip morphs are mathematically similar to the reconstructed skin cage, independently authored
    offsets let the overlay drift away from the flesh-colored socket/lip surface during VMD playback.

    This finalizer treats the restored opaque skin as the deformation authority for detailed dynamic
    heads. Each visible/front overlay vertex is projected to the closest front skin triangle once,
    then standard facial morphs use that triangle's barycentric skin deformation. Simple/coherent
    faces keep the existing aperture behavior; highly fragmented eye art and detailed lip overlays
    get the surface binding that Diane requires.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def surface_bound_face_morphs(
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
        by_name = {morph.name_en: morph for morph in morphs}

        fragmented_left = _is_fragmented_surface(mesh, group, regions.left_eye_surface)
        fragmented_right = _is_fragmented_surface(mesh, group, regions.right_eye_surface)
        left_eye_surface = (
            regions.left_eye_surface
            if fragmented_left and len(regions.left_eye_surface) >= 12 else frozenset()
        )
        right_eye_surface = (
            regions.right_eye_surface
            if fragmented_right and len(regions.right_eye_surface) >= 12 else frozenset()
        )

        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        # Small/simple heads already satisfy the exact aperture-lock contract. Surface-bind only a
        # genuinely detailed lip overlay, where independent per-island motion is visually unstable.
        if len(mouth_surface) < 24:
            mouth_surface = frozenset()

        left_bindings = _surface_bindings(
            mesh, group, left_eye_surface, regions.center, regions.size
        )
        right_bindings = _surface_bindings(
            mesh, group, right_eye_surface, regions.center, regions.size
        )
        mouth_bindings = _surface_bindings(
            mesh, group, mouth_surface, regions.center, regions.size
        )

        def source_pmx_indices(source):
            return {
                pmx_index
                for source_index in source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }

        def source_delta_map(morph):
            by_pmx = {vertex_index: delta for vertex_index, delta in morph.offsets}
            cache = {}

            def get(source_index):
                if source_index in cache:
                    return cache[source_index]
                values = [
                    by_pmx[pmx_index]
                    for pmx_index in source_to_pmx.get((group, source_index), ())
                    if pmx_index in by_pmx
                ]
                if not values:
                    value = (0.0, 0.0, 0.0)
                else:
                    count = float(len(values))
                    value = tuple(
                        sum(item[axis] for item in values) / count
                        for axis in range(3)
                    )
                cache[source_index] = value
                return value

            return get

        def replace_surface(name, remove_source, bindings):
            morph = by_name.get(name)
            if morph is None or not bindings:
                return

            # Read the skin deformation before adding/replacing any overlay offsets.
            skin_delta = source_delta_map(morph)

            remove_pmx = source_pmx_indices(remove_source)
            if remove_pmx:
                morph.offsets[:] = [
                    (vertex_index, delta)
                    for vertex_index, delta in morph.offsets
                    if vertex_index not in remove_pmx
                ]

            for source_index in sorted(bindings):
                tri, weights = bindings[source_index]
                values = [skin_delta(index) for index in tri]
                delta = tuple(
                    weights[0] * values[0][axis]
                    + weights[1] * values[1][axis]
                    + weights[2] * values[2][axis]
                    for axis in range(3)
                )
                if max(abs(value) for value in delta) < 1e-7:
                    continue
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, delta))

        combined_eye_surface = frozenset(
            set(left_eye_surface) | set(right_eye_surface)
        )
        replace_surface("BlinkLeft", left_eye_surface, left_bindings)
        replace_surface("BlinkRight", right_eye_surface, right_bindings)
        combined_bindings = dict(left_bindings)
        combined_bindings.update(right_bindings)
        for name in ("Blink", "EyeWide", "HalfLid", "HappyEyes"):
            replace_surface(name, combined_eye_surface, combined_bindings)

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
            replace_surface(name, mouth_surface, mouth_bindings)

        return morphs

    pmx._reconstructed_face_morphs = surface_bound_face_morphs
