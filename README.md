# Roblox Avatar Conversion Kit

A local-first toolkit for turning a **Roblox avatar export package** (`OBJ + MTL + textures`, optionally with `avatar_manifest.json`) into files that are easier to use in **MMD**, **Blender**, **GLB**, and **VTubing / VRM** workflows.

> **Current status: v0.3.11 prototype.** The kit reconstructs a humanoid rig, conservative smooth body weights, MMD-compatible motion bones/IK, gaze and facial morphs, clean OBJ-only geometry inference, and restrained secondary physics. Roblox OBJ exports still do **not** contain original skin weights or source blend-shape/FACS deltas, so reconstructed deformation and expressions should be visually reviewed before production use.

## What it does

- Securely validates and extracts user-provided ZIP packages.
- Uses `avatar_manifest.json` when available, and can fall back to conservative geometry-only inference when a clean Roblox OBJ/MTL package has no manifest.
- Removes obvious `Baseplate*` / terrain helper geometry from geometry-only avatar exports.
- Reconstructs a humanoid skeleton from R15 body-part transforms or inferred `Rig*` geometry.
- Reconstructs **conservative smooth body weights with up to four bone influences** and enforces a strong primary-bone floor so chibi proportions do not collapse.
- Detects layered clothing and safer secondary-motion appendages while keeping silhouette-defining hair shells, ears, swords and ordinary props rigid by default.
- Creates experimental **PMX 2.0** in UTF-16LE with MMD-standard body names, root/center/groove controls, leg + toe IK, shoulder/twist helpers, gaze controls, reconstructed facial morphs, display frames and collision-safe spring templates.
- Reconstructs real PMX vertex morphs for blink, left/right wink, `あ / い / う / え / お`, and smile when the exported head contains separable front-face geometry.
- In geometry-only animated-head exports, hides detected internal mouth/cavity geometry in the neutral pose and reveals it through mouth morphs instead of leaving it visible across the face.
- Generates a Blender build script with smooth skinning, editable facial expression keys, VRM 1.0 humanoid mapping, VRM LookAt, SpringBone chains and rest-pose diagnostics.
- Can hand a generated PMX to a **user-supplied PMXEditor on Windows** for acceptance/count validation, optional re-save and screenshot capture.
- Never downloads arbitrary `meshId` / `textureId` URLs from the manifest.

## Quick start

```bash
python -m pip install -e .

# Inspect either a manifest-backed or clean OBJ-only Roblox export
rack inspect DIANE_Clean.zip

# Direct MMD conversion
rack pmx DIANE_Clean.zip -o output/diane/DIANE_Clean.pmx

# Windows: convert and validate using a local PMXEditor copy
rack pmx DIANE_Clean.zip -o output/diane/DIANE_Clean.pmx --pmxeditor "C:\\Tools\\PmxEditor"

# Disable generated secondary physics
rack pmx DIANE_Clean.zip -o output/diane/DIANE_Clean-no-physics.pmx --no-physics

# Manifest-backed Blender/VRM preparation
rack prepare Diane.zip -o output/diane --vrm Diane.vrm
```

Geometry-only ZIPs are currently supported directly by `rack inspect` and `rack pmx`. The Blender/VRM preparation path still requires the richer manifest-backed export so its source transforms can be reproduced safely.

## Facial expressions and neutral animated-head handling

OBJ does not carry the avatar's original Roblox blend-shape/FACS deltas, so the kit does **not claim to recover the source facial rig exactly**. When the head `Rig*` mesh contains enough disconnected front-face geometry, the converter identifies eye and mouth regions relative to the head bounds and generates real PMX vertex morphs.

v0.3.11 currently reconstructs:

- `まばたき` / Blink
- `ウィンク` / BlinkLeft
- `ウィンク右` / BlinkRight
- `あ` / MouthOpen
- `い` / MouthI
- `う` / MouthU
- `え` / MouthE
- `お` / MouthO
- `笑い` / Smile
- four gaze bone morphs: LookLeft / LookRight / LookUp / LookDown

These are actual vertex/bone morphs, not zero-delta placeholders, but their shapes are reconstructed from exported geometry. Texture-only heads or heads without safely separable facial geometry do not receive fabricated vertex morphs.

Some Roblox animated heads export internal mouth/tongue/cavity pieces that Roblox composites differently from MMD. On geometry-only conversions, v0.3.11 detects the same mouth components used for the reconstructed morphs, tucks them deeper inside the head for the neutral pose, and adds the inverse depth movement to the vowel/smile morphs. This keeps the neutral face clean while preserving animatable mouth geometry.

## MMD motion compatibility

v0.3.11 was checked against a user-supplied set of classic PMD models and a real VMD motion. The converter now follows the motion hierarchy those files consistently expect instead of simply translating Roblox joints one-for-one.

The PMX motion structure includes:

- `全ての親` → `センター` → `グルーブ` global controls.
- `下半身` and `上半身` as siblings under Groove/Center motion, matching the classic PMD structure; `上半身2` continues from upper body.
- Shoulder-P / shoulder helpers plus arm and wrist twist helpers used by semistandard VMD tracks.
- Standard leg → knee → ankle chains.
- Leg IK targeting the ankle through knee + leg, using the classic 40-iteration / 0.5-weight pattern.
- Toe bones and toe IK, with toe IK parented to leg IK and solved through the ankle.
- `両目`, left-eye and right-eye controls.
- Tail/cowlick physics kept outside the normal humanoid motion chain.

