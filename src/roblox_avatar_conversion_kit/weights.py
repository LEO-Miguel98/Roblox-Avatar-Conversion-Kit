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
    if primary in {"hips", "spine", "chest", "neck"}:
        names.extend(name for name in ("hips", "spine", "chest", "neck") if name in by_name)
    result = []
    for name in names:
        if name in by_name and name not in result:
            result.append(name)
    return result


def weights_for_point(point, primary, bones, *, max_influences=4):
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
    total = sum(value for _, value in scored) or 1.0
    normalized = [VertexWeight(name, value / total) for name, value in scored]
    kept = [weight for weight in normalized if weight.weight >= 0.025] or [max(normalized, key=lambda weight: weight.weight)]
    total = sum(weight.weight for weight in kept)
    return [VertexWeight(weight.bone, weight.weight / total) for weight in kept]


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
