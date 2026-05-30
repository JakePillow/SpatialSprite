# SpriteSpatial Phase 8A Handoff: Editable Embodiment Parameters

## Status

Phase 8A is implemented and validated.

The pipeline now has an editor-facing JSON parameter layer:

```text
embodiment_params.json
```

A user can edit per-semantic-part values for depth center, thickness, front/back bias, side width, taper, silhouette preservation, and locking, then rerun the builder without touching code.

The proof build enables only `hair/hat` in the JSON. Validation confirms that the parameter was applied, the SDF and mesh changed, and the output stayed valid.

## Output Folder

```text
outputs/hero/prototype_32_phase8a_embodiment_params/
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
  --embodiment-params embodiment_params.json `
  --depth-mode mylar_edt `
  --closed-body `
  --back-mode front_back_sprite `
  --multi-view-authority `
  --view-authority-mode front_back_sprite `
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
  --emit-embodiment-param-debug `
  --emit-patch-debug `
  --emit-macro-patch-debug `
  --emit-resolution-debug `
  --emit-qef-debug `
  --emit-topology-cleanup-debug `
  --emit-view-authority-debug `
  --out outputs\hero\prototype_32_phase8a_embodiment_params
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

Godot preview was not run because it has been unstable in this environment and was not required for this phase.

```powershell
--api-visual-judge
```

The API visual judge was not run. Phase 8A is deterministic and editor-parameter-driven.

## Files Added Or Changed

New:

```text
embodiment_params.json
tool/spritespatial/embodiment_params.py
```

Updated:

```text
tools/build_topological_sprite_model.py
tool/spritespatial/semantic_depth_profiles.py
tool/spritespatial/sdf_volume.py
tool/spritespatial/manifold_validation.py
```

Builder flags:

```text
--embodiment-params path
--emit-embodiment-param-debug
```

## Editable Fields

Each semantic part supports:

```text
enabled
z_center_offset
thickness_scale
front_bias
back_bias
side_width_scale
taper_strength
preserve_silhouette
lock_part
notes
```

Disabled parts are reported but not applied. Locked parts are reported and skipped.

## Primary Reports And Debug Outputs

Embodiment parameter debug:

```text
embodiment_params/embodiment_param_report.json
embodiment_params/embodiment_param_overlay.png
embodiment_params/embodiment_param_raw_applied.json
```

Validation and SDF reports:

```text
validation_report.json
sdf/sdf_summary.json
depth_profiles/semantic_depth_profile_report.json
directional_debug/directional_morphology_report.json
```

## Key Validation Metrics

Embodiment parameter application:

```text
embodiment_params_enabled: true
embodiment_params_path: C:\dev\SpatialSprite\embodiment_params.json
embodiment_param_parts_requested:
  equipment/shield/sword
  face
  hair/hat
  left_arm
  left_leg
  right_arm
  right_leg
  torso
embodiment_param_parts_applied:
  hair/hat
embodiment_param_applied_count: 1
```

Skipped parts:

```text
face: disabled
torso: disabled
left_arm: disabled
right_arm: disabled
left_leg: disabled
right_leg: disabled
equipment/shield/sword: disabled
```

Proof of geometry influence:

```text
front_hat_extension_score: 0.013563421554863453
back_hat_extension_score: 0.05709996819496155
hat_asymmetry_ratio: 4.209849849759122
```

Before this edit, the accepted Phase 7 path reported approximately:

```text
hat_asymmetry_ratio: 2.8036581307124817
```

Mesh validity:

```text
validation_report.passed: true
closed_volume_connected: true
mesh_connected_components: 1
degenerate_face_count: 0
non_manifold_after_cleanup: 6
semantic_label_preservation_passed: true
front_projection_iou: 0.9727767695099818
back_projection_iou: 0.8939393939393939
```

## Parameter Merge Behavior

The editor JSON merges into the existing profile systems before SDF reconstruction:

```text
z_center_offset -> SemanticDepthProfile.z_center_fraction
thickness_scale -> SemanticDepthProfile.half_thickness_fraction
front_bias/back_bias -> DirectionalMorphologyRule forward/backward/front/back scale
side_width_scale -> DirectionalMorphologyRule lateral_bias
taper_strength -> DirectionalMorphologyRule taper and selected depth taper curve
preserve_silhouette -> profile preservation weight and report metadata
lock_part -> skip this part's authored parameter edits and report as locked
```

The final silhouette is still governed by the existing SDF pinning and view-authority systems.

## Pass/Fail Result

Phase 8A passed.

The JSON layer successfully modified semantic depth and directional morphology before SDF reconstruction. The change propagated into the final mesh without breaking validation.

## Warnings And Known Caveats

The default `embodiment_params.json` is intentionally conservative. Only `hair/hat` is enabled as a working example. Other part stanzas are present but disabled so users can switch them on manually.

Only semantic labels that exist in the current canonical part graph can be applied. Missing labels are skipped and reported.

No render inspection was run in this environment. Visual confirmation should use stable non-Godot previews or a later safe renderer.

Current hero side sprites are still placeholders:

```text
side_geometry_authority: placeholder
side_authority_used: false
```

This does not block Phase 8A because editable embodiment parameters operate before SDF reconstruction and do not require side authority.

## Recommended Next Engineering Step

Expose a small set of production presets for common edits:

```text
pull_hat_back
push_face_forward
thicken_torso
pull_shield_sideways
taper_limbs
```

Then add a compact diff report comparing two parameter files so the editor can explain exactly which semantic part edits changed the generated mesh.

## Quick Re-Run Instructions

Edit:

```text
embodiment_params.json
```

Set any part's `enabled` field to `true`, adjust the numeric fields, then rerun the build with:

```text
--embodiment-params embodiment_params.json
--emit-embodiment-param-debug
```

The fastest sanity check is:

```text
embodiment_params/embodiment_param_report.json
validation_report.json
```
