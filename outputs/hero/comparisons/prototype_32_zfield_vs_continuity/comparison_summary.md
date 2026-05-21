# SpriteSpatial Profile Comparison

Verdict: **better_with_caveats**

## Metrics

- Baseline faces: 1798
- Candidate faces: 2208
- Baseline voxels: 727
- Candidate voxels: 1094
- Candidate primitives: {'shell': 1, 'ellipsoid': 1, 'rounded_cuboid': 1, 'tapered_prism': 4}
- Candidate semantic warnings: {'disconnected_body_parts': 5, 'tiny_orphan_regions': 2, 'ambiguous_assignment': 1, 'outline_regions_merged_into_body': 0, 'left_right_confusion': 0, 'torso_head_overlap': 1, 'equipment_merged_into_body': 0, 'depth_discontinuities': 0}

## Questions

1. Side profile improved: **True**. Continuity score is 1.0; occupied voxels changed from 727 to 1094; depth span 0.600 vs baseline 0.550.
2. Head/torso/limb volume coherent: **True**. Primitive mix is {'shell': 1, 'ellipsoid': 1, 'rounded_cuboid': 1, 'tapered_prism': 4}; head/torso/limbs are no longer all cuboid/flat.
3. Outline shell controlled: **True**. Outline shell voxels 146; outline source pixels 146.
4. Face/voxel budget ok: **True**. Candidate faces 2208; baseline faces 1798; profile budget treated as 4000.
5. Front readability preserved: **True**. Baseline alpha coverage 0.3529; Candidate front projection 0.3529.
6. Worsened semantic parts: ['semantic labels remain disconnected in source decomposition', 'torso/head semantic overlap remains']

## Render Note

Side-by-side images are Python fallback orthographic renders from mesh JSON, not Godot captures.
