from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class AvatarPackage:
    root: Path
    manifest_path: Path
    obj_path: Path
    mtl_path: Path | None
    manifest: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.manifest.get("rootName") or self.obj_path.stem)


def _one(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        raise ValueError(f"Expected exactly one {label}; found {len(paths)}")
    return paths[0]


def discover_package(root: Path) -> AvatarPackage:
    root = Path(root)
    manifests = list(root.rglob("avatar_manifest.json"))
    manifest_path = _one(manifests, "avatar_manifest.json")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest is unexpectedly large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Manifest root must be a JSON object")

    package_dir = manifest_path.parent
    objs = sorted(package_dir.glob("*.obj"))
    obj_path = _one(objs, "OBJ")
    mtls = sorted(package_dir.glob("*.mtl"))
    mtl_path = mtls[0] if mtls else None
    return AvatarPackage(package_dir, manifest_path, obj_path, mtl_path, manifest)


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if manifest.get("version") != 1:
        warnings.append(f"Untested manifest version: {manifest.get('version')!r}")
    if not isinstance(manifest.get("meshParts"), list):
        raise ValueError("Manifest is missing meshParts")
    if not isinstance(manifest.get("joints"), list):
        raise ValueError("Manifest is missing joints")
    notes = manifest.get("notes") or []
    if any("does not contain bones/skin weights" in str(n) for n in notes):
        warnings.append("Source OBJ has no native skin weights; weights must be reconstructed.")
    return warnings
