from __future__ import annotations

import math
import struct
from pathlib import Path

from .obj import ObjMesh


def _group_components(mesh, group):
    from collections import defaultdict
    adj = defaultdict(set)
    vertices = set()
    for face in mesh.faces:
        if face.group != group:
            continue
        ids = [corner[0] for corner in face.corners]
        vertices.update(ids)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                adj[ids[i]].add(ids[j])
                adj[ids[j]].add(ids[i])
    seen = set()
    out = []
    for start in vertices:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = set()
        while stack:
            v = stack.pop()
            comp.add(v)
            for n in adj[v]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(comp)
    return out


def _face_regions(mesh, mapping):
    groups = mesh.group_vertex_indices()
    candidates = [g for g in groups if mapping.get(g) == "head" and g.lower().startswith("rig")]
    if not candidates:
        candidates = [g for g in groups if mapping.get(g) == "head"]
    if not candidates:
        return None
    group = max(candidates, key=lambda g: len(groups[g]))
    indices = groups[group]
    lo, hi = mesh.bounds(indices)
    center = tuple((lo[i] + hi[i]) * 0.5 for i in range(3))
    size = tuple(max(hi[i] - lo[i], 1e-6) for i in range(3))
    width, height, depth = size
    front_cut = lo[2] + 0.25 * depth
    eyes = []
    mouths = []
    for comp in _group_components(mesh, group):
        pts = [mesh.vertices[i] for i in comp]
        clo = tuple(min(p[a] for p in pts) for a in range(3))
        chi = tuple(max(p[a] for p in pts) for a in range(3))
        cc = tuple((clo[a] + chi[a]) * 0.5 for a in range(3))
        cs = tuple(chi[a] - clo[a] for a in range(3))
        ax = abs(cc[0] - center[0])
        if (cc[2] <= front_cut and 0.08 * width <= ax <= 0.44 * width
                and center[1] - 0.20 * height <= cc[1] <= center[1] + 0.06 * height
                and cs[0] <= 0.40 * width and cs[1] <= 0.34 * height):
            eyes.append((comp, cc))
        if (cc[2] <= front_cut and ax <= 0.21 * width
                and center[1] - 0.43 * height <= cc[1] <= center[1] - 0.24 * height
                and cs[0] <= 0.32 * width and cs[1] <= 0.22 * height):
            mouths.append((comp, cc))
    left = set().union(*(c for c, cc in eyes if cc[0] >= center[0])) if eyes else set()
    right = set().union(*(c for c, cc in eyes if cc[0] < center[0])) if eyes else set()
    mouth = set().union(*(c for c, _ in mouths)) if mouths else set()
    hide = min(max(depth * 0.36, 0.12), depth * 0.48)
    return {
        "group": group, "center": center, "size": size,
        "left": frozenset(left), "right": frozenset(right),
        "mouth": frozenset(mouth), "mouth_components": len(mouths), "hide": hide,
    }


def _copy_mesh_with_hidden_mouth(mesh, regions):
    vertices = list(mesh.vertices)
    if regions:
        for i in regions["mouth"]:
            x, y, z = vertices[i]
            vertices[i] = (x, y, z + regions["hide"])
    return ObjMesh(vertices=vertices, uvs=list(mesh.uvs), normals=list(mesh.normals), faces=list(mesh.faces))


