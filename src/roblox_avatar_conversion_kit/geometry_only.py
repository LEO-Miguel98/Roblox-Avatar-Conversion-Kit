from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .features import DynamicAccessory, EyeRig, FeaturePlan, LayeredClothing
from .obj import ObjMesh
from .rig import Bone


@dataclass(frozen=True)
class _GroupInfo:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    center: tuple[float, float, float]
    size: tuple[float, float, float]


def _group_infos(mesh: ObjMesh) -> dict[str, _GroupInfo]:
    out: dict[str, _GroupInfo] = {}
    for name, indices in mesh.group_vertex_indices().items():
        lo, hi = mesh.bounds(indices)
        out[name] = _GroupInfo(
            name=name,
            lo=lo,
            hi=hi,
            center=tuple((lo[i] + hi[i]) * 0.5 for i in range(3)),
            size=tuple(hi[i] - lo[i] for i in range(3)),
        )
    return out


def _mid(a, b, t=0.5):
    return tuple((1.0 - t) * a[i] + t * b[i] for i in range(3))


def _distance(a, b):
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def normalize_geometry_only_mesh(mesh: ObjMesh) -> tuple[float, float, float]:
    """Remove obvious scene helpers and move an OBJ-only avatar to a useful model origin."""
    mesh.faces[:] = [
        face for face in mesh.faces
        if not face.group.lower().startswith(("baseplate", "terrain"))
    ]
    groups = mesh.group_vertex_indices()
    rig_indices = sorted({
        index
        for name, indices in groups.items()
        if name.lower().startswith("rig")
        for index in indices
    })
    if not rig_indices:
        raise ValueError("Geometry-only inference requires Rig* body groups")

    avatar_indices = sorted({index for indices in groups.values() for index in indices})
    rig_lo, rig_hi = mesh.bounds(rig_indices)
    avatar_lo, _ = mesh.bounds(avatar_indices)
    translation = (
        -((rig_lo[0] + rig_hi[0]) * 0.5),
        -avatar_lo[1],
        -((rig_lo[2] + rig_hi[2]) * 0.5),
    )
    mesh.vertices[:] = [
        tuple(point[i] + translation[i] for i in range(3))
        for point in mesh.vertices
    ]
    return translation


def _left_right(pair: list[_GroupInfo]) -> dict[str, _GroupInfo]:
    if len(pair) != 2:
        raise ValueError("Expected a left/right pair while inferring geometry-only R15 layout")
    ordered = sorted(pair, key=lambda item: item.center[0])
    # Standard MMD convention places the model's left-side bones on +X.
    return {"right": ordered[0], "left": ordered[1]}


def _infer_rig_layout(mesh: ObjMesh):
    infos = _group_infos(mesh)
    rigs = [item for name, item in infos.items() if name.lower().startswith("rig")]
    if len(rigs) < 11:
        raise ValueError(
            f"Geometry-only inference currently expects at least 11 Rig* groups; found {len(rigs)}"
        )

    head = max(rigs, key=lambda item: item.center[1])
    rest = [item for item in rigs if item.name != head.name]
    torso = sorted(
        rest,
        key=lambda item: (abs(item.center[0]), -(item.size[0] * item.size[1])),
    )[:2]
    upper_torso, lower_torso = sorted(torso, key=lambda item: item.center[1], reverse=True)

    limbs = [item for item in rest if item.name not in {upper_torso.name, lower_torso.name}]
    limbs = sorted(limbs, key=lambda item: item.center[1], reverse=True)
    if len(limbs) < 8:
        raise ValueError("Could not infer four symmetric limb levels from Rig* groups")
    limbs = limbs[:8]

    arms = _left_right(limbs[0:2])
    hands = _left_right(limbs[2:4])
    legs = _left_right(limbs[4:6])
    feet = _left_right(limbs[6:8])
    return infos, head, upper_torso, lower_torso, arms, hands, legs, feet


