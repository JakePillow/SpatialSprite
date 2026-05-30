# Phase 7D Comparison Summary

## Verdict

Phase 7D passed. Constraint arbitration runs deterministically, default parameters preserve the Phase 7C result, and edited JSON changes reconstruction without breaking topology.

## Key Metrics

- Side IoU baseline/default/edited: 0.5785997357992074 / 0.5785997357992074 / 0.5751633986928104
- Hat asymmetry default -> edited: 2.8036581307124817 -> 3.5040642730619114
- Directional readability default -> edited: 0.2620183005928993 -> 0.3024684086441994
- Non-manifold after cleanup default -> edited: 6 -> 7
- Degenerate faces edited: 0
- Mesh connected components edited: 1

## Arbitration

- Conflict zones: 115
- Topology-risk zones: 194
- Weighted blend regions: 23
- Rejected constraints after voxel-level side arbitration: 152

## Caveat

The edited fixture requested equipment/shield/sword edits, but that canonical part is not present in the fixture graph, so it is reported as skipped rather than silently faked.
