# SpriteSpatial Functionality Audit + Best 3D Recreation Attempt

## Scope

This audit tested the current repository as a working sprite-to-3D system and generated a best-effort model from an existing sample sprite.

Chosen asset:

```text
assets/samples/hero/spriteasset_v1.json
```

Reason for choosing it:

```text
The hero sample has the strongest authored support in the repo: front/back sprites, side references, and complete semantic override masks.
```

Godot was not run because it has been unstable in this environment.

## Output Folder

```text
outputs/hero/audit_best_3d_recreation/
```

## Build Command Run

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
  --emit-surface-net-debug `
  --out outputs\hero\audit_best_3d_recreation
```

## Verification Run

```powershell
python tools\validate_project.py --skip-godot
python -m unittest test_build_topological_sprite_model.py
```

Both passed.

## Preview Outputs

Best quick preview:

```text
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_contact_sheet.png
```

Individual preview frames:

```text
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_0.png
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_45.png
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_90.png
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_135.png
outputs/hero/audit_best_3d_recreation/python_mesh_preview/preview_180.png
```

Older fallback comparison previews:

```text
outputs/hero/audit_best_3d_recreation/python_fallback_preview_vs_phase1/
outputs/hero/audit_best_3d_recreation/python_fallback_preview_vs_phase6h/
```

The older comparison renderer does not understand the newest face-material metadata, so the custom `python_mesh_preview` contact sheet is the more useful visual output.

## Key Result

The system generated a closed, colored, semantic 3D mesh from the hero sprite.

Core validation:

```text
passed: true
sdf_volume_shape: 45x34x35
surface_net_vertices: 3212
surface_net_faces: 3216
mesh_connected_components: 1
degenerate_face_count: 0
non_manifold_after_cleanup: 7
semantic_label_preservation_passed: true
hat_asymmetry_ratio: 2.802311212197138
```

QEF/Hermite meshing:

```text
qef_enabled: true
surface_net_vertex_placement: patch_qef
qef_acceptance_ratio: 0.9517434620174346
qef_orientation: reflected
qef_orientation_guard_applied: true
staircase_artifact_before_qef: 0.5131218140038312
staircase_artifact_after_qef: 0.4723069560582821
planar_surface_score_before_qef: 0.9545646305974974
planar_surface_score_after_qef: 0.9642501471764979
```

Render/material metrics:

```text
internal_black_face_ratio: 0.024564676616915422
outer_outline_preservation_score: 0.7178571428571429
source_colour_match_score: 0.7712213987886382
voxel_face_readability_score: 0.8649002324263706
```

Source authority:

```text
front: authored
back: authored
left: mirrored_placeholder
right: mirrored_placeholder
fidelity_limit: side_inferred
back_geometry_authority: semantic_rules
```

Important: `semantic_rules` does not yet use the authored back sprite as true geometry authority. `front_back_sprite` is still effectively scaffolded/deferred in the current backend.

## System Functionality Audit

### 1. Asset And Profile Layer

Status: working.

The repo has a usable asset schema, canonical profiles, render profiles, depth profiles, morphology profiles, patch profiles, macro-patch profiles, remeshing profiles, and resolution profiles.

Strengths:

```text
profiles/prototype_32.json
profiles/depth_profiles/humanoid_voxel.json
profiles/morphology_profiles/fantasy_humanoid.json
profiles/resolution_profiles/prototype_adaptive.json
profiles/render_profiles/voxel_sprite.json
```

Gaps:

```text
Profile interactions are now complex and not all profile combinations are benchmarked.
quality_64 requires stronger source authority than many sample assets can provide.
```

### 2. Source Coverage And View Authority

Status: working, but currently conservative.

The system correctly distinguishes authored, inferred, missing, and placeholder views. For this hero asset it identifies the side references as mirrored placeholders and therefore marks the fidelity limit as `side_inferred`.

Main gap:

```text
Authored back exists, but the active closed-body backend is still using semantic back rules rather than true authored back geometry.
```

### 3. Semantic Override And Semantic Authority

Status: strong.

Manual semantic masks are loaded and validated. The hero asset has masks for head, face, hat/hair, torso, arms, legs, boots/feet, equipment, and outline.

Strengths:

