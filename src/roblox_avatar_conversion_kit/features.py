from __future__ import annotations

import re
from dataclasses import dataclass
from math import sqrt
from typing import Any

from .obj import ObjMesh
from .rig import BODY_PART_TO_BONE, Bone

EXPRESSION_PRESETS = (
    "happy", "angry", "sad", "relaxed", "surprised",
    "aa", "ih", "ou", "ee", "oh",
    "blink", "blinkLeft", "blinkRight", "neutral",
)
DYNAMIC_KEYWORDS = (
    "hair", "bang", "cowlick", "tail", "ear", "ribbon", "ponytail",
    "cape", "scarf", "wing", "pixie", "fluffy", "wolf cut",
)
DYNAMIC_EXCLUDES = (
    "face", "speech", "bubble", "katana", "sword", "glove", "jacket",
    "legging", "short", "shirt", "pants",
)

@dataclass(frozen=True)
class EyeRig:
    master_position: tuple[float, float, float]
    left_position: tuple[float, float, float]
    right_position: tuple[float, float, float]
    head_position: tuple[float, float, float]

@dataclass(frozen=True)
class DynamicAccessory:
    name: str
    group: str
    parent_bone: str
    bone_name: str
    terminal_name: str
    root_position: tuple[float, float, float]
    center_position: tuple[float, float, float]
    tail_position: tuple[float, float, float]
    size: tuple[float, float, float]
    stiffness: float
    drag_force: float
    gravity_power: float
    angular_limit: float

@dataclass(frozen=True)
class FeaturePlan:
    eyes: EyeRig | None
    dynamics: tuple[DynamicAccessory, ...]
    expression_presets: tuple[str, ...] = EXPRESSION_PRESETS
    native_expression_source: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "eyes": None if not self.eyes else {
                "master_position": self.eyes.master_position,
                "left_position": self.eyes.left_position,
                "right_position": self.eyes.right_position,
                "head_position": self.eyes.head_position,
            },
            "dynamic_accessories": [
                {
                    "name": d.name,
                    "group": d.group,
                    "parent_bone": d.parent_bone,
                    "bone_name": d.bone_name,
                    "terminal_name": d.terminal_name,
                    "root_position": d.root_position,
                    "center_position": d.center_position,
                    "tail_position": d.tail_position,
                    "size": d.size,
                    "stiffness": d.stiffness,
                    "drag_force": d.drag_force,
                    "gravity_power": d.gravity_power,
                    "angular_limit": d.angular_limit,
                }
                for d in self.dynamics
            ],
            "expression_presets": list(self.expression_presets),
            "native_expression_source": self.native_expression_source,
            "expression_mode": "native" if self.native_expression_source else "editable-scaffold",
        }


def _transform_point(point, translation):
    return tuple(float(point[i]) + translation[i] for i in range(3))


def _dist(a, b):
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _group_bounds(mesh: ObjMesh):
    out = {}
    for group, indices in mesh.group_vertex_indices().items():
        lo, hi = mesh.bounds(indices)
        center = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
        size = tuple(hi[i] - lo[i] for i in range(3))
        out[group] = (lo, hi, center, size)
    return out


def _target_bone(manifest, accessory):
    handle_full = (accessory.get("handle") or {}).get("fullName")
    for joint in manifest.get("joints", []):
        if joint.get("name") != "AccessoryWeld" or joint.get("part0") != handle_full:
            continue
        target_name = str(joint.get("part1", "")).split(".")[-1]
        return BODY_PART_TO_BONE.get(target_name, "spine")
    return "spine"


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "Accessory"
    return value[:36]


def build_eye_rig(manifest: dict[str, Any], translation) -> EyeRig | None:
    head = next(
        (part for part in manifest.get("meshParts", []) if part.get("name") == "Head" and part.get("cframe")),
        None,
    )
    if not head:
        return None
    center = _transform_point(head["cframe"][:3], translation)
    size = tuple(float(v) for v in head.get("size", [1.0, 1.0, 1.0]))
    # Roblox characters face -Z. Keep the eye controllers just in front of the head surface.
    y = center[1] + size[1] * 0.07
    z = center[2] - size[2] * 0.48
    dx = size[0] * 0.18
    return EyeRig(
        master_position=(center[0], y, z),
        left_position=(center[0] - dx, y, z),
        right_position=(center[0] + dx, y, z),
        head_position=center,
    )


