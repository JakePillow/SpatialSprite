# SpriteSpatial Phase 8C Handoff: Embodiment Presets + Preset Diff Runner

## Status

Phase 8C is implemented and validated.

This phase adds creator-facing embodiment presets on top of the raw `embodiment_params.json` controls, then routes preset-generated params through the existing Phase 8B diff runner.

## Added

Preset profiles:

```text
profiles/embodiment_presets/humanoid_common.json
profiles/embodiment_presets/fantasy_humanoid.json
profiles/embodiment_presets/platformer_common.json
```

Preset module:

```text
tool/spritespatial/embodiment_presets.py
```

CLI:

```text
tools/apply_embodiment_preset.py
```

## Primary Test Output

```text
outputs/hero_side_fixture/preset_tests/pull_hat_back_075/
```

Key files:

```text
edited_params.json
preset_application_report.json
param_diff_report.json
param_diff_summary.md
changed_parts.json
metric_delta_table.csv
AI_AGENT_HANDOFF.md
base/
edited/
```

## Command Run

```powershell
python tools\apply_embodiment_preset.py `
  --asset assets\samples\hero_side_fixture\spriteasset_v1.json `
  --semantic-overrides assets\samples\hero_side_fixture\semantic_overrides `
  --base-params assets\samples\hero_side_fixture\embodiment_params_default.json `
  --preset-profile profiles\embodiment_presets\fantasy_humanoid.json `
  --preset-id pull_hat_back `
  --intensity 0.75 `
  --out-params outputs\hero_side_fixture\preset_tests\pull_hat_back_075\edited_params.json `
  --run-diff `
  --diff-out outputs\hero_side_fixture\preset_tests\pull_hat_back_075
```

## Preset Application

```text
preset_id: pull_hat_back
intensity: 0.75
target_parts: hair/hat
applied_parts: hair/hat
skipped_parts: []
valid_for_asset: true
```

Intensity scaling was confirmed. Examples:

```text
z_center_offset: 0.0 -> -0.0225
thickness_scale: 1.0 -> 1.12
back_bias: 0.0 -> 0.18
taper_strength: 0.0 -> 0.18
```

## Diff Result

```text
edit_valid: true
edit_changed_geometry: true
edit_preserved_hard_gates: true
likely_improvement: true
```

Key deltas:

```text
hat_asymmetry_ratio: 2.8036581307124817 -> 3.506145075401276
directional_readability_score: 0.2620183005928993 -> 0.30265904366970064
side_projection_iou: 0.5785997357992074 -> 0.5812417437252312
non_manifold_after_cleanup: 6 -> 6
planar_macro_patch_count: 5 -> 5
rejected_constraint_count: 152 -> 152
```

## Secondary Test

`thicken_torso` at intensity `0.5` also ran with diff:

```text
outputs/hero_side_fixture/preset_tests/thicken_torso_050/
```

Result:

```text
edit_valid: true
edit_changed_geometry: true
likely_improvement: true
applied_parts: torso
```

## Missing-Part Test

`pull_equipment_sideways` at intensity `0.75` was applied without running a diff to verify skip behavior:

```text
outputs/hero_side_fixture/preset_tests/pull_equipment_sideways_075/
```

Result:

```text
applied_parts: []
skipped_parts:
  equipment/shield/sword: part_not_present
valid_for_asset: false
```

This is expected because the fixture has an empty equipment override mask, so there is no canonical equipment part to modify.

## Verification

Run:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed.

## Commands Deliberately Not Run

```text
Godot
API visual judge
```

This phase is deterministic preset/diff infrastructure only.

## Honest Caveat

Presets validate against nonempty semantic override masks as a lightweight editor-facing proxy for canonical part availability. The full builder remains authoritative: if a part is absent from the final canonical part graph, the diff runner will still report it as skipped.

## Recommended Next Step

Use these preset reports to drive a small UI picker later: preset name, intensity slider, skipped-part warnings, and a one-screen metric diff summary. No geometry work is needed for that next editor step.
