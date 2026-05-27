# SpriteSpatial Phase 6H Handoff: Adaptive High-Resolution SDF Production Path

## Status

Phase 6H is implemented and validated for the hero asset.

The adaptive SDF path promotes the Phase 6G resolution signal into a controlled production option. It requests high-detail sampling from `prototype_adaptive`, clamps the effective sampling to the configured voxel budget, then runs topology cleanup before render/material assignment.

The result improves the useful topology signals versus the 1.0 baseline while controlling non-manifold edges.

## Output Folder

```text
outputs/hero/prototype_32_phase6h_adaptive_sdf/
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
  --topology-cleanup `
  --surface-net-smoothing-alpha 0.65 `
  --preserve-silhouette-edges `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-patch-debug `
  --emit-macro-patch-debug `
  --emit-resolution-debug `
  --emit-topology-cleanup-debug `
  --out outputs\hero\prototype_32_phase6h_adaptive_sdf
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
tool/spritespatial/sdf_volume.py
tool/spritespatial/topology_cleanup.py
tool/spritespatial/manifold_validation.py
tool/spritespatial/voxel_render_profile.py
tools/build_topological_sprite_model.py
```

Resolution profiles:

```text
profiles/resolution_profiles/prototype_adaptive.json
profiles/resolution_profiles/quality_adaptive.json
profiles/resolution_profiles/debug_uniform_2x.json
```

Builder additions:

```text
--adaptive-sdf-resolution
--resolution-profile
--emit-resolution-debug
--topology-cleanup
--emit-topology-cleanup-debug
```

## Primary Outputs

```text
mesh.json
mesh_patch.json
topological_model.json
surface_nets_report.json
validation_report.json
resolution/voxel_budget_report.json
topology_cleanup/cleanup_report.json
topology_cleanup/mesh_topology_cleaned.json
patch_nets/patch_report.json
macro_patches/macro_patch_report.json
```

## Debug Outputs

Resolution debug:

```text
resolution/resolution_profile_used.json
resolution/adaptive_region_map.png
resolution/high_detail_band_debug.png
resolution/semantic_boundary_resolution_debug.png
resolution/voxel_budget_report.json
resolution/resolution_debug_payload.json
```

Topology cleanup debug:

```text
topology_cleanup/non_manifold_edges_before.json
topology_cleanup/non_manifold_edges_after.json
topology_cleanup/cleanup_report.json
topology_cleanup/repaired_edge_debug.png
topology_cleanup/sliver_face_debug.png
```

Patch and macro-patch debug:

```text
patch_nets/patch_graph.json
patch_nets/patch_id_map.png
patch_nets/before_after_contact_sheet.png
macro_patches/macro_patch_graph.json
macro_patches/macro_patch_id_map.png
macro_patches/before_after_contact_sheet.png
```

## Key Validation Metrics

Adaptive SDF:

```text
adaptive_sdf_resolution_enabled: true
resolution_profile: prototype_adaptive
sdf_resolution_strategy: highres_internal_downsampled
sdf_volume_shape: [45, 34, 35]
sdf_resolution_scale: 1.420615826752797
effective_voxel_budget_multiplier: 2.7890625
adaptive_high_detail_region_count: 4
silhouette_band_high_res_enabled: true
semantic_boundary_high_res_enabled: true
```

Patch topology versus Phase 6F 1.0 baseline:

```text
surface_flow_after: 0.47614215635667057
baseline_surface_flow_after: 0.46557124540533334
planar_macro_patch_count: 8
baseline_planar_macro_patch_count: 2
macro_patch_count: 409
mean_macro_patch_size: 7.799511002444988
macro_patch_coherence_score: 0.565845239207836
baseline_macro_patch_coherence_score: 0.4968846047569451
```

Topology cleanup:

```text
topology_cleanup_applied: true
non_manifold_before_cleanup: 12
non_manifold_after_cleanup: 7
baseline_non_manifold_edge_count: 11
target_max_non_manifold_edges: 26
duplicate_faces_removed: 0
duplicate_vertices_merged: 0
sliver_faces_removed: 0
non_manifold_faces_removed: 12
```

Mesh preservation:

```text
mesh_connected_components: 1
degenerate_face_count: 0
semantic_label_preservation_passed: true
silhouette_drift_px: 0.0
hat_asymmetry_ratio: 2.802311212197138
validation_report.passed: true
```

Render profile metrics:

```text
internal_black_face_ratio: 0.024564676616915422
outer_outline_preservation_score: 0.7178571428571429
source_colour_match_score: 0.7712213987886382
side_face_shading_score: 1.0
voxel_face_readability_score: 0.8649002324263706
```

## Pass/Fail Result

Phase 6H passed.

Hard gates:

```text
validation_report.passed: true
mesh_connected_components: 1
semantic labels preserved: true
degenerate_face_count: 0
silhouette drift: 0.0
hat asymmetry target preserved: true
non_manifold_after_cleanup <= 26: true
voxel budget <= 3.0: true
```

Repository verification:

```text
validate_project.py --skip-godot: passed
test_build_topological_sprite_model.py: 12 tests passed
```

## Known Warnings

Expected prototype warnings:

```text
Authored back sprite is available but semantic_rules uses it only as optional comparison, not geometry authority.
Side profile is generated from primitive/SDF priors. Provide side sprite for higher fidelity.
Semantic override overlap ratio 0.535 exceeds warning threshold 0.20.
Directional labels are absent from this asset and will be gated: equipment/shield/sword.
```

## Diagnosis

Adaptive high resolution is useful. Compared with the 1.0 Phase 6F baseline, it increases planar macro-patches and improves surface-flow while keeping the mesh connected and reducing non-manifold edges after cleanup.

Layer diagnosis:

```text
semantic issue: not the blocker; canonical parts and labels remain stable.
SDF issue: partially improved; higher sampling exposes better patch structure.
meshing issue: still present; patch vertex adjustment remains rejected and QEF/Hermite placement is still not implemented.
render issue: not the primary blocker for this phase.
```

The production path is now safer than uniform 2x because the adaptive profile keeps the voxel budget under 3x and topology cleanup controls non-manifold edges. It is still not a final surface-quality solution.

## Recommended Next Engineering Step

Keep the adaptive SDF path as the production high-resolution option, then implement QEF/Hermite-corrected patch-aware Surface Nets vertex placement. That next step should use this Phase 6H output as the controlled high-resolution input rather than returning to uniform 2x.

## Handoff Checklist

- [x] adaptive SDF resolution profiles added
- [x] adaptive builder flags added
- [x] topology cleanup module added
- [x] topology cleanup builder flags added
- [x] resolution debug outputs generated
- [x] topology cleanup debug outputs generated
- [x] voxel budget enforced
- [x] non-manifold edge count controlled
- [x] mesh remains connected
- [x] semantic labels preserved
- [x] silhouette drift remains within tolerance
- [x] hat asymmetry preserved
- [x] Godot preview not run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