def detect_dynamic_accessories(
    manifest: dict[str, Any], mesh: ObjMesh, translation, bones: list[Bone]
) -> tuple[DynamicAccessory, ...]:
    bounds = _group_bounds(mesh)
    handle_bounds = {name: value for name, value in bounds.items() if name.lower().startswith("handle")}
    bone_positions = {bone.name: bone.position for bone in bones}
    found: list[tuple[float, DynamicAccessory]] = []

    for accessory in manifest.get("accessories", []):
        name = str(accessory.get("name") or "Accessory")
        lower_name = name.lower()
        if not any(keyword in lower_name for keyword in DYNAMIC_KEYWORDS):
            continue
        if any(keyword in lower_name for keyword in DYNAMIC_EXCLUDES):
            continue
        handle = accessory.get("handle") or {}
        if not handle.get("cframe"):
            continue
        handle_center = _transform_point(handle["cframe"][:3], translation)
        handle_size = tuple(max(float(v), 1e-5) for v in handle.get("size", [1, 1, 1]))

        best = None
        for group, (lo, hi, center, size) in handle_bounds.items():
            score = sum(((center[i] - handle_center[i]) / handle_size[i]) ** 2 for i in range(3))
            if best is None or score < best[0]:
                best = (score, group, lo, hi, center, size)
        if not best or best[0] > 0.25:
            continue

        score, group, lo, hi, center, size = best
        parent_bone = _target_bone(manifest, accessory)
        parent_position = bone_positions.get(parent_bone, center)
        # Closest point on the accessory bounds to its welded parent gives a better rotation pivot
        # than simply rotating the whole object around its geometric center.
        root = tuple(min(max(parent_position[i], lo[i]), hi[i]) for i in range(3))
        if _dist(root, center) < 0.08:
            axis = max(range(3), key=lambda i: size[i])
            direction = -1.0 if axis == 1 else 1.0
            tail = list(root)
            tail[axis] += direction * max(size[axis] * 0.35, 0.12)
            tail = tuple(tail)
        else:
            tail = center

        if "tail" in lower_name:
            stiffness, drag, gravity, limit = 0.35, 0.45, 0.25, 0.65
        elif "ear" in lower_name:
            stiffness, drag, gravity, limit = 0.65, 0.60, 0.10, 0.28
        elif "cowlick" in lower_name or "bang" in lower_name or "hair" in lower_name or "fluffy" in lower_name or "wolf cut" in lower_name:
            stiffness, drag, gravity, limit = 0.50, 0.55, 0.15, 0.40
        else:
            stiffness, drag, gravity, limit = 0.50, 0.55, 0.15, 0.42

        bone_name = f"rackDynamic_{group}_{_safe_name(name)}"
        found.append(
            (
                score,
                DynamicAccessory(
                    name=name,
                    group=group,
                    parent_bone=parent_bone,
                    bone_name=bone_name,
                    terminal_name=bone_name + "_end",
                    root_position=root,
                    center_position=center,
                    tail_position=tail,
                    size=size,
                    stiffness=stiffness,
                    drag_force=drag,
                    gravity_power=gravity,
                    angular_limit=limit,
                ),
            )
        )

    # If two manifest accessories accidentally match the same OBJ group, keep the better spatial match.
    output = []
    seen_groups = set()
    for _, dynamic in sorted(found, key=lambda item: item[0]):
        if dynamic.group in seen_groups:
            continue
        seen_groups.add(dynamic.group)
        output.append(dynamic)
    return tuple(output)


def analyze_features(manifest, mesh, translation, bones) -> FeaturePlan:
    # OBJ cannot carry source blend-shape deltas. A standard expression scaffold is generated for
    # Blender/VRM, but it remains zero-delta until the user or a future source format supplies shapes.
    return FeaturePlan(
        eyes=build_eye_rig(manifest, translation),
        dynamics=detect_dynamic_accessories(manifest, mesh, translation, bones),
        native_expression_source=False,
    )
