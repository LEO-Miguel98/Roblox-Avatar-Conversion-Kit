# Roadmap

## v0.1 — package reconstruction ✅
- Secure ZIP ingestion
- Manifest + OBJ/MTL parsing
- R15 skeleton reconstruction
- Accessory weld matching
- Experimental direct PMX writer
- Blender build script

## v0.2 — better deformation ✅
- Smooth reconstructed body weights with up to four influences
- BDEF1/BDEF2/BDEF4 PMX output
- Japanese MMD bone aliases
- PMX center bone and leg IK controllers
- Better Blender bone tails and smooth weighting
- Optional GLB export from the generated Blender script
- VRM rest-pose diagnostics
- Rigid accessory weighting preserved as a fallback-safe behavior

## v0.3 — MMD / VTuber finishing ✅ core
- MMD eye controller bones and gaze-control bone morphs
- MMD display frames for root, face, expressions and physics
- Conservative automatic detection of dynamic accessories
- PMX accessory rigid-body and spring-joint templates
- Blender editable standard facial-expression shape-key scaffold
- VRM 1.0 preset expression bindings
- VRM LookAt setup
- VRM SpringBone1 chains for detected dynamic accessories
- Optional VRM 1.0 export from the generated Blender script
- Feature diagnostics surfaced in `rack inspect` and `conversion-plan.json`

## v0.3.1 — MMD compatibility hotfix ✅
- PMX text encoding switched from UTF-8 to UTF-16LE
- PMX header encoding flag switched from `1` to `0`
- Regression coverage verifies Japanese and English PMX names are actually UTF-16LE
- Diane PMX structurally validated to exact end-of-file after the encoding change

## v0.3.2 — visual preservation / MMD correction ✅
- Strong primary-bone weight floors for chibi body parts
- Head/hand/foot deformation protection
- WrapLayer clothing detection and region-constrained skinning
- Rigid preservation for whole hair shells, bangs, ears, swords and face props
- Multi-segment spring chains only for safer appendages
- Generated PMX physics collision masking to prevent startup explosions
- MMD edge-outline suppression for Roblox-texture fidelity
- UTF-16LE PMX retained

## v0.3.3 — PMXEditor bridge ✅
- Static discovery of a user-supplied PMXEditor package
- AnyCPU PEPlugin bridge compiled locally against the user's `PEPlugin.dll`
- PMXEditor acceptance/object-count JSON report
- Optional PMXEditor re-save and visible-window screenshot
- PMXEditor binaries remain external and are never redistributed

## v0.3.4 — integrated PMXEditor validation ✅
- `rack pmx --pmxeditor PATH` converts and validates in one command on Windows
- Original converter PMX is preserved; PMXEditor outputs are sidecars
- Automatic PMXEditor-resaved PMX, JSON report, and screenshot by default
- Writer-vs-PMXEditor count comparison for vertices, materials, bones, morphs, rigid bodies and joints
- Non-zero exit code on PMXEditor rejection or count mismatch

## v0.3.5 — standardized PMXEditor visual view ✅
- Front-facing model framing from PMXEditor-parsed vertex bounds
- Solid rendering with editing overlays hidden for cleaner silhouette screenshots
- View normalization status included in PMXEditor reports

## v0.3.6 — UV-origin correction ✅
- OBJ texture V coordinates are converted for PMX with `(u, v) -> (u, 1-v)`
- Corrected upside-down texture sampling exposed by Diane's face/hair and speech-bubble regression
- The attempted global X inversion was subsequently removed in v0.3.7 because it mirrored Diane's left/right layout

## v0.3.7 — left/right + planar prop correction ✅
- Roblox-to-MMD geometry preserves X and flips depth only: `(x, y, z) -> (x, y, -z)`
- Restores Diane's speech bubble and sword layout to the same left/right arrangement as the Roblox source
- Detects extremely thin `Handle*` billboard accessories generically from mesh bounds
- Billboard accessories receive an additional U flip while ordinary hair, clothing, swords and body meshes remain unchanged
- Diane's `Handle8` speech bubble is the regression case: ~1% thickness-to-size ratio, so its text becomes readable without mirroring the entire avatar
- UTF-16LE text, v0.3.2 conservative weights, WrapLayer skinning and physics behavior remain intact

## v0.3.8 — clean OBJ inference + tuned secondary motion ✅
- Accepts a single Roblox OBJ/MTL package even when `avatar_manifest.json` is absent
- Removes giant `Baseplate*` scene helpers and recenters the visible avatar automatically
- Infers Diane-style 11-group humanoid layout into standard MMD-compatible hips/spine/chest/neck/head/arm/leg/foot bone names
- Keeps rigid props rigid while inferring likely layered jacket/lower-body/footwear groups for body-following skinning
- Geometry-only eye controller positions are reconstructed from the inferred head bounds
- Shark-tail detection uses the strongest behind-the-body depth projection and generates a four-segment spring chain
- Heart/cowlick detection uses the highest small accessory and generates a two-segment, high-damping, very-low-angle wiggle chain
- Clean Diane regression intentionally excludes the old fairy and speech-bubble accessories

## v0.3.9 — reconstructed facial animation ✅ implementation
- Detects the densest humanoid `Rig*` mesh mapped to the head instead of deforming head accessories such as hair
- Splits disconnected front-face geometry into eye and mouth regions using head-relative bounds
- Generates real PMX vertex morphs for `Blink`, `BlinkLeft`, `BlinkRight`, `MouthOpen`, and `Smile`
- Keeps the existing four gaze bone morphs, giving clean Diane nine usable face/gaze controls in the MMD Expressions frame
- Does not claim recovery of original Roblox FACS or source blendshapes; these are reconstructed morphs from the exported geometry
- Clean Diane regression generates 1,550 blink vertex offsets, 772/778 left/right wink offsets, and 838 offsets each for mouth-open and smile
- UTF-16LE, v0.3.8 clean-OBJ inference, tail physics and restrained heart/cowlick physics remain unchanged

### v0.3.x refinement
- Automatic T/A-pose normalization for VRM workflows
- Native expression/morph ingestion when the source format actually contains morph deltas
- Better eye-geometry detection / assignment for avatars that have separate eye meshes
- Additional reconstructed mouth vowels / expression tuning
- Material tuning for MMD / MToon-style workflows
- Weight and physics heatmap / deformation diagnostics
- More sophisticated multi-segment hair, skirt and tail chains
- Visual regression scoring using PMXEditor screenshots against known-good avatar references

## v0.4 — animation conversion
- Roblox animation keyframe ingestion
- Retargeting to reconstructed humanoid
- VMD export
- VRM Animation (`.vrma`) export path

## v0.5 — desktop conversion experience
- Drag-and-drop desktop UI
- Conversion presets: MMD, VRM/VTuber, Blender, GLB
- Batch conversion and conversion reports
- Optional Blender command-line automation when Blender is installed locally
- PMXEditor-assisted Windows validation as a selectable MMD QA step
