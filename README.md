# Roblox Avatar Conversion Kit

A local-first toolkit for turning a **Roblox avatar export package** (`OBJ + MTL + textures + avatar_manifest.json`) into files that are easier to use in **MMD**, **Blender**, **GLB**, and **VTubing / VRM** workflows.

> **Current status: v0.1 prototype.** Geometry, materials, textures, R15 structure, accessory weld targets, and a reconstructed skeleton are handled. Roblox OBJ exports do **not** contain original skin weights, so generated weights are reconstructed and should be reviewed before production use.

## What it does

- Securely validates and extracts user-provided ZIP packages.
- Reads the exporter manifest instead of guessing only from OBJ geometry.
- Reconstructs a humanoid skeleton from R15 body part positions.
- Matches `Rig*` OBJ groups back to body parts using transformed MeshPart bounds.
- Matches `Handle*` groups to accessories and follows Roblox `AccessoryWeld` targets.
- Creates an **experimental PMX 2.0** file for MMD.
- Generates a Blender build script that creates an armature and baseline weights.
- Detects the VRM Add-on for Blender and assigns VRM 1.0 humanoid bones when available.
- Never downloads arbitrary `meshId` / `textureId` URLs from the manifest.

## Quick start

```bash
python -m pip install -e .

# Inspect an export first
rack inspect Diane.zip

# Prepare an editable workspace + Blender build script
rack prepare Diane.zip -o output/diane

# Experimental direct MMD conversion
rack pmx Diane.zip -o output/diane/Diane.pmx
```

For Blender, open Blender and run `output/diane/build_in_blender.py` from the Scripting workspace. Review the armature/weights, then export GLB normally or VRM through the VRM Add-on for Blender.

## Why reconstruction is necessary

OBJ stores geometry/material references, not an armature or skin weights. The exporter manifest preserves Roblox body-part transforms, Motor6D/accessory weld information, attachment metadata, and other reconstruction hints. This kit combines those sources rather than claiming the lost weights can be recovered exactly.

## Conversion targets

| Target | Status | Notes |
|---|---|---|
| Inspection / reconstruction plan | ✅ | Stable first-pass feature |
| Blender scene builder | ✅ prototype | Creates armature + rigid group weights |
| PMX 2.0 | 🧪 experimental | Opens as a basic MMD model; weights/physics need refinement |
| GLB/glTF | ➡️ via Blender | Blender built-in export |
| VRM 1.0 | ➡️ via Blender | Uses VRM Add-on when installed |
| VMD / Roblox animation conversion | Planned | Requires animation source data |
| MMD morphs / expressions | Planned | Face mesh/morph reconstruction pass |
| MMD physics | Planned | Hair/tail/accessory rigid-body generation |

## Security model

The converter treats avatar packages as untrusted input. ZIP extraction blocks path traversal and symlinks, limits file count and expanded size, and only accepts known model/image data file types. It does not execute files from an archive and does not fetch external URLs stored in manifests. See [SECURITY.md](SECURITY.md).

## Asset rights

Only convert avatars and assets you own or have permission to modify/use outside Roblox. This project does not bypass Roblox permissions, encryption, authentication, or protected asset delivery.

## Development

```bash
python -m unittest discover -s tests -v
```

The project intentionally starts with a Python-standard-library core to keep installation small and reduce dependency/supply-chain risk.
