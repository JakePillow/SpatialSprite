# SpriteSpatial Phase 7A Handoff: Authored Multi-View Geometry Authority

## Status

Phase 7A is implemented and validated for the hero asset.

The pipeline now supports `--back-mode front_back_sprite` as a real geometry authority mode. The authored front sprite constrains the positive/front projection, the authored back sprite constrains the negative/rear projection, and placeholder side sprites are explicitly rejected as geometry authority.

The output is structurally valid: the SDF is closed and connected, the final mesh is connected, semantic labels are preserved, degenerate faces remain zero, and topology cleanup passes.

## Output Folder

```text
outputs/hero/prototype_32_phase7a_multiview_authority/
```

## Command Run

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
  --back-mode front_back_sprite `
  --multi-view-authority `
  --view-authority-mode front_back_sprite `
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
  --emit-view-authority-debug `
  --out outputs\hero\prototype_32_phase7a_multiview_authority
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

Godot preview was skipped because it has been unstable in this environment and the user explicitly asked not to keep launching it.

```powershell
--api-visual-judge
```

The OpenAI/API visual judge was not run. API tools are advisory only in this project; they do not mutate geometry, generate sprites, or improve the SDF/mesh. Running this same build locally in PowerShell should produce the same deterministic geometry.

## Files Added Or Changed

Implementation:

```text
tool/spritespatial/view_authority.py
tool/spritespatial/back_hemisphere.py
tool/spritespatial/sdf_volume.py
tool/spritespatial/manifold_validation.py
tools/build_topological_sprite_model.py
```

No functional change was needed in `tool/spritespatial/source_coverage.py`; the existing source coverage layer already classified:

```text
front: authored
back: authored
left: mirrored_placeholder
right: mirrored_placeholder
```

Builder flags added:

```text
--multi-view-authority
--view-authority-mode front_back_sprite|front_back_side|auto
--emit-view-authority-debug
```

## Primary Reports And Debug Outputs

View authority:

```text
view_authority/front_back_view_correspondence.json
view_authority/view_authority_report.json
view_authority/projection_iou_report.json
view_authority/front_constraint_mask.png
view_authority/back_constraint_mask.png
view_authority/side_constraint_mask.png
view_authority/front_back_conflict_map.png
view_authority/semantic_correspondence_overlay.png
view_authority/front_projection_mask.png
view_authority/back_projection_mask.png
```

Core outputs:

```text
sdf/sdf_volume.npy
sdf/semantic_volume.npy
sdf/occupancy_volume.npy
sdf/sdf_summary.json
meshing/surface_nets_input.npz
mesh.json
mesh_patch.json
topology_cleanup/mesh_topology_cleaned.json
validation_report.json
```

Existing debug layers also emitted:

```text
semantic_parts/
depth_profiles/
directional_debug/
patch_nets/
macro_patches/
qef/
topology_cleanup/
material_debug/
```

## Key Validation Metrics

View authority:

```text
multi_view_authority_enabled: true
front_geometry_authority: authored_front
back_geometry_authority: authored_back
side_geometry_authority: placeholder
front_back_sprite_backend_enabled: true
front_back_correspondence_passed: true
side_authority_used: false
view_constraint_conflict_count: 38
front_projection_iou: 0.9727767695099818
back_projection_iou: 0.8939393939393939
projection_measurement_stage: post_volume_cleanup
```

The previous semantic-rules outputs projected against the authored back sprite at about:

```text
semantic_rules_back_projection_iou: 0.68972
phase7a_authored_back_projection_iou: 0.89394
```

SDF and topology:

```text
closed_volume_connected: true
connected_component_count: 1
seam_discontinuity_max: 0.0
sdf_volume_shape: [45, 34, 35]
effective_voxel_budget_multiplier: 2.7890625
surface_nets_ready: true
manifold_ready_estimate: true
```

Mesh:

```text
mesh_backend: surface_nets_patch
surface_net_vertex_placement: patch_qef
surface_net_vertices: 4166
surface_net_faces: 4154
mesh_connected_components: 1
degenerate_face_count: 0
non_manifold_after_cleanup: 5
semantic_label_preservation_passed: true
```

QEF and morphology:

```text
qef_enabled: true
qef_cells_processed: 4166
qef_cells_accepted: 4018
qef_acceptance_ratio: 0.9644743158905424
qef_max_displacement: 0.07000195980072021
hat_asymmetry_ratio: 2.8036581307124817
directional_feature_preservation_score: 1.0
```

## Pass/Fail Result

Phase 7A passed.

Hard gates:

```text
validation_report.passed: true
back_geometry_authority == authored_back
front_back_sprite_backend_enabled == true
closed_volume_connected == true
mesh_connected_components == 1
degenerate_face_count == 0
semantic_label_preservation_passed == true
front_projection_iou >= 0.80
back_projection_iou >= 0.80
```

## Warnings And Known Caveats

The hero asset still has no true authored side-view authority:

```text
left: mirrored_placeholder
right: mirrored_placeholder
side_geometry_authority: placeholder
side_authority_used: false
```

So side views are still generated from deterministic depth/morphology priors. This phase fixes authored back authority; it does not solve missing side authority.

The semantic override overlap warning remains:

```text
override_overlap_ratio: 0.5350553505535055
```

It is tolerated by `prototype_32`, but would need stricter authored masks for high-quality production.

Patch stabilisation remains guarded:

```text
patch_adjustment_accepted: false
```

QEF still improves the extraction metrics, but patch vertex adjustment itself is not being accepted.

## Diagnosis

Semantic issue:

Semantic part consolidation remains stable. Required semantic labels are preserved, and authored back correspondence passes.

SDF issue:

The authored back sprite now contributes to actual SDF geometry authority. Initial enforcement created tiny disconnected depth islands, so the implementation now fills non-outline authority columns between front/back samples and pins authored back seam pixels to the shared front seam. This restored closed connectivity.

Meshing issue:

The final mesh is connected and valid. Non-manifold edges are controlled after cleanup, but not fully eliminated.

Render issue:

No Godot render was run. Visual quality should be inspected from stable non-Godot previews or a later Godot run only when the local executable is stable.

View authority issue:

Back authority is fixed. Side authority is still the main blocker for side/back rotational fidelity because the side sprites are mirrored placeholders, not independently authored views.

## Recommended Next Engineering Step

Add or extract a true authored side sprite and run:

```text
--multi-view-authority --view-authority-mode front_back_side
```

Then compare side projection IoU and side visual mapping before further SDF or meshing work. If side authority remains unavailable, the next quality ceiling is not API usage; it is deterministic reconstruction from insufficient source views.

## Handoff Checklist

- [x] `front_back_sprite` is a real back-geometry backend.
- [x] Authored back sprite is used as geometry authority.
- [x] Placeholder side sprites are not treated as authoritative.
- [x] Front/back correspondence report is generated.
- [x] View authority debug masks are generated.
- [x] SDF volume is connected.
- [x] Mesh remains connected.
- [x] Degenerate faces remain zero.
- [x] Semantic labels are preserved.
- [x] Hat asymmetry is preserved.
- [x] Back projection improves versus previous semantic-rules output.
- [x] `python tools\validate_project.py --skip-godot` passes.
- [x] `python -m unittest test_build_topological_sprite_model.py` passes.
- [x] Godot was not run.
- [x] API visual judge was not run because it is advisory only.
