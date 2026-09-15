from __future__ import annotations

import math
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .features import FeaturePlan, dynamic_chain
from .obj import Material, ObjMesh
from .rig import Bone
from .weights import VertexWeight, compute_group_vertex_weights, summarize_weights, weights_for_layered_point


def _text(value: str) -> bytes:
    raw = value.encode("utf-16-le")
    return struct.pack("<i", len(raw)) + raw


def _vec2(value): return struct.pack("<2f", *value)
def _vec3(value): return struct.pack("<3f", *value)
def _vec4(value): return struct.pack("<4f", *value)
def _mmd_vec3(value): return (value[0], value[1], -value[2])

MMD_JP = {
    "center": "センター", "hips": "下半身", "spine": "上半身", "chest": "上半身2",
    "neck": "首", "head": "頭", "eyes": "両目", "leftEye": "左目", "rightEye": "右目",
    "leftUpperArm": "左腕", "leftLowerArm": "左ひじ", "leftHand": "左手首",
    "rightUpperArm": "右腕", "rightLowerArm": "右ひじ", "rightHand": "右手首",
    "leftUpperLeg": "左足", "leftLowerLeg": "左ひざ", "leftFoot": "左足首",
    "rightUpperLeg": "右足", "rightLowerLeg": "右ひざ", "rightFoot": "右足首",
    "leftLegIK": "左足ＩＫ", "rightLegIK": "右足ＩＫ",
}

@dataclass(frozen=True)
class _PmxBone:
    name: str
    parent: str | None
    position: tuple[float, float, float]
    ik_target: str | None = None
    ik_links: tuple[str, ...] = ()

@dataclass(frozen=True)
class _BoneMorph:
    name_jp: str
    name_en: str
    bone_name: str
    rotation: tuple[float, float, float, float]

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


def _quat_axis_angle(axis: tuple[float, float, float], angle: float):
    half = angle / 2.0
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def _pmx_bones(bones: list[Bone], features: FeaturePlan | None) -> list[_PmxBone]:
    by_name = {bone.name: bone for bone in bones}
    hips = by_name.get("hips") or bones[0]
    result = [_PmxBone("center", None, hips.position)]
    for bone in bones:
        result.append(_PmxBone(bone.name, "center" if bone.name == "hips" else bone.parent, bone.position))

    if features and features.eyes:
        eye = features.eyes
        result.extend([
            _PmxBone("eyes", "head", eye.master_position),
            _PmxBone("leftEye", "eyes", eye.left_position),
            _PmxBone("rightEye", "eyes", eye.right_position),
        ])

    if features:
        for dynamic in features.dynamics:
            for segment in dynamic_chain(dynamic):
                result.append(_PmxBone(segment["name"], segment["parent"], tuple(segment["position"])))

    for side in ("left", "right"):
        foot, lower, upper = f"{side}Foot", f"{side}LowerLeg", f"{side}UpperLeg"
        if foot in by_name and lower in by_name and upper in by_name:
            result.append(_PmxBone(f"{side}LegIK", "center", by_name[foot].position, foot, (lower, upper)))
    return result


def _eye_morphs(features: FeaturePlan | None) -> list[_BoneMorph]:
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


def _chain_vertex_weights(point, dynamic) -> list[VertexWeight]:
    chain = dynamic_chain(dynamic)
    if not chain:
        return []
    if len(chain) == 1:
        return [VertexWeight(chain[0]["name"], 1.0)]
    root = dynamic.root_position
    tail = dynamic.tail_position
    axis = tuple(tail[i] - root[i] for i in range(3))
    denom = sum(value * value for value in axis)
    if denom <= 1e-12:
        return [VertexWeight(chain[0]["name"], 1.0)]
    rel = tuple(point[i] - root[i] for i in range(3))
    t = max(0.0, min(1.0, sum(rel[i] * axis[i] for i in range(3)) / denom))
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


