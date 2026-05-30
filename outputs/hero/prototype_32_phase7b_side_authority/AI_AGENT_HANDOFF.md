# SpriteSpatial Phase 7B Handoff: Authored Side View Ingestion + Front/Back/Side Authority

## Status

Phase 7B is implemented and validated for the hero asset.

The `front_back_side` authority mode now exists as a real pipeline mode. It can ingest authored side sprites and apply side silhouette constraints during SDF construction. It also validates side semantic authority if side override masks are present.

For the current hero asset, the side files are correctly rejected:

```text
left_status: mirrored_placeholder
right_status: mirrored_placeholder
side_geometry_authority: placeholder
side_authority_used: false
```

This is the intended result. The current build remains stable and documents that a true authored side sprite is required before side authority can improve geometry.

## Output Folder

```text
outputs/hero/prototype_32_phase7b_side_authority/
```

## Command Run

```powershell
python tools\build_topological_sprite_model.py `
  --asset assets\samples\hero\spriteasset_v1.json `
  --profile profiles\prototype_32.json `
  --semantic-overrides assets\samples\hero\semantic_overrides `
  --semantic-override-mode supplement `
  --semantic-parts `
  --semantic-depth-profiles `
  --semantic-depth-profile humanoid_voxel `
  --directional-morphology `
  --morphology-profile fantasy_humanoid `
  --depth-mode mylar_edt `
  --closed-body `
  --back-mode front_back_sprite `
  --multi-view-authority `
  --view-authority-mode front_back_side `
  --mesh-backend surface_nets_patch `
  --patch-profile humanoid_voxel `
  --macro-patches `
  --macro-patch-profile humanoid_voxel `
  --adaptive-sdf-resolution `
  --resolution-profile prototype_adaptive `
  --surface-net-vertex-placement patch_qef `
  --qef-regularization 0.001 `
  --qef-max-displacement 0.35 `
  --topology-cleanup `
  --surface-net-smoothing-alpha 0.65 `
  --preserve-silhouette-edges `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-patch-debug `
  --emit-macro-patch-debug `
  --emit-resolution-debug `
  --emit-qef-debug `
  --emit-topology-cleanup-debug `
  --emit-view-authority-debug `
  --out outputs\hero\prototype_32_phase7b_side_authority
