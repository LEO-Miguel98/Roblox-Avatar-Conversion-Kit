from __future__ import annotations

import math
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .features import FeaturePlan, dynamic_chain
from .obj import Material, ObjMesh
from .rig import Bone
from .weights import (
    VertexWeight,
    compute_group_vertex_weights,
    summarize_weights,
    weights_for_layered_point,
)


def _text(value: str) -> bytes:
    raw = value.encode("utf-16-le")
    return struct.pack("<i", len(raw)) + raw


def _vec2(value):
    return struct.pack("<2f", *value)


def _vec3(value):
    return struct.pack("<3f", *value)


def _vec4(value):
    return struct.pack("<4f", *value)


def _mmd_vec3(value):
    return (value[0], value[1], -value[2])


def _mmd_uv(value, *, flip_u: bool = False):
    u, v = value
    return (1.0 - u if flip_u else u, 1.0 - v)


def _planar_uv_flip_groups(mesh: ObjMesh, threshold: float = 0.025):
    out: set[str] = set()
    for group, indices in mesh.group_vertex_indices().items():
        if not group.lower().startswith("handle") or not indices:
            continue
        lo, hi = mesh.bounds(indices)
        size = tuple(max(float(hi[i] - lo[i]), 0.0) for i in range(3))
        longest = max(size)
        if longest > 1e-8 and min(size) / longest <= threshold:
            out.add(group)
    return out


MMD_JP = {
    "allParent": "全ての親",
    "center": "センター",
    "groove": "グルーブ",
    "hips": "下半身",
    "spine": "上半身",
    "chest": "上半身2",
    "neck": "首",
    "head": "頭",
    "eyes": "両目",
    "leftEye": "左目",
    "rightEye": "右目",
    "leftShoulderP": "左肩P",
    "leftShoulder": "左肩",
    "leftUpperArm": "左腕",
    "leftArmTwist": "左腕捩",
    "leftLowerArm": "左ひじ",
    "leftWristTwist": "左手捩",
    "leftHand": "左手首",
    "rightShoulderP": "右肩P",
    "rightShoulder": "右肩",
    "rightUpperArm": "右腕",
    "rightArmTwist": "右腕捩",
    "rightLowerArm": "右ひじ",
    "rightWristTwist": "右手捩",
    "rightHand": "右手首",
    "leftUpperLeg": "左足",
    "leftLowerLeg": "左ひざ",
    "leftFoot": "左足首",
    "leftToe": "左つま先",
    "rightUpperLeg": "右足",
    "rightLowerLeg": "右ひざ",
    "rightFoot": "右足首",
    "rightToe": "右つま先",
    "leftLegIK": "左足ＩＫ",
    "rightLegIK": "右足ＩＫ",
    "leftToeIK": "左つま先ＩＫ",
    "rightToeIK": "右つま先ＩＫ",
}


@dataclass(frozen=True)
class _PmxBone:
    name: str
    parent: str | None
    position: tuple[float, float, float]
    ik_target: str | None = None
    ik_links: tuple[str, ...] = ()
    ik_iterations: int = 40
    ik_weight: float = 0.5
    movable: bool = False


@dataclass(frozen=True)
class _BoneMorph:
    name_jp: str
    name_en: str
    bone_name: str
    rotation: tuple[float, float, float, float]


@dataclass(frozen=True)
class _VertexMorph:
    name_jp: str
    name_en: str
    panel: int
    offsets: list[tuple[int, tuple[float, float, float]]]


@dataclass(frozen=True)
class _RigidBody:
    name: str
    bone_name: str
    shape_size: tuple[float, float, float]
    position: tuple[float, float, float]
    operation: int
    mass: float
    linear_damping: float
    angular_damping: float
    group: int
    collision_mask: int


@dataclass(frozen=True)
class _Joint:
    name: str
    rigid_a: str
    rigid_b: str
    position: tuple[float, float, float]
    angular_limit: float
    spring: float


@dataclass(frozen=True)
class _FaceRegions:
    group: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    left_eye: frozenset[int]
    right_eye: frozenset[int]
    mouth: frozenset[int]
    mouth_components: int
    hide_depth: float


def _lerp(a, b, t: float):
    return tuple((1.0 - t) * a[i] + t * b[i] for i in range(3))