def _morph_builder(base, original_mesh, regions):
    def build(_mesh, mapping, source_to_pmx, *args, **kwargs):
        if not regions:
            return []
        group = regions["group"]
        center = regions["center"]
        width, height, _ = regions["size"]
        out = []

        def blink(jp, en, src):
            if len(src) < 12:
                return None
            line = sum(original_mesh.vertices[i][1] for i in src) / len(src)
            offsets = []
            for vi in src:
                p = original_mesh.vertices[vi]
                delta = (0.0, (line - p[1]) * 0.88, 0.0)
                if abs(delta[1]) < 1e-5:
                    continue
                for pi in source_to_pmx.get((group, vi), ()):
                    offsets.append((pi, base._mmd_vec3(delta)))
            return base._VertexMorph(jp, en, 2, offsets) if offsets else None

        lb = blink("ウィンク", "BlinkLeft", regions["left"])
        rb = blink("ウィンク右", "BlinkRight", regions["right"])
        if lb and rb:
            out.append(base._VertexMorph("まばたき", "Blink", 2, lb.offsets + rb.offsets))
            out.extend([lb, rb])
        elif lb:
            out.append(lb)
        elif rb:
            out.append(rb)

        mouth = regions["mouth"]
        if len(mouth) < 12:
            return out
        line = sum(original_mesh.vertices[i][1] for i in mouth) / len(mouth)
        buckets = {name: [] for name in ("a", "i", "u", "e", "o", "smile")}
        reveal_z = -regions["hide"]
        for vi in mouth:
            p = original_mesh.vertices[vi]
            rel_y = p[1] - line
            rel_x = p[0] - center[0]
            xnorm = min(abs(rel_x) / max(0.21 * width, 1e-6), 1.0)
            sx = 1.0 if rel_x >= 0 else -1.0
            dy_a = (-0.075 * height if rel_y <= 0 else 0.018 * height) * (0.55 + 0.45 * min(abs(rel_y) / max(0.11 * height, 1e-6), 1.0))
            deltas = {
                "a": (0.0, dy_a, reveal_z),
                "i": (0.025 * width * xnorm * sx, -0.010 * height * (1.0 - xnorm), reveal_z),
                "u": (-0.035 * width * xnorm * sx, -0.018 * height if rel_y <= 0 else 0.006 * height, reveal_z),
                "e": (0.018 * width * xnorm * sx, -0.045 * height if rel_y <= 0 else 0.012 * height, reveal_z),
                "o": (-0.022 * width * xnorm * sx, -0.052 * height if rel_y <= 0 else 0.010 * height, reveal_z),
                "smile": (0.015 * width * xnorm * sx, 0.045 * height * (xnorm ** 1.25), reveal_z),
            }
            for pi in source_to_pmx.get((group, vi), ()):
                for key, delta in deltas.items():
                    buckets[key].append((pi, base._mmd_vec3(delta)))
        names = [
            ("a", "あ", "MouthOpen"), ("i", "い", "MouthI"),
            ("u", "う", "MouthU"), ("e", "え", "MouthE"),
            ("o", "お", "MouthO"), ("smile", "笑い", "Smile"),
        ]
        for key, jp, en in names:
            if buckets[key]:
                out.append(base._VertexMorph(jp, en, 3, buckets[key]))
        return out
    return build


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _lerp(a, b, t):
    return tuple((1 - t) * a[i] + t * b[i] for i in range(3))


