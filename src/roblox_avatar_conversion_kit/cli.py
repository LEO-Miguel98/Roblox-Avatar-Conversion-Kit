from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from .archive import inspect_zip, safe_extract_zip
from .blender import write_blender_script
from .features import analyze_features
from .geometry_only import infer_geometry_only_avatar, normalize_geometry_only_mesh
from .manifest import discover_package, validate_manifest
from .obj import parse_mtl, parse_obj
from .pmx import write_pmx
from .pmxeditor import PmxEditorBridgeError, validate_with_pmxeditor
from .pmxeditor_pipeline import compare_pmxeditor_counts, default_validation_outputs
from .rig import build_bones, infer_manifest_translation, map_groups_to_bones
from .weights import compute_group_vertex_weights, primary_weight_diagnostics, summarize_weights


def _load(zip_path: Path, workdir: Path):
    safe_extract_zip(zip_path, workdir)
    package = discover_package(workdir)
    warnings = validate_manifest(package.manifest)
    mesh = parse_obj(package.obj_path)
    materials = parse_mtl(package.mtl_path)

    if package.manifest:
        translation = infer_manifest_translation(package.manifest, mesh)
        bones = build_bones(package.manifest, translation)
        mapping = map_groups_to_bones(package.manifest, mesh, translation)
        features = analyze_features(package.manifest, mesh, translation, bones)
    else:
        translation = normalize_geometry_only_mesh(mesh)
        bones, mapping, features, inferred_warnings = infer_geometry_only_avatar(mesh)
        warnings.extend(inferred_warnings)

    if not features.native_expression_source:
        warnings.append(
            "OBJ contains no native blend-shape deltas; generated facial expressions are editable/reconstructed controls rather than original source morphs."
        )
    return package, warnings, mesh, materials, translation, bones, mapping, features


def cmd_inspect(args) -> int:
    source = Path(args.input)
    zip_info = inspect_zip(source)
    with tempfile.TemporaryDirectory(prefix="rack-") as td:
        package, warnings, mesh, materials, translation, bones, mapping, features = _load(source, Path(td))
        smooth = compute_group_vertex_weights(mesh, bones, mapping, smooth=True)
        result = {
            "package": package.name,
            "archive": zip_info,
            "manifest_mode": "manifest" if package.manifest else "geometry-only",
            "manifest_stats": package.manifest.get("stats", {}),
            "obj": {
                "vertices": len(mesh.vertices),
                "triangles": len(mesh.faces),
                "groups": len(mesh.group_vertex_indices()),
            },
            "materials": len(materials),
            "model_translation": translation,
            "group_to_bone": mapping,
            "bones": [bone.name for bone in bones],
            "reconstructed_weights": summarize_weights(smooth),
            "primary_weight_diagnostics": primary_weight_diagnostics(mesh, smooth, mapping),
            "vtuber_features": features.to_dict(),
            "warnings": warnings,
        }
    print(json.dumps(result, indent=2))
    return 0


