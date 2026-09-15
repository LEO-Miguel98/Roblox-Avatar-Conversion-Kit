# Roblox Avatar Conversion Kit

A local-first toolkit for turning a **Roblox avatar export package** (`OBJ + MTL + textures + avatar_manifest.json`) into files that are easier to use in **MMD**, **Blender**, **GLB**, and **VTubing / VRM** workflows.

> **Current status: v0.2 prototype.** Geometry, materials, textures, R15 structure, accessory weld targets, reconstructed humanoid bones, smooth body weights, MMD leg IK, and Blender/VRM helpers are implemented. Roblox OBJ exports do **not** contain original skin weights, so generated weights are reconstructed and should still be reviewed before production use.

## What it does

- Securely validates and extracts user-provided ZIP packages.
- Reads the exporter manifest instead of guessing only from OBJ geometry.
- Reconstructs a humanoid skeleton from R15 body part positions.
- Matches `Rig*` OBJ groups back to body parts using transformed MeshPart bounds.
- Matches `Handle*` groups to accessories and follows Roblox `AccessoryWeld` targets.
- Reconstructs **smooth body weights with up to four bone influences** while keeping accessories rigid.
- Creates an experimental **PMX 2.0** file with BDEF1/BDEF2/BDEF4 weights, Japanese MMD bone aliases, center bone, and leg IK controllers.
- Generates a Blender build script with improved bone tails, smooth skinning, VRM 1.0 humanoid mapping, and rest-pose diagnostics.
- Can have the generated Blender script export a **GLB** automatically.
- Never downloads arbitrary `meshId` / `textureId` URLs from the manifest.

## Quick start

```bash
python -m pip install -e .

# Inspect an export and reconstructed weight statistics
rack inspect Diane.zip

# Prepare an editable Blender workspace
rack prepare Diane.zip -o output/diane

# Prepare Blender workflow and automatically export a GLB when the generated script is run
rack prepare Diane.zip -o output/diane --glb Diane.glb

# Direct MMD conversion with reconstructed smooth weights and leg IK
rack pmx Diane.zip -o output/diane/Diane.pmx

# Compatibility fallback to the v0.1 rigid weighting behavior
rack pmx Diane.zip -o output/diane/Diane-rigid.pmx --rigid-weights
```

For Blender, open Blender and run `output/diane/build_in_blender.py` from the Scripting workspace. If the VRM Add-on for Blender is installed, the script assigns the VRM 1.0 humanoid bone slots it can identify. It also warns when the imported Roblox rest pose is far from a T/A-pose instead of pretending the model is production-ready.

## Why reconstruction is necessary

OBJ stores geometry and material references, not an armature or skin weights. The exporter manifest preserves Roblox body-part transforms, Motor6D/accessory weld information, attachment metadata, and reconstruction hints. This kit combines those sources rather than claiming lost weights can be recovered exactly.

v0.2 improves deformation by blending body vertices against the reconstructed bone chain. Accessory meshes remain rigidly attached to their inferred weld target so hats, hair pieces, clothing accessories, and similar parts do not deform like skin.

## Conversion targets

| Target | Status | Notes |
|---|---|---|
| Inspection / reconstruction plan | ✅ | Includes smooth-weight diagnostics |
| Blender scene builder | ✅ prototype | Armature + reconstructed smooth body weights |
| PMX 2.0 | ✅ experimental | Smooth weights, Japanese aliases, center + leg IK |
| GLB/glTF | ✅ via Blender | Optional automatic GLB export |
| VRM 1.0 | ➡️ via Blender | Humanoid mapping when VRM Add-on is installed; rest-pose review still required |
| VMD / Roblox animation conversion | Planned | Requires animation source data |
| MMD morphs / expressions | Planned | Face mesh/morph reconstruction pass |
| MMD physics | Planned | Hair/tail/accessory rigid-body generation |
| VRM expressions / spring bones | Planned | VTuber-specific finishing pass |

## Diane validation

The uploaded Diane export was used as the real-world regression model without publishing Diane's assets to this public repository. The v0.2 conversion preserves **36,773 triangles and 16 materials**, creates **20 PMX bones including two leg IK controllers**, and uses reconstructed BDEF2/BDEF4 influences around body joints while keeping accessory groups rigid.

## Security model

The converter treats avatar packages as untrusted input. ZIP extraction blocks path traversal and symlinks, limits file count and expanded size, and only accepts known model/image data file types. It does not execute files from an archive and does not fetch external URLs stored in manifests. See [SECURITY.md](SECURITY.md).

## Asset rights

Only convert avatars and assets you own or have permission to modify/use outside Roblox. This project does not bypass Roblox permissions, encryption, authentication, or protected asset delivery.

## Development

```bash
python -m unittest discover -s tests -v
```

The Python core intentionally has no runtime third-party dependency, which keeps installation small and reduces supply-chain risk.