def _distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _quat_axis_angle(axis, angle):
    half = angle / 2.0
    scale = math.sin(half)
    return (
        axis[0] * scale,
        axis[1] * scale,
        axis[2] * scale,
        math.cos(half),
    )


def _ground_y(mesh: ObjMesh | None) -> float:
    if mesh is None or not mesh.faces:
        return 0.0
    used = {corner[0] for face in mesh.faces for corner in face.corners}
    if not used:
        return 0.0
    return min(mesh.vertices[index][1] for index in used)


def _foot_toe_position(
    side: str,
    by: dict[str, Bone],
    mesh: ObjMesh | None,
    group_to_bone: dict[str, str] | None,
    ground_y: float,
):
    foot = by[f"{side}Foot"]
    lower = by[f"{side}LowerLeg"]
    if mesh is not None and group_to_bone:
        group_indices = mesh.group_vertex_indices()
        candidates = [
            group
            for group, bone_name in group_to_bone.items()
            if bone_name == f"{side}Foot" and group.lower().startswith("rig")
        ]
        indices = sorted(
            {
                index
                for group in candidates
                for index in group_indices.get(group, ())
            }
        )
        if indices:
            lo, hi = mesh.bounds(indices)
            return (
                foot.position[0],
                max(ground_y, lo[1] + (hi[1] - lo[1]) * 0.06),
                lo[2],
            )

    length = max(_distance(lower.position, foot.position), 0.1)
    return (
        foot.position[0],
        ground_y,
        foot.position[2] - length * 0.45,
    )


def _pmx_bones(
    bones: list[Bone],
    features: FeaturePlan | None,
    *,
    mesh: ObjMesh | None = None,
    group_to_bone: dict[str, str] | None = None,
):
    """Build an MMD-friendly hierarchy from reconstructed Roblox bones.

    The parent layout follows the stable conventions observed across classic PMD models, while
    helper bones cover the semistandard tracks used by modern VMD motions.
    """
    by = {bone.name: bone for bone in bones}
    hips = by.get("hips") or bones[0]
    ground = _ground_y(mesh)
    center_y = ground + (hips.position[1] - ground) * 0.64
    center = (hips.position[0], center_y, hips.position[2])
    groove = center

    result: list[_PmxBone] = [
        _PmxBone("allParent", None, (hips.position[0], ground, hips.position[2]), movable=True),
        _PmxBone("center", "allParent", center, movable=True),
        _PmxBone("groove", "center", groove, movable=True),
    ]

    for side in ("left", "right"):
        arm = by.get(f"{side}UpperArm")
        elbow = by.get(f"{side}LowerArm")
        wrist = by.get(f"{side}Hand")
        chest = by.get("chest") or by.get("spine")
        if arm and elbow and wrist and chest:
            shoulder_p = _lerp(chest.position, arm.position, 0.08)
            shoulder = _lerp(chest.position, arm.position, 0.16)
            arm_twist = _lerp(arm.position, elbow.position, 0.33)
            wrist_twist = _lerp(elbow.position, wrist.position, 0.27)
            result.extend(
                [
                    _PmxBone(f"{side}ShoulderP", "chest" if "chest" in by else "spine", shoulder_p),
                    _PmxBone(f"{side}Shoulder", f"{side}ShoulderP", shoulder),
                    _PmxBone(f"{side}ArmTwist", f"{side}UpperArm", arm_twist),
                    _PmxBone(f"{side}WristTwist", f"{side}LowerArm", wrist_twist),
                ]
            )

    helper_names = {item.name for item in result}
    for bone in bones:
        parent = bone.parent
        if bone.name == "hips":
            parent = "groove"
        elif bone.name == "spine":
            parent = "groove"
        elif bone.name in {"leftUpperArm", "rightUpperArm"}:
            side = "left" if bone.name.startswith("left") else "right"
            if f"{side}Shoulder" in helper_names:
                parent = f"{side}Shoulder"
        elif bone.name in {"leftLowerArm", "rightLowerArm"}:
            side = "left" if bone.name.startswith("left") else "right"
            if f"{side}ArmTwist" in helper_names:
                parent = f"{side}ArmTwist"
        elif bone.name in {"leftHand", "rightHand"}:
            side = "left" if bone.name.startswith("left") else "right"
            if f"{side}WristTwist" in helper_names:
                parent = f"{side}WristTwist"
        result.append(_PmxBone(bone.name, parent, bone.position))

    for side in ("left", "right"):
        foot = by.get(f"{side}Foot")
        lower = by.get(f"{side}LowerLeg")
        upper = by.get(f"{side}UpperLeg")
        if not (foot and lower and upper):
            continue
        toe = _foot_toe_position(side, by, mesh, group_to_bone, ground)
        result.append(_PmxBone(f"{side}Toe", f"{side}Foot", toe))
        result.append(
            _PmxBone(
                f"{side}LegIK",
                "allParent",
                foot.position,
                f"{side}Foot",
                (f"{side}LowerLeg", f"{side}UpperLeg"),
                ik_iterations=40,
                ik_weight=0.5,
                movable=True,
            )
        )
        result.append(
            _PmxBone(
                f"{side}ToeIK",
                f"{side}LegIK",
                toe,
                f"{side}Toe",
                (f"{side}Foot",),
                ik_iterations=3,
                ik_weight=1.0,
                movable=True,
            )
        )

    if features and features.eyes:
        eyes = features.eyes
        result.extend(
            [
                _PmxBone("eyes", "head", eyes.master_position),
                _PmxBone("leftEye", "eyes", eyes.left_position),
                _PmxBone("rightEye", "eyes", eyes.right_position),
            ]
        )

    if features:
        for dynamic in features.dynamics:
            for segment in dynamic_chain(dynamic):
                result.append(
                    _PmxBone(
                        segment["name"],
                        segment["parent"],
                        tuple(segment["position"]),
                    )
                )
    return result


