from __future__ import annotations

import numpy as np

from spritespatial.depthfields.schema import DepthDiagnostics, DepthProfile, RegionDepthDiagnostics
from spritespatial.depthfields.validation import isolated_spike_count


def build_diagnostics(
    depth: np.ndarray,
    alpha_mask: np.ndarray,
    silhouette: np.ndarray,
    region_masks: dict[str, np.ndarray],
    profiles: dict[str, DepthProfile],
    labels: np.ndarray,
    join_discontinuity_max: float,
    spike_sigma: float,
) -> DepthDiagnostics:
    regions: list[RegionDepthDiagnostics] = []
    assigned = np.zeros(alpha_mask.shape, dtype=bool)
    for region_id, mask in region_masks.items():
        profile = profiles[region_id]
        selected = np.asarray(mask, dtype=bool)
        assigned |= selected
        values = depth[selected]
        boundary_gaps: list[float] = []
        for y, x in np.argwhere(selected):
            for ny, nx in ((y, x + 1), (y + 1, x)):
                if (
                    ny < labels.shape[0] and nx < labels.shape[1]
                    and labels[ny, nx] and labels[ny, nx] != labels[y, x]
                ):
                    boundary_gaps.append(abs(float(depth[y, x]) - float(depth[ny, nx])))
        mean_gap = float(np.mean(boundary_gaps)) if boundary_gaps else 0.0
        mean = float(values.mean()) if values.size else 0.0
        residual = float(values.std()) / max(mean, 1e-6) if values.size and mean > 0 else 0.0
        warnings: list[str] = []
        if not profile.explicit:
            warnings.append("profile_fallback")
        if residual > 0.75:
            warnings.append("high_primitive_residual_estimate")
        regions.append(
            RegionDepthDiagnostics(
                region_id=region_id,
                semantic_class=profile.semantic_class,
                profile_name=profile.profile,
                max_depth=profile.max_depth_factor,
                actual_depth_min=float(values.min()) if values.size else 0.0,
                actual_depth_max=float(values.max()) if values.size else 0.0,
                actual_depth_mean=mean,
                silhouette_pin_passed=bool(np.all(np.abs(depth[selected & silhouette]) <= 1e-6)),
                spike_count=isolated_spike_count(depth, selected, spike_sigma),
                continuity_score=max(0.0, 1.0 - mean_gap / max(profile.max_depth_factor, 1e-6)),
                primitive_residual_estimate=residual,
                explicit_profile=profile.explicit,
                warnings=tuple(warnings),
            )
        )
    return DepthDiagnostics(
        regions=tuple(regions),
        silhouette_pin_passed=bool(np.all(np.abs(depth[silhouette]) <= 1e-6)),
        isolated_spike_count=isolated_spike_count(depth, alpha_mask, spike_sigma),
        join_discontinuity_max=join_discontinuity_max,
        assigned_pixel_count=int((assigned & alpha_mask).sum()),
        opaque_pixel_count=int(np.asarray(alpha_mask, dtype=bool).sum()),
    )
