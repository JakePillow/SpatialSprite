from __future__ import annotations

import numpy as np

from spritespatial.depthfields.schema import BlendJunction, DepthConfig, DepthProfile
from spritespatial.validation import ValidationReport, ValidationSeverity

HARD_PROFILES = {"linear", "plateau", "hard", "wedge"}


def isolated_spike_count(depth: np.ndarray, mask: np.ndarray, sigma: float = 3.0) -> int:
    values = np.asarray(depth, dtype=np.float32)
    selected = np.asarray(mask, dtype=bool) & (values > 0.0)
    spikes = 0
    for y, x in np.argwhere(selected):
        y0, y1 = max(0, y - 1), min(values.shape[0], y + 2)
        x0, x1 = max(0, x - 1), min(values.shape[1], x + 2)
        local = values[y0:y1, x0:x1][selected[y0:y1, x0:x1]]
        if local.size <= 2:
            continue
        mean, std = float(local.mean()), float(local.std())
        if std > 1e-6 and float(values[y, x]) > mean + sigma * std:
            spikes += 1
    return spikes


def validate_depth_field(
    depth: np.ndarray,
    alpha_mask: np.ndarray,
    silhouette: np.ndarray,
    profiles: dict[str, DepthProfile],
    region_masks: dict[str, np.ndarray],
    junctions: list[BlendJunction],
    config: DepthConfig,
) -> ValidationReport:
    report = ValidationReport(stage="depth_synthesis")
    values = np.asarray(depth, dtype=np.float32)
    alpha = np.asarray(alpha_mask, dtype=bool)
    if not alpha.any():
        report.add(ValidationSeverity.FATAL, "empty_alpha_mask", "The sprite alpha mask is empty.")
        return report
    if not np.isfinite(values).all():
        report.add(ValidationSeverity.FATAL, "non_finite_depth", "The depth field contains NaN or infinite values.")
    if float(values.min()) < -1e-6:
        report.add(ValidationSeverity.ERROR, "negative_depth", "Depth must be non-negative.", context={"minimum": float(values.min())})
    if float(values.max()) > config.max_total_depth + 1e-6:
        report.add(ValidationSeverity.ERROR, "depth_above_limit", "Depth exceeds the configured maximum.", context={"maximum": float(values.max()), "limit": config.max_total_depth})
    if bool(np.any(values[~alpha] != 0.0)):
        report.add(ValidationSeverity.ERROR, "depth_outside_alpha", "Transparent pixels contain depth.")
    if bool(np.any(np.abs(values[silhouette]) > 1e-6)):
        report.add(ValidationSeverity.ERROR, "silhouette_unpinned", "Outer silhouette pixels must be pinned to zero.")

    spikes = isolated_spike_count(values, alpha, config.spike_sigma)
    if spikes:
        report.add(ValidationSeverity.WARNING, "isolated_depth_spikes", f"Detected {spikes} isolated depth spikes.", context={"count": spikes})

    for region_id, profile in profiles.items():
        if not profile.explicit:
            report.add(ValidationSeverity.ERROR, "implicit_profile_fallback", f"Region {region_id} has no explicit semantic profile assignment.", region_id=region_id)
        mask = region_masks[region_id]
        actual_max = float(values[mask].max()) if mask.any() else 0.0
        if profile.layer == "detail" and actual_max > config.detail_depth_threshold + 1e-6:
            report.add(ValidationSeverity.ERROR, "detail_depth_above_cap", f"Detail region {region_id} became major geometry.", region_id=region_id, context={"maximum": actual_max, "limit": config.detail_depth_threshold})
        if profile.primitive_hint in {"plate", "blade", "hard_prop"} and profile.profile not in HARD_PROFILES:
            report.add(ValidationSeverity.ERROR, "soft_hard_prop_profile", f"Hard prop {region_id} uses soft profile {profile.profile}.", region_id=region_id)

    for junction in junctions:
        if junction.max_discontinuity_after > config.join_discontinuity_threshold:
            report.add(
                ValidationSeverity.WARNING,
                "join_discontinuity",
                f"Depth discontinuity remains between {junction.class_a} and {junction.class_b}.",
                context={"maximum": junction.max_discontinuity_after, "limit": config.join_discontinuity_threshold},
            )
    if not report.issues:
        report.add(ValidationSeverity.INFO, "depth_field_valid", "Depth field passed all acceptance criteria.")
    return report