def _eye_morphs(features: FeaturePlan | None):
    if not features or not features.eyes:
        return []
    yaw = math.radians(18.0)
    pitch = math.radians(12.0)
    return [
        _BoneMorph("視線左", "LookLeft", "eyes", _quat_axis_angle((0, 1, 0), yaw)),
        _BoneMorph("視線右", "LookRight", "eyes", _quat_axis_angle((0, 1, 0), -yaw)),
        _BoneMorph("視線上", "LookUp", "eyes", _quat_axis_angle((1, 0, 0), -pitch)),
        _BoneMorph("視線下", "LookDown", "eyes", _quat_axis_angle((1, 0, 0), pitch)),
    ]


def _group_components(mesh: ObjMesh, group: str):
    faces = [face for face in mesh.faces if face.group == group]
    adjacency: dict[int, set[int]] = defaultdict(set)
    vertices: set[int] = set()
    for face in faces:
        indices = [corner[0] for corner in face.corners]
        vertices.update(indices)
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                adjacency[indices[i]].add(indices[j])
                adjacency[indices[j]].add(indices[i])

    seen: set[int] = set()
    components: list[set[int]] = []
    for start in vertices:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component: set[int] = set()
        while stack:
            vertex = stack.pop()
            component.add(vertex)
            for neighbor in adjacency[vertex]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def _analyze_face_regions(mesh: ObjMesh, group_to_bone: dict[str, str]) -> _FaceRegions | None:
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

    eyes = []
    mouths = []
    for component in _group_components(mesh, group):
        points = [mesh.vertices[index] for index in component]
        comp_lo = tuple(min(point[axis] for point in points) for axis in range(3))
        comp_hi = tuple(max(point[axis] for point in points) for axis in range(3))
        comp_center = tuple((comp_lo[axis] + comp_hi[axis]) * 0.5 for axis in range(3))
        comp_size = tuple(comp_hi[axis] - comp_lo[axis] for axis in range(3))
        offset_x = abs(comp_center[0] - center[0])

        if (
            comp_center[2] <= front_cut
            and 0.08 * width <= offset_x <= 0.44 * width
            and center[1] - 0.20 * height <= comp_center[1] <= center[1] + 0.06 * height
            and comp_size[0] <= 0.40 * width
            and comp_size[1] <= 0.34 * height
        ):
            eyes.append((component, comp_center))

        if (
            comp_center[2] <= front_cut
            and offset_x <= 0.21 * width
            and center[1] - 0.43 * height <= comp_center[1] <= center[1] - 0.24 * height
            and comp_size[0] <= 0.32 * width
            and comp_size[1] <= 0.22 * height
        ):
            mouths.append((component, comp_center))

    left_eye = (
        set().union(*(component for component, comp_center in eyes if comp_center[0] >= center[0]))
        if eyes
        else set()
    )
    right_eye = (
        set().union(*(component for component, comp_center in eyes if comp_center[0] < center[0]))
        if eyes
        else set()
    )
    mouth = set().union(*(component for component, _ in mouths)) if mouths else set()
    hide_depth = min(max(depth * 0.36, 0.12), depth * 0.48)
    return _FaceRegions(
        group=group,
        center=center,
        size=size,
        left_eye=frozenset(left_eye),
        right_eye=frozenset(right_eye),
        mouth=frozenset(mouth),
        mouth_components=len(mouths),
        hide_depth=hide_depth,
    )


