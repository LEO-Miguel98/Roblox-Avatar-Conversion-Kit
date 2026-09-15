from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from importlib.resources import files
from dataclasses import dataclass
from pathlib import Path


class PmxEditorBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PmxEditorInstall:
    root: Path
    executable: Path
    peplugin: Path


def discover_pmxeditor(path: Path) -> PmxEditorInstall:
    path = Path(path).expanduser().resolve()
    if path.is_file():
        if path.name.lower() not in {"pmxeditor.exe", "pmxeditor_x64.exe"}:
            raise PmxEditorBridgeError(f"Not a PMXEditor executable: {path}")
        root = path.parent
        executable = path
    else:
        root = path
        preferred = root / "PmxEditor_x64.exe"
        fallback = root / "PmxEditor.exe"
        executable = preferred if preferred.is_file() else fallback
    if not root.is_dir() or not executable.is_file():
        raise PmxEditorBridgeError(
            "PMXEditor folder must contain PmxEditor_x64.exe or PmxEditor.exe"
        )
    peplugin = root / "Lib" / "PEPlugin" / "PEPlugin.dll"
    if not peplugin.is_file():
        raise PmxEditorBridgeError(f"PEPlugin.dll not found under {root}")
    return PmxEditorInstall(root=root, executable=executable, peplugin=peplugin)


def inspect_package(path: Path) -> dict:
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        install = discover_pmxeditor(path)
        return {
            "kind": "directory",
            "root": str(install.root),
            "executable": install.executable.name,
            "peplugin": str(install.peplugin),
            "x64": (install.root / "PmxEditor_x64.exe").is_file(),
            "x86": (install.root / "PmxEditor.exe").is_file(),
            "plugin_api": True,
        }
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise PmxEditorBridgeError(f"PMXEditor package not found: {path}")
    with zipfile.ZipFile(path) as zf:
        names = [name.replace("\\", "/") for name in zf.namelist()]
    roots = set()
    for name in names:
        if name.endswith("/PmxEditor_x64.exe") or name.endswith("/PmxEditor.exe"):
            roots.add(name.rsplit("/", 1)[0])
    candidates = []
    for root in sorted(roots):
        prefix = root + "/"
        candidate = {
            "root": root,
            "x64": prefix + "PmxEditor_x64.exe" in names,
            "x86": prefix + "PmxEditor.exe" in names,
            "plugin_api": prefix + "Lib/PEPlugin/PEPlugin.dll" in names,
            "pmx_library": prefix + "Lib/System/PmxLib.dll" in names,
            "csscript": prefix + "_plugin/CSScript/CSScript.dll" in names,
        }
        if candidate["plugin_api"]:
            candidates.append(candidate)
    if not candidates:
        raise PmxEditorBridgeError("ZIP does not contain a recognizable PMXEditor + PEPlugin layout")
    selected = candidates[0]
    return {
        "kind": "zip",
        "archive": str(path),
        "file_count": len(names),
        **selected,
    }


def _framework_csc() -> Path:
    if os.name != "nt":
        raise PmxEditorBridgeError("PMXEditor bridge compilation is supported on Windows only")
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PmxEditorBridgeError(
        ".NET Framework 4 C# compiler was not found. Install/enable .NET Framework 4.x."
    )