```

## Verification Run

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed.

## Commands Deliberately Not Run

```powershell
godot
```

Godot preview was not run because it has been unstable in this environment and the user asked to stop launching it.

```powershell
--api-visual-judge
```

The API visual judge was not run. API output is advisory only and does not mutate geometry or improve the deterministic SDF/mesh.

## Files Added Or Changed

Implementation:

```text
tool/spritespatial/source_coverage.py
tool/spritespatial/view_authority.py
tool/spritespatial/sdf_volume.py
tool/spritespatial/manifold_validation.py
tool/spritespatial/canonical_views.py
tools/build_topological_sprite_model.py
```

Builder additions:

```text
--view-authority-mode front_back_side
--allow-mirrored-side-fallback
--emit-view-authority-debug
```

`--allow-mirrored-side-fallback` is explicit and opt-in. It is not used by the required Phase 7B build.

## Primary Reports And Debug Outputs

View authority:

```text
view_authority/front_back_view_correspondence.json
view_authority/side_view_correspondence.json
view_authority/side_authority_report.json
view_authority/view_authority_report.json
view_authority/projection_iou_report.json
```

Constraint/debug masks:

```text
view_authority/front_constraint_mask.png
view_authority/back_constraint_mask.png
view_authority/side_constraint_mask.png
view_authority/front_projection_mask.png
view_authority/back_projection_mask.png
view_authority/side_projection_mask.png
view_authority/front_back_conflict_map.png
view_authority/side_conflict_map.png
view_authority/front_back_side_conflict_map.png
view_authority/semantic_correspondence_overlay.png
view_authority/semantic_side_correspondence_overlay.png
```

Core outputs:

```text
sdf/sdf_volume.npy
sdf/semantic_volume.npy
sdf/occupancy_volume.npy
sdf/sdf_summary.json
meshing/surface_nets_input.npz
mesh.json
mesh_patch.json
topology_cleanup/mesh_topology_cleaned.json
validation_report.json
```

## Key Validation Metrics

Side authority:

```text
front_back_side_backend_enabled: true
side_geometry_authority: placeholder
side_semantic_authority: missing
side_authority_used: false
side_mirror_fallback_used: false
side_view_correspondence_passed: true
side_projection_iou: 0.0
side_constraint_conflict_count: 0
```

Front/back authority remains stable:

```text
back_geometry_authority: authored_back
front_projection_iou: 0.9727767695099818
back_projection_iou: 0.8939393939393939
front_back_correspondence_passed: true
```

SDF and mesh:

```text
closed_volume_connected: true
mesh_connected_components: 1
degenerate_face_count: 0
non_manifold_after_cleanup: 5
semantic_label_preservation_passed: true
hat_asymmetry_ratio: 2.8036581307124817
validation_report.passed: true
```

## Pass/Fail Result

Phase 7B passed.

The phase passes because it implements side-view authority support and correctly refuses to use the current mirrored placeholder sides as geometry authority.

## Warnings And Known Caveats

Current hero side sprites are not true authored side views:

```text
left: mirrored_placeholder
right: mirrored_placeholder
```

No side SDF constraint is applied in this output:

```text
side_authority_used: false
```

No side semantic override masks were present in:

```text
assets/samples/hero/semantic_overrides/side/
assets/samples/hero/semantic_overrides/left/
assets/samples/hero/semantic_overrides/right/
```

Therefore:

```text
side_semantic_authority: missing
```

## Manual True-Side Test Path

To activate side geometry authority:

1. Add a true side sprite to the hero asset folder.
2. Update `assets/samples/hero/spriteasset_v1.json` so `left` or `right` points at the authored side sprite.
3. Optionally add side semantic masks under one of:

```text
assets/samples/hero/semantic_overrides/side/
assets/samples/hero/semantic_overrides/left/
assets/samples/hero/semantic_overrides/right/
```

4. Rerun the same Phase 7B command.

Expected result with a distinct authored side sprite:

```text
side_geometry_authority: authored_side
side_authority_used: true
side_semantic_authority: silhouette_only
```

If side semantic masks are provided:

```text
side_semantic_authority: semantic_masks
```

## Diagnosis

Semantic issue:

No new semantic failure. Current side semantic authority is absent because no side override masks exist.

SDF issue:

The SDF side-constraint path is implemented but inactive for the current hero because the side source files are placeholders.

Meshing issue:

Mesh validity remains stable. There is no side-authority-driven meshing improvement yet because no side authority was used.

Render issue:

No render inspection was run. Visual side improvement should not be expected until a true side sprite is supplied.

View authority issue:

Back authority is fixed from Phase 7A. The remaining fidelity blocker is still missing true side authority.

## Recommended Next Engineering Step

Provide or extract a true authored hero side sprite, update `spriteasset_v1.json`, and rerun this same command. If `side_authority_used` becomes true but side visuals still do not improve, inspect:

```text
view_authority/side_projection_mask.png
view_authority/side_constraint_mask.png
view_authority/side_conflict_map.png
view_authority/projection_iou_report.json
```

That will separate source-view conflict from SDF/meshing limitations.

## Handoff Checklist

- [x] `front_back_side` mode is implemented.
- [x] Side authority detection distinguishes authored sides from mirrored placeholders.
- [x] Placeholder side views are rejected.
- [x] Side semantic mask folders are supported.
- [x] Side SDF projection constraint path is implemented.
- [x] Side debug reports and masks are generated.
- [x] Current hero build remains valid without side authority.
- [x] Mesh remains connected.
- [x] Degenerate faces remain zero.
- [x] Semantic labels are preserved.
- [x] `python tools\validate_project.py --skip-godot` passes.
- [x] `python -m unittest test_build_topological_sprite_model.py` passes.
- [x] Godot was not run.
