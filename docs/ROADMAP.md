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
- Conservative automatic detection of dynamic hair / bangs / cowlicks / ears / tails / similar accessories
- PMX accessory rigid-body and spring-joint templates
- Blender editable standard facial-expression shape-key scaffold
- VRM 1.0 preset expression bindings
- VRM LookAt setup
- VRM SpringBone1 chains for detected dynamic accessories
- Optional VRM 1.0 export from the generated Blender script
- Feature diagnostics surfaced in `rack inspect` and `conversion-plan.json`

### v0.3.x refinement
- Automatic T/A-pose normalization for VRM workflows
- Native expression/morph ingestion when the source format actually contains morph deltas
- Better eye-geometry detection / assignment for avatars that have separate eye meshes
- Material tuning for MMD / MToon-style workflows
- Weight and physics heatmap / deformation diagnostics
- More sophisticated multi-segment hair, skirt and tail chains

## v0.3.1 — MMD compatibility hotfix ✅
- PMX text encoding switched from UTF-8 to UTF-16LE
- PMX header encoding flag switched from `1` to `0`
- Regression coverage verifies Japanese and English PMX names are actually UTF-16LE
- Diane PMX structurally validated to exact end-of-file after the encoding change

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
