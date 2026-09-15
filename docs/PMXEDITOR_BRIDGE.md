# PMXEditor bridge

Roblox Avatar Conversion Kit can use a **user-supplied PMXEditor installation on Windows** as an additional acceptance and visual-validation layer. PMXEditor itself is not bundled or redistributed by this project.

The bridge was designed against PMXEditor 0.2.5.4f English / 2.0. Static inspection confirmed both x86/x64 executables, the official `PEPlugin.dll` API, `PmxLib.dll`, CSScript, plugin documentation, PMXEditor startup support for a `.pmx` path, and plugin-accessible view/camera controls.

## What the bridge does

`RackPmxBridge.dll` is an AnyCPU PEPlugin built locally from source against the `PEPlugin.dll` already present in the user's PMXEditor folder. It can run at PMXEditor startup, wait for the requested PMX to become the active model, retrieve PMXEditor's own `IPXPmx` state, report object counts, and optionally re-save the model through PMXEditor's own serializer.

The Python side can also capture the visible PMXEditor window to PNG on Windows. This is a screen capture, so the editor window must be visible and unobscured; it is intended for regression comparison, not headless CI rendering.

## Standardized visual capture

As of v0.3.5 the bridge prepares PMXEditor's viewport before a validation screenshot. It computes the model bounds from PMXEditor's own vertex data, centers the camera on the model, uses a repeatable front-facing camera distance, switches to solid rendering, and hides edit overlays such as bones, vertices, normals, weight maps, rigid bodies, and joints.

This makes repeated screenshots substantially more useful for comparing the converted silhouette against a known-good Roblox reference. View normalization is best-effort: a view-setting problem is reported as `view_error` without turning an otherwise valid PMX acceptance into a false failure. The JSON report also records whether `view_normalized` succeeded.

For advanced/manual debugging, setting the Windows environment variable `RACK_PMX_NORMALIZE_VIEW=0` before launching validation leaves PMXEditor's current view settings alone.

## One-command conversion + PMXEditor validation

The normal `rack pmx` command can hand the freshly generated PMX directly to PMXEditor:

```powershell
rack pmx Diane.zip -o .\output\Diane.pmx `
  --pmxeditor "C:\Tools\PmxEditor"
```

By default this keeps the original converter PMX untouched and creates sidecars next to it:

- `Diane.pmxeditor-report.json` — PMXEditor's acceptance/object-count report
- `Diane.pmxeditor.pmx` — PMXEditor's own re-serialized copy
- `Diane.pmxeditor.png` — standardized screenshot of the visible PMXEditor window

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
rack-pmxeditor inspect C:\Tools\PmxEditor_2.0.zip
rack-pmxeditor install --editor C:\Tools\PmxEditor
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

The built-in PMX writer still performs its own structural validation, but PMXEditor adds a second implementation. A successful bridge report proves PMXEditor accepted the generated PMX into its object model. The PMXEditor-resaved copy proves its own serializer can write that model back out. The standardized screenshot gives us a repeatable visual checkpoint for comparing silhouette, hair and accessory placement, materials, and rig display against the original Roblox avatar.
