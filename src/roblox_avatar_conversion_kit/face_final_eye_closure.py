from __future__ import annotations


def install(pmx):
    """Make blink eyelid artwork finish on the actual deformed skin socket.

    Copying the same delta is correct for lips, but not for a Blink when the disconnected eyelid
    overlay starts at a different neutral Y than the flesh-colored socket. For blink-like morphs the
    visible eye surface is therefore target-locked to the nearest moving socket skin position.
    """
    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def closed_eye_morphs(
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
        width, height, depth = regions.size
        skin_vertices = {
            corner[0]
            for face in mesh.faces
            if face.group == group and (face.material or "").endswith("__RACK_SKIN")
            for corner in face.corners
            if mesh.vertices[corner[0]][2] <= regions.center[2] - 0.015 * depth
        }

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

        def target_lock(morph, surface):
            if not surface:
                return
            points = [mesh.vertices[index] for index in surface]
            xmid = sum(point[0] for point in points) / len(points)
            ymid = sum(point[1] for point in points) / len(points)
            candidates = {
                index
                for index in skin_vertices
                if abs(mesh.vertices[index][0] - xmid) <= 0.18 * width
                and abs(mesh.vertices[index][1] - ymid) <= 0.15 * height
            }
            read = source_delta_reader(morph)
            moving = {
                index: read(index)
                for index in candidates
                if max(abs(value) for value in read(index)) >= 1e-7
            }
            if not moving:
                return

            remove = source_pmx(surface)
            morph.offsets[:] = [item for item in morph.offsets if item[0] not in remove]
            sx = max(0.16 * width, 1e-6)
            sy = max(0.13 * height, 1e-6)
            for source_index in sorted(surface):
                point = mesh.vertices[source_index]
                nearest = min(
                    moving,
                    key=lambda other: (
                        ((mesh.vertices[other][0] - point[0]) / sx) ** 2
                        + ((mesh.vertices[other][1] - point[1]) / sy) ** 2
                    ),
                )
                skin_point = mesh.vertices[nearest]
                skin_delta = moving[nearest]
                # PMX Y has the same sign as the source mesh.  X/Z keep the skin displacement,
                # while Y is chosen so both disconnected surfaces finish at one closure position.
                source_delta = (
                    skin_delta[0],
                    (skin_point[1] + skin_delta[1]) - point[1],
                    skin_delta[2],
                )
                converted = pmx._mmd_vec3(source_delta)
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, converted))

        blink_sides = {
            "Blink": (regions.left_eye_surface, regions.right_eye_surface),
            "BlinkLeft": (regions.left_eye_surface,),
            "BlinkRight": (regions.right_eye_surface,),
            "BlinkLeft2": (regions.left_eye_surface,),
            "BlinkRight2": (regions.right_eye_surface,),
            "BlinkRight2Alt": (regions.right_eye_surface,),
        }
        for morph in morphs:
            for surface in blink_sides.get(morph.name_en, ()):
                target_lock(morph, surface)

        return morphs

    pmx._reconstructed_face_morphs = closed_eye_morphs