def _reconstructed_face_morphs(
    mesh: ObjMesh,
    group_to_bone: dict[str, str],
    source_to_pmx,
    *,
    regions: _FaceRegions | None = None,
    mouth_hidden_at_neutral: bool = False,
) -> list[_VertexMorph]:
    regions = regions or _analyze_face_regions(mesh, group_to_bone)
    if regions is None:
        return []

    group = regions.group
    center = regions.center
    width, height, _depth = regions.size
    morphs: list[_VertexMorph] = []

    def blink(name_jp: str, name_en: str, source: frozenset[int]):
        if len(source) < 12:
            return None
        ys = [mesh.vertices[index][1] for index in source]
        line = sum(ys) / len(ys)
        offsets = []
        for vertex_index in source:
            point = mesh.vertices[vertex_index]
            delta = (0.0, (line - point[1]) * 0.88, 0.0)
            if abs(delta[1]) < 1e-5:
                continue
            for pmx_index in source_to_pmx.get((group, vertex_index), ()):
                offsets.append((pmx_index, _mmd_vec3(delta)))
        return _VertexMorph(name_jp, name_en, 2, offsets) if offsets else None

    left_blink = blink("ウィンク", "BlinkLeft", regions.left_eye)
    right_blink = blink("ウィンク右", "BlinkRight", regions.right_eye)
    if left_blink and right_blink:
        morphs.append(
            _VertexMorph(
                "まばたき",
                "Blink",
                2,
                left_blink.offsets + right_blink.offsets,
            )
        )
        morphs.extend([left_blink, right_blink])
    elif left_blink:
        morphs.append(left_blink)
    elif right_blink:
        morphs.append(right_blink)

    mouth = regions.mouth
    if len(mouth) < 12:
        return morphs

    ys = [mesh.vertices[index][1] for index in mouth]
    line = sum(ys) / len(ys)
    reveal_z = -regions.hide_depth if mouth_hidden_at_neutral else 0.0
    a_offsets = []
    i_offsets = []
    u_offsets = []
    e_offsets = []
    o_offsets = []
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
        dy_smile = 0.045 * height * (xnorm ** 1.25)
        dx_smile = 0.015 * width * xnorm * sign_x

        for pmx_index in source_to_pmx.get((group, vertex_index), ()):
            a_offsets.append((pmx_index, _mmd_vec3((0.0, dy_a, reveal_z))))
            i_offsets.append((pmx_index, _mmd_vec3((dx_i, dy_i, reveal_z))))
            u_offsets.append((pmx_index, _mmd_vec3((dx_u, dy_u, reveal_z))))
            e_offsets.append((pmx_index, _mmd_vec3((dx_e, dy_e, reveal_z))))
            o_offsets.append((pmx_index, _mmd_vec3((dx_o, dy_o, reveal_z))))
            smile_offsets.append((pmx_index, _mmd_vec3((dx_smile, dy_smile, reveal_z))))

    if a_offsets:
        morphs.append(_VertexMorph("あ", "MouthOpen", 3, a_offsets))
    if i_offsets:
        morphs.append(_VertexMorph("い", "MouthI", 3, i_offsets))
    if u_offsets:
        morphs.append(_VertexMorph("う", "MouthU", 3, u_offsets))
    if e_offsets:
        morphs.append(_VertexMorph("え", "MouthE", 3, e_offsets))
    if o_offsets:
        morphs.append(_VertexMorph("お", "MouthO", 3, o_offsets))
    if smile_offsets:
        morphs.append(_VertexMorph("笑い", "Smile", 3, smile_offsets))
    return morphs


