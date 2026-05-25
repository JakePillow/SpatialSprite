# SpriteSpatial Phase 5G.3 AI Agent Handoff

Output root:

`C:\dev\SpatialSprite\outputs\hero\prototype_32_phase5g3_semantic_parts`

Source asset:

`C:\dev\SpatialSprite\assets\samples\hero\spriteasset_v1.json`

Build command used for this output:

```powershell
python tools\build_topological_sprite_model.py --asset assets\samples\hero\spriteasset_v1.json --profile profiles\prototype_32.json --semantic-overrides assets\samples\hero\semantic_overrides --semantic-override-mode supplement --semantic-parts --semantic-depth-profiles --semantic-depth-profile humanoid_voxel --directional-morphology --morphology-profile fantasy_humanoid --depth-mode mylar_edt --closed-body --back-mode semantic_rules --mesh-backend surface_nets --surface-net-smoothing-alpha 0.65 --render-profile voxel_sprite --emit-semantic-parts-debug --emit-directional-debug --out outputs\hero\prototype_32_phase5g3_semantic_parts
```

Note: This verified output was generated without `--godot-preview`, `--emit-render-diagnostics`, `--emit-canonical-view-metrics`, or `--emit-visual-mapping` to avoid Godot crash dialogs.

## Primary Reports

- `validation_report.json`
- `topological_model.json`
- `mesh.json`
- `surface_nets_report.json`
- `voxel_render_report.json`
- `semantic_boundary_debug.json`
- `part_graph.json`
- `semantic_report.json`
- `semantic_warnings.json`
- `semantic_override_report.json`

## Phase 5G.3 Semantic Parts

Directory:

