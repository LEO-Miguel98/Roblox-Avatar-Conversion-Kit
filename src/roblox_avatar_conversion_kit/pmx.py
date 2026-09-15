from __future__ import annotations

import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .obj import Material, ObjMesh
from .rig import Bone
from .weights import compute_group_vertex_weights, summarize_weights


def _text(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw


def _vec2(value):
    return struct.pack("<2f", *value)


def _vec3(value):
    return struct.pack("<3f", *value)


def _vec4(value):
    return struct.pack("<4f", *value)


def _mmd_vec3(value):
    return (value[0], value[1], -value[2])


MMD_JP = {
    "center": "センター",
    "hips": "下半身",
    "spine": "上半身",
    "chest": "上半身2",
    "neck": "首",
    "head": "頭",
    "leftUpperArm": "左腕",
    "leftLowerArm": "左ひじ",
    "leftHand": "左手首",
    "rightUpperArm": "右腕",
    "rightLowerArm": "右ひじ",
    "rightHand": "右手首",
    "leftUpperLeg": "左足",
    "leftLowerLeg": "左ひざ",
    "leftFoot": "左足首",
    "rightUpperLeg": "右足",
    "rightLowerLeg": "右ひざ",
    "rightFoot": "右足首",
    "leftLegIK": "左足ＩＫ",
    "rightLegIK": "右足ＩＫ",
}


@dataclass(frozen=True)
class _PmxBone:
    name: str
    parent: str | None
    position: tuple[float, float, float]
    ik_target: str | None = None
    ik_links: tuple[str, ...] = ()


def _pmx_bones(bones: list[Bone]) -> list[_PmxBone]:
    by_name = {bone.name: bone for bone in bones}
    hips = by_name.get("hips") or bones[0]
    result = [_PmxBone("center", None, hips.position)]
    for bone in bones:
        result.append(
            _PmxBone(
                bone.name,
                "center" if bone.name == "hips" else bone.parent,
                bone.position,
            )
        )

    for side in ("left", "right"):
        foot = f"{side}Foot"
        lower = f"{side}LowerLeg"
        upper = f"{side}UpperLeg"
        if foot in by_name and lower in by_name and upper in by_name:
            result.append(
                _PmxBone(
                    f"{side}LegIK",
                    "center",
                    by_name[foot].position,
                    foot,
                    (lower, upper),
                )
            )
    return result


def _write_weight(blob: bytearray, bone_index: dict[str, int], values) -> bytearray:
    values = [value for value in values if value.bone in bone_index]
    if len(values) <= 1:
        bone = bone_index.get(values[0].bone if values else "spine", 0)
        blob += struct.pack("<Bi", 0, bone)  # BDEF1
    elif len(values) == 2:
        first, second = values
        blob += struct.pack("<Bii", 1, bone_index[first.bone], bone_index[second.bone])  # BDEF2
        blob += struct.pack("<f", first.weight)
    else:
        values = values[:4]
        while len(values) < 4:
            values.append(type(values[0])(values[0].bone, 0.0))
        total = sum(value.weight for value in values) or 1.0
        blob += struct.pack("<B", 2)  # BDEF4
        for value in values:
            blob += struct.pack("<i", bone_index[value.bone])
        for value in values:
            blob += struct.pack("<f", value.weight / total)
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
) -> dict:
    pmx_bones = _pmx_bones(bones)
    bone_index = {bone.name: index for index, bone in enumerate(pmx_bones)}

    textures: list[str] = []
    for material in materials.values():
        if material.map_kd and material.map_kd not in textures:
            textures.append(material.map_kd)
    texture_index = {name: index for index, name in enumerate(textures)}

    source_weights = compute_group_vertex_weights(mesh, bones, group_to_bone, smooth=smooth_weights)
    vertex_map: dict[tuple, int] = {}
    out_vertices: list[tuple] = []
    indices_by_material: dict[str | None, list[int]] = defaultdict(list)

    for face in mesh.faces:
        face_indices: list[int] = []
        for vertex_index, uv_index, normal_index in face.corners:
            key = (vertex_index, uv_index, normal_index, face.group)
            if key not in vertex_map:
                position = _mmd_vec3(mesh.vertices[vertex_index])
                uv = mesh.uvs[uv_index] if uv_index is not None and 0 <= uv_index < len(mesh.uvs) else (0.0, 0.0)
                normal = (
                    _mmd_vec3(mesh.normals[normal_index])
                    if normal_index is not None and 0 <= normal_index < len(mesh.normals)
                    else (0.0, 1.0, 0.0)
                )
                weights = source_weights.get((face.group, vertex_index)) or []
                vertex_map[key] = len(out_vertices)
                out_vertices.append((position, normal, uv, weights))
            face_indices.append(vertex_map[key])
        indices_by_material[face.material].extend(reversed(face_indices))

    material_order = list(dict.fromkeys(face.material for face in mesh.faces))
    blob = bytearray()
    blob += b"PMX "
    blob += struct.pack("<f", 2.0)
    blob += struct.pack("<B", 8)
    blob += bytes([1, 0, 4, 4, 4, 4, 4, 4])
    comment = "Generated by Roblox Avatar Conversion Kit v0.2. Smooth weights are reconstructed and approximate."
    blob += _text(model_name) + _text(model_name) + _text(comment) + _text(comment)

    blob += struct.pack("<i", len(out_vertices))
    pmx_weight_counts = defaultdict(int)
    for position, normal, uv, weights in out_vertices:
        blob += _vec3(position) + _vec3(normal) + _vec2(uv)
        blob = _write_weight(blob, bone_index, weights)
        pmx_weight_counts[min(max(len(weights), 1), 4)] += 1
        blob += struct.pack("<f", 1.0)  # edge scale

    flat_indices = [index for material in material_order for index in indices_by_material[material]]
    blob += struct.pack("<i", len(flat_indices))
    for index in flat_indices:
        blob += struct.pack("<I", index)

    blob += struct.pack("<i", len(textures))
    for texture in textures:
        blob += _text(texture)

    blob += struct.pack("<i", len(material_order))
    for number, material_name in enumerate(material_order):
        material = materials.get(material_name or "") or Material(material_name or f"Material{number + 1}")
        blob += _text(material.name) + _text(material.name)
        blob += _vec4((*material.kd, material.alpha))
        blob += _vec3(material.ks)
        blob += struct.pack("<f", max(0.0, material.ns))
        blob += _vec3(tuple(channel * 0.5 for channel in material.kd))
        blob += struct.pack("<B", 0x1F)
        blob += _vec4((0.0, 0.0, 0.0, 1.0))
        blob += struct.pack("<f", 1.0)
        blob += struct.pack("<i", texture_index.get(material.map_kd, -1))
        blob += struct.pack("<i", -1)
        blob += struct.pack("<B", 0)
        blob += struct.pack("<B", 1)
        blob += struct.pack("<B", 0)
        blob += _text("")
        blob += struct.pack("<i", len(indices_by_material[material_name]))

    blob += struct.pack("<i", len(pmx_bones))
    for bone in pmx_bones:
        parent = bone_index.get(bone.parent, -1) if bone.parent else -1
        blob += _text(MMD_JP.get(bone.name, bone.name)) + _text(bone.name)
        blob += _vec3(_mmd_vec3(bone.position))
        blob += struct.pack("<i", parent)
        blob += struct.pack("<i", 0)
        flags = 0x001A
        if bone.name == "center":
            flags |= 0x0004
        if bone.ik_target:
            flags |= 0x0020 | 0x0004
        blob += struct.pack("<H", flags)
        blob += _vec3((0.0, 0.1, 0.0))
        if bone.ik_target:
            blob += struct.pack("<iif", bone_index[bone.ik_target], 40, 0.5)
            blob += struct.pack("<i", len(bone.ik_links))
            for link in bone.ik_links:
                blob += struct.pack("<iB", bone_index[link], 0)

    # Morphs, display frames, rigid bodies, joints. Physics/morph generation comes later.
    blob += struct.pack("<iiii", 0, 0, 0, 0)

    Path(output).write_bytes(blob)
    return {
        "vertices": len(out_vertices),
        "triangles": len(flat_indices) // 3,
        "materials": len(material_order),
        "textures": len(textures),
        "bones": len(pmx_bones),
        "ik_bones": sum(1 for bone in pmx_bones if bone.ik_target),
        "weight_modes": dict(sorted(pmx_weight_counts.items())),
        "source_weight_summary": summarize_weights(source_weights),
        "bytes": len(blob),
    }
