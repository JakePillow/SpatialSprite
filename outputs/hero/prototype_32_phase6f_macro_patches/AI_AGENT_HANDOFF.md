# SpriteSpatial Phase 6F Handoff: Semantic Macro-Patch Consolidation

## Status

Phase 6F is implemented and validated for the hero asset.

The new macro-patch layer consolidates fragmented semantic patch-net micro-patches before patch-aware vertex stabilisation. It preserves the connected mesh, semantic labels, silhouette authority, non-manifold count, and directional hat extension.

Important caveat: macro-patch construction improves patch fragmentation metrics, but the guarded vertex stabilisation still rejects geometric adjustment because staircase and surface-flow scores do not improve. This is a structural step forward, not a visual-quality win yet.

## Output Folder

```text
outputs/hero/prototype_32_phase6f_macro_patches/
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
  --surface-net-smoothing-alpha 0.65 `
  --preserve-silhouette-edges `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-patch-debug `
  --emit-macro-patch-debug `
  --out outputs\hero\prototype_32_phase6f_macro_patches
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

Godot preview was skipped because previous Godot preview runs have been unstable in this environment and the task explicitly required no Godot preview unless stable.

## Files Added Or Changed

Primary implementation:

```text
tool/spritespatial/semantic_macro_patches.py
tool/spritespatial/semantic_patch_nets.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

Macro-patch profiles:

```text
profiles/macro_patch_profiles/humanoid_voxel.json
profiles/macro_patch_profiles/humanoid_lowpoly.json
profiles/macro_patch_profiles/stylised_npr.json
```

Builder additions:

```text
--macro-patches
--macro-patch-profile
--emit-macro-patch-debug
```

Existing Phase 6D/6E files remain in place:

```text
tool/spritespatial/semantic_patch_nets.py
tool/spritespatial/semantic_remeshing.py
profiles/patch_profiles/
profiles/remeshing_profiles/
```

## Primary Outputs

```text
mesh.json
mesh_patch.json
topological_model.json
surface_nets_report.json
validation_report.json
patch_nets/patch_graph.json
patch_nets/patch_report.json
macro_patches/macro_patch_graph.json
macro_patches/macro_patch_report.json
```

## Debug Outputs

Macro-patch debug:

```text
macro_patches/micro_vs_macro_patch_map.png
macro_patches/macro_patch_id_map.png
macro_patches/macro_patch_boundary_debug.png
macro_patches/macro_patch_normal_debug.png
macro_patches/absorbed_fragments_debug.png
macro_patches/before_after_macro_patch_wireframe.png
macro_patches/before_after_contact_sheet.png
```

Patch-net debug:

```text
patch_nets/patch_id_map.png
patch_nets/patch_boundary_debug.png
patch_nets/patch_normal_debug.png
patch_nets/patch_curvature_debug.png
patch_nets/patch_planar_projection_debug.png
patch_nets/before_after_patch_wireframe.png
patch_nets/before_after_contact_sheet.png
```

Upstream debug also present:

```text
semantic_parts/semantic_part_graph.json
semantic_parts/canonical_parts_overlay.png
semantic_authority/semantic_authority_report.json
directional_debug/hat_asymmetry_debug.json
depth_profiles/semantic_thickness_debug.png
sdf/sdf_summary.json
meshing/surface_nets_input.npz
material_debug/face_type_counts.json
```

## Key Validation Metrics

Semantic and SDF foundation:

```text
semantic_parts_enabled: true
raw_region_count: 64
canonical_part_count: 9
part_reduction_ratio: 0.859375
geometry_uses_canonical_parts: true
semantic_depth_profiles_enabled: true
directional_morphology_enabled: true
hat_asymmetry_ratio: 3.0448860329956453
closed_volume_connected: true
```

Patch-net baseline:

