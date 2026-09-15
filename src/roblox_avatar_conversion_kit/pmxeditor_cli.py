from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pmxeditor import (
    PmxEditorBridgeError,
    inspect_package,
    install_bridge,
    validate_with_pmxeditor,
)


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_inspect(args) -> int:
    _print(inspect_package(Path(args.path)))
    return 0


def cmd_install(args) -> int:
    _print(install_bridge(Path(args.editor)))
    return 0


def cmd_validate(args) -> int:
    result = validate_with_pmxeditor(
        Path(args.model),
        editor=Path(args.editor),
        report=Path(args.report) if args.report else None,
        resave=Path(args.resave) if args.resave else None,
        screenshot=Path(args.screenshot) if args.screenshot else None,
        timeout=args.timeout,
        keep_open=not args.close,
        install_if_missing=not args.no_install,
    )
    _print(result)
    return 0 if result.get("status") == "accepted" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rack-pmxeditor",
        description="PMXEditor bridge for Roblox Avatar Conversion Kit",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Statically inspect a PMXEditor folder or ZIP")
    inspect_parser.add_argument("path")
    inspect_parser.set_defaults(func=cmd_inspect)

    install_parser = sub.add_parser("install", help="Compile/install the RACK PEPlugin bridge")
    install_parser.add_argument("--editor", required=True, help="PMXEditor folder or executable")
    install_parser.set_defaults(func=cmd_install)

    validate_parser = sub.add_parser(
        "validate", help="Open a PMX in PMXEditor and obtain an acceptance report"
    )
    validate_parser.add_argument("model")
    validate_parser.add_argument("--editor", required=True, help="PMXEditor folder or executable")
    validate_parser.add_argument("--report", help="JSON report output path")
    validate_parser.add_argument("--resave", help="Resave through PMXEditor's own PMX serializer")
    validate_parser.add_argument("--screenshot", help="Capture the visible PMXEditor window to PNG")
    validate_parser.add_argument("--timeout", type=float, default=45.0)
    validate_parser.add_argument("--close", action="store_true", help="Close PMXEditor after reporting")
    validate_parser.add_argument(
        "--no-install", action="store_true", help="Do not auto-install the bridge when missing"
    )
    validate_parser.set_defaults(func=cmd_validate)
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
