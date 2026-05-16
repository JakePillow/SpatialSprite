SpriteSpatial reference analysis task.

Reference:
debug/reference/FoliageVsUndead/clips/foliage_reference_capture.mp4
debug/reference/FoliageVsUndead/frames/
debug/reference/FoliageVsUndead/foliage_contact_sheet.jpg

Important correction:
The target is NOT only billboard sprites.
The target is a real 3D model/volume that preserves sprite-authored identity.

Current SpriteSpatial problem:
Rotation is wrong because the object behaves like a flat sprite/card with directional texture switching.
The in-between rotation is not spatially coherent.

Reference goal:
Study the FoliageVsUndead capture visually.
Identify how its characters/objects seem to preserve 2D/cartoon/sprite-like readability while still existing as coherent 3D forms.

Do not decompile Unreal assets.
Use only visual reference frames and runtime capture.

Implementation direction:
We need to move from:
- flat Sprite3D direction switching

toward:
- real 3D proxy model / volume
- sprite-authored key-view textures
- continuous rotation in-between views
- front/side/back views that resolve cleanly
- no hard snapping unless stylised intentionally

New SpriteSpatial target:
1. Generate a simple 3D model/volume from sprite proportions.
2. Use the sprite as the authoritative front texture/key view.
3. Use side/back sprites as authored directional key views.
4. During rotation, interpolate through actual 3D geometry rather than swapping flat cards.
5. The model should have coherent thickness, silhouette, and volume.
6. Voxelisation may be used as an intermediate scaffold, but the final output should read as stylised 3D, not Minecraft voxels.

Suggested next prototype:
Create Track C: sprite-guided low-poly/proxy model.

Files:
- scripts/sprite_guided_proxy_model.gd
- scenes/link_proxy_model_test.tscn

Requirements:
- Build a simple 3D body volume from sprite alpha mask or bounding regions.
- Standardise world dimensions:
  - sprite_width_units
  - sprite_height_units
  - body_depth_units
- Generate approximate torso/head/limb volumes if possible.
- Apply front sprite/key texture to front-facing surface.
- Apply side/back textures to side/back surfaces where available.
- Rotation must be continuous, not just texture snapping.
- At canonical angles, visual should strongly resemble the authored sprite.
- At in-between angles, real 3D volume should carry the rotation.

Keep Track A and Track B intact.
Add Track C separately.