def _physics(features: FeaturePlan | None, bones: list[_PmxBone]):
    if not features:
        return [], []
    bone_positions = {bone.name: bone.position for bone in bones}
    rigid: list[_RigidBody] = []
    joints: list[_Joint] = []
    anchors = {}
    for dynamic in features.dynamics:
        chain = dynamic_chain(dynamic)
        if not chain:
            continue
        parent = dynamic.parent_bone
        if parent not in anchors:
            anchor_name = f"rackAnchor_{parent}"
            anchors[parent] = anchor_name
            rigid.append(_RigidBody(
                name=anchor_name,
                bone_name=parent,
                shape_size=(0.04, 0.04, 0.04),
                position=bone_positions.get(parent, dynamic.root_position),
                operation=0,
                mass=0.0,
                linear_damping=1.0,
                angular_damping=1.0,
                group=0,
                collision_mask=0xFFFF,
            ))
        previous_body = anchors[parent]
        segment_count = max(len(chain), 1)
        for index, segment in enumerate(chain):
            body_name = f"rackBody_{dynamic.group}_{index + 1:02d}"
            # Conservative half-extents plus collision masking prevent overlapping generated
            # accessories from exploding apart when MMD enables physics on frame 1.
            half = tuple(max(min(float(v) * 0.12 / segment_count, 0.22), 0.025) for v in dynamic.size)
            volume = max(dynamic.size[0] * dynamic.size[1] * dynamic.size[2], 0.001)
            mass = max(0.03, min(volume * 0.025 / segment_count, 0.35))
            rigid.append(_RigidBody(
                name=body_name,
                bone_name=segment["name"],
                shape_size=half,
                position=tuple(segment["position"]),
                operation=1,
                mass=mass,
                linear_damping=max(dynamic.drag_force, 0.65),
                angular_damping=max(min(dynamic.drag_force + 0.2, 0.95), 0.75),
                group=1,
                collision_mask=0xFFFF,
            ))
            joints.append(_Joint(
                name=f"rackJoint_{dynamic.group}_{index + 1:02d}",
                rigid_a=previous_body,
                rigid_b=body_name,
                position=tuple(segment["position"]),
                angular_limit=min(dynamic.angular_limit * 0.45, 0.28),
                spring=12.0 + 30.0 * dynamic.stiffness,
            ))
            previous_body = body_name
    return rigid, joints


