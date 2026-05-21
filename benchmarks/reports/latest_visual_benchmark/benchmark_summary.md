# SpriteSpatial Visual Benchmark

Generated: 2026-05-21T21:26:46.744501+00:00
Passed: False
Reference phase: phase6b_surface_flow
Reference status: {'reference_path': 'C:\\dev\\SpatialSprite\\benchmarks\\reference_visual_benchmark.json', 'reference_phase': 'phase6b_surface_flow', 'established': True, 'updated': False, 'regression_checks_run': False, 'reason': 'previous reference did not contain a passing reference phase'}

## Phase Metrics

### hero::baseline_smoothed
- front_iou: 0.0
- side_iou: None
- back_iou: None
- worst_view_iou: 0.0
- semantic_match_ratio: None
- source_colour_match_score: 0.7826129523321708
- voxel_face_readability_score: 0.8745072111313699
- side_profile_readability_score: 0.0
- directional_readability_score: 0.0
- oblique_surface_readability: 0.0
- staircase_artifact_score: 0.0
- surface_fragmentation_score: 0.0
- internal_black_face_ratio: 0.015799256505576207
- non_manifold_edge_count: 5
- degenerate_face_count: 0

### hero::phase5e_semantic_depth
- front_iou: 0.4787985865724382
- side_iou: 0.4613259668508287
- back_iou: 0.46397188049209137
- worst_view_iou: 0.4613259668508287
- semantic_match_ratio: 0.2394259928947228
- source_colour_match_score: 0.7757156863597992
- voxel_face_readability_score: 0.8758938662393962
- side_profile_readability_score: 0.9406017943796912
- directional_readability_score: 0.0
- oblique_surface_readability: 0.0
- staircase_artifact_score: 0.0
- surface_fragmentation_score: 0.0
- internal_black_face_ratio: 0.01845018450184502
- non_manifold_edge_count: 4
- degenerate_face_count: 0

### hero::phase5g_directional_morphology
- front_iou: 0.4787985865724382
- side_iou: 0.4613259668508287
- back_iou: 0.46397188049209137
- worst_view_iou: 0.4613259668508287
- semantic_match_ratio: 0.2394259928947228
- source_colour_match_score: 0.7760426436133646
- voxel_face_readability_score: 0.8754571952910519
- side_profile_readability_score: 0.9406017943796912
- directional_readability_score: 0.16817652583122253
- oblique_surface_readability: 0.0
- staircase_artifact_score: 0.0
- surface_fragmentation_score: 0.0
- internal_black_face_ratio: 0.018427518427518427
- non_manifold_edge_count: 4
- degenerate_face_count: 0

### hero::phase6b_surface_flow
- front_iou: 0.4614065180102916
- side_iou: 0.4712328767123288
- back_iou: 0.46397188049209137
- worst_view_iou: 0.4614065180102916
- semantic_match_ratio: 0.23280213337746475
- source_colour_match_score: 0.773665961990151
- voxel_face_readability_score: 0.8745471245693484
- side_profile_readability_score: 0.9406017943796912
- directional_readability_score: 0.16817652583122253
- oblique_surface_readability: 0.8290383152797385
- staircase_artifact_score: 0.07310621242484969
- surface_fragmentation_score: 0.0
- internal_black_face_ratio: 0.01948051948051948
- non_manifold_edge_count: 5
- degenerate_face_count: 0

## Failures

- {'phase': 'hero::baseline_smoothed', 'gate': 'validation_report_passed', 'value': False}
