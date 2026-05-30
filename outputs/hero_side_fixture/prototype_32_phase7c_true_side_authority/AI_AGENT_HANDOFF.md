# SpriteSpatial Phase 7C Handoff: True Side Sprite Test Asset + Front/Back/Side Validation

## Status

Phase 7C is implemented and validated.

A controlled fixture asset was added at:

```text
assets/samples/hero_side_fixture/
```

The fixture copies the existing hero front/back sprites and adds a synthetic side-view fixture. This is not production art. It is explicitly marked as:

```text
authored_side_fixture
```

The purpose is to prove that `front_back_side` authority activates correctly when a non-placeholder side source is present.

## Output Folder

```text
outputs/hero_side_fixture/prototype_32_phase7c_true_side_authority/
```

## Command Run

```powershell
python tools\build_topological_sprite_model.py `
  --asset assets\samples\hero_side_fixture\spriteasset_v1.json `
  --profile profiles\prototype_32.json `
  --semantic-overrides assets\samples\hero_side_fixture\semantic_overrides `
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
  --view-authority-mode front_back_side `
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
  --out outputs\hero_side_fixture\prototype_32_phase7c_true_side_authority
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

Godot preview was not run because it has been unstable in this environment and the user asked to stop launching it.

```powershell
--api-visual-judge
```

The API visual judge was not run. This phase is deterministic and only proves source-view authority activation.

## Files Added Or Changed

Fixture asset:

```text
assets/samples/hero_side_fixture/spriteasset_v1.json
assets/samples/hero_side_fixture/README_FIXTURE.md
assets/samples/hero_side_fixture/hero_front.png
assets/samples/hero_side_fixture/hero_back.png
assets/samples/hero_side_fixture/hero_side_fixture_left.png
assets/samples/hero_side_fixture/hero_side_fixture_right.png
assets/samples/hero_side_fixture/semantic_overrides/
assets/samples/hero_side_fixture/semantic_overrides/side/
```

Implementation updates:

```text
tool/spritespatial/asset_schema.py
tool/spritespatial/source_coverage.py
tool/spritespatial/view_authority.py
tool/spritespatial/sdf_volume.py
tool/spritespatial/manifold_validation.py
tool/spritespatial/canonical_views.py
tools/build_topological_sprite_model.py
```

## Primary Reports And Debug Outputs

View authority:

```text
view_authority/side_authority_report.json
view_authority/side_view_correspondence.json
view_authority/view_authority_report.json
view_authority/projection_iou_report.json
view_authority/side_constraint_mask.png
view_authority/side_projection_mask.png
view_authority/side_conflict_map.png
view_authority/front_back_side_conflict_map.png
view_authority/semantic_side_correspondence_overlay.png
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

Comparison:

```text
outputs/hero_side_fixture/comparisons/phase7b_no_side_vs_phase7c_true_side/comparison_report.json
outputs/hero_side_fixture/comparisons/phase7b_no_side_vs_phase7c_true_side/comparison_summary.md
outputs/hero_side_fixture/comparisons/phase7b_no_side_vs_phase7c_true_side/metric_delta_table.csv
outputs/hero_side_fixture/comparisons/phase7b_no_side_vs_phase7c_true_side/side_authority_mask_contact_sheet.png
```

## Key Validation Metrics

Side authority:

```text
front_back_side_backend_enabled: true
side_geometry_authority: authored_side_fixture
side_semantic_authority: semantic_masks
side_authority_used: true
side_mirror_fallback_used: false
side_view_correspondence_passed: true
side_projection_iou: 0.5785997357992074
side_constraint_conflict_count: 319
side_constraint_partially_weighted: true
side_constraint_voxels_filled: 66
```

Front/back authority:

```text
front_geometry_authority: authored_front
back_geometry_authority: authored_back
front_projection_iou: 0.9727767695099818
back_projection_iou: 0.9053030303030303
front_back_correspondence_passed: true
```

SDF and mesh:

```text
closed_volume_connected: true
connected_component_count: 1
mesh_connected_components: 1
degenerate_face_count: 0
non_manifold_after_cleanup: 6
semantic_label_preservation_passed: true
hat_asymmetry_ratio: 2.8036581307124817
validation_report.passed: true
```

Comparison against Phase 7B:

```text
Phase 7B side_authority_used: false
Phase 7C side_authority_used: true
Phase 7B side_projection_iou: 0.0
Phase 7C side_projection_iou: 0.5785997357992074
Phase 7B mesh_connected_components: 1
Phase 7C mesh_connected_components: 1
Phase 7B degenerate_face_count: 0
Phase 7C degenerate_face_count: 0
```

## Pass/Fail Result

Phase 7C passed.

The side authority path is proven:

```text
side_geometry_authority: authored_side_fixture
side_authority_used: true
side_projection_iou > 0.0
validation_report.passed: true
```

## Warnings And Known Caveats

The side sprite is synthetic fixture art:

```text
assets/samples/hero_side_fixture/README_FIXTURE.md
```

It proves the pipeline mechanism, not production visual quality.

Side enforcement is partially weighted:

```text
side_constraint_partially_weighted: true
```

This is intentional. The first strict side enforcement produced disconnected SDF islands. The final implementation preserves topology by only filling side constraint voxels that can attach to existing volume and by avoiding destructive side carving.

Non-manifold edges increased slightly versus Phase 7B:

```text
Phase 7B non_manifold_after_cleanup: 5
Phase 7C non_manifold_after_cleanup: 6
```

This remains within the current validation tolerance.

## Diagnosis

Side asset detection:

Passed. The fixture metadata is read and reported as `authored_side_fixture`.

Side semantic masks:

Passed. Minimal side masks are present and reported as `semantic_masks`.

SDF constraint conflict:

Managed. Strict side enforcement disconnected the SDF; topology-preserving side enforcement fixed this while keeping side projection nonzero and meaningful.

Meshing instability:

No blocking instability. Mesh remains connected with zero degenerate faces.

Side silhouette quality:

Fixture quality is basic. It is good enough to validate authority activation, not to judge final visual fidelity.

## Recommended Next Engineering Step

Replace the synthetic fixture with a real authored side sprite from the same character/source set. Keep the same `front_back_side` command and compare:

```text
side_projection_iou
side_constraint_conflict_count
side_constraint_partially_weighted
mesh_connected_components
non_manifold_after_cleanup
visual side readability
```

If a real side sprite still needs partial weighting, the next task should improve multi-view conflict resolution rather than adding more smoothing or meshing features.

## Handoff Checklist

- [x] Side-authority fixture asset exists.
- [x] Fixture is explicitly marked as synthetic test authority.
- [x] `spriteasset_v1.json` includes front, back, left, and right.
- [x] Minimal side semantic masks exist.
- [x] `front_back_side` mode uses side geometry authority.
- [x] `side_authority_used` becomes true.
- [x] `side_projection_iou` is reported and greater than zero.
- [x] Mesh remains connected.
- [x] Degenerate faces remain zero.
- [x] Semantic labels are preserved.
- [x] Comparison report against Phase 7B is generated.
- [x] `python tools\validate_project.py --skip-godot` passes.
- [x] `python -m unittest test_build_topological_sprite_model.py` passes.
- [x] Godot was not run.