def _infer_layered_clothing(
    handles: list[_GroupInfo],
    *,
    excluded: set[str],
    hips_y: float,
    chest_y: float,
    foot_y: float,
    torso_width: float,
) -> tuple[LayeredClothing, ...]:
    output: list[LayeredClothing] = []
    for item in handles:
        if item.name in excluded:
            continue
        longest = max(item.size)
        shortest = max(min(item.size), 1e-5)
        aspect = longest / shortest

        if item.center[1] < foot_y - 0.20 and item.size[1] > 0.45:
            output.append(LayeredClothing(
                name=f"Inferred footwear {item.name}",
                group=item.name,
                accessory_type="GeometryOnly",
                profile="feet",
            ))
            continue

        if (
            hips_y + 0.15 <= item.center[1] <= chest_y + 0.25
            and item.size[1] > 0.80
            and item.size[0] > torso_width * 1.35
            and aspect < 6.0
        ):
            output.append(LayeredClothing(
                name=f"Inferred upper clothing {item.name}",
                group=item.name,
                accessory_type="GeometryOnly",
                profile="upper_body",
            ))
            continue

        if (
            abs(item.center[1] - hips_y) <= 0.30
            and item.size[1] > 0.32
            and longest < 1.60
            and aspect < 4.0
        ):
            output.append(LayeredClothing(
                name=f"Inferred lower clothing {item.name}",
                group=item.name,
                accessory_type="GeometryOnly",
                profile="lower_body",
            ))
    return tuple(output)