```text
semantic_patch_nets_enabled: true
patch_profile: humanoid_voxel
patch_count: 517
mean_patch_size: 3.1102514506769827
small_patch_ratio: 0.7059961315280464
planar_patch_count: 0
curved_patch_count: 517
silhouette_patch_count: 292
semantic_boundary_patch_count: 246
```

Macro-patch consolidation:

```text
macro_patches_enabled: true
macro_patch_profile: humanoid_voxel
micro_patch_count: 517
macro_patch_count: 273
macro_patch_reduction_ratio: 0.47195357833655704
mean_macro_patch_size: 5.82051282051282
small_macro_patch_ratio: 0.5604395604395604
planar_macro_patch_count: 2
curved_macro_patch_count: 14
directional_feature_macro_patch_count: 20
noise_fragments_absorbed: 151
macro_patch_coherence_score: 0.4968846047569451
```

Mesh and preservation:

```text
mesh_backend: surface_nets_patch
surface_net_vertices: 1608
surface_net_faces: 1620
surface_net_triangles: 3240
degenerate_face_count: 0
non_manifold_edge_count: 11
mesh_connected_components: 1
semantic_label_preservation_passed: true
semantic_boundary_preservation_score: 1.0
silhouette_edge_preservation_score: 1.0
directional_feature_preservation_score: 1.0
```

Visual topology metrics:

```text
triangle_count_before_patch: 3240
triangle_count_after_patch: 3240
staircase_artifact_before: 0.505232111323363
staircase_artifact_after: 0.505232111323363
surface_flow_before: 0.46557124540533334
surface_flow_after: 0.46557124540533334
patch_adjustment_accepted: false
patch_vertices_adjusted: 0
silhouette_drift_px: 0.0
```

## Pass/Fail Result

Phase 6F passes structurally.

Hard gates passed:

```text
semantic labels preserved
mesh connected
degenerate_face_count: 0
silhouette_drift_px: 0.0
hat extension preserved
non_manifold_edge_count did not increase
validation_report.passed: true
```

Repository checks passed:

```text
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
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

Macro-patches fixed part of the Phase 6E bottleneck:

```text
patch_count: 517 -> 273
mean_patch_size: 3.110 -> 5.821
small_patch_ratio: 0.706 -> 0.560
planar_patch_count: 0 -> 2
noise_fragments_absorbed: 151
```

However, the surface itself did not improve:

```text
staircase_artifact_before == staircase_artifact_after
surface_flow_before == surface_flow_after
patch_adjustment_accepted: false
```

Layer diagnosis:

```text
semantic issue: unlikely for this pass; canonical parts and labels are stable.
SDF issue: possible; grid resolution may still be too low for larger clean patches.
meshing issue: likely; surface-net vertex placement remains too cell-local even after macro grouping.
render issue: not the primary blocker for this phase.
```

The most likely next bottleneck is either SDF resolution or surface-net vertex placement. If macro-patch metrics are now acceptable but geometry still does not move, the next useful extraction-side step is QEF/Hermite-style vertex placement or a higher-resolution SDF test, not another post-mesh relaxation pass.

## Recommended Next Engineering Step

Run one controlled experiment:

```text
1. Keep the same semantic/macro-patch graph.
2. Increase the SDF grid resolution or depth slices for a temporary diagnostic build.
3. Compare patch_count, planar_macro_patch_count, staircase_artifact_after, and surface_flow_after.
```

If resolution helps, improve the Phase 5E/5A SDF sampling path. If resolution does not help, implement QEF/Hermite-corrected patch-aware Surface Nets vertex placement.

## Handoff Checklist

- [x] macro-patch module added
- [x] macro-patch profiles added
- [x] builder flags added
- [x] macro-patches integrated into `surface_nets_patch`
- [x] macro-patch graph generated
- [x] macro debug outputs generated
- [x] validation report extended
- [x] mesh remains connected
- [x] semantic labels preserved
- [x] no degenerate faces introduced
- [x] silhouette preserved
- [x] directional hat feature preserved
- [x] Godot preview not run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
- [x] visual caveat recorded honestly
