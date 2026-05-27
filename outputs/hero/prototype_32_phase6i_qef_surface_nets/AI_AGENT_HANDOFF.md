# SpriteSpatial Phase 6I Handoff: QEF/Hermite Patch-Aware Surface Nets Vertex Placement

## Status

Phase 6I is implemented and validated for the hero asset.

The Surface Nets extractor now supports Hermite/QEF-style vertex placement through `average`, `qef`, and `patch_qef` modes. The Phase 6I build uses `patch_qef` with adaptive SDF resolution, semantic patches, macro-patches, and topology cleanup.

The first direct QEF displacement worsened the established metrics for this SDF sign convention, so the implementation includes a constrained orientation guard for `patch_qef`. It compares standard, direct-QEF, and reflected-QEF placement and keeps the best bounded variant. The final output improves staircase and planar surface metrics while preserving topology, semantics, silhouette, and hat asymmetry.

## Output Folder

```text
outputs/hero/prototype_32_phase6i_qef_surface_nets/
```

## Command Run

Godot preview was intentionally not run.

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
  --back-mode semantic_rules `
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
  --out outputs\hero\prototype_32_phase6i_qef_surface_nets
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

Godot preview was skipped because preview execution has been unstable in this environment and this phase did not require it.

## Files Added Or Changed

Primary implementation:

```text
tool/spritespatial/hermite_qef.py
tool/spritespatial/surface_nets.py
tool/spritespatial/semantic_patch_nets.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

Builder additions:

```text
--surface-net-vertex-placement average|qef|patch_qef
--qef-regularization
--qef-max-displacement
--emit-qef-debug
```

## Primary Outputs

```text
mesh.json
mesh_patch.json
topological_model.json
surface_nets_report.json
validation_report.json
patch_nets/patch_report.json
macro_patches/macro_patch_report.json
topology_cleanup/cleanup_report.json
```

## Debug Outputs

QEF debug:

```text
qef/hermite_samples.json
qef/qef_cell_report.json
qef/qef_displacement_debug.png
qef/qef_rejection_debug.png
qef/qef_normal_debug.png
qef/qef_condition_debug.json
qef/before_after_qef_wireframe.png
qef/before_after_qef_contact_sheet.png
```

Patch and macro-patch debug:

```text
patch_nets/patch_graph.json
patch_nets/patch_report.json
patch_nets/before_after_contact_sheet.png
macro_patches/macro_patch_graph.json
macro_patches/macro_patch_report.json
macro_patches/before_after_contact_sheet.png
```

Topology cleanup debug:

```text
topology_cleanup/non_manifold_edges_before.json
topology_cleanup/non_manifold_edges_after.json
topology_cleanup/cleanup_report.json
topology_cleanup/repaired_edge_debug.png
topology_cleanup/sliver_face_debug.png
```

## Key Validation Metrics

QEF:

```text
surface_net_vertex_placement: patch_qef
qef_enabled: true
qef_cells_processed: 3212
qef_cells_accepted: 3057
qef_acceptance_ratio: 0.9517434620174346
qef_mean_displacement: 0.059975738113207895
qef_max_displacement: 0.07000192254781723
qef_max_displacement_limit: 0.35
qef_fallback_count: 155
qef_condition_warning_count: 0
qef_orientation: reflected
qef_orientation_guard_applied: true
```

QEF quality:

```text
staircase_artifact_before_qef: 0.5131218140038312
staircase_artifact_after_qef: 0.4723069560582821
surface_flow_before_qef: 0.47614215635667057
surface_flow_after_qef: 0.47583257060035233
planar_surface_score_before_qef: 0.9545646305974974
planar_surface_score_after_qef: 0.9642501471764979
qef_quality_metric_improved: true
```

Patch/macro-patch:

```text
patch_adjustment_accepted: false
macro_patch_count: 278
planar_macro_patch_count: 10
small_macro_patch_ratio: 0.4892086330935252
patch_coherence_score: 0.6556176084099868
```

Topology and preservation:

```text
topology_cleanup_applied: true
non_manifold_before_cleanup: 12
non_manifold_after_cleanup: 7
mesh_connected_components: 1
degenerate_face_count: 0
semantic_label_preservation_passed: true
silhouette_drift_px: 0.0
hat_asymmetry_ratio: 2.802311212197138
validation_report.passed: true
```

## Pass/Fail Result

Phase 6I passed.

Hard gates:

```text
mesh_connected_components == 1
degenerate_face_count == 0
semantic_label_preservation_passed == true
qef_cells_accepted > 0
qef_max_displacement <= qef_max_displacement_limit
non_manifold_after_cleanup == 7
hat_asymmetry_ratio > 2.0
validation_report.passed == true
```

## Warnings And Known Caveats

The model is still missing authored side-view authority. Side profile remains generated from primitive/SDF priors.

The authored back sprite exists, but `back_mode=semantic_rules` uses it only for optional comparison, not geometry authority.

The direct QEF solve moved vertices in a direction that worsened the project metrics. The final `patch_qef` output uses the reflected constrained Hermite displacement because it scores better for this SDF convention.

Patch stabilisation is still rejected:

```text
patch_adjustment_accepted: false
```

This means the improvement comes from QEF/Hermite vertex placement at extraction time, not from the existing patch vertex stabiliser.

## Diagnosis

Semantic issue:

The semantic part layer is stable and labels are preserved. No new semantic failure is indicated.

SDF issue:

Adaptive SDF resolution remains useful. The SDF sign convention appears to make direct QEF displacement visually worse, so the sign/orientation guard is currently necessary.

Meshing issue:

QEF improves staircase and planar scores, but surface-flow is almost flat/slightly lower. Patch grouping remains the likely next meshing bottleneck because patch adjustment remains rejected and the patch report still flags threshold grouping.

Render issue:

No new render path was tested. Godot was intentionally skipped, so visual improvement should be inspected separately with stable non-Godot previews or a later safe Godot run.

## Recommended Next Engineering Step

Stabilise the QEF orientation policy with a small regression benchmark across hero/Mario or another authored sprite before making `patch_qef` a default. Then tune patch/macro-patch thresholds or add Hermite normal smoothing, because surface-flow did not materially improve even though staircase and planar metrics did.

## Handoff Checklist

- [x] Hermite samples are extracted.
- [x] QEF vertex placement runs.
- [x] `patch_qef` builder flag is supported.
- [x] QEF debug artefacts are generated.
- [x] QEF accepted cells are greater than zero.
- [x] Mesh remains connected.
- [x] Degenerate faces remain zero.
- [x] Semantic labels are preserved.
- [x] Hat asymmetry is preserved.
- [x] Non-manifold edges are controlled after cleanup.
- [x] At least one required quality metric improves.
- [x] `python tools\validate_project.py --skip-godot` passes.
- [x] `python -m unittest test_build_topological_sprite_model.py` passes.
- [x] Godot was not run.
