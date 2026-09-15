# Roblox Avatar Conversion Kit

A local-first toolkit for turning a **Roblox avatar export package** (`OBJ + MTL + textures + avatar_manifest.json`) into files that are easier to use in **MMD**, **Blender**, **GLB**, and **VTubing / VRM** workflows.

> **Current status: v0.3.1 prototype.** The kit now reconstructs a humanoid rig, smooth body weights, MMD IK, gaze controllers, dynamic accessory physics, VRM humanoid/look-at metadata, SpringBone chains, and an editable facial-expression scaffold. Roblox OBJ exports do **not** contain original skin weights or blend-shape deltas, so generated deformation and expression data are reconstructed scaffolding and should be reviewed before production use.

## What it does

- Securely validates and extracts user-provided ZIP packages.
- Reads the exporter manifest instead of guessing only from OBJ geometry.
- Reconstructs a humanoid skeleton from R15 body part positions.
- Matches `Rig*` OBJ groups back to body parts using transformed MeshPart bounds.
- Matches `Handle*` groups to accessories and follows Roblox `AccessoryWeld` targets.
- Reconstructs **smooth body weights with up to four bone influences** while keeping ordinary accessories rigid.
- Detects likely dynamic hair, bangs, cowlicks, ears, tails, ribbons, wings, scarves, capes, and similar accessories from manifest + mesh placement.
- Creates experimental **PMX 2.0** with **UTF-16LE text by default for MMD compatibility**, BDEF1/BDEF2/BDEF4 weights, Japanese MMD bone aliases, center bone, leg IK, gaze-control bone morphs, display frames, and generated accessory rigid bodies/joints.
- Generates a Blender build script with improved bone tails, smooth skinning, editable facial expression keys, VRM 1.0 humanoid mapping, VRM LookAt, SpringBone chains, and rest-pose diagnostics.
- Can have the generated Blender script export **GLB** and, when the VRM Add-on for Blender is installed, **VRM 1.0**.
- Never downloads arbitrary `meshId` / `textureId` URLs from the manifest.

## Quick start

```bash
python -m pip install -e .

# Inspect an export, reconstructed weights, and VTuber feature plan
rack inspect Diane.zip

# Prepare an editable Blender workspace
rack prepare Diane.zip -o output/diane

# Prepare Blender and export GLB when the generated script is run
rack prepare Diane.zip -o output/diane --glb Diane.glb

# Prepare Blender and export VRM 1.0 (requires VRM Add-on for Blender)
rack prepare Diane.zip -o output/diane --vrm Diane.vrm

# Direct MMD conversion with reconstructed weights, gaze controls, IK and accessory physics
rack pmx Diane.zip -o output/diane/Diane.pmx

# Disable generated accessory physics when a model needs manual setup
rack pmx Diane.zip -o output/diane/Diane-no-physics.pmx --no-physics

# Compatibility fallback to the v0.1 rigid body-weighting behavior
rack pmx Diane.zip -o output/diane/Diane-rigid.pmx --rigid-weights
```

For Blender, open `output/diane/build_in_blender.py` in Blender's Scripting workspace and run it. If the VRM Add-on for Blender is installed, the generated script configures the humanoid bone slots it can identify, LookAt, standard expression bindings, and SpringBone chains for detected dynamic accessories.

## Facial expressions and eye tracking

OBJ does not carry native blend-shape/morph deltas. The kit therefore **does not invent facial deformation**. In the Blender/VRM path it creates standard editable zero-delta keys such as `blink`, `blinkLeft`, `blinkRight`, `happy`, `angry`, `sad`, vowel shapes, and related VRM presets, then binds them to VRM expressions. You can sculpt or replace those keys in Blender without rebuilding the conversion pipeline.

For MMD, v0.3 adds `両目` / left-eye / right-eye controller bones and four gaze bone morphs (`LookLeft`, `LookRight`, `LookUp`, `LookDown`). These controls provide a standard rigging target, but visible eye movement still depends on the avatar having eye geometry/weights that can be assigned to those controls. Texture-only Roblox eyes cannot be automatically reconstructed into true eye geometry from OBJ alone.

## Hair / tail / accessory physics

The converter uses the manifest's accessory transforms and `AccessoryWeld` targets plus OBJ group bounds to detect likely dynamic accessories. For PMX it adds conservative rigid-body and spring-joint templates. For VRM it adds SpringBone1 chains through the VRM Add-on when available. Detection is intentionally conservative and excludes obvious swords, gloves, clothing, speech bubbles, and face props.

Generated physics are **starting values**, not a substitute for model-specific tuning. Review collision behavior, stiffness, drag, gravity, pivots, and clipping in MMD/Blender before production use.

## Why reconstruction is necessary

OBJ stores geometry and material references, not an armature, skin weights, or expression deltas. The exporter manifest preserves Roblox body-part transforms, Motor6D/accessory weld information, attachment metadata, and reconstruction hints. This kit combines those sources rather than claiming lost data can be recovered exactly.

## Conversion targets

| Target | Status | Notes |
|---|---|---|
| Inspection / reconstruction plan | ✅ | Includes smooth-weight and VTuber feature diagnostics |
| Blender scene builder | ✅ prototype | Armature + reconstructed smooth body weights + expression scaffold |
| PMX 2.0 | ✅ experimental | UTF-16LE text, smooth weights, Japanese aliases, center/IK, gaze controls, display frames, accessory physics |
| GLB/glTF | ✅ via Blender | Optional automatic GLB export |
| VRM 1.0 | ✅ experimental via Blender | Humanoid map, LookAt, preset expression bindings, SpringBone and optional `.vrm` export |
| VMD / Roblox animation conversion | Planned | Requires animation source data |
| Native facial morph recovery | Source-dependent | OBJ has no morph deltas; richer source data is required |
| Automatic T/A-pose normalization | Planned | Current script diagnoses problematic rest poses |
| Weight/physics heatmap diagnostics | Planned | Future visual QA pass |

## Diane validation

The uploaded Diane export is used as the real-world regression model without publishing Diane's source assets to this public repository. The v0.3.1 conversion preserves **36,773 triangles and 16 materials**, creates **29 PMX bones** including leg IK and eye controls, detects **6 dynamic accessory pieces**, generates **9 rigid bodies and 6 spring joints**, and adds **4 gaze morph controllers**. A structural PMX parser consumes the generated file to its exact end-of-file boundary after generation.

## MMD text encoding

PMX files are written with the PMX global text encoding flag set to `0` and all text encoded as **UTF-16LE**. This improves compatibility with MMD/PMX Editor setups that expect UTF-16 for Japanese bone, morph, display-frame, rigid-body and joint names.

## Security model

The converter treats avatar packages as untrusted input. ZIP extraction blocks path traversal and symlinks, limits file count and expanded size, and only accepts known model/image data file types. It does not execute files from an archive and does not fetch external URLs stored in manifests. See [SECURITY.md](SECURITY.md).

Generated Blender scripts only reference files extracted from the local package and optional user-selected output paths. The converter does not require Roblox cookies, API keys, session tokens, or private credentials.

## Asset rights

Only convert avatars and assets you own or have permission to modify/use outside Roblox. This project does not bypass Roblox permissions, encryption, authentication, or protected asset delivery.

## Development

```bash
python -m unittest discover -s tests -v
```

The Python core intentionally has no runtime third-party dependency, which keeps installation small and reduces supply-chain risk.
