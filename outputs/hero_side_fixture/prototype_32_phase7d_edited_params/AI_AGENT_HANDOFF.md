# SpriteSpatial Phase 7D Handoff: Constraint Arbitration + Editable Embodiment Parameters

## Status

Phase 7D is implemented and validated on the `hero_side_fixture` asset.

This phase adds two editor-facing systems before SDF closure:

```text
tool/spritespatial/embodiment_params.py
tool/spritespatial/constraint_arbitration.py
```

The build now supports deterministic arbitration between front, back, side, semantic, topology, and morphology constraints, plus JSON-only embodiment edits for semantic parts.

## Output Folders

Default 7D parameters:

```text
outputs/hero_side_fixture/prototype_32_phase7d_default_params/
```

Edited 7D parameters:

```text
outputs/hero_side_fixture/prototype_32_phase7d_edited_params/
```

Comparison:

```text
outputs/hero_side_fixture/comparisons/phase7c_vs_phase7d_arbitrated_embodiment/
```

## Editable Params File

```text
assets/samples/hero_side_fixture/embodiment_params.json
```

The edited fixture currently modifies:

```text
hair/hat
torso
equipment/shield/sword
```

`equipment/shield/sword` is requested but skipped because this fixture does not currently produce that canonical part.

## Command Run: Edited Params

```powershell
python tools\build_topological_sprite_model.py `
  --asset assets\samples\hero_side_fixture\spriteasset_v1.json `
  --profile profiles\prototype_32.json `
  --semantic-overrides assets\samples\hero_side_fixture\semantic_overrides `
  --semantic-override-mode supplement `
  --semantic-parts `
  --semantic-depth-profiles `
  --semantic-depth-profile humanoid_voxel `
  --directional-morphology `
  --morphology-profile fantasy_humanoid `
  --embodiment-params assets\samples\hero_side_fixture\embodiment_params.json `
  --depth-mode mylar_edt `
  --closed-body `
  --back-mode front_back_sprite `
  --multi-view-authority `
  --view-authority-mode front_back_side `
  --constraint-arbitration `
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
  --emit-embodiment-debug `
  --emit-patch-debug `
  --emit-macro-patch-debug `
  --emit-resolution-debug `
  --emit-qef-debug `
  --emit-topology-cleanup-debug `
  --emit-view-authority-debug `
  --out outputs\hero_side_fixture\prototype_32_phase7d_edited_params
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

Godot preview was not run because it has been unstable in this environment and was not needed for Phase 7D validation.

```powershell
--api-visual-judge
```

The API visual judge was not run. Phase 7D is deterministic and does not use runtime ML or generated art.

## Files Added Or Changed

New:

```text
tool/spritespatial/constraint_arbitration.py
assets/samples/hero_side_fixture/embodiment_params.json
```

Updated:

```text
tool/spritespatial/embodiment_params.py
tool/spritespatial/sdf_volume.py
tool/spritespatial/semantic_depth_profiles.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

Builder flags:

```text
--constraint-arbitration
--embodiment-params path
--emit-embodiment-debug
--emit-embodiment-param-debug
```

`--emit-embodiment-debug` and `--emit-embodiment-param-debug` target the same internal flag.

## Debug Outputs

Embodiment and arbitration outputs:

```text
embodiment/embodiment_params_applied.json
embodiment/embodiment_param_report.json
embodiment/embodiment_delta_report.json
embodiment/embodiment_param_overlay.png
embodiment/part_depth_debug.png
embodiment/constraint_arbitration_report.json
embodiment/constraint_conflict_map.png
embodiment/authority_zone_map.png
embodiment/topology_risk_map.png
embodiment/weighted_blend_regions.png
embodiment/rejected_constraints.json
```

View authority outputs:

```text
view_authority/front_constraint_mask.png
view_authority/back_constraint_mask.png
view_authority/side_constraint_mask.png
view_authority/front_projection_mask.png
view_authority/back_projection_mask.png
view_authority/side_projection_mask.png
view_authority/projection_iou_report.json
view_authority/view_authority_report.json
```

## Key Edited Build Metrics

Validation:

```text
passed: true
closed_volume_connected: true
mesh_connected_components: 1
degenerate_face_count: 0
semantic_label_preservation_passed: true
non_manifold_after_cleanup: 7
```

Authority:

```text
front_geometry_authority: authored_front
back_geometry_authority: authored_back
side_geometry_authority: authored_side_fixture
side_authority_used: true
front_projection_iou: 0.9727767695099818
back_projection_iou: 0.9034090909090909
side_projection_iou: 0.5751633986928104
```

Constraint arbitration:

```text
constraint_arbitration_enabled: true
conflict_zone_count: 115
topology_risk_zone_count: 194
weighted_blend_region_count: 23
rejected_constraint_count: 152
```

Embodiment:

```text
embodiment_params_loaded: true
embodiment_parts_modified: 2
embodiment_param_parts_applied:
  hair/hat
  torso
embodiment_param_parts_skipped:
  equipment/shield/sword: part_not_present
```

Geometry effect:

```text
hat_asymmetry_ratio default: 2.8036581307124817
hat_asymmetry_ratio edited: 3.5040642730619114
directional_readability_score default: 0.2620183005928993
directional_readability_score edited: 0.3024684086441994
planar_macro_patch_count default: 5
planar_macro_patch_count edited: 6
```

## Pass/Fail Result

Phase 7D passed.

Default 7D parameters preserve the Phase 7C result while adding arbitration metadata. Edited 7D parameters change reconstruction from JSON only, and the mesh stays connected with zero degenerate faces.

## Honest Diagnosis

Semantic ambiguity:

Still present for equipment. The fixture has equipment override files, but the canonical part graph does not expose `equipment/shield/sword` as a geometry part in this run, so the requested shield-side edit is skipped instead of fabricated.

Arbitration:

Working. It detects front/back/side conflicts, topology-risk zones, weighted blend zones, and rejected side rows. It also prevents side constraint application from being treated as unconditional truth.

SDF blending:

Stable for this fixture. Side enforcement is still conservative and reports partially weighted side constraints because side IoU remains below the front/back projection quality.

Meshing:

Stable. The edited build has one connected mesh, zero degenerate faces, and non-manifold count remains controlled after cleanup.

Insufficient authored views:

Not the blocker for this fixture. Front, back, and fixture side authority are active. For production art, the synthetic side fixture should be replaced with a true artist-authored side sprite.

## Recommended Next Engineering Step

Add a parameter-diff runner that builds two parameter files and reports only:

```text
changed semantic parts
SDF metric deltas
mesh topology deltas
projection IoU deltas
arbitration deltas
```

That would make the editor loop much easier to reason about before any UI work begins.