`semantic_parts\`

Files:

- `semantic_part_graph.json`
- `part_reduction_report.json`
- `canonical_parts_overlay.png`
- `raw_vs_canonical_parts.png`
- `orphan_absorption_debug.png`
- `outline_debris_debug.png`
- `masks\outline.png`
- `masks\head.png`
- `masks\face.png`
- `masks\hair_hat.png`
- `masks\torso.png`
- `masks\left_arm.png`
- `masks\right_arm.png`
- `masks\left_leg.png`
- `masks\right_leg.png`
- `components\*_components.png`

Key semantic part metrics:

```json
{
  "semantic_parts_enabled": true,
  "raw_region_count": 64,
  "raw_semantic_part_count": 9,
  "canonical_part_count": 9,
  "part_reduction_ratio": 0.859375,
  "tiny_orphans_absorbed": 8,
  "outline_debris_removed": 0,
  "geometry_uses_canonical_parts": true,
  "canonical_required_parts_present": true,
  "passed": true
}
```

## Semantic Authority

Directory:

`semantic_authority\`

Files:

- `semantic_authority_report.json`
- `hair_hat_authority_debug.png`
- `override_priority_resolution.png`
- `front_back_semantic_correspondence.json`
- `directional_morphology_gate_debug.json`

Key authority metrics:

```json
{
  "semantic_authority_enabled": true,
  "override_overlap_ratio": 0.5350553505535055,
  "hat_authority_passed": true,
  "hat_pixel_count": 12,
  "hat_component_count": 1,
  "hat_head_attachment_score": 1.0,
  "hat_torso_overlap_count": 0,
  "hat_directional_morphology_allowed": true,
  "directional_morphology_gated_labels": ["equipment/shield/sword"],
  "back_geometry_authority": "semantic_rules",
  "front_back_semantic_correspondence_passed": true,
  "passed": true
}
```

Important warning:

- `override_overlap_ratio` is `0.535`, which is allowed for `prototype_32` but should remain visible. A stricter quality profile should fail much earlier.

## Directional Morphology

Directory:

`directional_debug\`

Files:

- `directional_morphology_report.json`
- `hat_asymmetry_debug.json`
- `hat_direction_debug.png`
- `hat_front_back_profile_debug.png`
- `side_hat_projection_debug.png`
- `directional_field_map.png`
- `morphology_bias_overlay.png`
- `semantic_axis_debug.png`
- `directional_occupancy_slices.png`
- `side_projection_debug.png`
- `top_projection_debug.png`
- `slices\directional_slice_*.png`

Key directional metrics:

```json
{
  "directional_morphology_enabled": true,
  "hat_pointed_back_present": true,
  "front_hat_extension_score": 0.019873885437846184,
  "back_hat_extension_score": 0.06051371619105339,
  "hat_asymmetry_ratio": 3.0448860329956453
}
```

## Depth And SDF

Mylar front depth:

- `mylar\mylar_depth_report.json`
- `mylar\z_front.npy`
- `mylar\z_front.png`
- `mylar\z_body.png`
- `mylar\silhouette_pin_debug.png`
- `mylar\z_regions\*.png`

Back hemisphere:

- `back\back_rules.json`
- `back\z_back.npy`
- `back\z_back.png`
- `back\back_hemisphere_debug.png`
- `back\seam_debug.png`

Seam:

- `seam\seam_validation.json`
- `seam\seam_mask.png`
- `seam\seam_rings.json`
- `seam\seam_components.json`

SDF:

- `sdf\sdf_summary.json`
- `sdf\sdf_volume.npy`
- `sdf\semantic_volume.npy`
- `sdf\occupancy_volume.npy`
- `sdf\sdf_slice_contact_sheet.png`
- `sdf\sdf_slices\slice_*.png`

Key SDF metrics:

```json
{
  "sdf_volume_shape": [32, 24, 25],
  "sdf_sign_consistency": true,
  "sdf_dtype": "float32",
  "semantic_dtype": "int32",
  "closed_volume_connected": true,
  "hollow_gap_ratio": 0.0,
  "surface_nets_ready": true,
  "manifold_ready_estimate": true
}
```

## Semantic Depth Profiles

Directory:

`depth_profiles\`

Files:

- `semantic_depth_profile_report.json`
- `semantic_depth_map.png`
- `semantic_thickness_debug.png`
- `semantic_z_slices.png`
- `occupancy_volume_slices.png`
- `profile_assignment_overlay.png`
- `side_projection_debug.png`
- `top_projection_debug.png`

Key semantic depth metrics:

```json
{
  "semantic_depth_profiles_enabled": true,
  "uniform_slab_ratio": 0.014760147601476014,
  "semantic_depth_variance": 19.912256240844727,
  "side_profile_readability_score": 0.9266591662322414
}
```

## Meshing And Materials

Meshing:

- `meshing\surface_nets_input.npz`
- `meshing\meshing_backend_report.json`
- `meshing\optional_closed_preview_mesh.json`
- `surface_nets_report.json`
- `mesh.json`

Key mesh metrics:

```json
{
  "mesh_backend": "surface_nets",
  "surface_net_vertices": 1608,
  "surface_net_faces": 1620,
  "active_cell_count": 1608,
  "semantic_boundary_edge_count": 336,
  "degenerate_face_count": 0,
  "non_manifold_edge_count": 11,
  "mesh_connected_components": 1,
  "semantic_label_preservation_passed": true
}
```

Voxel render material pass:

- `material_debug\face_type_counts.json`
- `material_debug\render_profile.json`
- `material_debug\render_colour_swatches.png`
- `voxel_render_report.json`

Key material metrics:

```json
{
  "render_profile": "voxel_sprite",
  "internal_black_face_ratio": 0.02345679012345679,
  "outer_outline_preservation_score": 0.7682926829268293,
  "source_colour_match_score": 0.7785665695808106,
  "side_face_shading_score": 1.0,
  "voxel_face_readability_score": 0.8796777760898729
}
```

## Raw Debug Still Available

Raw CCL/region debug was preserved:

- `region_id_map.png`
- `region_overlay.png`
- `part_graph.json`
- `per_part_mesh_debug\part_000_mask.png` through `part_063_mask.png`

These are debug-only for this phase. Geometry consumes canonical semantic parts when `semantic_parts_enabled` is true.

## Validation

Final validation:

```json
{
  "passed": true,
  "semantic_parts_enabled": true,
  "geometry_uses_canonical_parts": true,
  "canonical_required_parts_present": true,
  "closed_volume_connected": true,
  "surface_net_zero_faces": false,
  "surface_net_degenerate_faces": false,
  "semantic_label_preservation_passed": true
}
```

Repository-level verification performed:

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed.
