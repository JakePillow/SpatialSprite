# SpriteSpatial Profile Comparison

Verdict: **better**

## Metrics

- Baseline faces: 1518
- Candidate faces: 1518
- Baseline voxels: 1751
- Candidate voxels: 1751
- Candidate primitives: {'shell': 1, 'ellipsoid': 2, 'rounded_cuboid': 3, 'tapered_prism': 4}
- Candidate semantic warnings: {'disconnected_body_parts': 5, 'tiny_orphan_regions': 2, 'ambiguous_assignment': 1, 'outline_regions_merged_into_body': 0, 'left_right_confusion': 0, 'torso_head_overlap': 1, 'equipment_merged_into_body': 0, 'depth_discontinuities': 0}
- Candidate override metrics: {'mode': 'supplement', 'override_pixels_applied': 271, 'override_overlap_count': 145, 'unlabelled_opaque_pixel_ratio': 0.0, 'critical_label_coverage': {'head': 20, 'torso': 79, 'left_leg': 30, 'right_leg': 22}, 'torso_head_overlap_count_after_override': 0, 'disconnected_critical_labels_after_override': 0}
- Candidate smoothing: {'enabled': True, 'mode': 'hybrid_lowpoly', 'silhouette_drift_px': 0.0, 'outline_preservation_score': 1.0, 'semantic_boundary_violation_count': 0, 'face_count_before_smoothing': 3036, 'face_count_after_smoothing': 3036, 'degenerate_faces_removed': 0, 'smoothing_passed': True}

## Questions

1. Side profile improved: **True**. Continuity score is 1.0; occupied voxels changed from 1751 to 1751; depth span 0.554 vs baseline 0.600.
2. Head/torso/limb volume coherent: **True**. Primitive mix is {'shell': 1, 'ellipsoid': 2, 'rounded_cuboid': 3, 'tapered_prism': 4}; head/torso/limbs are no longer all cuboid/flat.
3. Outline shell controlled: **True**. Outline shell voxels 50; outline source pixels 50.
4. Face/voxel budget ok: **True**. Candidate faces 1518; baseline faces 1518; profile budget treated as 4000.
5. Front readability preserved: **True**. Baseline alpha coverage 0.3529; Candidate front projection 0.3529.
6. Worsened semantic parts: none detected by validation, though source semantic warnings remain.
7. Smoothing passed: **True**. Mode hybrid_lowpoly; drift 0.00px; outline preservation 1.000; semantic boundary violations 0; faces 3036 -> 3036.

## Render Note

Side-by-side images are Python fallback orthographic renders from mesh JSON, not Godot captures.
