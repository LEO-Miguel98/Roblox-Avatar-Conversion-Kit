from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class AvatarPackage:
    root: Path
    manifest_path: Path | None
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
    if len(manifests) > 1:
        raise ValueError(f"Expected at most one avatar_manifest.json; found {len(manifests)}")

    if manifests:
        manifest_path = manifests[0]
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("Manifest is unexpectedly large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest root must be a JSON object")
        package_dir = manifest_path.parent
        obj_path = _one(sorted(package_dir.glob("*.obj")), "OBJ")
        mtls = sorted(package_dir.glob("*.mtl"))
        return AvatarPackage(package_dir, manifest_path, obj_path, mtls[0] if mtls else None, manifest)

    # Geometry-only packages are common when an avatar is exported directly as OBJ/MTL.  Keep the
    # secure single-model assumption, but no longer require a manifest when the package contains one
    # unambiguous OBJ.
    objs = sorted(root.rglob("*.obj"))
    obj_path = _one(objs, "OBJ")
    package_dir = obj_path.parent
    mtls = sorted(package_dir.glob("*.mtl"))
    return AvatarPackage(package_dir, None, obj_path, mtls[0] if mtls else None, {})


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not manifest:
        warnings.append(
            "No avatar_manifest.json found; using conservative geometry-only rig/accessory inference."
        )
        return warnings

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
