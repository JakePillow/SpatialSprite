# SpriteSpatial Phase 6C Handoff: Semantic Surface Cohesion

## Status

Phase 6C is implemented and validated for the hero asset.

The cohesion pass is structurally safe: the mesh remains connected, labels are preserved, no degenerate faces were introduced, the silhouette did not drift, and the hat tip/outline were preserved.

Important caveat: the surface-quality metrics did not improve. Normal discontinuity and fragmentation rose slightly, so this should be treated as a safe diagnostic pass rather than a visual win. The next bottleneck appears to be surface-nets topology/extraction rather than semantic authority, SDF closure, or render styling.

## Output Folder

```text
outputs/hero/prototype_32_phase6c_surface_cohesion/
```

## Command Run

Godot preview was intentionally omitted because Godot has been unstable in this environment.

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
  --surface-cohesion `
  --surface-cohesion-profile humanoid_voxel `
  --surface-cohesion-strength 0.35 `
  --surface-cohesion-iterations 2 `
  --render-profile voxel_sprite `
  --emit-semantic-parts-debug `
  --emit-directional-debug `
  --emit-surface-cohesion-debug `
  --out outputs\hero\prototype_32_phase6c_surface_cohesion
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
tool/spritespatial/surface_cohesion.py
profiles/surface_cohesion_profiles/humanoid_voxel.json
tools/build_topological_sprite_model.py
```

Primary generated outputs:

```text
outputs/hero/prototype_32_phase6c_surface_cohesion/mesh.json
outputs/hero/prototype_32_phase6c_surface_cohesion/mesh_cohesive.json
outputs/hero/prototype_32_phase6c_surface_cohesion/validation_report.json
outputs/hero/prototype_32_phase6c_surface_cohesion/surface_cohesion/surface_cohesion_report.json
outputs/hero/prototype_32_phase6c_surface_cohesion/surface_cohesion/cohesion_diagnosis.json
```

## Debug Outputs

Surface cohesion debug:

```text
surface_cohesion/vertex_displacement_debug.json
surface_cohesion/normal_discontinuity_debug.png
surface_cohesion/seam_alignment_debug.png
surface_cohesion/semantic_boundary_preservation.png
surface_cohesion/before_after_mesh_stats.json
surface_cohesion/before_after_contact_sheet.png
```

Upstream debug kept with this build:

```text
semantic_parts/semantic_part_graph.json
semantic_parts/canonical_parts_overlay.png
semantic_parts/raw_vs_canonical_parts.png
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

Surface nets mesh:

```text
mesh_backend: surface_nets
surface_net_vertices: 1608
surface_net_faces: 1620
degenerate_face_count: 0
non_manifold_edge_count: 11
mesh_connected_components: 1
semantic_label_preservation_passed: true
```

Surface cohesion:

```text
surface_cohesion_enabled: true
surface_cohesion_profile: humanoid_voxel
cohesion_vertices_adjusted: 485
mean_vertex_displacement: 0.036422934383153915
max_vertex_displacement: 0.2746351361274719
semantic_boundary_preservation_score: 0.9784221873605038
normal_discontinuity_before: 0.5344287545946667
normal_discontinuity_after: 0.5368797624373873
surface_fragmentation_before: 0.5459280732025827
surface_fragmentation_after: 0.5475212283003512
silhouette_drift_px: 0.0
hat_tip_preserved: true
outline_preserved: true
```

Voxel render profile metrics:

```text
render_profile: voxel_sprite
internal_black_face_ratio: 0.02345679012345679
outer_outline_preservation_score: 0.7682926829268293
source_colour_match_score: 0.7785665695808106
side_face_shading_score: 1.0
voxel_face_readability_score: 0.8796777760898729
```

## Fail Conditions

All Phase 6C hard gates passed:

```text
surface_cohesion_degenerate_faces_introduced: false
surface_cohesion_mesh_disconnected: false
surface_cohesion_semantic_labels_disappeared: false
surface_cohesion_silhouette_drift_exceeded: false
surface_cohesion_max_vertex_displacement_exceeded: false
surface_cohesion_outline_preservation_failed: false
surface_cohesion_hat_tip_preservation_failed: false
```

## Known Warnings

The validation report still carries these expected warnings:

```text
Authored back sprite is available but semantic_rules uses it only as optional comparison, not geometry authority.
Side profile is generated from primitive/SDF priors. Provide side sprite for higher fidelity.
Semantic override overlap ratio 0.535 exceeds warning threshold 0.20.
Directional labels are absent from this asset and will be gated: equipment/shield/sword.
```

These warnings do not block prototype_32.

## Diagnosis

The generated diagnosis is:

```text
surface_metric_improved: false
semantic_issue: false
sdf_issue: false
meshing_issue: true
render_issue: false
likely_cause: meshing issue
```

Interpretation:

- semantic authority is clean enough for this phase
- canonical semantic parts are active and reduced the raw region graph
- closed SDF connectivity and semantic preservation are good
- local post-mesh relaxation is safe but does not reduce the current normal/fragmentation metric
- the next likely bottleneck is surface-nets topology, extraction density, or the cohesion objective itself

## Recommended Next Step

Do not keep increasing cohesion strength blindly. The next engineering step should inspect surface-nets topology and consider a topology-aware extraction or a better cohesion objective before more relaxation.

## Handoff Checklist

- [x] semantic parts enabled
- [x] geometry consumes canonical parts
- [x] semantic depth profiles enabled
- [x] directional morphology enabled
- [x] surface cohesion enabled
- [x] cohesive mesh written
- [x] validation report updated
- [x] debug outputs generated
- [x] no Godot preview run
- [x] `validate_project.py --skip-godot` passed
- [x] `python -m unittest test_build_topological_sprite_model.py` passed
- [x] quality caveat recorded instead of overstated
