# Embodiment Parameter Diff Summary

## Verdict

- edit_valid: True
- edit_changed_geometry: True
- likely_improvement: True

## What Was Edited

- hair/hat: back_authority_weight, back_bias, enabled, front_bias, notes, side_authority_weight, side_width_scale, taper_strength, thickness_scale, topology_preservation_weight, z_center_offset

## What Was Applied

- hair/hat

## What Was Skipped

- Nothing was skipped.

## Geometry And Validation

- Hat asymmetry: 2.8036581307124817 -> 3.506145075401276 (delta 0.7024869446887942)
- Directional readability: 0.2620183005928993 -> 0.30265904366970064 (delta 0.04064074307680132)
- Side projection IoU: 0.5785997357992074 -> 0.5812417437252312 (delta 0.0026420079260237594)
- Non-manifold edges after cleanup: 6 -> 6 (delta 0)
- Planar macro patches: 5 -> 5 (delta 0)
- Rejected constraints: 152 -> 152 (delta 0)

## Recommendation

Keep this edit family and try a small follow-up pass on the same part; adjust one field at a time so the next diff remains explainable.