```text
override priority handling exists
hat authority validation exists
semantic part consolidation works
canonical part count is much lower than raw region count
```

Gaps:

```text
The system still depends heavily on authored masks for good output.
Raw sprite colour segmentation alone is not enough for high-quality reconstruction.
```

### 4. Depth And Volume Layer

Status: working and currently the strongest part of the system.

Implemented layers include:

```text
Mylar EDT front depth
semantic anatomical depth profiles
directional morphology
asymmetric hat morphology
adaptive SDF resolution
closed SDF volume
semantic volume preservation
```

Strengths:

```text
The volume is connected.
Semantic labels survive through the volume.
The hat/back asymmetry metric passes.
Adaptive resolution improves topology signals.
```

Gaps:

```text
True authored side and back constraints are not yet driving the closed SDF.
The SDF is still front-derived and rule-derived in side/back views.
```

### 5. Meshing Layer

Status: structurally successful, visually still rough.

Current strongest backend:

```text
surface_nets_patch + macro_patches + patch_qef + topology_cleanup
```

Strengths:

```text
nonzero mesh
connected mesh
semantic labels preserved
degenerate faces remain zero
QEF/Hermite improves staircase and planar metrics
topology cleanup controls non-manifold edges
```

Gaps:

```text
Patch adjustment is still rejected.
Surface flow barely improves.
The mesh still reads as welded voxel anatomy in places.
Non-manifold edges are controlled but not zero.
```

### 6. Render Layer

Status: metadata path works; Godot path is unstable in this environment.

The voxel render profile applies material metadata, source-color matching, side darkening, and black seam suppression. The Python fallback preview can render those face colors from JSON.

Gaps:

```text
Godot preview should not be treated as reliable on this machine right now.
The current mesh JSON does not have a universal standalone preview/export tool.
GLB/export path is not the main validated output yet.
```

### 7. Diagnostics And Benchmarking

Status: broad but fragmented.

Available tools include:

```text
tools/validate_project.py
tools/run_resolution_diagnostic.py
tools/run_visual_benchmark.py
tools/compare_profile_outputs.py
tool/spritespatial/render_diagnostics.py
tool/spritespatial/render_comparison.py
tool/spritespatial/api_visual_judge.py
```

Strengths:

```text
validation gates catch structural failures
resolution diagnostic produced a useful decision
visual mapping exists for sprite-vs-render comparison
benchmark harness exists
```

Gaps:

```text
The default validation command validates the baseline path, not every latest phase path.
Some comparison tooling still has old labels and does not fully understand current material metadata.
Visual quality scoring is useful but not yet authoritative.
```

## Honest Visual Assessment

This is the closest current non-Godot 3D recreation I could generate from the repository files.

What worked:

```text
The hero becomes a closed colored 3D volume.
Front identity is recognizable.
Semantic regions survive.
The hat/outline/body mass are visible.
The mesh rotates and remains connected.
QEF reduces staircase artifacts.
```

What still looks weak:

```text
Side view is not truly authored.
The silhouette is still chunky.
The body reads as welded voxel chunks rather than clean stylised low-poly anatomy.
The face/front details become noisy in 3D.
The side profile still exposes front-derived assumptions.
```

## Main Bottleneck

The biggest bottleneck is no longer raw infrastructure. It is view authority and meshing quality.

Priority gap:

```text
The backend needs actual authored side/back silhouette constraints feeding the SDF, then patch/QEF placement needs to use those view constraints.
```

Secondary gap:

```text
Patch/macro-patch logic still does not move vertices after QEF because its guarded stabilisation rejects the adjustment.
```

## Recommended Next Engineering Steps

1. Make authored back and side views real geometry authority.
2. Add a proper JSON mesh preview/export tool that uses `face_metadata.render_color`.
3. Extend validation so latest-phase builds are first-class validation targets.
4. Tune patch/macro-patch grouping after QEF, because QEF improved staircase but not surface flow.
5. Add GLB export only after preview/render validation is stable.

## Pass/Fail

Functional system audit: pass.

Best-effort 3D recreation attempt: pass structurally, mixed visually.

The system can generate a deterministic closed semantic 3D sprite model today. It is not yet a faithful high-quality 3D recreation from all angles.
