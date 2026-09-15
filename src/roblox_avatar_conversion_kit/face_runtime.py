from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaceRegions:
    group: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    left_eye: frozenset[int]
    right_eye: frozenset[int]
    left_eye_surface: frozenset[int]
    right_eye_surface: frozenset[int]
    left_brow: frozenset[int]
    right_brow: frozenset[int]
    # `mouth` intentionally remains the subset that write_pmx hides in the neutral pose.
    # Keeping that compatibility lets us hide only the internal cavity without touching the writer.
    mouth: frozenset[int]
    mouth_all: frozenset[int]
    mouth_surface: frozenset[int]
    mouth_components: int
    hide_depth: float


def install(pmx):
    """Install face-region analysis and reconstructed facial morphs into the PMX writer."""

    def analyze_face_regions(mesh, group_to_bone):
        groups = mesh.group_vertex_indices()
        candidates = [
            group
            for group in groups
            if group_to_bone.get(group) == "head" and group.lower().startswith("rig")
        ]
        if not candidates:
            candidates = [group for group in groups if group_to_bone.get(group) == "head"]
        if not candidates:
            return None

        group = max(candidates, key=lambda name: len(groups[name]))
        indices = groups[group]
        lo, hi = mesh.bounds(indices)
        center = tuple((lo[i] + hi[i]) * 0.5 for i in range(3))
        size = tuple(max(hi[i] - lo[i], 1e-6) for i in range(3))
        width, height, depth = size
        front_cut = lo[2] + 0.25 * depth

        skin_vertices = {
            corner[0]
            for face in mesh.faces
            if face.group == group and (face.material or "").endswith("__RACK_SKIN")
            for corner in face.corners
        }

        eyes = []
        brows = []
        mouths = []
        for component in pmx._group_components(mesh, group):
            if component and component.issubset(skin_vertices):
                continue
            points = [mesh.vertices[index] for index in component]
            comp_lo = tuple(min(point[axis] for point in points) for axis in range(3))
            comp_hi = tuple(max(point[axis] for point in points) for axis in range(3))
            comp_center = tuple((comp_lo[axis] + comp_hi[axis]) * 0.5 for axis in range(3))
            comp_size = tuple(comp_hi[axis] - comp_lo[axis] for axis in range(3))
            offset_x = abs(comp_center[0] - center[0])

            is_brow = (
                comp_center[2] <= front_cut
                and 0.10 * width <= offset_x <= 0.48 * width
                and center[1] + 0.015 * height <= comp_center[1] <= center[1] + 0.08 * height
                and comp_size[0] <= 0.40 * width
                and comp_size[1] <= 0.085 * height
                and len(component) >= 7
            )
            if is_brow:
                brows.append((component, comp_center, comp_size))
                continue

            if (
                comp_center[2] <= front_cut
                and 0.08 * width <= offset_x <= 0.44 * width
                and center[1] - 0.20 * height <= comp_center[1] <= center[1] + 0.04 * height
                and comp_size[0] <= 0.40 * width
                and comp_size[1] <= 0.34 * height
            ):
                eyes.append((component, comp_center, comp_size))

            if (
                comp_center[2] <= front_cut
                and offset_x <= 0.21 * width
                and center[1] - 0.43 * height <= comp_center[1] <= center[1] - 0.24 * height
                and comp_size[0] <= 0.32 * width
                and comp_size[1] <= 0.22 * height
            ):
                mouths.append((component, comp_center, comp_size))

        left_eye = (
            set().union(*(component for component, comp_center, _ in eyes if comp_center[0] >= center[0]))
            if eyes else set()
        )
        right_eye = (
            set().union(*(component for component, comp_center, _ in eyes if comp_center[0] < center[0]))
            if eyes else set()
        )

        # Prefer thin, front-most eye pieces as the motion driver for the surrounding socket skin.
        # The full eye region still receives the expression morph; this only avoids deeper eyeball/
        # accessory pieces pulling the facial shell in the wrong direction.
        eye_surface_components = [
            (component, comp_center)
            for component, comp_center, comp_size in eyes
            if (
                (comp_center[2] - lo[2]) <= 0.16 * depth
                and comp_size[2] <= 0.04 * depth
            )
        ]
        left_eye_surface = (
            set().union(*(
                component
                for component, comp_center in eye_surface_components
                if comp_center[0] >= center[0]
            ))
            if eye_surface_components else set()
        )
        right_eye_surface = (
            set().union(*(
                component
                for component, comp_center in eye_surface_components
                if comp_center[0] < center[0]
            ))
            if eye_surface_components else set()
        )
        if len(left_eye_surface) < 12:
            left_eye_surface = set(left_eye)
        if len(right_eye_surface) < 12:
            right_eye_surface = set(right_eye)

        left_brow = (
            set().union(*(component for component, comp_center, _ in brows if comp_center[0] >= center[0]))
            if brows else set()
        )
        right_brow = (
            set().union(*(component for component, comp_center, _ in brows if comp_center[0] < center[0]))
            if brows else set()
        )

        mouth_all = set().union(*(component for component, _, _ in mouths)) if mouths else set()
        # Dynamic heads often contain a thin lip/front-face layer plus deeper mouth/teeth/tongue
        # pieces. The old implementation hid the entire union, which made even the visible lip
        # surface travel through the head on every expression. Keep thin front pieces on the face
        # and hide only the deeper cavity when we can distinguish them safely.
        mouth_surface_components = [
            component
            for component, comp_center, comp_size in mouths
            if (
                (comp_center[2] - lo[2]) <= 0.12 * depth
                and comp_size[2] <= 0.03 * depth
            )
        ]
        mouth_surface = (
            set().union(*mouth_surface_components) if mouth_surface_components else set()
        )
        if len(mouth_surface) < 12:
            mouth_surface = set(mouth_all)
        mouth_hidden = set(mouth_all) - set(mouth_surface)
        # If an export does not provide a separable surface/cavity layout, retain the conservative
        # legacy behavior rather than leaving unknown internal geometry visible through the face.
        if len(mouth_hidden) < 12 and len(mouth_all) >= 12:
            mouth_hidden = set(mouth_all)

        hide_depth = min(max(depth * 0.36, 0.12), depth * 0.48)
        return FaceRegions(
            group=group,
            center=center,
            size=size,
            left_eye=frozenset(left_eye),
            right_eye=frozenset(right_eye),
            left_eye_surface=frozenset(left_eye_surface),
            right_eye_surface=frozenset(right_eye_surface),
            left_brow=frozenset(left_brow),
            right_brow=frozenset(right_brow),
            mouth=frozenset(mouth_hidden),
            mouth_all=frozenset(mouth_all),
            mouth_surface=frozenset(mouth_surface),
            mouth_components=len(mouths),
            hide_depth=hide_depth,
        )

    def reconstructed_face_morphs(
        mesh,
        group_to_bone,
        source_to_pmx,
        *,
        regions=None,
        mouth_hidden_at_neutral=False,
    ):
        regions = regions or analyze_face_regions(mesh, group_to_bone)
        if regions is None:
            return []

        group = regions.group
        center = regions.center
        width, height, _depth = regions.size
        morphs = []

        def append_source_offsets(source, delta_fn):
            offsets = []
            for vertex_index in source:
                point = mesh.vertices[vertex_index]
                delta = delta_fn(vertex_index, point)
                if max(abs(value) for value in delta) < 1e-6:
                    continue
                for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                    offsets.append((pmx_index, pmx._mmd_vec3(delta)))
            return offsets

        def blink(name_jp, name_en, source, reference):
            if len(source) < 12:
                return None
            reference = reference if len(reference) >= 12 else source
            ys = [mesh.vertices[index][1] for index in reference]
            line = sum(ys) / len(ys)
            offsets = append_source_offsets(
                source,
                lambda _idx, point: (0.0, (line - point[1]) * 0.88, 0.0),
            )
            return pmx._VertexMorph(name_jp, name_en, 2, offsets) if offsets else None

        left_blink = blink(
            "ウィンク", "BlinkLeft", regions.left_eye, regions.left_eye_surface
        )
        right_blink = blink(
            "ウィンク右", "BlinkRight", regions.right_eye, regions.right_eye_surface
        )
        if left_blink and right_blink:
            morphs.append(pmx._VertexMorph(
                "まばたき", "Blink", 2, left_blink.offsets + right_blink.offsets
            ))
            morphs.extend([left_blink, right_blink])
        elif left_blink:
            morphs.append(left_blink)
        elif right_blink:
            morphs.append(right_blink)

        eye_sides = [
            (regions.left_eye, regions.left_eye_surface),
            (regions.right_eye, regions.right_eye_surface),
        ]
        eye_sides = [(source, ref) for source, ref in eye_sides if len(source) >= 12]
        if eye_sides:
            surprise = []
            half_lid = []
            happy = []
            for source, reference in eye_sides:
                reference = reference if len(reference) >= 12 else source
                ys = [mesh.vertices[index][1] for index in reference]
                xs = [mesh.vertices[index][0] for index in reference]
                line = sum(ys) / len(ys)
                xmid = sum(xs) / len(xs)
                xspan = max(max(xs) - min(xs), 1e-6)
                for vertex_index in source:
                    point = mesh.vertices[vertex_index]
                    rel_y = point[1] - line
                    rel_x = (point[0] - xmid) / xspan
                    for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                        surprise.append((pmx_index, pmx._mmd_vec3((0.0, rel_y * 0.16, 0.0))))
                        half_lid.append((
                            pmx_index,
                            pmx._mmd_vec3((
                                0.0,
                                (line - point[1]) * 0.42 if rel_y > 0 else 0.0,
                                0.0,
                            )),
                        ))
                        arch = 0.018 * height * (1.0 - min(abs(rel_x) * 2.0, 1.0))
                        happy.append((
                            pmx_index,
                            pmx._mmd_vec3((0.0, (line + arch - point[1]) * 0.64, 0.0)),
                        ))
            if surprise:
                morphs.append(pmx._VertexMorph("びっくり", "EyeWide", 2, surprise))
            if half_lid:
                morphs.append(pmx._VertexMorph("じと目", "HalfLid", 2, half_lid))
            if happy:
                morphs.append(pmx._VertexMorph("にこり", "HappyEyes", 2, happy))

        brow_sources = [source for source in (regions.left_brow, regions.right_brow) if len(source) >= 6]
        if brow_sources:
            brow_raise = []
            brow_lower = []
            brow_sad = []
            brow_angry = []
            brow_serious = []
            for source in brow_sources:
                for vertex_index in source:
                    point = mesh.vertices[vertex_index]
                    innerness = 1.0 - min(
                        abs(point[0] - center[0]) / max(0.46 * width, 1e-6), 1.0
                    )
                    for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                        brow_raise.append((pmx_index, pmx._mmd_vec3((0.0, 0.035 * height, 0.0))))
                        brow_lower.append((pmx_index, pmx._mmd_vec3((0.0, -0.028 * height, 0.0))))
                        brow_sad.append((pmx_index, pmx._mmd_vec3((0.0, (0.052 * innerness - 0.014) * height, 0.0))))
                        brow_angry.append((pmx_index, pmx._mmd_vec3((0.0, (-0.048 * innerness + 0.012) * height, 0.0))))
                        brow_serious.append((pmx_index, pmx._mmd_vec3((0.0, (-0.020 - 0.008 * innerness) * height, 0.0))))
            morphs.extend([
                pmx._VertexMorph("上", "BrowRaise", 1, brow_raise),
                pmx._VertexMorph("下", "BrowLower", 1, brow_lower),
                pmx._VertexMorph("困る", "BrowSad", 1, brow_sad),
                pmx._VertexMorph("怒り", "BrowAngry", 1, brow_angry),
                pmx._VertexMorph("真面目", "BrowSerious", 1, brow_serious),
            ])

        mouth = regions.mouth_all
        if len(mouth) < 12:
            return morphs

        mouth_reference = regions.mouth_surface if len(regions.mouth_surface) >= 12 else mouth
        ys = [mesh.vertices[index][1] for index in mouth_reference]
        line = sum(ys) / len(ys)
        hidden_mouth = regions.mouth if mouth_hidden_at_neutral else frozenset()
        a_offsets = []
        i_offsets = []
        u_offsets = []
        e_offsets = []
        o_offsets = []
        n_offsets = []
        wide_offsets = []
        smile_offsets = []
        for vertex_index in mouth:
            point = mesh.vertices[vertex_index]
            rel_y = point[1] - line
            rel_x = point[0] - center[0]
            xnorm = min(abs(rel_x) / max(0.21 * width, 1e-6), 1.0)
            sign_x = 1.0 if rel_x >= 0 else -1.0
            dy_a = (-0.075 * height if rel_y <= 0 else 0.018 * height) * (
                0.55 + 0.45 * min(abs(rel_y) / max(0.11 * height, 1e-6), 1.0)
            )
            dx_i = 0.025 * width * xnorm * sign_x
            dy_i = -0.010 * height * (1.0 - xnorm)
            dx_u = -0.035 * width * xnorm * sign_x
            dy_u = -0.018 * height if rel_y <= 0 else 0.006 * height
            dx_e = 0.018 * width * xnorm * sign_x
            dy_e = -0.045 * height if rel_y <= 0 else 0.012 * height
            dx_o = -0.022 * width * xnorm * sign_x
            dy_o = -0.052 * height if rel_y <= 0 else 0.010 * height
            dy_n = (line - point[1]) * 0.68
            dx_wide = 0.030 * width * xnorm * sign_x
            dy_smile = 0.045 * height * (xnorm ** 1.25)
            dx_smile = 0.015 * width * xnorm * sign_x
            reveal_z = -regions.hide_depth if vertex_index in hidden_mouth else 0.0

            for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                a_offsets.append((pmx_index, pmx._mmd_vec3((0.0, dy_a, reveal_z))))
                i_offsets.append((pmx_index, pmx._mmd_vec3((dx_i, dy_i, reveal_z))))
                u_offsets.append((pmx_index, pmx._mmd_vec3((dx_u, dy_u, reveal_z))))
                e_offsets.append((pmx_index, pmx._mmd_vec3((dx_e, dy_e, reveal_z))))
                o_offsets.append((pmx_index, pmx._mmd_vec3((dx_o, dy_o, reveal_z))))
                # Closed-mouth and closed-smile shapes must not pull the hidden mouth cavity back
                # through the face. Only open vowel/wide shapes reveal internal geometry.
                n_offsets.append((pmx_index, pmx._mmd_vec3((0.0, dy_n, 0.0))))
                wide_offsets.append((pmx_index, pmx._mmd_vec3((dx_wide, -0.006 * height, reveal_z))))
                smile_offsets.append((pmx_index, pmx._mmd_vec3((dx_smile, dy_smile, 0.0))))

        if a_offsets:
            morphs.append(pmx._VertexMorph("あ", "MouthOpen", 3, a_offsets))
        if i_offsets:
            morphs.append(pmx._VertexMorph("い", "MouthI", 3, i_offsets))
        if u_offsets:
            morphs.append(pmx._VertexMorph("う", "MouthU", 3, u_offsets))
        if e_offsets:
            morphs.append(pmx._VertexMorph("え", "MouthE", 3, e_offsets))
        if o_offsets:
            morphs.append(pmx._VertexMorph("お", "MouthO", 3, o_offsets))
        if n_offsets:
            morphs.append(pmx._VertexMorph("ん", "MouthClosed", 3, n_offsets))
        if wide_offsets:
            morphs.append(pmx._VertexMorph("口横広げ", "MouthWide", 3, wide_offsets))
        if smile_offsets:
            morphs.append(pmx._VertexMorph("笑い", "Smile", 3, smile_offsets))
        return morphs

    pmx._FaceRegions = FaceRegions
    pmx._analyze_face_regions = analyze_face_regions
    pmx._reconstructed_face_morphs = reconstructed_face_morphs