def _motion_bones_builder(base, mesh, mapping):
    def build(bones, features, *args, **kwargs):
        by = {b.name: b for b in bones}
        hips = by.get("hips") or bones[0]
        used = {c[0] for f in mesh.faces for c in f.corners}
        ground = min((mesh.vertices[i][1] for i in used), default=0.0)
        center = (hips.position[0], ground + (hips.position[1] - ground) * 0.64, hips.position[2])
        P = base._PmxBone
        result = [P("allParent", None, (hips.position[0], ground, hips.position[2])), P("center", "allParent", center), P("groove", "center", center)]
        helper_names = set()
        for side in ("left", "right"):
            arm = by.get(f"{side}UpperArm"); elbow = by.get(f"{side}LowerArm"); wrist = by.get(f"{side}Hand")
            chest = by.get("chest") or by.get("spine")
            if arm and elbow and wrist and chest:
                vals = [
                    P(f"{side}ShoulderP", "chest" if "chest" in by else "spine", _lerp(chest.position, arm.position, 0.08)),
                    P(f"{side}Shoulder", f"{side}ShoulderP", _lerp(chest.position, arm.position, 0.16)),
                    P(f"{side}ArmTwist", f"{side}UpperArm", _lerp(arm.position, elbow.position, 0.33)),
                    P(f"{side}WristTwist", f"{side}LowerArm", _lerp(elbow.position, wrist.position, 0.27)),
                ]
                result.extend(vals); helper_names.update(v.name for v in vals)
        for b in bones:
            parent = b.parent
            if b.name in {"hips", "spine"}:
                parent = "groove"
            elif b.name.endswith("UpperArm"):
                side = "left" if b.name.startswith("left") else "right"
                if f"{side}Shoulder" in helper_names: parent = f"{side}Shoulder"
            elif b.name.endswith("LowerArm"):
                side = "left" if b.name.startswith("left") else "right"
                if f"{side}ArmTwist" in helper_names: parent = f"{side}ArmTwist"
            elif b.name.endswith("Hand"):
                side = "left" if b.name.startswith("left") else "right"
                if f"{side}WristTwist" in helper_names: parent = f"{side}WristTwist"
            result.append(P(b.name, parent, b.position))
        groups = mesh.group_vertex_indices()
        for side in ("left", "right"):
            foot = by.get(f"{side}Foot"); lower = by.get(f"{side}LowerLeg"); upper = by.get(f"{side}UpperLeg")
            if not (foot and lower and upper): continue
            candidates = [g for g, bn in mapping.items() if bn == f"{side}Foot" and g.lower().startswith("rig")]
            ids = sorted({i for g in candidates for i in groups.get(g, ())})
            if ids:
                lo, hi = mesh.bounds(ids); toe = (foot.position[0], max(ground, lo[1] + (hi[1]-lo[1]) * 0.06), lo[2])
            else:
                toe = (foot.position[0], ground, foot.position[2] - max(_dist(lower.position, foot.position), 0.1) * 0.45)
            result.append(P(f"{side}Toe", f"{side}Foot", toe))
            result.append(P(f"{side}LegIK", "allParent", foot.position, f"{side}Foot", (f"{side}LowerLeg", f"{side}UpperLeg")))
            result.append(P(f"{side}ToeIK", f"{side}LegIK", toe, f"{side}Toe", (f"{side}Foot",)))
        if features and features.eyes:
            e = features.eyes
            result.extend([P("eyes", "head", e.master_position), P("leftEye", "eyes", e.left_position), P("rightEye", "eyes", e.right_position)])
        if features:
            for d in features.dynamics:
                for s in base.dynamic_chain(d):
                    result.append(P(s["name"], s["parent"], tuple(s["position"])))
        return result
    return build


def _read_text(data, offset, encoding):
    n = struct.unpack_from("<i", data, offset)[0]; offset += 4
    raw = bytes(data[offset:offset+n]); offset += n
    return raw.decode(encoding, errors="replace"), offset


