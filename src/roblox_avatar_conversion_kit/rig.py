from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .obj import ObjMesh


BODY_PART_TO_BONE = {
    "LowerTorso": "hips",
    "UpperTorso": "spine",
    "Head": "head",
    "LeftUpperArm": "leftUpperArm",
    "LeftLowerArm": "leftLowerArm",
    "LeftHand": "leftHand",
    "RightUpperArm": "rightUpperArm",
    "RightLowerArm": "rightLowerArm",
    "RightHand": "rightHand",
    "LeftUpperLeg": "leftUpperLeg",
    "LeftLowerLeg": "leftLowerLeg",
    "LeftFoot": "leftFoot",
    "RightUpperLeg": "rightUpperLeg",
    "RightLowerLeg": "rightLowerLeg",
    "RightFoot": "rightFoot",
}

PARENT = {
    "hips": None,
    "spine": "hips",
    "chest": "spine",
    "neck": "chest",
    "head": "neck",
    "leftUpperArm": "chest",
    "leftLowerArm": "leftUpperArm",
    "leftHand": "leftLowerArm",
    "rightUpperArm": "chest",
    "rightLowerArm": "rightUpperArm",
    "rightHand": "rightLowerArm",
    "leftUpperLeg": "hips",
    "leftLowerLeg": "leftUpperLeg",
    "leftFoot": "leftLowerLeg",
    "rightUpperLeg": "hips",
    "rightLowerLeg": "rightUpperLeg",
    "rightFoot": "rightLowerLeg",
}


@dataclass(frozen=True)
class Bone:
    name: str
    parent: str | None
    position: tuple[float, float, float]


def _body_parts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    names = set(BODY_PART_TO_BONE)
    return [p for p in manifest.get("meshParts", []) if p.get("name") in names]


def infer_manifest_translation(manifest: dict[str, Any], mesh: ObjMesh) -> tuple[float, float, float]:
    body = _body_parts(manifest)
    if not body:
        raise ValueError("No R15 body mesh parts found in manifest")
    group_indices = mesh.group_vertex_indices()
    rig_indices = sorted({i for name, idxs in group_indices.items() if name.lower().startswith("rig") for i in idxs})
    if not rig_indices:
        rig_indices = list(range(len(mesh.vertices)))
    _, obj_hi = mesh.bounds(rig_indices)
    manifest_hi = tuple(max(float(p["cframe"][a]) + float(p["size"][a]) / 2.0 for p in body) for a in range(3))
    return tuple(obj_hi[a] - manifest_hi[a] for a in range(3))


def _transform_point(point: list[float] | tuple[float, ...], translation: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(float(point[a]) + translation[a] for a in range(3))


def build_bones(manifest: dict[str, Any], translation: tuple[float, float, float]) -> list[Bone]:
    parts = {p["name"]: p for p in _body_parts(manifest)}
    required = set(BODY_PART_TO_BONE)
    missing = sorted(required.difference(parts))
    if missing:
        raise ValueError(f"Manifest is missing required R15 parts: {', '.join(missing)}")

    def c(name: str) -> tuple[float, float, float]:
        return _transform_point(parts[name]["cframe"][:3], translation)

    def midpoint(a: str, b: str) -> tuple[float, float, float]:
        pa, pb = c(a), c(b)
        return tuple((pa[i] + pb[i]) / 2.0 for i in range(3))

    upper = c("UpperTorso")
    lower = c("LowerTorso")
    chest = tuple((2.0 * upper[i] + lower[i]) / 3.0 for i in range(3))

    pos = {
        "hips": lower,
        "spine": midpoint("LowerTorso", "UpperTorso"),
        "chest": chest,
        "neck": midpoint("UpperTorso", "Head"),
        "head": c("Head"),
        "leftUpperArm": midpoint("UpperTorso", "LeftUpperArm"),
        "leftLowerArm": midpoint("LeftUpperArm", "LeftLowerArm"),
        "leftHand": midpoint("LeftLowerArm", "LeftHand"),
        "rightUpperArm": midpoint("UpperTorso", "RightUpperArm"),
        "rightLowerArm": midpoint("RightUpperArm", "RightLowerArm"),
        "rightHand": midpoint("RightLowerArm", "RightHand"),
        "leftUpperLeg": midpoint("LowerTorso", "LeftUpperLeg"),
        "leftLowerLeg": midpoint("LeftUpperLeg", "LeftLowerLeg"),
        "leftFoot": midpoint("LeftLowerLeg", "LeftFoot"),
        "rightUpperLeg": midpoint("LowerTorso", "RightUpperLeg"),
        "rightLowerLeg": midpoint("RightUpperLeg", "RightLowerLeg"),
        "rightFoot": midpoint("RightLowerLeg", "RightFoot"),
    }
    return [Bone(name, PARENT[name], pos[name]) for name in PARENT]


def map_groups_to_bones(manifest: dict[str, Any], mesh: ObjMesh, translation: tuple[float, float, float]) -> dict[str, str]:
    parts = _body_parts(manifest)
    by_group = mesh.group_vertex_indices()
    result: dict[str, str] = {}

    for group, indices in by_group.items():
        lo, hi = mesh.bounds(indices)
        center = tuple((lo[a] + hi[a]) / 2.0 for a in range(3))
        if group.lower().startswith("rig"):
            best = None
            for part in parts:
                pc = _transform_point(part["cframe"][:3], translation)
                size = part.get("size", [1, 1, 1])
                score = sum(((center[a] - pc[a]) / max(float(size[a]), 1e-5)) ** 2 for a in range(3))
                if best is None or score < best[0]:
                    best = (score, part["name"])
            if best:
                result[group] = BODY_PART_TO_BONE[best[1]]
                continue

        best_accessory = None
        for accessory in manifest.get("accessories", []):
            handle = accessory.get("handle") or {}
            if not handle.get("cframe"):
                continue
            hc = _transform_point(handle["cframe"][:3], translation)
            size = handle.get("size", [1, 1, 1])
            score = sum(((center[a] - hc[a]) / max(float(size[a]), 1e-5)) ** 2 for a in range(3))
            if best_accessory is None or score < best_accessory[0]:
                best_accessory = (score, accessory)

        target_bone = None
        if best_accessory:
            accessory = best_accessory[1]
            handle_full = (accessory.get("handle") or {}).get("fullName")
            for joint in manifest.get("joints", []):
                if joint.get("name") == "AccessoryWeld" and joint.get("part0") == handle_full:
                    target_name = str(joint.get("part1", "")).split(".")[-1]
                    target_bone = BODY_PART_TO_BONE.get(target_name)
                    break
        result[group] = target_bone or "spine"
    return result
