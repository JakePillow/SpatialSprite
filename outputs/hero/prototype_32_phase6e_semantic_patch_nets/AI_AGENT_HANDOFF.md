# SpriteSpatial Phase 6E Handoff: Semantic Patch Surface Nets

## Status

Phase 6E is implemented and validated for the hero asset.

The new `surface_nets_patch` backend constructs semantic active-cell patches before render/export. It preserves mesh connectivity, semantic labels, silhouette authority, non-manifold count, and directional hat extension.

Important caveat: this phase preserved topology metrics but did not improve them. Patch construction works, but patch-aware vertex stabilisation was rejected by the safety guard because the proposed movement did not improve staircase or surface-flow metrics. The likely issue is patch grouping thresholds and/or patch fragmentation, not semantic authority or SDF closure.

## Output Folder

```text
outputs/hero/prototype_32_phase6e_semantic_patch_nets/
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
  --surface-net-smoothing-alpha 0.65 `
  --preserve-silhouette-edges `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-patch-debug `
  --out outputs\hero\prototype_32_phase6e_semantic_patch_nets
```

## Verification Run

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed.

## Files Added Or Changed

Primary implementation:

```text
tool/spritespatial/semantic_patch_nets.py
tool/spritespatial/surface_nets.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

Patch profiles:

```text
profiles/patch_profiles/humanoid_voxel.json
profiles/patch_profiles/humanoid_lowpoly.json
profiles/patch_profiles/stylised_npr.json
```

Builder additions:

```text
--mesh-backend surface_nets_patch
--patch-profile
--emit-patch-debug
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
```

## Debug Outputs

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

Patch construction:

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
patch_coherence_score: 0.6095744680851064
patch_adjustment_accepted: false
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
planar_surface_score_before: 0.9581630442613437
planar_surface_score_after: 0.9581630442613437
patch_vertices_adjusted: 0
silhouette_drift_px: 0.0
```

## Fail Conditions

All hard patch-net gates passed:

```text
semantic_patch_nets_zero_faces: false
semantic_patch_nets_semantic_labels_disappeared: false
semantic_patch_nets_mesh_disconnected: false
semantic_patch_nets_degenerate_faces_introduced: false
semantic_patch_nets_silhouette_drift_exceeded: false
semantic_patch_nets_hat_asymmetry_dropped: false
semantic_patch_nets_non_manifold_edge_count_increased: false
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

The patch report states:

```text
patch_metric_improved_or_preserved: true
sdf_resolution_too_low: false
surface_net_vertex_placement_issue: false
authored_side_view_missing: false
render_material_readability_issue: false
patch_grouping_threshold_issue: true
likely_cause: patch grouping thresholds
```

Interpretation:

- Patch graph construction is functioning and produces detailed patch debug artefacts.
- Patch placement is guarded correctly: it refused to apply a movement that would not improve the metrics.
- The metrics were preserved exactly, but not improved.
- The high small-patch ratio and zero planar patches indicate patch grouping is too fragmented or curvature thresholds are too strict.
- This still confirms the next work should happen inside patch construction/extraction, not as another post-mesh relaxation pass.

## Recommended Next Step

Inspect `patch_nets/patch_graph.json`, `patch_nets/patch_id_map.png`, and `patch_nets/patch_curvature_debug.png`. The next likely fix is to merge compatible small patches into larger semantic patch regions or tune curvature/normal bucketing so some stable planar patches form before vertex stabilisation.

## Handoff Checklist

- [x] semantic patch-net module added
- [x] patch profiles added
- [x] `surface_nets_patch` backend wired
- [x] patch graph generated
- [x] patch debug outputs generated
- [x] mesh patch written
- [x] semantic labels preserved
- [x] mesh remains connected
- [x] no degenerate faces introduced
- [x] non-manifold count did not increase
- [x] silhouette and hat extension preserved
- [x] Godot preview not run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
- [x] visual caveat recorded honestly
