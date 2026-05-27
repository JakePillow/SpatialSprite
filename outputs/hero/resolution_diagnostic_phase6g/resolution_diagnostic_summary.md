# SpriteSpatial Phase 6G Resolution Diagnostic

Resolution helped: `true`
Best scale: `2.0`
Recommended next step: `increase_resolution_path`

Higher SDF resolution improved at least one target topology metric while preserving hard gates. Caveat: non-manifold edge count increased by 45, so the production path needs topology cleanup.

## Scale Metrics

| scale | passed | sdf shape | macro patches | small macro ratio | planar macro patches | staircase | surface flow | non-manifold | hat asymmetry |
|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | True | [32, 24, 25] | 273 | 0.5604 | 2 | 0.5052 | 0.4656 | 11 | 3.0449 |
| 1.5 | True | [48, 36, 37] | 468 | 0.5769 | 8 | 0.5125 | 0.4715 | 24 | 2.7851 |
| 2.0 | True | [64, 48, 49] | 695 | 0.5842 | 20 | 0.4972 | 0.5029 | 56 | 4.2751 |

## Notes

- Semantics, morphology, rendering profile, patch profile, and macro-patch profile are held constant.
- Only SDF X/Y sampling scale and Z sampling scale change.
- Godot preview is not run by this diagnostic.
