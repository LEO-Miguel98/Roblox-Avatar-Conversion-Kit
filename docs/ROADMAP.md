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

## v0.3 — MMD / VTuber finishing
- Automatic T/A-pose normalization for VRM workflows
- MMD display frames and material tuning
- Face expression / morph reconstruction
- Eye look / blink helpers
- Hair, ears, tail, skirt and accessory physics templates
- VRM expressions, look-at and spring bones
- Weight heatmap / deformation diagnostics

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