def _patch_bone_flags(path):
    data = bytearray(Path(path).read_bytes())
    if data[:4] != b"PMX ":
        return
    header_size = data[8]
    globals_ = data[9:9+header_size]
    encoding = "utf-16-le" if globals_[0] == 0 else "utf-8"
    vertex_index_size, texture_index_size, material_index_size, bone_index_size = globals_[2], globals_[3], globals_[4], globals_[5]
    o = 9 + header_size
    for _ in range(4): _, o = _read_text(data, o, encoding)
    vcount = struct.unpack_from("<i", data, o)[0]; o += 4
    for _ in range(vcount):
        o += 12 + 12 + 8
        deform = data[o]; o += 1
        if deform == 0: o += bone_index_size
        elif deform == 1: o += bone_index_size * 2 + 4
        elif deform in (2, 4): o += bone_index_size * 4 + 16
        elif deform == 3: o += bone_index_size * 2 + 4 + 36
        else: raise ValueError(f"Unsupported PMX deform type {deform}")
        o += 4
    icount = struct.unpack_from("<i", data, o)[0]; o += 4 + icount * vertex_index_size
    tcount = struct.unpack_from("<i", data, o)[0]; o += 4
    for _ in range(tcount): _, o = _read_text(data, o, encoding)
    mcount = struct.unpack_from("<i", data, o)[0]; o += 4
    for _ in range(mcount):
        _, o = _read_text(data, o, encoding); _, o = _read_text(data, o, encoding)
        o += 16 + 12 + 4 + 12 + 1 + 16 + 4 + texture_index_size * 2 + 1
        toon = data[o]; o += 1
        o += 1 if toon else texture_index_size
        _, o = _read_text(data, o, encoding); o += 4
    bcount = struct.unpack_from("<i", data, o)[0]; o += 4
    for _ in range(bcount):
        jp, o = _read_text(data, o, encoding); en, o = _read_text(data, o, encoding)
        o += 12 + bone_index_size + 4
        flags_off = o; flags = struct.unpack_from("<H", data, o)[0]; o += 2
        if jp in {"全ての親", "グルーブ"} or en in {"allParent", "groove"}:
            struct.pack_into("<H", data, flags_off, flags | 0x0004)
            flags |= 0x0004
        o += bone_index_size if flags & 0x0001 else 12
        if flags & 0x0100 or flags & 0x0200: o += bone_index_size + 4
        if flags & 0x0400: o += 12
        if flags & 0x0800: o += 24
        if flags & 0x2000: o += 4
        if flags & 0x0020:
            o += bone_index_size
            iter_off = o; o += 4
            weight_off = o; o += 4
            if jp in {"左つま先ＩＫ", "右つま先ＩＫ"} or en in {"leftToeIK", "rightToeIK"}:
                struct.pack_into("<i", data, iter_off, 3)
                struct.pack_into("<f", data, weight_off, 1.0)
            links = struct.unpack_from("<i", data, o)[0]; o += 4
            for _ in range(links):
                o += bone_index_size
                limited = data[o]; o += 1
                if limited: o += 24
    Path(path).write_bytes(data)


def apply():
    from . import pmx as base
    if getattr(base, "_v0311_applied", False):
        return
    original_write = base.write_pmx
    base.MMD_JP.update({
        "allParent": "全ての親", "groove": "グルーブ",
        "leftShoulderP": "左肩P", "rightShoulderP": "右肩P",
        "leftShoulder": "左肩", "rightShoulder": "右肩",
        "leftArmTwist": "左腕捩", "rightArmTwist": "右腕捩",
        "leftWristTwist": "左手捩", "rightWristTwist": "右手捩",
        "leftToe": "左つま先", "rightToe": "右つま先",
        "leftToeIK": "左つま先ＩＫ", "rightToeIK": "右つま先ＩＫ",
    })

    def write_pmx(output, *, model_name, mesh, materials, bones, group_to_bone, smooth_weights=True, features=None, accessory_physics=True):
        geometry_only = bool(getattr(base, "_geometry_only_textured_materials", lambda _f: False)(features))
        regions = _face_regions(mesh, group_to_bone) if geometry_only else None
        hide_mouth = bool(regions and len(regions["mouth"]) >= 12)
        working_mesh = _copy_mesh_with_hidden_mouth(mesh, regions) if hide_mouth else mesh
        old_bones = base._pmx_bones
        old_morphs = base._reconstructed_face_morphs
        try:
            base._pmx_bones = _motion_bones_builder(base, mesh, group_to_bone)
            if hide_mouth:
                base._reconstructed_face_morphs = _morph_builder(base, mesh, regions)
            stats = original_write(output, model_name=model_name, mesh=working_mesh, materials=materials, bones=bones, group_to_bone=group_to_bone, smooth_weights=smooth_weights, features=features, accessory_physics=accessory_physics)
        finally:
            base._pmx_bones = old_bones
            base._reconstructed_face_morphs = old_morphs
        _patch_bone_flags(output)
        stats["neutral_hidden_mouth_vertices"] = len(regions["mouth"]) if hide_mouth else 0
        stats["neutral_hidden_mouth_components"] = regions["mouth_components"] if hide_mouth else 0
        stats["toe_ik_bones"] = 2 if all(f"{s}Foot" in {b.name for b in bones} for s in ("left", "right")) else 0
        stats["semistandard_motion_bones"] = 14
        stats["motion_compat_profile"] = "classic-pmd-plus-semstandard-vmd"
        return stats

    base.write_pmx = write_pmx
    base._v0311_applied = True
