# Embodiment Parameter Diff Summary

## Verdict

- edit_valid: True
- edit_changed_geometry: True
- likely_improvement: True

## What Was Edited

- equipment/shield/sword: back_authority_weight, enabled, front_authority_weight, notes, side_authority_weight, side_width_scale, thickness_scale, topology_preservation_weight, z_center_offset
- hair/hat: back_authority_weight, back_bias, enabled, front_bias, notes, side_authority_weight, side_width_scale, taper_strength, thickness_scale, topology_preservation_weight, z_center_offset
- torso: enabled, notes, side_authority_weight, thickness_scale, topology_preservation_weight

## What Was Applied

- hair/hat
- torso

## What Was Skipped

- equipment/shield/sword: part_not_present

## Geometry And Validation

- Hat asymmetry: 2.8036581307124817 -> 3.5040642730619114 (delta 0.7004061423494297)
- Directional readability: 0.2620183005928993 -> 0.3024684086441994 (delta 0.04045010805130006)
- Side projection IoU: 0.5785997357992074 -> 0.5751633986928104 (delta -0.003436337106397014)
- Non-manifold edges after cleanup: 6 -> 7 (delta 1)
- Planar macro patches: 5 -> 6 (delta 1)
- Rejected constraints: 152 -> 152 (delta 0)

## Recommendation

Resolve skipped semantic parts before tuning them further; equipment/shield/sword needs a real canonical part before side-offset edits can affect geometry.
