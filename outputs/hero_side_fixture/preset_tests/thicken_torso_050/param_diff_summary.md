# Embodiment Parameter Diff Summary

## Verdict

- edit_valid: True
- edit_changed_geometry: True
- likely_improvement: True

## What Was Edited

- torso: enabled, notes, side_authority_weight, thickness_scale, topology_preservation_weight

## What Was Applied

- torso

## What Was Skipped

- Nothing was skipped.

## Geometry And Validation

- Hat asymmetry: 2.8036581307124817 -> 2.8036581307124817 (delta 0.0)
- Directional readability: 0.2620183005928993 -> 0.2620183005928993 (delta 0.0)
- Side projection IoU: 0.5785997357992074 -> 0.5710560625814863 (delta -0.007543673217721092)
- Non-manifold edges after cleanup: 6 -> 7 (delta 1)
- Planar macro patches: 5 -> 5 (delta 0)
- Rejected constraints: 152 -> 152 (delta 0)

## Recommendation

Keep this edit family and try a small follow-up pass on the same part; adjust one field at a time so the next diff remains explainable.
