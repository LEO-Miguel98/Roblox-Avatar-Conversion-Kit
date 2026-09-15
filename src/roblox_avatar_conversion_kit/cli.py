from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from .archive import inspect_zip, safe_extract_zip
from .blender import write_blender_script
from .manifest import discover_package, validate_manifest
from .obj import parse_mtl, parse_obj
from .pmx import write_pmx
from .rig import build_bones, infer_manifest_translation, map_groups_to_bones


def _load(zip_path: Path, workdir: Path):
    safe_extract_zip(zip_path, workdir)
    package = discover_package(workdir)
    warnings = validate_manifest(package.manifest)
    mesh = parse_obj(package.obj_path)
    materials = parse_mtl(package.mtl_path)
    translation = infer_manifest_translation(package.manifest, mesh)
    bones = build_bones(package.manifest, translation)
    mapping = map_groups_to_bones(package.manifest, mesh, translation)
    return package, warnings, mesh, materials, translation, bones, mapping


def cmd_inspect(args) -> int:
    source = Path(args.input)
    zip_info = inspect_zip(source)
    with tempfile.TemporaryDirectory(prefix="rack-") as td:
        package, warnings, mesh, materials, translation, bones, mapping = _load(source, Path(td))
        result = {
            "package": package.name,
            "archive": zip_info,
            "manifest_stats": package.manifest.get("stats", {}),
            "obj": {"vertices": len(mesh.vertices), "triangles": len(mesh.faces), "groups": len(mesh.group_vertex_indices())},
            "materials": len(materials),
            "manifest_to_obj_translation": translation,
            "group_to_bone": mapping,
            "bones": [b.name for b in bones],
            "warnings": warnings,
        }
    print(json.dumps(result, indent=2))
    return 0


def cmd_prepare(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    package, warnings, mesh, materials, translation, bones, mapping = _load(source, output)
    plan = {
        "package": package.name,
        "source_obj": str(package.obj_path.relative_to(output)),
        "translation": translation,
        "group_to_bone": mapping,
        "bones": [{"name": b.name, "parent": b.parent, "position": b.position} for b in bones],
        "warnings": warnings,
    }
    (output / "conversion-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    write_blender_script(output / "build_in_blender.py", obj_path=package.obj_path, bones=bones, group_to_bone=mapping)
    print(f"Prepared: {output}")
    return 0


def cmd_pmx(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rack-") as td:
        package, warnings, mesh, materials, translation, bones, mapping = _load(source, Path(td))
        stats = write_pmx(output, model_name=package.name, mesh=mesh, materials=materials, bones=bones, group_to_bone=mapping)
        for mat in materials.values():
            if mat.map_kd:
                src = package.root / mat.map_kd
                if src.is_file():
                    shutil.copy2(src, output.parent / src.name)
    print(json.dumps({"output": str(output), "stats": stats, "warnings": warnings}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rack", description="Roblox avatar conversion toolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect", help="Analyze a Roblox avatar export ZIP")
    p.add_argument("input")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("prepare", help="Securely extract and create Blender/rig reconstruction files")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("pmx", help="Create an experimental PMX 2.0 model with reconstructed rigid weights")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_pmx)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