def _write_weight(blob: bytearray, bone_index: dict[str, int], values) -> bytearray:
    values = [value for value in values if value.bone in bone_index]
    if len(values) <= 1:
        bone = bone_index.get(values[0].bone if values else "spine", 0)
        blob += struct.pack("<Bi", 0, bone)
    elif len(values) == 2:
        first, second = values
        blob += struct.pack("<Bii", 1, bone_index[first.bone], bone_index[second.bone])
        blob += struct.pack("<f", first.weight)
    else:
        values = values[:4]
        while len(values) < 4:
            values.append(type(values[0])(values[0].bone, 0.0))
        total = sum(value.weight for value in values) or 1.0
        blob += struct.pack("<B", 2)
        for value in values: blob += struct.pack("<i", bone_index[value.bone])
        for value in values: blob += struct.pack("<f", value.weight / total)
    return blob


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
) -> dict:
    pmx_bones = _pmx_bones(bones, features)
    bone_index = {bone.name: index for index, bone in enumerate(pmx_bones)}
    effective_mapping = dict(group_to_bone)
    spring_dynamics = {
        dynamic.group: dynamic
        for dynamic in (features.dynamics if features and accessory_physics else ())
        if dynamic.physics_mode == "spring"
    }

    textures: list[str] = []
    for material in materials.values():
        if material.map_kd and material.map_kd not in textures: textures.append(material.map_kd)
    texture_index = {name: index for index, name in enumerate(textures)}

    source_weights = compute_group_vertex_weights(mesh, bones, effective_mapping, smooth=smooth_weights)
    layered_items = {item.group: item for item in (features.layered_clothing if features else ())}
    layered_groups = set(layered_items)
    for group, item in layered_items.items():
        for index in mesh.group_vertex_indices().get(group, ()):
            source_weights[(group, index)] = weights_for_layered_point(mesh.vertices[index], bones, profile=item.profile)
    # Only explicitly safe spring candidates get secondary-motion weights. Silhouette-defining
    # hair shells, bangs, ears, swords and face props remain rigid on their weld target.
    for group, dynamic in spring_dynamics.items():
        for index in mesh.group_vertex_indices().get(group, ()):
            source_weights[(group, index)] = _chain_vertex_weights(mesh.vertices[index], dynamic)
    vertex_map = {}; out_vertices = []; indices_by_material = defaultdict(list)
    for face in mesh.faces:
        face_indices = []
        for vertex_index, uv_index, normal_index in face.corners:
            key = (vertex_index, uv_index, normal_index, face.group)
            if key not in vertex_map:
                position = _mmd_vec3(mesh.vertices[vertex_index])
                uv = mesh.uvs[uv_index] if uv_index is not None and 0 <= uv_index < len(mesh.uvs) else (0.0, 0.0)
                normal = _mmd_vec3(mesh.normals[normal_index]) if normal_index is not None and 0 <= normal_index < len(mesh.normals) else (0.0, 1.0, 0.0)
                weights = source_weights.get((face.group, vertex_index)) or []
                vertex_map[key] = len(out_vertices); out_vertices.append((position, normal, uv, weights))
            face_indices.append(vertex_map[key])
        indices_by_material[face.material].extend(reversed(face_indices))

    material_order = list(dict.fromkeys(face.material for face in mesh.faces))
    morphs = _eye_morphs(features)
    rigid_bodies, joints = _physics(features if accessory_physics else None, pmx_bones)
    rigid_index = {body.name: i for i, body in enumerate(rigid_bodies)}

    blob = bytearray(b"PMX ")
    blob += struct.pack("<fB", 2.0, 8)
    blob += bytes([0, 0, 4, 4, 4, 4, 4, 4])
    comment = "Generated by Roblox Avatar Conversion Kit v0.3.2. Skin weights and accessory physics are reconstructed and approximate."
    blob += _text(model_name) + _text(model_name) + _text(comment) + _text(comment)

    blob += struct.pack("<i", len(out_vertices))
    pmx_weight_counts = defaultdict(int)
    for position, normal, uv, weights in out_vertices:
        blob += _vec3(position) + _vec3(normal) + _vec2(uv)
        blob = _write_weight(blob, bone_index, weights)
        pmx_weight_counts[min(max(len(weights), 1), 4)] += 1
        blob += struct.pack("<f", 1.0)

    flat_indices = [index for material in material_order for index in indices_by_material[material]]
    blob += struct.pack("<i", len(flat_indices))
    for index in flat_indices: blob += struct.pack("<I", index)

    blob += struct.pack("<i", len(textures))
    for texture in textures: blob += _text(texture)

    blob += struct.pack("<i", len(material_order))
    for number, material_name in enumerate(material_order):
        material = materials.get(material_name or "") or Material(material_name or f"Material{number + 1}")
        blob += _text(material.name) + _text(material.name)
        blob += _vec4((*material.kd, material.alpha)) + _vec3(material.ks) + struct.pack("<f", max(0.0, material.ns))
        blob += _vec3(tuple(channel * 0.35 for channel in material.kd)) + struct.pack("<B", 0x0F)
        blob += _vec4((0.0, 0.0, 0.0, 1.0)) + struct.pack("<f", 0.0)
        blob += struct.pack("<iiBBB", texture_index.get(material.map_kd, -1), -1, 0, 1, 0)
        blob += _text("") + struct.pack("<i", len(indices_by_material[material_name]))

    blob += struct.pack("<i", len(pmx_bones))
    for bone in pmx_bones:
        parent = bone_index.get(bone.parent, -1) if bone.parent else -1
        blob += _text(MMD_JP.get(bone.name, bone.name)) + _text(bone.name)
        blob += _vec3(_mmd_vec3(bone.position)) + struct.pack("<ii", parent, 0)
        flags = 0x001A
        if bone.name == "center": flags |= 0x0004
        if bone.ik_target: flags |= 0x0020 | 0x0004
        blob += struct.pack("<H", flags) + _vec3((0.0, 0.1, 0.0))
        if bone.ik_target:
            blob += struct.pack("<iif", bone_index[bone.ik_target], 40, 0.5)
            blob += struct.pack("<i", len(bone.ik_links))
            for link in bone.ik_links: blob += struct.pack("<iB", bone_index[link], 0)

    # Bone morphs: functional gaze controls even when source OBJ has no blend-shape deltas.
    blob += struct.pack("<i", len(morphs))
    for morph in morphs:
        blob += _text(morph.name_jp) + _text(morph.name_en)
        blob += struct.pack("<BBi", 2, 2, 1)  # Eye panel, bone morph, one offset
        blob += struct.pack("<i", bone_index[morph.bone_name])
        blob += _vec3((0.0, 0.0, 0.0)) + _vec4(morph.rotation)

    # Display frames: root, facial/gaze controls, and generated physics bones.
    frames = []
    frames.append(("Root", "Root", 1, [(0, bone_index["center"])]))
    if morphs:
        frames.append(("表情", "Expressions", 1, [(1, i) for i in range(len(morphs))]))
    face_bones = [name for name in ("head", "eyes", "leftEye", "rightEye") if name in bone_index]
    if face_bones:
        frames.append(("顔", "Face", 0, [(0, bone_index[name]) for name in face_bones]))
    physics_bones = [segment["name"] for d in (features.dynamics if features and accessory_physics else ()) for segment in dynamic_chain(d) if segment["name"] in bone_index]
    if physics_bones:
        frames.append(("物理", "Physics", 0, [(0, bone_index[name]) for name in physics_bones]))
    blob += struct.pack("<i", len(frames))
    for local_name, en_name, special, elements in frames:
        blob += _text(local_name) + _text(en_name) + struct.pack("<Bi", special, len(elements))
        for target_type, target_index in elements:
            blob += struct.pack("<Bi", target_type, target_index)

    blob += struct.pack("<i", len(rigid_bodies))
    for body in rigid_bodies:
        blob += _text(body.name) + _text(body.name)
        blob += struct.pack("<iBH", bone_index.get(body.bone_name, -1), body.group, body.collision_mask)
        blob += struct.pack("<B", 1)  # box
        blob += _vec3(body.shape_size) + _vec3(_mmd_vec3(body.position)) + _vec3((0.0, 0.0, 0.0))
        blob += struct.pack("<fffffB", body.mass, body.linear_damping, body.angular_damping, 0.0, 0.5, body.operation)

    blob += struct.pack("<i", len(joints))
    for joint in joints:
        limit = joint.angular_limit
        blob += _text(joint.name) + _text(joint.name) + struct.pack("<Bii", 0, rigid_index[joint.rigid_a], rigid_index[joint.rigid_b])
        blob += _vec3(_mmd_vec3(joint.position)) + _vec3((0.0, 0.0, 0.0))
        blob += _vec3((0.0, 0.0, 0.0)) + _vec3((0.0, 0.0, 0.0))
        blob += _vec3((-limit, -limit * 0.55, -limit)) + _vec3((limit, limit * 0.55, limit))
        blob += _vec3((0.0, 0.0, 0.0)) + _vec3((joint.spring, joint.spring * 0.6, joint.spring))

    Path(output).write_bytes(blob)
    return {
        "vertices": len(out_vertices), "triangles": len(flat_indices) // 3,
        "materials": len(material_order), "textures": len(textures), "bones": len(pmx_bones),
        "ik_bones": sum(1 for bone in pmx_bones if bone.ik_target), "gaze_morphs": len(morphs),
        "dynamic_accessory_bones": len(physics_bones), "rigid_bodies": len(rigid_bodies), "physics_joints": len(joints),
        "spring_accessories": len(spring_dynamics),
        "rigid_preserved_accessories": sum(1 for d in (features.dynamics if features else ()) if d.physics_mode != "spring"),
        "layered_clothing_groups": len(layered_groups),
        "weight_modes": dict(sorted(pmx_weight_counts.items())), "source_weight_summary": summarize_weights(source_weights),
        "material_edges": "disabled", "text_encoding": "utf-16-le", "bytes": len(blob),
    }
