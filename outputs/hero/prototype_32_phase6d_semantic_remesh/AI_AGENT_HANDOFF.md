# SpriteSpatial Phase 6D Handoff: Topology-Aware Semantic Remeshing

## Status

Phase 6D is implemented and validated for the hero asset.

The remeshing pass is structurally safe: semantic labels are preserved, the mesh remains connected, no degenerate faces or triangle inversions were introduced, the canonical silhouette was preserved, and the directional hat extension did not collapse.

Important caveat: visual topology metrics are mixed. Triangle count decreased slightly, but staircase artifact and surface-flow metrics worsened slightly. Treat this as a working topology-aware remeshing infrastructure pass, not as a solved visual-readability pass.

## Output Folder

```text
outputs/hero/prototype_32_phase6d_semantic_remesh/
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
  --mesh-backend surface_nets `
  --surface-net-smoothing-alpha 0.65 `
  --semantic-remesh `
  --remesh-profile humanoid_lowpoly `
  --remesh-iterations 1 `
  --remesh-strength 0.35 `
  --preserve-silhouette-edges `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-remesh-debug `
  --out outputs\hero\prototype_32_phase6d_semantic_remesh
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
tool/spritespatial/semantic_remeshing.py
tool/spritespatial/surface_nets.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

Profiles:

```text
profiles/remeshing_profiles/humanoid_lowpoly.json
profiles/remeshing_profiles/voxel_character.json
profiles/remeshing_profiles/stylised_npr.json
```

Builder flags added:

```text
--semantic-remesh
--remesh-profile
--remesh-iterations
--remesh-strength
--preserve-silhouette-edges / --no-preserve-silhouette-edges
--emit-remesh-debug
```

## Primary Outputs

```text
mesh.json
mesh_remeshed.json
topological_model.json
surface_nets_report.json
validation_report.json
remeshing/remesh_report.json
remeshing/topology_changes.json
```

## Debug Outputs

```text
remeshing/triangle_density_heatmap.png
remeshing/planar_regions_debug.png
remeshing/silhouette_edge_debug.png
remeshing/semantic_edge_lock_debug.png
remeshing/before_after_wireframe.png
remeshing/before_after_contact_sheet.png
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

Surface nets after remesh:

```text
mesh_backend: surface_nets
surface_net_vertices: 1605
surface_net_faces: 1590
surface_net_triangles: 3180
degenerate_face_count: 0
non_manifold_edge_count: 11
mesh_connected_components: 1
semantic_label_preservation_passed: true
```

Semantic remeshing:

```text
semantic_remesh_enabled: true
remesh_profile: humanoid_lowpoly
triangle_count_before: 3240
triangle_count_after: 3180
triangle_reduction_ratio: 0.018518518518518517
coplanar_merge_count: 30
remesh_vertices_adjusted: 418
mean_vertex_displacement: 0.025443023070693016
max_vertex_displacement: 0.26436737179756165
silhouette_drift_px: 0.0
silhouette_edge_preservation_score: 1.0
semantic_boundary_preservation_score: 1.0
directional_feature_preservation_score: 1.0
```

Visual topology metrics:

```text
staircase_artifact_before: 0.505232111323363
staircase_artifact_after: 0.5090833295209716
surface_flow_before: 0.46557124540533334
surface_flow_after: 0.4612104449388662
planar_surface_score_before: 0.9581630442613437
planar_surface_score: 0.9556480303875305
oblique_readability_score: 0.9236375005718542
lowpoly_coherence_score: 0.6066266499806054
```

## Fail Conditions

All hard remeshing gates passed:

```text
semantic_remesh_silhouette_drift_exceeded: false
semantic_remesh_semantic_labels_disappeared: false
semantic_remesh_mesh_disconnected: false
semantic_remesh_directional_asymmetry_dropped: false
semantic_remesh_hat_extension_collapsed: false
semantic_remesh_triangle_inversion_occurred: false
semantic_remesh_degenerate_faces_introduced: false
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

The remesh report states:

```text
topology_metric_improved: true
visual_metric_improved: false
semantic_issue: false
sdf_issue: false
meshing_issue: true
render_issue: false
likely_cause: meshing issue
```

Interpretation:

- The remesher made real topology changes: 30 coplanar merges and a small triangle-count reduction.
- Preservation constraints worked: no silhouette drift, labels preserved, hat extension preserved.
- The visual metric signal did not improve; staircase and surface-flow scores moved slightly in the wrong direction.
- The next bottleneck is still topology construction from surface nets, not semantic authority or SDF closure.

## Recommended Next Step

Inspect `remeshing/before_after_wireframe.png` and `remeshing/topology_changes.json` before increasing remesh strength. The better next engineering move is likely a topology-aware patch builder inside or immediately after surface nets, rather than stronger post-mesh relaxation.

## Handoff Checklist

- [x] semantic remeshing module added
- [x] remeshing profiles added
- [x] builder flags wired
- [x] validation fields added
- [x] remeshed mesh written
- [x] remesh debug outputs generated
- [x] semantic labels preserved
- [x] mesh remains connected
- [x] no degenerate faces introduced
- [x] hat extension preserved
- [x] Godot preview not run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
- [x] visual caveat recorded honestly
