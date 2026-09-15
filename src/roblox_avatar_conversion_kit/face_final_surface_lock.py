from __future__ import annotations


def _local_skin_vertices(mesh, group, center, size, feature, *, radius_x, radius_y):
    if not feature:
        return frozenset()
    points = [mesh.vertices[index] for index in feature]
    xmid = sum(point[0] for point in points) / len(points)
    ymid = sum(point[1] for point in points) / len(points)
    depth = size[2]
    return frozenset(
        corner[0]
        for face in mesh.faces
        if face.group == group and (face.material or "").endswith("__RACK_SKIN")
        for corner in face.corners
        if abs(mesh.vertices[corner[0]][0] - xmid) <= radius_x
        and abs(mesh.vertices[corner[0]][1] - ymid) <= radius_y
        and mesh.vertices[corner[0]][2] <= center[2] - 0.015 * depth
    )


def install(pmx):
    """Final morph-space lock between visible face overlays and the flesh-colored skin.

    Topology reconstruction establishes the real socket/lip deformation first. This last pass runs
    after every VMD compatibility alias and copies the *finished* skin displacement onto the visible
    overlay. Therefore additive VMD blends cannot change the neutral overlay-to-skin relative vector.
    """
    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def locked_face_morphs(
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
        width, height, _depth = regions.size
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        left_eye = regions.left_eye_surface
        right_eye = regions.right_eye_surface

        mouth_skin = _local_skin_vertices(
            mesh,
            group,
            regions.center,
            regions.size,
            mouth_surface,
            radius_x=0.18 * width,
            radius_y=0.12 * height,
        )
        left_skin = _local_skin_vertices(
            mesh,
            group,
            regions.center,
            regions.size,
            left_eye,
            radius_x=0.18 * width,
            radius_y=0.15 * height,
        )
        right_skin = _local_skin_vertices(
            mesh,
            group,
            regions.center,
            regions.size,
            right_eye,
            radius_x=0.18 * width,
            radius_y=0.15 * height,
        )

        def source_pmx(source):
            return {
                pmx_index
                for source_index in source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }

        def source_delta_reader(morph):
            by_pmx = {index: delta for index, delta in morph.offsets}
            cache = {}

            def read(source_index):
                if source_index in cache:
                    return cache[source_index]
                values = [
                    by_pmx[pmx_index]
                    for pmx_index in source_to_pmx.get((group, source_index), ())
                    if pmx_index in by_pmx
                ]
                if not values:
                    result = (0.0, 0.0, 0.0)
                else:
                    count = float(len(values))
                    result = tuple(
                        sum(value[axis] for value in values) / count for axis in range(3)
                    )
                cache[source_index] = result
                return result

            return read

        def hard_lock(morph, feature, skin, sx, sy):
            if not feature or not skin:
                return
            read = source_delta_reader(morph)
            moving_skin = {
                index: read(index)
                for index in skin
                if max(abs(value) for value in read(index)) >= 1e-7
            }
            if not moving_skin:
                return

            remove = source_pmx(feature)
            if remove:
                morph.offsets[:] = [item for item in morph.offsets if item[0] not in remove]

            scale_x = max(float(sx), 1e-6)
            scale_y = max(float(sy), 1e-6)
            for source_index in sorted(feature):
                point = mesh.vertices[source_index]
                nearest = min(
                    moving_skin,
                    key=lambda other: (
                        ((mesh.vertices[other][0] - point[0]) / scale_x) ** 2
                        + ((mesh.vertices[other][1] - point[1]) / scale_y) ** 2
                    ),
                )
                delta = moving_skin[nearest]
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, delta))

        for morph in morphs:
            if morph.panel == 3:
                hard_lock(
                    morph,
                    mouth_surface,
                    mouth_skin,
                    0.12 * width,
                    0.08 * height,
                )
            elif morph.panel == 2:
                hard_lock(
                    morph,
                    left_eye,
                    left_skin,
                    0.16 * width,
                    0.13 * height,
                )
                hard_lock(
                    morph,
                    right_eye,
                    right_skin,
                    0.16 * width,
                    0.13 * height,
                )

        return morphs

    pmx._reconstructed_face_morphs = locked_face_morphs