def infer_geometry_only_avatar(mesh: ObjMesh):
    """Infer a usable humanoid rig/features from a Roblox OBJ that has no avatar_manifest.json."""
    infos, head, upper_torso, lower_torso, arms, hands, legs, feet = _infer_rig_layout(mesh)

    hips = lower_torso.center
    spine = _mid(lower_torso.center, upper_torso.center)
    chest = upper_torso.center
    neck = _mid(upper_torso.center, head.center)
    head_position = head.center

    bones = [
        Bone("hips", None, hips),
        Bone("spine", "hips", spine),
        Bone("chest", "spine", chest),
        Bone("neck", "chest", neck),
        Bone("head", "neck", head_position),
    ]
    mapping: dict[str, str] = {
        lower_torso.name: "hips",
        upper_torso.name: "spine",
        head.name: "head",
    }

    for side in ("left", "right"):
        arm = arms[side]
        hand = hands[side]
        leg = legs[side]
        foot = feet[side]
        upper_arm = arm.center
        lower_arm = _mid(arm.center, hand.center, 0.58)
        hand_position = hand.center
        upper_leg = _mid(hips, leg.center, 0.45)
        lower_leg = leg.center
        foot_position = foot.center
        bones.extend([
            Bone(f"{side}UpperArm", "chest", upper_arm),
            Bone(f"{side}LowerArm", f"{side}UpperArm", lower_arm),
            Bone(f"{side}Hand", f"{side}LowerArm", hand_position),
            Bone(f"{side}UpperLeg", "hips", upper_leg),
            Bone(f"{side}LowerLeg", f"{side}UpperLeg", lower_leg),
            Bone(f"{side}Foot", f"{side}LowerLeg", foot_position),
        ])
        mapping[arm.name] = f"{side}UpperArm"
        mapping[hand.name] = f"{side}Hand"
        mapping[leg.name] = f"{side}UpperLeg"
        mapping[foot.name] = f"{side}Foot"

    handles = [
        item for name, item in infos.items()
        if name.lower().startswith("handle")
    ]
    dynamics: list[DynamicAccessory] = []
    dynamic_groups: set[str] = set()

    # Highest small/flat handle is a reliable geometry-only cue for a cowlick/heart antenna.
    heart = max(handles, key=lambda item: item.center[1]) if handles else None
    if heart and heart.center[1] > head.center[1] + head.size[1] * 0.45:
        dynamic_groups.add(heart.name)
        root = (heart.center[0], heart.lo[1], heart.center[2])
        tip = (heart.center[0], heart.hi[1], heart.center[2])
        dynamics.append(DynamicAccessory(
            name="Heart hair / cowlick",
            group=heart.name,
            parent_bone="head",
            bone_name=f"rackDynamic_{heart.name}_HeartHair",
            terminal_name=f"rackDynamic_{heart.name}_HeartHair_end",
            root_position=root,
            center_position=heart.center,
            tail_position=tip,
            size=heart.size,
            stiffness=0.90,
            drag_force=0.90,
            gravity_power=0.03,
            angular_limit=0.09,
            physics_mode="spring",
            segments=2,
        ))

    # Shark tails project strongly behind the torso in Z. Restrict the search below the head so
    # hair shells do not win the depth-aspect test.
    tail_candidates = [
        item for item in handles
        if item.name not in dynamic_groups and item.center[1] < head.center[1] - 0.35
    ]
    tail = None
    if tail_candidates:
        tail = max(
            tail_candidates,
            key=lambda item: item.size[2] / max(item.size[0], item.size[1], 1e-5),
        )
        depth_ratio = tail.size[2] / max(tail.size[0], tail.size[1], 1e-5)
        if depth_ratio >= 1.15:
            dynamic_groups.add(tail.name)
            root_z = tail.lo[2] if abs(tail.lo[2] - hips[2]) <= abs(tail.hi[2] - hips[2]) else tail.hi[2]
            tip_z = tail.hi[2] if root_z == tail.lo[2] else tail.lo[2]
            root = (tail.center[0], hips[1], root_z)
            tip = (tail.center[0], tail.center[1], tip_z)
            dynamics.append(DynamicAccessory(
                name="Shark tail",
                group=tail.name,
                parent_bone="hips",
                bone_name=f"rackDynamic_{tail.name}_SharkTail",
                terminal_name=f"rackDynamic_{tail.name}_SharkTail_end",
                root_position=root,
                center_position=tail.center,
                tail_position=tip,
                size=tail.size,
                stiffness=0.42,
                drag_force=0.58,
                gravity_power=0.10,
                angular_limit=0.68,
                physics_mode="spring",
                segments=4,
            ))

    foot_y = min(feet["left"].center[1], feet["right"].center[1])
    layered = _infer_layered_clothing(
        handles,
        excluded=dynamic_groups,
        hips_y=hips[1],
        chest_y=chest[1],
        foot_y=foot_y,
        torso_width=upper_torso.size[0],
    )
    layered_groups = {item.group for item in layered}

    anchors = {"head": head_position, "spine": spine, "hips": hips}
    for item in handles:
        if item.name in dynamic_groups:
            mapping[item.name] = "head" if heart and item.name == heart.name else "hips"
        elif item.name in layered_groups:
            mapping[item.name] = "spine"
        elif item.center[1] > neck[1]:
            mapping[item.name] = "head"
        else:
            mapping[item.name] = min(
                anchors,
                key=lambda name: _distance(item.center, anchors[name]),
            )

    eye_y = head.center[1] + head.size[1] * 0.04
    eye_z = head.lo[2] + head.size[2] * 0.05
    eye_dx = head.size[0] * 0.20
    eyes = EyeRig(
        master_position=(head.center[0], eye_y, eye_z),
        left_position=(head.center[0] + eye_dx, eye_y, eye_z),
        right_position=(head.center[0] - eye_dx, eye_y, eye_z),
        head_position=head_position,
    )
    features = FeaturePlan(
        eyes=eyes,
        dynamics=tuple(dynamics),
        layered_clothing=layered,
        native_expression_source=False,
    )
    warnings = [
        "No avatar_manifest.json was supplied; humanoid bones and accessory roles were inferred from OBJ geometry.",
        "Geometry-only rig inference is conservative: rigid props stay rigid, while only the detected tail and cowlick receive spring physics.",
        "OBJ carries no source facial morph deltas; facial expression morphs must be reconstructed from visible face geometry or authored separately.",
    ]
    return bones, mapping, features, warnings
