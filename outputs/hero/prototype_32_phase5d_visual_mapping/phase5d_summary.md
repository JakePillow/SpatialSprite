# Phase 5D Visual Diagnostics

Phase 5D measures rotational silhouette quality. It does not correct geometry.

## Canonical View Metrics
- front_iou: 0.450034548281223
- oblique_iou: 0.22666951516827105
- side_iou: 0.2500192746136817
- side_135_iou: 0.22831376856949429
- back_iou: 0.4427893584828052
- worst_view: oblique

## View Authority
- side_profile_authority: primitive_prior
- back_view_authority: authored
- source_coverage_fidelity_limit: side_inferred

## Similarity Warnings
- front_back_visual_similarity_warning: True
- side_front_visual_similarity_warning: True
- front_back_aligned_iou: 0.9113952957296186
- side_front_aligned_iou: 0.7542158941734828

Interpretation: high front/back or side/front aligned IoU indicates a likely front-derived view and should be corrected in Phase 6 only after an authored or canonical target is chosen.
