from __future__ import annotations

from collections import Counter


def install(pmx):
    """Make the restored facial skin the authoritative eye/mouth aperture motion.

    v0.3.21 made ordinary VMD tracks surface-only, but the visible eye/lip surfaces and the
    flesh-colored socket/lip borders still computed their displacement independently. Even small
    differences become a visible gap while a motion is playing.

    This finalizer pairs every visible feature vertex with its nearest local opaque-skin boundary.
    Mouth and non-blink eye expressions inherit that exact boundary delta, preserving the neutral
    attachment under arbitrary additive VMD blends. Blink goes one step further: the visible eye
    surface is vertically snapped to the paired skin boundary's *deformed* Y position so no white or
    black slit can remain between the eyelid feature and the actual flesh-colored socket.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def aperture_locked_face_morphs(
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

        edge_counts = Counter()
        for face in mesh.faces:
            if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
                continue
            ids = [corner[0] for corner in face.corners]
            for index, first in enumerate(ids):
                second = ids[(index + 1) % len(ids)]
                edge_counts[tuple(sorted((first, second)))] += 1

        boundary = {
            vertex
            for edge, count in edge_counts.items()
            if count == 1
            for vertex in edge
        }
        front_boundary = frozenset(
            index
            for index in boundary
            if mesh.vertices[index][2] <= center[2] - 0.06 * depth
        )
        if not front_boundary:
            return morphs

        def source_pmx_indices(source):
            return {
                pmx_index
                for source_index in source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }

        def local_boundary(source, *, radius_x, radius_y, side=None):
            if not source:
                return frozenset()
            points = [mesh.vertices[index] for index in source]
            rx = max(float(radius_x), 1e-6)
            ry = max(float(radius_y), 1e-6)
            output = set()
            for index in front_boundary:
                point = mesh.vertices[index]
                if side is not None and side * (point[0] - center[0]) < -0.02 * width:
                    continue
                nearest = min(
                    ((point[0] - other[0]) / rx) ** 2
                    + ((point[1] - other[1]) / ry) ** 2
                    for other in points
                )
                if nearest < 1.0:
                    output.add(index)
            return frozenset(output)

        def pair_to_boundary(source, candidates, *, scale_x, scale_y):
            if not source or not candidates:
                return {}
            sx = max(float(scale_x), 1e-6)
            sy = max(float(scale_y), 1e-6)
            output = {}
            for source_index in source:
                point = mesh.vertices[source_index]
                output[source_index] = min(
                    candidates,
                    key=lambda boundary_index: (
                        ((point[0] - mesh.vertices[boundary_index][0]) / sx) ** 2
                        + ((point[1] - mesh.vertices[boundary_index][1]) / sy) ** 2
                    ),
                )
            return output

        def lock_feature_to_boundary(name, remove_source, pair_map, *, snap_y=False):
            morph = by_name.get(name)
            if morph is None or not pair_map:
                return

            # Capture the authoritative skin deltas before removing feature-island entries.
            by_pmx = {vertex_index: delta for vertex_index, delta in morph.offsets}

            def boundary_delta(source_index):
                values = [
                    by_pmx[pmx_index]
                    for pmx_index in source_to_pmx.get((group, source_index), ())
                    if pmx_index in by_pmx
                ]
                if not values:
                    return (0.0, 0.0, 0.0)
                count = float(len(values))
                return tuple(sum(value[axis] for value in values) / count for axis in range(3))

            # Remove every old feature-island delta first. The already-authored skin offsets stay
            # untouched and become the sole source of truth for this aperture.
            remove_pmx = source_pmx_indices(remove_source)
            if remove_pmx:
                morph.offsets[:] = [
                    (vertex_index, delta)
                    for vertex_index, delta in morph.offsets
                    if vertex_index not in remove_pmx
                ]

            for source_index in sorted(pair_map):
                boundary_index = pair_map[source_index]
                delta = boundary_delta(boundary_index)
                if snap_y:
                    # PMX flips source Z but leaves X/Y unchanged. Use the skin boundary's actual
                    # deformed Y target, not an independently estimated eye closure line.
                    boundary_target_y = mesh.vertices[boundary_index][1] + delta[1]
                    delta = (
                        delta[0],
                        boundary_target_y - mesh.vertices[source_index][1],
                        0.0,
                    )
                if max(abs(value) for value in delta) < 1e-7:
                    continue
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, delta))

        left_eye_surface = (
            regions.left_eye_surface
            if len(regions.left_eye_surface) >= 12 else regions.left_eye
        )
        right_eye_surface = (
            regions.right_eye_surface
            if len(regions.right_eye_surface) >= 12 else regions.right_eye
        )
        all_eye = frozenset(set(regions.left_eye) | set(regions.right_eye))

        left_eye_boundary = local_boundary(
            left_eye_surface,
            radius_x=0.16 * width,
            radius_y=0.13 * height,
            side=1.0,
        )
        right_eye_boundary = local_boundary(
            right_eye_surface,
            radius_x=0.16 * width,
            radius_y=0.13 * height,
            side=-1.0,
        )
        left_eye_pairs = pair_to_boundary(
            left_eye_surface,
            left_eye_boundary,
            scale_x=0.16 * width,
            scale_y=0.13 * height,
        )
        right_eye_pairs = pair_to_boundary(
            right_eye_surface,
            right_eye_boundary,
            scale_x=0.16 * width,
            scale_y=0.13 * height,
        )

        lock_feature_to_boundary(
            "BlinkLeft", regions.left_eye, left_eye_pairs, snap_y=True
        )
        lock_feature_to_boundary(
            "BlinkRight", regions.right_eye, right_eye_pairs, snap_y=True
        )
        combined_eye_pairs = dict(left_eye_pairs)
        combined_eye_pairs.update(right_eye_pairs)
        lock_feature_to_boundary("Blink", all_eye, combined_eye_pairs, snap_y=True)
        for name in ("EyeWide", "HalfLid", "HappyEyes"):
            lock_feature_to_boundary(name, all_eye, combined_eye_pairs)

        mouth_all = getattr(regions, "mouth_all", regions.mouth)
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        mouth_surface = mouth_surface if len(mouth_surface) >= 12 else mouth_all
        mouth_boundary = local_boundary(
            mouth_surface,
            radius_x=0.12 * width,
            radius_y=0.08 * height,
        )
        mouth_pairs = pair_to_boundary(
            mouth_surface,
            mouth_boundary,
            scale_x=0.12 * width,
            scale_y=0.08 * height,
        )
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
            lock_feature_to_boundary(name, mouth_all, mouth_pairs)

        return morphs

    pmx._reconstructed_face_morphs = aperture_locked_face_morphs