def cmd_prepare(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    package, warnings, mesh, materials, translation, bones, mapping, features = _load(source, output)
    if not package.manifest:
        raise ValueError(
            "Geometry-only ZIPs are currently supported by 'rack inspect' and 'rack pmx'. "
            "Blender/VRM prepare still requires avatar_manifest.json so the generated Blender script can reproduce source transforms safely."
        )
    smooth_weights = not args.rigid_weights
    accessory_physics = not args.no_physics
    expression_scaffold = not args.no_expression_scaffold
    prepared_weights = compute_group_vertex_weights(mesh, bones, mapping, smooth=smooth_weights)
    plan = {
        "package": package.name,
        "source_obj": str(package.obj_path.relative_to(output)),
        "translation": translation,
        "group_to_bone": mapping,
        "bones": [
            {"name": bone.name, "parent": bone.parent, "position": bone.position}
            for bone in bones
        ],
        "weight_mode": "smooth" if smooth_weights else "rigid",
        "weight_summary": summarize_weights(prepared_weights),
        "primary_weight_diagnostics": primary_weight_diagnostics(mesh, prepared_weights, mapping),
        "accessory_physics": accessory_physics,
        "expression_scaffold": expression_scaffold,
        "vtuber_features": features.to_dict(),
        "warnings": warnings,
    }
    (output / "conversion-plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )
    glb_path = output / args.glb if args.glb else None
    vrm_path = output / args.vrm if args.vrm else None
    write_blender_script(
        output / "build_in_blender.py",
        obj_path=package.obj_path,
        bones=bones,
        group_to_bone=mapping,
        smooth_weights=smooth_weights,
        glb_path=glb_path,
        vrm_path=vrm_path,
        features=features,
        accessory_physics=accessory_physics,
        expression_scaffold=expression_scaffold,
        model_name=package.name,
    )
    print(f"Prepared: {output}")
    if glb_path:
        print(f"Run build_in_blender.py inside Blender to build and export: {glb_path}")
    if vrm_path:
        print(
            "Run build_in_blender.py inside Blender with the VRM Add-on installed "
            f"to export: {vrm_path}"
        )
    return 0


def cmd_pmx(args) -> int:
    source = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rack-") as td:
        package, warnings, mesh, materials, translation, bones, mapping, features = _load(source, Path(td))
        stats = write_pmx(
            output,
            model_name=package.name,
            mesh=mesh,
            materials=materials,
            bones=bones,
            group_to_bone=mapping,
            smooth_weights=not args.rigid_weights,
            features=features,
            accessory_physics=not args.no_physics,
        )
        for material in materials.values():
            if material.map_kd:
                src = package.root / material.map_kd
                if src.is_file():
                    shutil.copy2(src, output.parent / src.name)

    pmxeditor_result = None
    exit_code = 0
    if args.pmxeditor:
        defaults = default_validation_outputs(output)
        report = Path(args.pmxeditor_report) if args.pmxeditor_report else defaults["report"]
        resave = None if args.no_pmxeditor_resave else defaults["resave"]
        screenshot = None if args.no_pmxeditor_screenshot else defaults["screenshot"]
        pmxeditor_result = validate_with_pmxeditor(
            output,
            editor=Path(args.pmxeditor),
            report=report,
            resave=resave,
            screenshot=screenshot,
            timeout=args.pmxeditor_timeout,
            keep_open=not args.pmxeditor_close,
            install_if_missing=not args.no_pmxeditor_install,
        )
        comparison = compare_pmxeditor_counts(stats, pmxeditor_result)
        pmxeditor_result["count_comparison"] = comparison
        if pmxeditor_result.get("status") != "accepted" or not comparison["matches"]:
            exit_code = 2

    print(json.dumps({
        "output": str(output),
        "stats": stats,
        "warnings": warnings,
        "pmxeditor": pmxeditor_result,
    }, indent=2))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rack", description="Roblox avatar conversion toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Analyze a Roblox avatar export ZIP")
    inspect_parser.add_argument("input")
    inspect_parser.set_defaults(func=cmd_inspect)

    prepare_parser = sub.add_parser(
        "prepare", help="Securely extract and create Blender/VRM reconstruction files"
    )
    prepare_parser.add_argument("input")
    prepare_parser.add_argument("-o", "--output", required=True)
    prepare_parser.add_argument(
        "--rigid-weights",
        action="store_true",
        help="Use v0.1 single-bone weights instead of reconstructed smooth weights",
    )
    prepare_parser.add_argument(
        "--glb",
        metavar="FILENAME",
        help="Have the generated Blender script export a GLB after building the rig",
    )
    prepare_parser.add_argument(
        "--vrm",
        metavar="FILENAME",
        help="Have the generated Blender script export VRM 1.0 when the VRM Add-on is installed",
    )
    prepare_parser.add_argument(
        "--no-physics",
        action="store_true",
        help="Disable reconstructed accessory/hair spring physics",
    )
    prepare_parser.add_argument(
        "--no-expression-scaffold",
        action="store_true",
        help="Do not create editable zero-delta facial expression shape keys",
    )
    prepare_parser.set_defaults(func=cmd_prepare)

    pmx_parser = sub.add_parser(
        "pmx",
        help="Create an MMD PMX 2.0 model with reconstructed weights, gaze controls, IK, and accessory physics",
    )
    pmx_parser.add_argument("input")
    pmx_parser.add_argument("-o", "--output", required=True)
    pmx_parser.add_argument(
        "--rigid-weights",
        action="store_true",
        help="Use v0.1 single-bone weights instead of reconstructed smooth weights",
    )
    pmx_parser.add_argument(
        "--no-physics",
        action="store_true",
        help="Disable generated accessory/hair PMX rigid bodies and joints",
    )
    pmx_parser.add_argument(
        "--pmxeditor",
        metavar="PATH",
        help="On Windows, validate the generated PMX with this PMXEditor folder/executable",
    )
    pmx_parser.add_argument("--pmxeditor-report", help="Override the PMXEditor JSON report path")
    pmx_parser.add_argument(
        "--pmxeditor-timeout", type=float, default=45.0,
        help="Seconds to wait for PMXEditor acceptance (default: 45)",
    )
    pmx_parser.add_argument(
        "--pmxeditor-close", action="store_true",
        help="Close PMXEditor after the acceptance report and optional screenshot are produced",
    )
    pmx_parser.add_argument(
        "--no-pmxeditor-install", action="store_true",
        help="Do not auto-install the RACK PMXEditor bridge when it is missing",
    )
    pmx_parser.add_argument(
        "--no-pmxeditor-resave", action="store_true",
        help="Do not create a PMXEditor-resaved sidecar PMX",
    )
    pmx_parser.add_argument(
        "--no-pmxeditor-screenshot", action="store_true",
        help="Do not capture the visible PMXEditor window to PNG",
    )
    pmx_parser.set_defaults(func=cmd_pmx)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except PmxEditorBridgeError as exc:
        print(f"PMXEditor bridge error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
