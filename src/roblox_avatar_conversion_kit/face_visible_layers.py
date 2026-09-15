from __future__ import annotations

from dataclasses import replace
from math import inf, sqrt

from .face_island_stability import _subset_components
from .face_surface_bind import _closest_point_barycentric, _skin_triangles


def _promote_dominant_lip_component(mesh, regions):
    """Keep the dominant mouth artwork component out of the hidden cavity.

    Some animated-head exports contain two very different visible mouth layers: a thin translucent
    mouth-line/seam near the face surface and a much larger colored lip component slightly deeper in
    the head. Earlier geometry-only reconstruction kept only the thin line as `mouth_surface`, so the
    colored lips were classified as cavity and stayed behind while the seam moved during VMD speech.

    Promote a clearly dominant connected mouth component when it is substantially larger than the
    rest. The strong dominance requirement keeps simple heads and similarly-sized teeth/tongue
    components on the conservative legacy path.
    """
    if regions is None or len(regions.mouth_all) < 12:
        return regions

    components = _subset_components(mesh, regions.group, regions.mouth_all)
    if not components:
        return regions
    components = sorted(components, key=len, reverse=True)
    largest = components[0]
    second = len(components[1]) if len(components) > 1 else 0
    if len(largest) < 24:
        return regions
    if second and len(largest) < int(second * 1.80):
        return regions

    surface = set(regions.mouth_surface)
    surface.update(largest)
    hidden = set(regions.mouth)
    hidden.difference_update(largest)
    return replace(
        regions,
        mouth=frozenset(hidden),
        mouth_surface=frozenset(surface),
    )


def _relaxed_surface_bindings(mesh, group, feature_vertices, center, size, max_fraction=0.34):
    """Bind deeper eye islands to nearby front skin triangles with a wider depth allowance."""
    triangles = _skin_triangles(mesh, group, center, size)
    if not triangles:
        return {}
    max_distance2 = (max_fraction * max(size)) ** 2
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
    """Promote actual visible lips and give deeper eye islands rigid socket-follow motion.

    The surface-binding pass handles the thin/front eye and mouth overlays. Diane exposed two
    remaining failure modes:

    * the dominant colored lip component was still in the hidden mouth set, so only a translucent
      seam moved while the real lips stayed behind;
    * deeper black/white eye artwork stayed static while the flesh-colored socket deformed.

    This finalizer promotes a clearly dominant lip component into the visible surface set before the
    PMX writer decides what to hide. For eye expressions it then moves each deeper disconnected eye
    island as one rigid piece using the average deformation of the nearby socket skin. Rigid island
    motion keeps iris/highlight/lash pieces from stretching apart while ensuring they no longer stay
    behind when the face moves.
    """

    base_analyze_face_regions = pmx._analyze_face_regions

    def visible_layer_regions(mesh, group_to_bone):
        regions = base_analyze_face_regions(mesh, group_to_bone)
        return _promote_dominant_lip_component(mesh, regions)

    pmx._analyze_face_regions = visible_layer_regions

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def visible_layer_face_morphs(
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
        left_deep = set(regions.left_eye) - set(regions.left_eye_surface)
        right_deep = set(regions.right_eye) - set(regions.right_eye_surface)
        if not left_deep and not right_deep:
            return morphs

        left_components = _subset_components(mesh, group, left_deep)
        right_components = _subset_components(mesh, group, right_deep)

        skin_vertices = {
            corner[0]
            for face in mesh.faces
            if face.group == group and (face.material or "").endswith("__RACK_SKIN")
            for corner in face.corners
        }

        def source_delta_reader(morph):
            by_pmx = {vertex_index: delta for vertex_index, delta in morph.offsets}
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
                    value = (0.0, 0.0, 0.0)
                else:
                    count = float(len(values))
                    value = tuple(
                        sum(item[axis] for item in values) / count
                        for axis in range(3)
                    )
                cache[source_index] = value
                return value

            return read

        def add_rigid_follow(name, components):
            morph = by_name.get(name)
            if morph is None or not components:
                return

            skin_delta = source_delta_reader(morph)
            move_source = set().union(*components)
            move_pmx = {
                pmx_index
                for source_index in move_source
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }
            if move_pmx:
                morph.offsets[:] = [
                    (vertex_index, delta)
                    for vertex_index, delta in morph.offsets
                    if vertex_index not in move_pmx
                ]

            for component in components:
                bindings = _relaxed_surface_bindings(
                    mesh,
                    group,
                    component,
                    regions.center,
                    regions.size,
                )
                samples = []
                for source_index, (tri, weights) in bindings.items():
                    if not any(index in skin_vertices for index in tri):
                        continue
                    values = [skin_delta(index) for index in tri]
                    samples.append(tuple(
                        weights[0] * values[0][axis]
                        + weights[1] * values[1][axis]
                        + weights[2] * values[2][axis]
                        for axis in range(3)
                    ))
                if not samples:
                    continue

                count = float(len(samples))
                delta = tuple(
                    sum(value[axis] for value in samples) / count
                    for axis in range(3)
                )
                if sqrt(sum(value * value for value in delta)) < 1e-7:
                    continue
                for source_index in component:
                    for pmx_index in source_to_pmx.get((group, source_index), ()):
                        morph.offsets.append((pmx_index, delta))

        add_rigid_follow("BlinkLeft", left_components)
        add_rigid_follow("BlinkRight", right_components)
        add_rigid_follow("Blink", left_components + right_components)
        for name in ("EyeWide", "HalfLid", "HappyEyes"):
            add_rigid_follow(name, left_components + right_components)

        return morphs

    pmx._reconstructed_face_morphs = visible_layer_face_morphs
