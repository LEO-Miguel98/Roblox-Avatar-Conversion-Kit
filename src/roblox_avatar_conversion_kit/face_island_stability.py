from __future__ import annotations


def _subset_components(mesh, group, subset):
    """Connected components for a selected source-vertex subset within one OBJ group."""
    subset = set(subset)
    if not subset:
        return []

    adjacency = {index: set() for index in subset}
    for face in mesh.faces:
        if face.group != group:
            continue
        ids = [corner[0] for corner in face.corners if corner[0] in subset]
        for i, first in enumerate(ids):
            for second in ids[i + 1:]:
                adjacency[first].add(second)
                adjacency[second].add(first)

    unseen = set(subset)
    output = []
    while unseen:
        start = unseen.pop()
        stack = [start]
        component = {start}
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        output.append(component)
    return sorted(output, key=len, reverse=True)


def _is_fragmented_surface(mesh, group, subset):
    """Return True when a supposed facial surface is really many detached feature islands."""
    components = _subset_components(mesh, group, subset)
    if len(components) < 12 or not subset:
        return False
    largest = len(components[0]) if components else 0
    return largest < max(12, int(len(subset) * 0.25))


def install(pmx):
    """Keep highly fragmented eye artwork rigid while the face skin performs the expression.

    Some Roblox dynamic heads export each iris/highlight/lash/eye-decoration piece as a separate
    disconnected island. Earlier reconstruction treated the union as an eyelid surface and bent all
    those islands during Blink/EyeWide/HalfLid/HappyEyes. On Diane that union is about 70 components
    per eye, which visibly tears the artwork apart even when the surrounding skin aperture is right.

    If an eye surface is highly fragmented, remove feature-island vertex offsets from standard eye
    morphs and let the already-authored opaque eye-socket skin cage perform the expression. The
    eyeball/iris/highlight artwork then stays rigidly attached to the head and is covered/revealed by
    the eyelid skin, which is the normal anatomical behavior.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def stable_island_face_morphs(
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
        if not (fragmented_left or fragmented_right):
            return morphs

        remove_source = set()
        if fragmented_left:
            remove_source.update(regions.left_eye)
        if fragmented_right:
            remove_source.update(regions.right_eye)

        remove_pmx = {
            pmx_index
            for source_index in remove_source
            for pmx_index in source_to_pmx.get((group, source_index), ())
        }
        if not remove_pmx:
            return morphs

        for name in (
            "Blink",
            "BlinkLeft",
            "BlinkRight",
            "EyeWide",
            "HalfLid",
            "HappyEyes",
        ):
            morph = by_name.get(name)
            if morph is None:
                continue
            morph.offsets[:] = [
                (vertex_index, delta)
                for vertex_index, delta in morph.offsets
                if vertex_index not in remove_pmx
            ]

        return morphs

    pmx._reconstructed_face_morphs = stable_island_face_morphs
