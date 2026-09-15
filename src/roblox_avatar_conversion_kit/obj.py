from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class Material:
    name: str
    kd: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ks: tuple[float, float, float] = (0.0, 0.0, 0.0)
    ns: float = 0.0
    alpha: float = 1.0
    map_kd: str | None = None


@dataclass
class Face:
    corners: list[tuple[int, int | None, int | None]]
    group: str
    material: str | None


@dataclass
class ObjMesh:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)
    normals: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[Face] = field(default_factory=list)

    def group_vertex_indices(self) -> dict[str, set[int]]:
        out: dict[str, set[int]] = {}
        for face in self.faces:
            bucket = out.setdefault(face.group, set())
            bucket.update(c[0] for c in face.corners)
        return out

    def bounds(self, indices: Iterable[int] | None = None) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        points = self.vertices if indices is None else [self.vertices[i] for i in indices]
        if not points:
            raise ValueError("Cannot calculate bounds of an empty point set")
        lo = tuple(min(p[a] for p in points) for a in range(3))
        hi = tuple(max(p[a] for p in points) for a in range(3))
        return lo, hi


def _resolve_index(raw: str, size: int) -> int:
    idx = int(raw)
    return idx - 1 if idx > 0 else size + idx


def parse_obj(path: Path) -> ObjMesh:
    mesh = ObjMesh()
    group = "default"
    material: str | None = None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        op = parts[0]
        if op == "v" and len(parts) >= 4:
            mesh.vertices.append(tuple(map(float, parts[1:4])))
        elif op == "vt" and len(parts) >= 3:
            mesh.uvs.append(tuple(map(float, parts[1:3])))
        elif op == "vn" and len(parts) >= 4:
            mesh.normals.append(tuple(map(float, parts[1:4])))
        elif op in {"g", "o"} and len(parts) >= 2:
            group = " ".join(parts[1:])
        elif op == "usemtl" and len(parts) >= 2:
            material = " ".join(parts[1:])
        elif op == "f" and len(parts) >= 4:
            corners = []
            for token in parts[1:]:
                fields = token.split("/")
                vi = _resolve_index(fields[0], len(mesh.vertices))
                ti = _resolve_index(fields[1], len(mesh.uvs)) if len(fields) > 1 and fields[1] else None
                ni = _resolve_index(fields[2], len(mesh.normals)) if len(fields) > 2 and fields[2] else None
                corners.append((vi, ti, ni))
            for i in range(1, len(corners) - 1):
                mesh.faces.append(Face([corners[0], corners[i], corners[i + 1]], group, material))
    if not mesh.vertices or not mesh.faces:
        raise ValueError("OBJ contains no usable mesh data")
    return mesh


def parse_mtl(path: Path | None) -> dict[str, Material]:
    if path is None or not Path(path).exists():
        return {}
    materials: dict[str, Material] = {}
    current: Material | None = None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        op = parts[0].lower()
        if op == "newmtl" and len(parts) >= 2:
            current = Material(" ".join(parts[1:]))
            materials[current.name] = current
        elif current and op == "kd" and len(parts) >= 4:
            current.kd = tuple(map(float, parts[1:4]))
        elif current and op == "ks" and len(parts) >= 4:
            current.ks = tuple(map(float, parts[1:4]))
        elif current and op == "ns" and len(parts) >= 2:
            current.ns = float(parts[1])
        elif current and op in {"d", "tr"} and len(parts) >= 2:
            value = float(parts[1])
            current.alpha = value if op == "d" else 1.0 - value
        elif current and op == "map_kd" and len(parts) >= 2:
            current.map_kd = " ".join(parts[1:])
    return materials
