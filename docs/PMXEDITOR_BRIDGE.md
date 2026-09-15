# PMXEditor bridge

Roblox Avatar Conversion Kit can use a **user-supplied PMXEditor installation on Windows** as an additional acceptance and visual-validation layer. PMXEditor itself is not bundled or redistributed by this project.

The bridge was designed against PMXEditor 0.2.5.4f English / 2.0. Static inspection confirmed both x86/x64 executables, the official `PEPlugin.dll` API, `PmxLib.dll`, CSScript, plugin documentation, and PMXEditor startup support for a `.pmx` path.

## What the bridge does

`RackPmxBridge.dll` is an AnyCPU PEPlugin built locally from source against the `PEPlugin.dll` already present in the user's PMXEditor folder. It can run at PMXEditor startup, wait for the requested PMX to become the active model, retrieve PMXEditor's own `IPXPmx` state, report object counts, and optionally re-save the model through PMXEditor's own serializer.

The Python side can also capture the visible PMXEditor window to PNG on Windows. This is a screen capture, so the editor window must be visible and unobscured; it is intended for regression comparison, not headless CI rendering.

## Commands

```powershell
# Safe/static inspection: does not execute PMXEditor
rack-pmxeditor inspect C:\Tools\PmxEditor_2.0.zip

# One-time bridge installation (compiles with .NET Framework 4 csc.exe)
rack-pmxeditor install --editor C:\Tools\PmxEditor

# Open a model in PMXEditor, generate a JSON report, have PMXEditor re-save it,
# keep the editor open, and capture what is visible on screen.
rack-pmxeditor validate .\Diane_v0.3.2.pmx `
  --editor C:\Tools\PmxEditor `
  --report .\Diane.pmxeditor-report.json `
  --resave .\Diane.pmxeditor-resaved.pmx `
  --screenshot .\Diane.pmxeditor.png

# Add --close for unattended validation after the report is written.
```

## Trust and safety boundary

The converter does not download, bundle, or silently execute a PMXEditor binary. `inspect` is static. `install` and `validate` are Windows-only and require a path chosen by the user. The bridge source is part of this repository and is compiled locally into PMXEditor's `_plugin/RACKBridge` folder. The only automatic PMXEditor launch occurs when the user explicitly runs `rack-pmxeditor validate`.

## Why this helps

The built-in PMX writer still performs its own structural validation, but PMXEditor adds a second implementation. A successful bridge report proves PMXEditor accepted the generated PMX into its object model. `--resave` then proves PMXEditor's own PMX serializer can write that model back out. `--screenshot` gives us a reproducible visual checkpoint for checking silhouette, hair and accessory placement, materials, and rig display against the original Roblox avatar.
