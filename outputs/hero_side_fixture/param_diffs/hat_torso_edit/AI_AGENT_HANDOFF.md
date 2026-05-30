# SpriteSpatial Phase 8B Handoff: Parameter Diff Runner + Edit Explainability

## Status

Phase 8B is implemented and validated.

The new runner builds a base params file and an edited params file, loads validation, embodiment, and arbitration reports from both builds, then emits compact editor-facing explainability outputs.

## Runner

```text
tools/run_embodiment_param_diff.py
```

## Input Params

Base:

```text
assets/samples/hero_side_fixture/embodiment_params_default.json
```

Edited:

```text
assets/samples/hero_side_fixture/embodiment_params.json
```

## Command Run

```powershell
python tools\run_embodiment_param_diff.py `
  --asset assets\samples\hero_side_fixture\spriteasset_v1.json `
  --profile profiles\prototype_32.json `
  --semantic-overrides assets\samples\hero_side_fixture\semantic_overrides `
  --base-params assets\samples\hero_side_fixture\embodiment_params_default.json `
  --edited-params assets\samples\hero_side_fixture\embodiment_params.json `
  --label-base default `
  --label-edited edited `
  --out outputs\hero_side_fixture\param_diffs\hat_torso_edit
```

## Output Folder

```text
outputs/hero_side_fixture/param_diffs/hat_torso_edit/
```

Sub-builds:

```text
base/
edited/
```

## Key Outputs

```text
param_diff_report.json
param_diff_summary.md
metric_delta_table.csv
changed_parts.json
arbitration_delta.json
sdf_delta.json
mesh_delta.json
projection_delta.json
AI_AGENT_HANDOFF.md
```

## Result

```text
edit_valid: true
edit_changed_geometry: true
edit_preserved_hard_gates: true
likely_improvement: true
```

## Changed Parts

Applied:

```text
hair/hat
torso
```

Skipped:

```text
equipment/shield/sword: part_not_present
```

## Key Deltas

```text
hat_asymmetry_ratio: 2.8036581307124817 -> 3.5040642730619114
directional_readability_score: 0.2620183005928993 -> 0.3024684086441994
side_projection_iou: 0.5785997357992074 -> 0.5751633986928104
non_manifold_after_cleanup: 6 -> 7
planar_macro_patch_count: 5 -> 6
rejected_constraint_count: 152 -> 152
```

## Judgment

Helpful deltas included:

```text
hat_asymmetry_ratio +0.7004061423494297
directional_readability_score +0.04045010805130006
back_hat_extension_score +0.00949990376830101
planar_macro_patch_count +1
```

Harmful but tolerated deltas included:

```text
back_projection_iou -0.0018939393939393367
side_projection_iou -0.003436337106397014
non_manifold_after_cleanup +1
qef_acceptance_ratio -0.00045107178267944636
```

The edit is still judged valid because the hard gates stayed intact:

```text
validation_report.passed: true
mesh_connected_components: 1
degenerate_face_count: 0
semantic_label_preservation_passed: true
closed_volume_connected: true
```

## Verification

Run:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed for this phase.

## Commands Deliberately Not Run

```text
Godot
API visual judge
```

This phase is deterministic and editor-explainability focused.

## Honest Caveat

The edited fixture requests `equipment/shield/sword`, but that canonical part is not present in this asset's current part graph. The diff reports it as skipped instead of pretending it affected geometry.

## Recommended Next Step

Before tuning equipment parameters, expose or author an actual `equipment/shield/sword` canonical part in the fixture. For the editor loop itself, the next useful step is a small UI or CLI preset layer that writes parameter files and immediately launches this diff runner.
