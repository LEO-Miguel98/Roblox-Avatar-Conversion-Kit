from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

from .obj import ObjMesh
from .rig import Bone


@dataclass(frozen=True)
class VertexWeight:
    bone: str
    weight: float


# Chibi / layered Roblox avatars are especially easy to over-smooth. These minimums keep each
# exported body-part mesh mostly on the bone it was spatially matched to while still allowing a
# small amount of joint blending. Head and extremities are intentionally much more rigid.
PRIMARY_WEIGHT_FLOORS = {
    "head": 0.97,
    "neck": 0.88,
    "leftHand": 0.92,
    "rightHand": 0.92,
    "leftFoot": 0.92,
    "rightFoot": 0.92,
    "hips": 0.74,
    "spine": 0.74,
    "chest": 0.76,
    "leftUpperArm": 0.72,
    "rightUpperArm": 0.72,
    "leftLowerArm": 0.72,
    "rightLowerArm": 0.72,
    "leftUpperLeg": 0.72,
    "rightUpperLeg": 0.72,
    "leftLowerLeg": 0.74,
    "rightLowerLeg": 0.74,
}
DEFAULT_PRIMARY_WEIGHT_FLOOR = 0.72


def _dist(a, b):
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _point_segment_distance(p, a, b):
    ab = tuple(b[i] - a[i] for i in range(3))
    ap = tuple(p[i] - a[i] for i in range(3))
    denom = sum(v * v for v in ab)
    if denom <= 1e-12:
        return _dist(p, a)
    t = max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / denom))
    q = tuple(a[i] + t * ab[i] for i in range(3))
    return _dist(p, q)


def _children(bones):
    out = defaultdict(list)
    for bone in bones:
        if bone.parent:
            out[bone.parent].append(bone.name)
    return out


def bone_segments(bones: list[Bone]):
    by_name = {bone.name: bone for bone in bones}
    children = _children(bones)
    out = {}
    for bone in bones:
        if children.get(bone.name):
            child = min(children[bone.name], key=lambda name: _dist(bone.position, by_name[name].position))
            out[bone.name] = (bone.position, by_name[child].position)
        elif bone.parent and bone.parent in by_name:
            parent = by_name[bone.parent].position
            direction = tuple(bone.position[i] - parent[i] for i in range(3))
            out[bone.name] = (bone.position, tuple(bone.position[i] + direction[i] * 0.35 for i in range(3)))
        else:
            out[bone.name] = (bone.position, (bone.position[0], bone.position[1] + 0.1, bone.position[2]))
    return out


def candidate_bones(primary: str, bones: list[Bone]) -> list[str]:
    by_name = {bone.name: bone for bone in bones}
    children = _children(bones)
    names = [primary]
    bone = by_name.get(primary)
    if bone and bone.parent:
        names.append(bone.parent)
    names.extend(children.get(primary, []))
    # v0.2 blended every torso bone against every other torso bone. That was too aggressive for
    # short/chibi avatars, so v0.3.2 intentionally limits candidates to the direct hierarchy.
    result = []
    for name in names:
        if name in by_name and name not in result:
            result.append(name)
    return result


def _enforce_primary_floor(values: list[VertexWeight], primary: str, floor: float) -> list[VertexWeight]:
    if not values:
        return [VertexWeight(primary, 1.0)]
    by_name = {value.bone: value.weight for value in values}
    current = by_name.get(primary, 0.0)
    if current >= floor:
        total = sum(by_name.values()) or 1.0
        return [VertexWeight(name, weight / total) for name, weight in by_name.items()]

    others = [(name, weight) for name, weight in by_name.items() if name != primary]
    other_total = sum(weight for _, weight in others)
    if other_total <= 1e-12:
        return [VertexWeight(primary, 1.0)]
    remainder = 1.0 - floor
    result = [VertexWeight(primary, floor)]
    result.extend(VertexWeight(name, remainder * weight / other_total) for name, weight in others)
    return result


