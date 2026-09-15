# PMXEditor 2.0 package inspection

The user-supplied `PmxEditor_2.0.zip` was inspected statically before integration. No uploaded EXE or DLL was executed during inspection.

Observed layout:

- PMXEditor 0.2.5.4f English / 2.0 portable folder.
- `PmxEditor.exe` (32-bit) and `PmxEditor_x64.exe` (64-bit).
- Official `Lib/PEPlugin/PEPlugin.dll` plugin API and XML documentation.
- `Lib/System/PmxLib.dll` PMX implementation.
- CSScript plugin and sample scripts for PMX model access/editing.
- PMXEditor documentation states that a `.pmx` or `.pmd` path can be supplied as a startup option.
- PEPlugin documentation exposes PMX model retrieval, update, file open/save, plugin boot-at-startup, and `IPXPmx.FromFile` / `IPXPmx.ToFile` operations.

The integration deliberately references the user's own local `PEPlugin.dll` when compiling `RackPmxBridge.dll`; PMXEditor binaries are not copied into this repository.