def install_bridge(editor: Path, *, source: Path | None = None) -> dict:
    install = discover_pmxeditor(editor)
    if os.name != "nt":
        raise PmxEditorBridgeError("PMXEditor itself and its bridge are Windows-only")

    plugin_dir = install.root / "_plugin" / "RACKBridge"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    source_path = plugin_dir / "RackPmxBridge.cs"
    if source is None:
        source_path.write_text(
            files("roblox_avatar_conversion_kit")
            .joinpath("pmxeditor_assets", "RackPmxBridge.cs")
            .read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        source = Path(source)
        if not source.is_file():
            raise PmxEditorBridgeError(f"Bridge source not found: {source}")
        shutil.copy2(source, source_path)

    output_dll = plugin_dir / "RackPmxBridge.dll"
    csc = _framework_csc()
    command = [
        str(csc),
        "/nologo",
        "/target:library",
        "/platform:anycpu",
        f"/out:{output_dll}",
        f"/reference:{install.peplugin}",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Windows.Forms.dll",
        str(source_path),
    ]
    completed = subprocess.run(command, cwd=plugin_dir, capture_output=True, text=True)
    if completed.returncode != 0 or not output_dll.is_file():
        raise PmxEditorBridgeError(
            "Could not compile RackPmxBridge.dll:\n"
            + (completed.stdout or "")
            + (completed.stderr or "")
        )
    return {
        "editor": str(install.executable),
        "plugin": str(output_dll),
        "compiler": str(csc),
    }


def _powershell_capture(pid: int, output: Path) -> None:
    script_text = (
        files("roblox_avatar_conversion_kit")
        .joinpath("pmxeditor_assets", "capture_window.ps1")
        .read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="rack-pmxeditor-") as td:
        script = Path(td) / "capture_window.ps1"
        script.write_text(script_text, encoding="utf-8")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProcessId",
            str(pid),
            "-OutputPath",
            str(Path(output).resolve()),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise PmxEditorBridgeError(
            "PMXEditor screenshot capture failed:\n"
            + (completed.stdout or "")
            + (completed.stderr or "")
        )


def validate_with_pmxeditor(
    model: Path,
    *,
    editor: Path,
    report: Path | None = None,
    resave: Path | None = None,
    screenshot: Path | None = None,
    timeout: float = 45.0,
    keep_open: bool = True,
    install_if_missing: bool = True,
) -> dict:
    if os.name != "nt":
        raise PmxEditorBridgeError("PMXEditor validation is available on Windows only")
    model = Path(model).expanduser().resolve()
    if not model.is_file() or model.suffix.lower() != ".pmx":
        raise PmxEditorBridgeError(f"PMX model not found: {model}")
    install = discover_pmxeditor(editor)
    plugin = install.root / "_plugin" / "RACKBridge" / "RackPmxBridge.dll"
    if not plugin.is_file():
        if not install_if_missing:
            raise PmxEditorBridgeError("RackPmxBridge.dll is not installed")
        install_bridge(install.root)

    report = Path(report or model.with_suffix(".pmxeditor-report.json")).expanduser().resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        report.unlink()
    if resave is not None:
        resave = Path(resave).expanduser().resolve()
        resave.parent.mkdir(parents=True, exist_ok=True)
    if screenshot is not None:
        screenshot = Path(screenshot).expanduser().resolve()
        screenshot.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["RACK_PMX_TARGET"] = str(model)
    env["RACK_PMX_REPORT"] = str(report)
    env["RACK_PMX_TIMEOUT"] = str(max(5, int(timeout)))
    env["RACK_PMX_AUTOCLOSE"] = "0" if keep_open else "1"
    if resave is not None:
        env["RACK_PMX_RESAVE"] = str(resave)
    else:
        env.pop("RACK_PMX_RESAVE", None)

    process = subprocess.Popen(
        [str(install.executable), str(model)],
        cwd=install.root,
        env=env,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if report.is_file():
            break
        if process.poll() is not None:
            break
        time.sleep(0.2)
    if not report.is_file():
        raise PmxEditorBridgeError(
            f"PMXEditor did not produce a bridge report within {timeout:.0f}s (exit={process.poll()})"
        )

    result = json.loads(report.read_text(encoding="utf-8"))
    result["editor_pid"] = process.pid
    result["editor_executable"] = str(install.executable)
    result["report"] = str(report)
    if screenshot is not None:
        # DirectX-backed windows must be visible and unobscured for this capture path.
        time.sleep(0.8)
        _powershell_capture(process.pid, screenshot)
        result["screenshot"] = str(screenshot)
    return result