def weights_for_point(point, primary, bones, *, max_influences=4, primary_floor: float | None = None):
    segments = bone_segments(bones)
    candidates = candidate_bones(primary, bones)
    if not candidates:
        return [VertexWeight(primary, 1.0)]

    scored = []
    for name in candidates:
        a, b = segments[name]
        length = max(_dist(a, b), 0.15)
        distance = _point_segment_distance(point, a, b)
        score = 1.0 / ((distance + 0.20 * length) ** 2)
        if name == primary:
            score *= 1.35
        scored.append((name, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    scored = scored[: max(1, max_influences)]
    if primary not in {name for name, _ in scored}:
        # The primary is always in candidates. Recompute its score only if a very unusual caller
        # uses max_influences smaller than the candidate count and it falls out of the top slice.
        a, b = segments[primary]
        length = max(_dist(a, b), 0.15)
        distance = _point_segment_distance(point, a, b)
        primary_score = 1.35 / ((distance + 0.20 * length) ** 2)
        if scored:
            scored[-1] = (primary, primary_score)
        else:
            scored = [(primary, primary_score)]

    total = sum(value for _, value in scored) or 1.0
    normalized = [VertexWeight(name, value / total) for name, value in scored]
    kept = [weight for weight in normalized if weight.weight >= 0.025 or weight.bone == primary]
    total = sum(weight.weight for weight in kept) or 1.0
    kept = [VertexWeight(weight.bone, weight.weight / total) for weight in kept]
    floor = PRIMARY_WEIGHT_FLOORS.get(primary, DEFAULT_PRIMARY_WEIGHT_FLOOR) if primary_floor is None else primary_floor
    return _enforce_primary_floor(kept, primary, max(0.0, min(float(floor), 1.0)))


LAYERED_PROFILE_BONES = {
    "upper_body": {"hips", "spine", "chest", "leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand"},
    "lower_body": {"hips", "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"},
    "legs": {"leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"},
    "hands": {"leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand"},
    "feet": {"leftLowerLeg", "leftFoot", "rightLowerLeg", "rightFoot"},
}

def weights_for_layered_point(point, bones: list[Bone], *, profile="upper_body", max_influences=4):
    # WrapLayer clothing should follow the body spatially rather than the single AccessoryWeld target.
    # Clothing profiles stop nearby but unrelated limbs (for example lowered hands beside shorts)
    # from stealing weights.
    allowed = LAYERED_PROFILE_BONES.get(profile, LAYERED_PROFILE_BONES["upper_body"])
    candidates = [bone for bone in bones if bone.name in allowed] or list(bones)
    if not candidates:
        return [VertexWeight("spine", 1.0)]
    primary = min(candidates, key=lambda bone: _dist(point, bone.position)).name
    floor = 0.62
    if primary in {"leftHand", "rightHand", "leftFoot", "rightFoot"}:
        floor = 0.78
    return weights_for_point(point, primary, bones, max_influences=max_influences, primary_floor=floor)


def compute_group_vertex_weights(mesh: ObjMesh, bones: list[Bone], group_to_bone: dict[str, str], *, smooth=True):
    out = {}
    for group, indices in mesh.group_vertex_indices().items():
        primary = group_to_bone.get(group, "spine")
        rigid = (not smooth) or (not group.lower().startswith("rig"))
        for index in indices:
            out[(group, index)] = (
                [VertexWeight(primary, 1.0)]
                if rigid
                else weights_for_point(mesh.vertices[index], primary, bones)
            )
    return out


def primary_weight_diagnostics(mesh: ObjMesh, weights, group_to_bone: dict[str, str]):
    result = {}
    for group, indices in mesh.group_vertex_indices().items():
        if not group.lower().startswith("rig"):
            continue
        primary = group_to_bone.get(group, "spine")
        values = []
        for index in indices:
            influence = weights.get((group, index), ())
            values.append(next((item.weight for item in influence if item.bone == primary), 0.0))
        if not values:
            continue
        result[group] = {
            "primary_bone": primary,
            "vertices": len(values),
            "min_primary_weight": round(min(values), 6),
            "average_primary_weight": round(sum(values) / len(values), 6),
            "below_50_percent": sum(value < 0.5 for value in values),
        }
    return result


def summarize_weights(weights):
    modes = defaultdict(int)
    max_count = 0
    for values in weights.values():
        count = len(values)
        max_count = max(max_count, count)
        modes[count] += 1
    return {
        "vertices": len(weights),
        "max_influences": max_count,
        "influence_counts": dict(sorted(modes.items())),
    }
