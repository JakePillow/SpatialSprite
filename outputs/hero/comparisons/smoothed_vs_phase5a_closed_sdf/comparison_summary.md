# SpriteSpatial Profile Comparison

Verdict: **infrastructure_only**

## Metrics

- Baseline faces: 1518
- Candidate faces: 0
- Baseline voxels: 1751
- Candidate voxels: 0
- Candidate primitives: {}
- Candidate semantic warnings: {}
- Candidate override metrics: {'mode': None, 'override_pixels_applied': 0, 'override_overlap_count': 0, 'unlabelled_opaque_pixel_ratio': 0.0, 'critical_label_coverage': {}, 'torso_head_overlap_count_after_override': None, 'disconnected_critical_labels_after_override': None}
- Candidate smoothing: {'enabled': False, 'mode': 'none', 'silhouette_drift_px': 0.0, 'outline_preservation_score': 1.0, 'semantic_boundary_violation_count': 0, 'face_count_before_smoothing': 0, 'face_count_after_smoothing': 0, 'degenerate_faces_removed': 0, 'smoothing_passed': True}
- Candidate Phase 5A: {'mylar_depth_enabled': True, 'closed_body_enabled': True, 'back_mode': 'semantic_rules', 'sdf_volume_shape': [32, 24, 25], 'sdf_dtype': 'float32', 'semantic_dtype': 'int32', 'surface_nets_ready': True, 'manifold_ready_estimate': True}

## Questions

1. Side profile improved: **False**. Continuity score is None; occupied voxels changed from 1751 to 0; depth span 0.000 vs baseline 0.554.
2. Head/torso/limb volume coherent: **False**. Primitive mix is {}; head/torso/limbs are no longer all cuboid/flat.
3. Outline shell controlled: **False**. Outline shell voxels 0; outline source pixels 0.
4. Face/voxel budget ok: **True**. Candidate faces 0; baseline faces 1518; profile budget treated as 4000.
5. Front readability preserved: **False**. Baseline alpha coverage 0.3529; Candidate front projection 0.0000.
6. Worsened semantic parts: none detected by validation, though source semantic warnings remain.
7. Smoothing passed: **True**. Smoothing was not enabled for the candidate.
8. Closed SDF infrastructure ready: **True**. Closed SDF infrastructure present; shape [32, 24, 25]; dtypes float32 / int32; manifold-ready estimate True.

## Render Note

Side-by-side images are Python fallback orthographic renders from mesh JSON, not Godot captures.
