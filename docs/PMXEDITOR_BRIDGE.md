# PMXEditor bridge

Roblox Avatar Conversion Kit can use a **user-supplied PMXEditor installation on Windows** as an additional acceptance and visual-validation layer. PMXEditor itself is not bundled or redistributed by this project.

The bridge was designed against PMXEditor 0.2.5.4f English / 2.0. Static inspection confirmed both x86/x64 executables, the official `PEPlugin.dll` API, `PmxLib.dll`, CSScript, plugin documentation, and PMXEditor startup support for a `.pmx` path.

## What the bridge does

`RackPmxBridge.dll` is an AnyCPU PEPlugin built locally from source against the `PEPlugin.dll` already present in the user's PMXEditor folder. It can run at PMXEditor startup, wait for the requested PMX to become the active model, retrieve PMXEditor's own `IPXPmx` state, report object counts, and optionally re-save the model through PMXEditor's own serializer.

The Python side can also capture the visible PMXEditor window to PNG on Windows. This is a screen capture, so the editor window must be visible and unobscured; it is intended for regression comparison, not headless CI rendering.

## One-command conversion + PMXEditor validation

As of v0.3.4, the normal `rack pmx` command can hand the freshly generated PMX directly to PMXEditor:

```powershell
rack pmx Diane.zip -o .\output\Diane.pmx `
  --pmxeditor "C:\Tools\PmxEditor"
```

By default this keeps the original converter PMX untouched and creates sidecars next to it:

- `Diane.pmxeditor-report.json` — PMXEditor's acceptance/object-count report
- `Diane.pmxeditor.pmx` — PMXEditor's own re-serialized copy
- `Diane.pmxeditor.png` — screenshot of the visible PMXEditor window

The command also compares PMXEditor's parsed counts with the converter's own generation statistics for vertices, materials, bones, morphs, rigid bodies, and joints. A mismatch makes the command return a non-zero exit code while preserving all files for debugging.

Useful options:

```powershell
# Close PMXEditor after validation/screenshot
rack pmx Diane.zip -o .\output\Diane.pmx --pmxeditor "C:\Tools\PmxEditor" --pmxeditor-close

# Keep the report but skip PMXEditor re-save or screenshot
rack pmx Diane.zip -o .\output\Diane.pmx --pmxeditor "C:\Tools\PmxEditor" --no-pmxeditor-resave
rack pmx Diane.zip -o .\output\Diane.pmx --pmxeditor "C:\Tools\PmxEditor" --no-pmxeditor-screenshot
```

## Standalone bridge commands

```powershell
# Safe/static inspection: does not execute PMXEditor
rack-pmxeditor inspect C:\Tools\PmxEditor_2.0.zip

# One-time bridge installation (compiles with .NET Framework 4 csc.exe)
rack-pmxeditor install --editor C:\Tools\PmxEditor

# Open an existing model in PMXEditor and generate explicit outputs
rack-pmxeditor validate .\Diane.pmx `
  --editor C:\Tools\PmxEditor `
  --report .\Diane.pmxeditor-report.json `
  --resave .\Diane.pmxeditor-resaved.pmx `
  --screenshot .\Diane.pmxeditor.png
```

## Trust and safety boundary

The converter does not download, bundle, or silently execute a PMXEditor binary. `inspect` is static. `install` and PMXEditor-backed validation are Windows-only and require a path chosen by the user. The bridge source is part of this repository and is compiled locally into PMXEditor's `_plugin/RACKBridge` folder.

When `--pmxeditor` is explicitly supplied to `rack pmx`, launching PMXEditor is part of that requested conversion command. Without that flag, normal PMX conversion remains completely independent of PMXEditor.

## Why this helps

The built-in PMX writer still performs its own structural validation, but PMXEditor adds a second implementation. A successful bridge report proves PMXEditor accepted the generated PMX into its object model. The PMXEditor-resaved copy proves its own serializer can write that model back out. The screenshot gives us a reproducible visual checkpoint for comparing silhouette, hair and accessory placement, materials, and rig display against the original Roblox avatar.
