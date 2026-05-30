# SpriteSpatial Phase 8C Handoff: Embodiment Presets + Preset Diff Runner

## Status

Phase 8C preset application completed.

## Preset

preset_id: pull_equipment_sideways
intensity: 0.75
target_parts: ['equipment/shield/sword']
applied_parts: []
skipped_parts: [{'part_id': 'equipment/shield/sword', 'reason': 'part_not_present'}]

## Outputs

```text
edited_params.json
preset_application_report.json
param_diff_report.json
param_diff_summary.md
changed_parts.json
metric_delta_table.csv
AI_AGENT_HANDOFF.md
```

## Diff Result

run_diff: False
diff_exit_code: None
edit_valid: None
edit_changed_geometry: None
likely_improvement: None

## Verification

Run after this phase:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Godot and API visual judge were not run by this preset runner.