def _chain_vertex_weights(point, dynamic):
    chain = dynamic_chain(dynamic)
    if not chain:
        return []
    if len(chain) == 1:
        return [VertexWeight(chain[0]["name"], 1.0)]
    root = dynamic.root_position
    tail = dynamic.tail_position
    axis = tuple(tail[i] - root[i] for i in range(3))
    denominator = sum(value * value for value in axis)
    if denominator <= 1e-12:
        return [VertexWeight(chain[0]["name"], 1.0)]
    relative = tuple(point[i] - root[i] for i in range(3))
    t = max(0.0, min(1.0, sum(relative[i] * axis[i] for i in range(3)) / denominator))
    scaled = t * (len(chain) - 1)
    left = min(int(scaled), len(chain) - 1)
    right = min(left + 1, len(chain) - 1)
    if left == right:
        return [VertexWeight(chain[left]["name"], 1.0)]
    blend = scaled - left
    return [
        VertexWeight(chain[left]["name"], 1.0 - blend),
        VertexWeight(chain[right]["name"], blend),
    ]


def _physics(features, bones):
    if not features:
        return [], []
    bone_positions = {bone.name: bone.position for bone in bones}
    rigid = []
    joints = []
    anchors = {}
    for dynamic in features.dynamics:
        chain = dynamic_chain(dynamic)
        if not chain:
            continue
        parent = dynamic.parent_bone
        if parent not in anchors:
            name = f"rackAnchor_{parent}"
            anchors[parent] = name
            rigid.append(
                _RigidBody(
                    name,
                    parent,
                    (0.04, 0.04, 0.04),
                    bone_positions.get(parent, dynamic.root_position),
                    0,
                    0.0,
                    1.0,
                    1.0,
                    0,
                    0xFFFF,
                )
            )
        previous = anchors[parent]
        segment_count = max(len(chain), 1)
        for index, segment in enumerate(chain):
            body = f"rackBody_{dynamic.group}_{index + 1:02d}"
            half = tuple(
                max(min(float(value) * 0.12 / segment_count, 0.22), 0.025)
                for value in dynamic.size
            )
            volume = max(dynamic.size[0] * dynamic.size[1] * dynamic.size[2], 0.001)
            mass = max(0.03, min(volume * 0.025 / segment_count, 0.35))
            rigid.append(
                _RigidBody(
                    body,
                    segment["name"],
                    half,
                    tuple(segment["position"]),
                    1,
                    mass,
                    max(dynamic.drag_force, 0.65),
                    max(min(dynamic.drag_force + 0.2, 0.95), 0.75),
                    1,
                    0xFFFF,
                )
            )
            joints.append(
                _Joint(
                    f"rackJoint_{dynamic.group}_{index + 1:02d}",
                    previous,
                    body,
                    tuple(segment["position"]),
                    min(dynamic.angular_limit * 0.45, 0.28),
                    12.0 + 30.0 * dynamic.stiffness,
                )
            )
            previous = body
    return rigid, joints


def _write_weight(blob, bone_index, values):
    values = [value for value in values if value.bone in bone_index]
    if len(values) <= 1:
        bone = bone_index.get(values[0].bone if values else "spine", 0)
        blob += struct.pack("<Bi", 0, bone)
    elif len(values) == 2:
        first, second = values
        blob += struct.pack("<Bii", 1, bone_index[first.bone], bone_index[second.bone]) + struct.pack("<f", first.weight)
    else:
        values = values[:4]
        while len(values) < 4:
            values.append(VertexWeight(values[0].bone, 0.0))
        total = sum(value.weight for value in values) or 1.0
        blob += struct.pack("<B", 2)
        for value in values:
            blob += struct.pack("<i", bone_index[value.bone])
        for value in values:
            blob += struct.pack("<f", value.weight / total)
    return blob


def _geometry_only_textured_materials(features: FeaturePlan | None) -> bool:
    if not features:
        return False
    if any(
        getattr(item, "accessory_type", "") == "GeometryOnly"
        for item in features.layered_clothing
    ):
        return True
    return any(
        dynamic.name in {"Shark tail", "Heart hair / cowlick"}
        for dynamic in features.dynamics
    )


def _pmx_diffuse(material: Material, *, neutralize_textured: bool = False):
    if neutralize_textured and material.map_kd:
        return (1.0, 1.0, 1.0)
    return material.kd


