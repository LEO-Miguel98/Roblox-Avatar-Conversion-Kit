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


def _point_segment_projection(p, a, b):
    ab = tuple(b[i] - a[i] for i in range(3))
    ap = tuple(p[i] - a[i] for i in range(3))
    denom = sum(v * v for v in ab)
    if denom <= 1e-12:
        return _dist(p, a), 0.0
    t = max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / denom))
    q = tuple(a[i] + t * ab[i] for i in range(3))
    return _dist(p, q), t


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
    "upper_garment": {"hips", "spine", "chest", "leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand"},
    "lower_body": {"hips", "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"},
    "legs": {"leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"},
    "hands": {"leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand"},
    "feet": {"leftLowerLeg", "leftFoot", "rightLowerLeg", "rightFoot"},
}


def _normalize_weight_map(values: dict[str, float], *, max_influences=4) -> list[VertexWeight]:
    kept = [(bone, max(float(weight), 0.0)) for bone, weight in values.items() if weight > 1e-8]
    kept.sort(key=lambda item: item[1], reverse=True)
    kept = kept[: max(1, max_influences)]
    total = sum(weight for _, weight in kept) or 1.0
    return [VertexWeight(bone, weight / total) for bone, weight in kept]


def _upper_garment_torso_weights(point, by_name: dict[str, Bone]) -> dict[str, float]:
    hips = by_name["hips"].position
    spine = by_name["spine"].position
    chest = by_name["chest"].position
    y = point[1]
    if y <= spine[1]:
        span = max(spine[1] - hips[1], 1e-6)
        t = max(0.0, min(1.0, (y - hips[1]) / span))
        return {"hips": 1.0 - t, "spine": t}
    span = max(chest[1] - spine[1], 1e-6)
    t = max(0.0, min(1.0, (y - spine[1]) / span))
    return {"spine": 1.0 - t, "chest": t}


def _upper_garment_sleeve_weights(point, side: str, by_name: dict[str, Bone]) -> dict[str, float]:
    upper_name = f"{side}UpperArm"
    lower_name = f"{side}LowerArm"
    hand_name = f"{side}Hand"
    upper = by_name[upper_name].position
    lower = by_name[lower_name].position
    hand = by_name[hand_name].position

    first_distance, first_t = _point_segment_projection(point, upper, lower)
    second_distance, second_t = _point_segment_projection(point, lower, hand)
    if first_distance <= second_distance:
        # At the shoulder seam, keep a little chest influence so the jacket does not split from the
        # torso when the arm lifts. That chest share fades rapidly before the elbow.
        chest = 0.22 * ((1.0 - first_t) ** 2)
        remainder = 1.0 - chest
        return {
            upper_name: remainder * (1.0 - first_t),
            lower_name: remainder * first_t,
            "chest": chest,
        }

    # Cuffs should follow the wrist, but they are still cloth around the forearm—not the hand mesh.
    # Cap wrist/hand influence at 15% even at the end of the sleeve.
    hand_share = 0.15 * second_t
    return {lower_name: 1.0 - hand_share, hand_name: hand_share}


def _weights_for_upper_garment_point(point, bones: list[Bone], *, max_influences=4):
    """Skin jackets/long sleeves without turning the sleeve into the hand.

    Central cloth follows hips/spine/chest. Each sleeve is side-locked and follows shoulder/upper
    arm -> elbow/lower arm, with only a small capped wrist contribution at the cuff. A smooth seam
    blend keeps the garment attached to the chest while preventing cross-arm contamination.
    """
    by_name = {bone.name: bone for bone in bones}
    if not all(name in by_name for name in ("hips", "spine", "chest")):
        return None

    chest_x = by_name["chest"].position[0]
    side = "left" if point[0] >= chest_x else "right"
    arm_names = (f"{side}UpperArm", f"{side}LowerArm", f"{side}Hand")
    if not all(name in by_name for name in arm_names):
        return _normalize_weight_map(_upper_garment_torso_weights(point, by_name), max_influences=max_influences)

    shoulder_span = abs(by_name[arm_names[0]].position[0] - chest_x)
    seam_start = max(0.16, shoulder_span * 0.58)
    seam_end = max(seam_start + 0.08, shoulder_span * 1.18)
    x_distance = abs(point[0] - chest_x)
    sleeve_mix = max(0.0, min(1.0, (x_distance - seam_start) / (seam_end - seam_start)))
    sleeve_mix = sleeve_mix * sleeve_mix * (3.0 - 2.0 * sleeve_mix)

    torso = _upper_garment_torso_weights(point, by_name)
    sleeve = _upper_garment_sleeve_weights(point, side, by_name)
    combined: dict[str, float] = defaultdict(float)
    for name, weight in torso.items():
        combined[name] += weight * (1.0 - sleeve_mix)
    for name, weight in sleeve.items():
        combined[name] += weight * sleeve_mix

    result = _normalize_weight_map(dict(combined), max_influences=max_influences)
    hand_name = f"{side}Hand"
    hand_value = next((item.weight for item in result if item.bone == hand_name), 0.0)
    if hand_value > 0.15:
        lower_name = f"{side}LowerArm"
        values = {item.bone: item.weight for item in result}
        excess = hand_value - 0.15
        values[hand_name] = 0.15
        values[lower_name] = values.get(lower_name, 0.0) + excess
        result = _normalize_weight_map(values, max_influences=max_influences)
    return result


def weights_for_layered_point(point, bones: list[Bone], *, profile="upper_body", max_influences=4):
    # WrapLayer clothing should follow the body spatially rather than the single AccessoryWeld target.
    # Clothing profiles stop nearby but unrelated limbs (for example lowered hands beside shorts)
    # from stealing weights.
    if profile in {"upper_body", "upper_garment"}:
        garment = _weights_for_upper_garment_point(point, bones, max_influences=max_influences)
        if garment:
            return garment

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
