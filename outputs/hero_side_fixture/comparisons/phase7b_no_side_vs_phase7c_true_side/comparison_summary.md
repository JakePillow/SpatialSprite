# Phase 7B vs Phase 7C Side Authority Comparison

Verdict: **side_authority_path_proven**

Phase 7B correctly rejected placeholder side sprites. Phase 7C uses a synthetic `authored_side_fixture` and activates side geometry authority.

| Metric | Phase 7B | Phase 7C | Delta |
|---|---:|---:|---:|
| `passed` | True | True |  |
| `front_back_side_backend_enabled` | True | True |  |
| `side_geometry_authority` | placeholder | authored_side_fixture |  |
| `side_semantic_authority` | missing | semantic_masks |  |
| `side_authority_used` | False | True |  |
| `side_projection_iou` | 0.0 | 0.5785997357992074 | 0.5785997357992074 |
| `side_constraint_conflict_count` | 0 | 319 | 319 |
| `front_projection_iou` | 0.9727767695099818 | 0.9727767695099818 | 0.0 |
| `back_projection_iou` | 0.8939393939393939 | 0.9053030303030303 | 0.011363636363636354 |
| `mesh_connected_components` | 1 | 1 | 0 |
| `degenerate_face_count` | 0 | 0 | 0 |
| `non_manifold_after_cleanup` | 5 | 6 | 1 |
| `semantic_label_preservation_passed` | True | True |  |
| `hat_asymmetry_ratio` | 2.8036581307124817 | 2.8036581307124817 | 0.0 |
| `surface_net_vertices` | 4166 | 4326 | 160 |
| `surface_net_faces` | 4154 | 4324 | 170 |

## Notes

- The Phase 7C side sprite is a fixture, not production art.
- `side_projection_iou` becomes nonzero because side authority is actually used.
- Mesh connectivity and zero degenerate faces are preserved.
