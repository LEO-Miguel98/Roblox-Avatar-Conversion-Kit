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
from .weights import compute_group_vertex_weights, summarize_weights


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
        smooth = compute_group_vertex_weights(mesh, bones, mapping, smooth=True)
        result = {
            "package": package.name,
            "archive": zip_info,
            "manifest_stats": package.manifest.get("stats", {}),
            "obj": {"vertices": len(mesh.vertices), "triangles": len(mesh.faces), "groups": len(mesh.group_vertex_indices())},
            "materials": len(materials),
            "manifest_to_obj_translation": translation,
            "group_to_bone": mapping,
            "bones": [bone.name for bone in bones],
            "reconstructed_weights": summarize_weights(smooth),
            "warnings": warnings,
        }
    print(json.dumps(result, indent=2))
    return 0


def cmd_prepare(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    package, warnings, mesh, materials, translation, bones, mapping = _load(source, output)
    smooth_weights = not args.rigid_weights
    plan = {
        "package": package.name,
        "source_obj": str(package.obj_path.relative_to(output)),
        "translation": translation,
        "group_to_bone": mapping,
        "bones": [{"name": bone.name, "parent": bone.parent, "position": bone.position} for bone in bones],
        "weight_mode": "smooth" if smooth_weights else "rigid",
        "weight_summary": summarize_weights(compute_group_vertex_weights(mesh, bones, mapping, smooth=smooth_weights)),
        "warnings": warnings,
    }
    (output / "conversion-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    glb_path = output / args.glb if args.glb else None
    write_blender_script(
        output / "build_in_blender.py",
        obj_path=package.obj_path,
        bones=bones,
        group_to_bone=mapping,
        smooth_weights=smooth_weights,
        glb_path=glb_path,
    )
    print(f"Prepared: {output}")
    if glb_path:
        print(f"Run build_in_blender.py inside Blender to build and export: {glb_path}")
    return 0


def cmd_pmx(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rack-") as td:
        package, warnings, mesh, materials, translation, bones, mapping = _load(source, Path(td))
        stats = write_pmx(
            output,
            model_name=package.name,
            mesh=mesh,
            materials=materials,
            bones=bones,
            group_to_bone=mapping,
            smooth_weights=not args.rigid_weights,
        )
        for material in materials.values():
            if material.map_kd:
                src = package.root / material.map_kd
                if src.is_file():
                    shutil.copy2(src, output.parent / src.name)
    print(json.dumps({"output": str(output), "stats": stats, "warnings": warnings}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rack", description="Roblox avatar conversion toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Analyze a Roblox avatar export ZIP")
    inspect_parser.add_argument("input")
    inspect_parser.set_defaults(func=cmd_inspect)

    prepare_parser = sub.add_parser("prepare", help="Securely extract and create Blender/rig reconstruction files")
    prepare_parser.add_argument("input")
    prepare_parser.add_argument("-o", "--output", required=True)
    prepare_parser.add_argument("--rigid-weights", action="store_true", help="Use v0.1 single-bone weights instead of reconstructed smooth weights")
    prepare_parser.add_argument("--glb", metavar="FILENAME", help="Have the generated Blender script export a GLB after building the rig")
    prepare_parser.set_defaults(func=cmd_prepare)

    pmx_parser = sub.add_parser("pmx", help="Create an MMD PMX 2.0 model with reconstructed weights and leg IK")
    pmx_parser.add_argument("input")
    pmx_parser.add_argument("-o", "--output", required=True)
    pmx_parser.add_argument("--rigid-weights", action="store_true", help="Use v0.1 single-bone weights instead of reconstructed smooth weights")
    pmx_parser.set_defaults(func=cmd_pmx)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