This improves compatibility with ordinary MMD/VMD motions, but it does not guarantee that every model-specific track in an arbitrary VMD can be reproduced. Motions may contain character-specific finger, tongue, breast, hair, effect or accessory tracks that Diane does not have.

## Clean OBJ inference and secondary motion

For clean Roblox exports that only contain OBJ/MTL/textures, the converter removes giant Baseplate/terrain helpers, recenters the visible avatar, reconstructs the humanoid from `Rig*` groups, and conservatively classifies likely clothing and secondary-motion accessories.

For clean Diane, the shark tail receives a **four-segment spring chain** so motion travels from the base toward the tip. The heart/cowlick receives a **two-segment high-damping, low-angle chain** so it gives only a small wiggle rather than behaving like loose hair.

Generated physics are starting values rather than a substitute for model-specific tuning. Review collision behavior, stiffness, drag, gravity, pivots and clipping in MMD before production use.

## Material / texture preservation

OBJ and PMX use opposite V texture origins, so texture V coordinates are converted during PMX generation. Extremely thin billboard props can receive an additional U correction without mirroring the whole character.

Geometry-only Roblox exports can also contain dark MTL `Kd` values on already-colored PNG textures. v0.3.10+ uses neutral white PMX diffuse/ambient values for those textured geometry-only materials so the PNG controls the visible color instead of being multiplied into charcoal. Manifest-backed conversions retain their existing MTL tint behavior, and untextured materials retain their MTL color.

## PMXEditor validation on Windows

PMXEditor itself is **not bundled**. Point the converter at a PMXEditor folder/executable you already have:

```powershell
rack pmx DIANE_Clean.zip -o .\output\DIANE_Clean.pmx `
  --pmxeditor "C:\Tools\PmxEditor"
```

The original generated PMX stays untouched. The validation pipeline can create a PMXEditor JSON report, PMXEditor-resaved sidecar PMX and screenshot, and compare PMXEditor's parsed object counts with the converter's own generation statistics. See [docs/PMXEDITOR_BRIDGE.md](docs/PMXEDITOR_BRIDGE.md).

## Why reconstruction is necessary

OBJ stores geometry and material references, not an armature, skin weights or source expression deltas. When a manifest is present it preserves Roblox body-part transforms, Motor6D/accessory weld information, attachment metadata and reconstruction hints. When it is absent, the geometry-only path uses conservative spatial inference rather than pretending missing data exists.

## Conversion targets

| Target | Status | Notes |
|---|---|---|
| Inspection / reconstruction plan | ✅ | Smooth-weight and feature diagnostics |
| Geometry-only OBJ/MTL inference | ✅ experimental | Removes scene helpers and infers a Diane-style humanoid from `Rig*` geometry |
| Blender scene builder | ✅ prototype | Manifest-backed armature + smooth weights + expression scaffold |
| PMX 2.0 | ✅ experimental | UTF-16LE, silhouette-safe weights, MMD motion hierarchy/IK, facial/gaze controls and conservative secondary physics |
| Reconstructed PMX face morphs | ✅ experimental | Blink/winks/A-I-U-E-O/smile when separable face geometry is detected |
| PMXEditor validation | ✅ Windows integration | Acceptance report, optional re-save/screenshot, count comparison |
| GLB/glTF | ✅ via Blender | Optional Blender export |
| VRM 1.0 | ✅ experimental via Blender | Humanoid map, LookAt, expression bindings and SpringBone |
| Roblox animation → VMD | Planned | Animation-source ingestion/retargeting remains v0.4 work |
| Native Roblox/FACS morph recovery | Source-dependent | OBJ has no original morph deltas |
| Automatic T/A-pose normalization | Planned | Current workflow focuses on MMD rest-pose preservation |

## Diane regression validation

The uploaded Diane exports are used as private real-world regression inputs; their source assets are not published in this public repository.

The current clean-Diane v0.3.11 regression produces **45,423 PMX vertices, 32,013 triangles, 13 materials, 43 bones, 4 IK bones, 13 expression/gaze morphs, 8 rigid bodies and 6 physics joints**. The additional bones include the MMD root/groove helpers, shoulder/twist helpers, toe bones and toe IK while retaining the four-segment shark tail and two-segment restrained heart/cowlick chain.

The neutral-face pass hides **838 detected mouth-region source vertices across 22 disconnected mouth components** inside the head until a reconstructed mouth morph is applied. A structural PMX parser consumes the generated UTF-16LE model to its exact end-of-file boundary.

PMXEditor-backed GUI validation remains Windows-side; Linux CI validates package installation, PMX generation logic, hierarchy/morph regression tests and the bridge code without pretending to execute the Windows/.NET/DirectX editor.

## MMD text encoding

PMX files are written with global text encoding flag `0` and all text encoded as **UTF-16LE**, including Japanese bone, morph, display-frame, rigid-body and joint names.

## Security model

The converter treats avatar packages as untrusted input. ZIP extraction blocks path traversal and symlinks, limits file count and expanded size, and only accepts known model/image data file types. It does not execute files from an avatar archive and does not fetch external URLs stored in manifests. See [SECURITY.md](SECURITY.md).

Generated Blender scripts only reference locally extracted package files and user-selected output paths. The converter does not require Roblox cookies, API keys, session tokens or private credentials.

## Asset rights

Only convert avatars and assets you own or have permission to modify/use outside Roblox. This project does not bypass Roblox permissions, encryption, authentication or protected asset delivery.

## Development

```bash
python -m unittest discover -s tests -v
```

The Python core intentionally has no runtime third-party dependency, which keeps installation small and reduces supply-chain risk.