def write_pmx(
    output: Path,
    *,
    model_name: str,
    mesh: ObjMesh,
    materials: dict[str, Material],
    bones: list[Bone],
    group_to_bone: dict[str, str],
    smooth_weights: bool = True,
    features: FeaturePlan | None = None,
    accessory_physics: bool = True,
):
    mapping = dict(group_to_bone)
    pmx_bones = _pmx_bones(bones, features, mesh=mesh, group_to_bone=mapping)
    bone_index = {bone.name: index for index, bone in enumerate(pmx_bones)}
    spring = {
        dynamic.group: dynamic
        for dynamic in (features.dynamics if features and accessory_physics else ())
        if dynamic.physics_mode == "spring"
    }
    planar = _planar_uv_flip_groups(mesh)
    neutralize_textured = _geometry_only_textured_materials(features)
    face_regions = _analyze_face_regions(mesh, mapping)
    hide_mouth = bool(
        neutralize_textured and face_regions is not None and len(face_regions.mouth) >= 12
    )

    textures = []
    for material in materials.values():
        if material.map_kd and material.map_kd not in textures:
            textures.append(material.map_kd)
    texture_index = {name: index for index, name in enumerate(textures)}

    weights = compute_group_vertex_weights(mesh, bones, mapping, smooth=smooth_weights)
    layered = {
        item.group: item for item in (features.layered_clothing if features else ())
    }
    layered_groups = set(layered)
    for group, item in layered.items():
        for index in mesh.group_vertex_indices().get(group, ()):
            weights[(group, index)] = weights_for_layered_point(
                mesh.vertices[index], bones, profile=item.profile
            )
    for group, dynamic in spring.items():
        for index in mesh.group_vertex_indices().get(group, ()):
            weights[(group, index)] = _chain_vertex_weights(mesh.vertices[index], dynamic)

    vertex_map = {}
    out_vertices = []
    source_to_pmx = defaultdict(list)
    indices_by_material = defaultdict(list)
    for face in mesh.faces:
        face_indices = []
        for vertex_index, uv_index, normal_index in face.corners:
            key = (vertex_index, uv_index, normal_index, face.group)
            if key not in vertex_map:
                source_point = mesh.vertices[vertex_index]
                if (
                    hide_mouth
                    and face_regions is not None
                    and face.group == face_regions.group
                    and vertex_index in face_regions.mouth
                ):
                    source_point = (
                        source_point[0],
                        source_point[1],
                        source_point[2] + face_regions.hide_depth,
                    )
                position = _mmd_vec3(source_point)
                uv = (
                    _mmd_uv(mesh.uvs[uv_index], flip_u=face.group in planar)
                    if uv_index is not None and 0 <= uv_index < len(mesh.uvs)
                    else (0.0, 0.0)
                )
                normal = (
                    _mmd_vec3(mesh.normals[normal_index])
                    if normal_index is not None and 0 <= normal_index < len(mesh.normals)
                    else (0.0, 1.0, 0.0)
                )
                vertex_weights = weights.get((face.group, vertex_index)) or []
                vertex_map[key] = len(out_vertices)
                out_vertices.append((position, normal, uv, vertex_weights))
                source_to_pmx[(face.group, vertex_index)].append(vertex_map[key])
            face_indices.append(vertex_map[key])
        indices_by_material[face.material].extend(reversed(face_indices))

    material_order = list(dict.fromkeys(face.material for face in mesh.faces))
    vertex_morphs = _reconstructed_face_morphs(
        mesh,
        mapping,
        source_to_pmx,
        regions=face_regions,
        mouth_hidden_at_neutral=hide_mouth,
    )
    bone_morphs = _eye_morphs(features)
    morphs = vertex_morphs + bone_morphs
    rigid, joints = _physics(features if accessory_physics else None, pmx_bones)
    rigid_index = {body.name: index for index, body in enumerate(rigid)}

    blob = bytearray(b"PMX ")
    blob += struct.pack("<fB", 2.0, 8) + bytes([0, 0, 4, 4, 4, 4, 4, 4])
    comment = (
        "Generated by Roblox Avatar Conversion Kit v0.3.11. "
        "Skin weights, facial morphs, helper bones and accessory physics are reconstructed and approximate."
    )
    blob += _text(model_name) + _text(model_name) + _text(comment) + _text(comment)

    blob += struct.pack("<i", len(out_vertices))
    counts = defaultdict(int)
    for position, normal, uv, vertex_weights in out_vertices:
        blob += _vec3(position) + _vec3(normal) + _vec2(uv)
        blob = _write_weight(blob, bone_index, vertex_weights)
        counts[min(max(len(vertex_weights), 1), 4)] += 1
        blob += struct.pack("<f", 1.0)

    flat_indices = [
        index
        for material_name in material_order
        for index in indices_by_material[material_name]
    ]
    blob += struct.pack("<i", len(flat_indices))
    for index in flat_indices:
        blob += struct.pack("<I", index)

    blob += struct.pack("<i", len(textures))
    for texture in textures:
        blob += _text(texture)

    blob += struct.pack("<i", len(material_order))
    for number, material_name in enumerate(material_order):
        material = materials.get(material_name or "") or Material(
            material_name or f"Material{number + 1}"
        )
        diffuse = _pmx_diffuse(material, neutralize_textured=neutralize_textured)
        blob += (
            _text(material.name)
            + _text(material.name)
            + _vec4((*diffuse, material.alpha))
            + _vec3(material.ks)
            + struct.pack("<f", max(0.0, material.ns))
            + _vec3(tuple(channel * 0.35 for channel in diffuse))
            + struct.pack("<B", 0x0F)
            + _vec4((0.0, 0.0, 0.0, 1.0))
            + struct.pack("<f", 0.0)
            + struct.pack(
                "<iiBBB",
                texture_index.get(material.map_kd, -1),
                -1,
                0,
                1,
                0,
            )
            + _text("")
            + struct.pack("<i", len(indices_by_material[material_name]))
        )

    blob += struct.pack("<i", len(pmx_bones))
    movable_names = {"allParent", "center", "groove"}
    for bone in pmx_bones:
        parent = bone_index.get(bone.parent, -1) if bone.parent else -1
        blob += (
            _text(MMD_JP.get(bone.name, bone.name))
            + _text(bone.name)
            + _vec3(_mmd_vec3(bone.position))
            + struct.pack("<ii", parent, 0)
        )
        flags = 0x001A
        if bone.movable or bone.name in movable_names:
            flags |= 0x0004
        if bone.ik_target:
            flags |= 0x0020 | 0x0004
        blob += struct.pack("<H", flags) + _vec3((0.0, 0.1, 0.0))
        if bone.ik_target:
            blob += struct.pack(
                "<iif",
                bone_index[bone.ik_target],
                bone.ik_iterations,
                bone.ik_weight,
            ) + struct.pack("<i", len(bone.ik_links))
            for link in bone.ik_links:
                blob += struct.pack("<iB", bone_index[link], 0)

    blob += struct.pack("<i", len(morphs))
    for morph in morphs:
        if isinstance(morph, _VertexMorph):
            blob += _text(morph.name_jp) + _text(morph.name_en) + struct.pack(
                "<BBi", morph.panel, 1, len(morph.offsets)
            )
            for vertex_index, delta in morph.offsets:
                blob += struct.pack("<I", vertex_index) + _vec3(delta)
        else:
            blob += _text(morph.name_jp) + _text(morph.name_en) + struct.pack(
                "<BBi", 2, 2, 1
            )
            blob += (
                struct.pack("<i", bone_index[morph.bone_name])
                + _vec3((0.0, 0.0, 0.0))
                + _vec4(morph.rotation)
            )

    root_bones = [
        name for name in ("allParent", "center", "groove") if name in bone_index
    ]
    frames = [
        ("Root", "Root", 1, [(0, bone_index[name]) for name in root_bones])
    ]
    body_bones = [
        name
        for name in ("hips", "spine", "chest", "neck", "head")
        if name in bone_index
    ]
    if body_bones:
        frames.append(("体", "Body", 0, [(0, bone_index[name]) for name in body_bones]))
    if morphs:
        frames.append(("表情", "Expressions", 1, [(1, index) for index in range(len(morphs))]))
    face_bones = [
        name for name in ("head", "eyes", "leftEye", "rightEye") if name in bone_index
    ]
    if face_bones:
        frames.append(("顔", "Face", 0, [(0, bone_index[name]) for name in face_bones]))
    ik_bones = [
        name
        for name in ("leftLegIK", "rightLegIK", "leftToeIK", "rightToeIK")
        if name in bone_index
    ]
    if ik_bones:
        frames.append(("ＩＫ", "IK", 0, [(0, bone_index[name]) for name in ik_bones]))
    physics_bones = [
        segment["name"]
        for dynamic in (features.dynamics if features and accessory_physics else ())
        for segment in dynamic_chain(dynamic)
        if segment["name"] in bone_index
    ]
    if physics_bones:
        frames.append(("物理", "Physics", 0, [(0, bone_index[name]) for name in physics_bones]))

    blob += struct.pack("<i", len(frames))
    for local_name, english_name, special, elements in frames:
        blob += _text(local_name) + _text(english_name) + struct.pack(
            "<Bi", special, len(elements)
        )
        for element_type, index in elements:
            blob += struct.pack("<Bi", element_type, index)

    blob += struct.pack("<i", len(rigid))
    for body in rigid:
        blob += (
            _text(body.name)
            + _text(body.name)
            + struct.pack(
                "<iBH",
                bone_index.get(body.bone_name, -1),
                body.group,
                body.collision_mask,
            )
            + struct.pack("<B", 1)
            + _vec3(body.shape_size)
            + _vec3(_mmd_vec3(body.position))
            + _vec3((0.0, 0.0, 0.0))
            + struct.pack(
                "<fffffB",
                body.mass,
                body.linear_damping,
                body.angular_damping,
                0.0,
                0.5,
                body.operation,
            )
        )

    blob += struct.pack("<i", len(joints))
    for joint in joints:
        limit = joint.angular_limit
        blob += (
            _text(joint.name)
            + _text(joint.name)
            + struct.pack(
                "<Bii",
                0,
                rigid_index[joint.rigid_a],
                rigid_index[joint.rigid_b],
            )
            + _vec3(_mmd_vec3(joint.position))
            + _vec3((0.0, 0.0, 0.0))
            + _vec3((0.0, 0.0, 0.0))
            + _vec3((0.0, 0.0, 0.0))
            + _vec3((-limit, -limit * 0.55, -limit))
            + _vec3((limit, limit * 0.55, limit))
            + _vec3((0.0, 0.0, 0.0))
            + _vec3((joint.spring, joint.spring * 0.6, joint.spring))
        )

    Path(output).write_bytes(blob)
    semistandard = [
        name
        for name in (
            "allParent",
            "groove",
            "leftShoulderP",
            "rightShoulderP",
            "leftShoulder",
            "rightShoulder",
            "leftArmTwist",
            "rightArmTwist",
            "leftWristTwist",
            "rightWristTwist",
            "leftToe",
            "rightToe",
            "leftToeIK",
            "rightToeIK",
        )
        if name in bone_index
    ]
    return {
        "vertices": len(out_vertices),
        "triangles": len(flat_indices) // 3,
        "materials": len(material_order),
        "textures": len(textures),
        "bones": len(pmx_bones),
        "ik_bones": sum(1 for bone in pmx_bones if bone.ik_target),
        "toe_ik_bones": sum(1 for side in ("left", "right") if f"{side}ToeIK" in bone_index),
        "semistandard_motion_bones": len(semistandard),
        "motion_compat_profile": "classic-pmd-plus-semstandard-vmd",
        "gaze_morphs": len(bone_morphs),
        "reconstructed_face_morphs": len(vertex_morphs),
        "face_morph_group": face_regions.group if face_regions else None,
        "neutral_hidden_mouth_vertices": len(face_regions.mouth) if hide_mouth and face_regions else 0,
        "neutral_hidden_mouth_components": face_regions.mouth_components if hide_mouth and face_regions else 0,
        "dynamic_accessory_bones": len(physics_bones),
        "rigid_bodies": len(rigid),
        "physics_joints": len(joints),
        "spring_accessories": len(spring),
        "layered_clothing_groups": len(layered_groups),
        "planar_uv_flip_groups": len(planar),
        "weight_modes": dict(sorted(counts.items())),
        "source_weight_summary": summarize_weights(weights),
        "material_edges": "disabled",
        "texture_color_mode": "texture-neutral" if neutralize_textured else "mtl-tinted",
        "neutralized_textured_materials": sum(
            1
            for material in materials.values()
            if neutralize_textured and material.map_kd
        ),
        "text_encoding": "utf-16-le",
        "bytes": len(blob),
    }
