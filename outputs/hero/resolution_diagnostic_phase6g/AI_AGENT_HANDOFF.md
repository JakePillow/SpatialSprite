# SpriteSpatial Phase 6G Handoff: Controlled SDF Resolution Diagnostic

## Status

Phase 6G diagnostic is implemented and executed for the hero asset.

Resolution helped: `true`
Best scale: `2.0`
Recommended next step: `increase_resolution_path`

Higher SDF resolution improved at least one target topology metric while preserving hard gates. Caveat: non-manifold edge count increased by 45, so the production path needs topology cleanup.

## Output Folder

```text
outputs\hero\resolution_diagnostic_phase6g
```

## Commands Run

```powershell
python tools\run_resolution_diagnostic.py --asset assets\samples\hero\spriteasset_v1.json --profile profiles\prototype_32.json --semantic-overrides assets\samples\hero\semantic_overrides --semantic-override-mode supplement --out outputs\hero\resolution_diagnostic_phase6g
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

## Commands Deliberately Not Run

```powershell
godot
```

Godot preview was intentionally skipped.

## Files Added Or Changed

```text
tool/spritespatial/sdf_volume.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
tools/run_resolution_diagnostic.py
```

## Primary Reports

```text
resolution_diagnostic_report.json
resolution_diagnostic_summary.md
metric_delta_table.csv
contact_sheets/
scale_1_0/resolution_diagnostic_metrics.json
scale_1_5/resolution_diagnostic_metrics.json
scale_2_0/resolution_diagnostic_metrics.json
```

## Key Metrics

| scale | passed | sdf shape | macro patches | small macro ratio | planar macro patches | staircase | surface flow | non-manifold | hat asymmetry |
|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | True | [32, 24, 25] | 273 | 0.5604 | 2 | 0.5052 | 0.4656 | 11 | 3.0449 |
| 1.5 | True | [48, 36, 37] | 468 | 0.5769 | 8 | 0.5125 | 0.4715 | 24 | 2.7851 |
| 2.0 | True | [64, 48, 49] | 695 | 0.5842 | 20 | 0.4972 | 0.5029 | 56 | 4.2751 |

## Pass/Fail Result

The diagnostic passes if all three scale builds complete and the comparison reports are generated. Individual scale validation status is listed above.

Repository verification passed:

```text
validate_project.py --skip-godot: passed
test_build_topological_sprite_model.py: 12 tests passed
```

## Diagnosis

Resolution materially helped under preservation gates. The next phase should make the higher-resolution SDF path production-ready and decide whether adaptive resolution is preferable to globally raising the grid. Non-manifold edges rose at the best scale, so this should be treated as a resolution signal, not a production-ready topology answer.

## Recommended Next Engineering Step

Promote an adaptive high-resolution SDF path, address the non-manifold increase, and rerun the visual benchmark before changing vertex placement.

## Handoff Checklist

- [x] SDF X/Y resolution scale flag added
- [x] Z resolution scale flag added
- [x] semantic masks remain source-authoritative
- [x] resolution diagnostic runner added
- [x] scale outputs generated or failures recorded
- [x] metric delta table generated
- [x] summary generated
- [x] contact sheets generated
- [x] Godot preview not run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
