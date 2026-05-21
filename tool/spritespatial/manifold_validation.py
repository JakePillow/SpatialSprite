from __future__ import annotations

from typing import Any

import numpy as np

from spritespatial.sdf_volume import labels_present_in_parts


def build_phase5a_validation(
    mylar: dict[str, Any],
    back: dict[str, Any],
    seam: dict[str, Any],
    sdf: dict[str, Any],
    meshing: dict[str, Any],
    parts: list[dict[str, Any]],
    back_mode: str,
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_coverage = source_coverage or {}
    mylar_report = mylar["report"]
    back_report = back["report"]
    seam_report = seam["report"]
    sdf_summary = sdf["summary"]
    semantic_depth_enabled = bool(sdf_summary.get("semantic_depth_profiles_enabled", False))
    directional_enabled = bool(sdf_summary.get("directional_morphology_enabled", False))
    surface_flow_enabled = bool(sdf_summary.get("surface_flow_enabled", False))
    mesh_report = meshing["report"]
    required_labels = labels_present_in_parts(parts)
    present_labels = list(sdf_summary.get("semantic_volume_labels", []))
    missing_labels = [label for label in required_labels if label not in present_labels]
    z_front = mylar["z_front"]
    z_back = back["z_back"]
    fail_conditions = {
        "silhouette_pin_fails": not mylar_report.get("silhouette_pin_confirmed", False),
        "front_back_seam_mismatch_exceeds_tolerance": seam_report.get("seam_discontinuity_max", 1.0) > 1e-6,
        "sdf_volume_empty": int(sdf_summary.get("occupied_voxels", 0)) <= 0,
        "critical_semantic_labels_disappear": bool(missing_labels),
        "hollow_gap_ratio_exceeds_threshold": float(sdf_summary.get("hollow_gap_ratio", 1.0)) > 0.20,
        "closed_volume_disconnected": not sdf_summary.get("closed_volume_connected", False),
        "z_front_contains_negative_values": bool(np.any(z_front < 0.0)),
        "z_back_contains_positive_values": bool(np.any(z_back > 0.0)),
        "semantic_volume_loses_labels_present_in_phase_1_4": bool(missing_labels),
        "surface_nets_input_not_loadable": not mesh_report.get("surface_nets_input_loadable", False),
        "inner_holes_detected_not_seamed": seam_report.get("inner_holes_detected", 0) != seam_report.get("inner_holes_seamed", 0),
        "mylar_isolated_spikes": mylar_report.get("isolated_spike_count", 0) > 0,
        "outline_full_depth_slab": mylar_report.get("outline_full_depth_slab", False),
        "missing_critical_back_regions": bool(back_report.get("missing_critical_back_regions", [])),
        "source_coverage_policy_failed": any(source_coverage.get("fail_conditions", {}).values()),
        "semantic_depth_uniform_slab": semantic_depth_enabled and float(sdf_summary.get("uniform_slab_ratio", 1.0)) > 0.70,
        "semantic_depth_variance_missing": semantic_depth_enabled and float(sdf_summary.get("semantic_depth_variance", 0.0)) <= 0.0,
        "semantic_outline_shell_too_thick": semantic_depth_enabled and float(sdf_summary.get("outline_shell_ratio", 0.0)) > 1.0,
        "semantic_side_profile_unreadable": semantic_depth_enabled and float(sdf_summary.get("side_profile_readability_score", 0.0)) < 0.20,
        "directional_morphology_missing": directional_enabled and int(sdf_summary.get("directional_semantic_count", 0)) <= 0,
        "directional_morphology_unreadable": directional_enabled
        and float(sdf_summary.get("directional_readability_score", 0.0)) < 0.10,
        "surface_flow_missing_transitions": surface_flow_enabled and int(sdf_summary.get("semantic_transition_count", 0)) <= 0,
        "surface_flow_continuity_low": surface_flow_enabled and float(sdf_summary.get("surface_continuity_score", 0.0)) < 0.12,
        "surface_flow_anatomical_flow_low": surface_flow_enabled and float(sdf_summary.get("anatomical_flow_score", 0.0)) < 0.20,
        "surface_flow_fragmentation_high": surface_flow_enabled
        and float(sdf_summary.get("surface_fragmentation_score", 1.0)) > 0.85,
    }
    return {
        "mylar_depth_enabled": True,
        "closed_body_enabled": True,
        "back_mode": back_mode,
        "front_max_depth": float(z_front.max()) if z_front.size else 0.0,
        "back_max_depth": float(abs(z_back.min())) if z_back.size else 0.0,
        "silhouette_pin_confirmed": mylar_report.get("silhouette_pin_confirmed", False),
        "seam_ring_count": seam_report.get("seam_ring_count", 0),
        "seam_discontinuity_max": seam_report.get("seam_discontinuity_max", 0.0),
        "inner_holes_detected": seam_report.get("inner_holes_detected", 0),
        "inner_holes_seamed": seam_report.get("inner_holes_seamed", 0),
        "sdf_volume_shape": sdf_summary.get("shape", []),
        "sdf_sign_consistency": sdf_summary.get("sdf_sign_consistency", False),
        "sdf_dtype": sdf_summary.get("sdf_dtype", ""),
        "semantic_dtype": sdf_summary.get("semantic_dtype", ""),
        "closed_volume_connected": sdf_summary.get("closed_volume_connected", False),
        "hollow_gap_ratio": sdf_summary.get("hollow_gap_ratio", 1.0),
        "semantic_volume_labels": present_labels,
        "required_semantic_volume_labels": required_labels,
        "missing_semantic_volume_labels": missing_labels,
        "surface_nets_input_loadable": mesh_report.get("surface_nets_input_loadable", False),
        "surface_nets_input_shape_valid": mesh_report.get("surface_nets_input_shape_valid", False),
        "surface_nets_ready": mesh_report.get("surface_nets_input_loadable", False)
        and mesh_report.get("surface_nets_input_shape_valid", False),
        "manifold_ready_estimate": sdf_summary.get("closed_volume_connected", False)
        and sdf_summary.get("sdf_sign_consistency", False),
        "front_back_sprite_deferred": back_report.get("front_back_sprite_deferred", False),
        "source_coverage": source_coverage,
        "build_warnings": list(source_coverage.get("warnings", [])),
        "semantic_depth_profiles_enabled": semantic_depth_enabled,
        "semantic_depth_profile": sdf_summary.get("semantic_depth_profile", ""),
        "uniform_slab_ratio": sdf_summary.get("uniform_slab_ratio", 0.0),
        "semantic_depth_variance": sdf_summary.get("semantic_depth_variance", 0.0),
        "head_depth_ratio": sdf_summary.get("head_depth_ratio", 0.0),
        "torso_depth_ratio": sdf_summary.get("torso_depth_ratio", 0.0),
        "limb_depth_ratio": sdf_summary.get("limb_depth_ratio", 0.0),
        "outline_shell_ratio": sdf_summary.get("outline_shell_ratio", 0.0),
        "side_projection_entropy": sdf_summary.get("side_projection_entropy", 0.0),
        "side_profile_readability_score": sdf_summary.get("side_profile_readability_score", 0.0),
        "directional_morphology_enabled": directional_enabled,
        "morphology_profile": sdf_summary.get("morphology_profile", ""),
        "directional_semantic_count": sdf_summary.get("directional_semantic_count", 0),
        "anisotropic_region_ratio": sdf_summary.get("anisotropic_region_ratio", 0.0),
        "rearward_extension_score": sdf_summary.get("rearward_extension_score", 0.0),
        "front_compression_score": sdf_summary.get("front_compression_score", 0.0),
        "directional_readability_score": sdf_summary.get("directional_readability_score", 0.0),
        "symmetric_volume_penalty": sdf_summary.get("symmetric_volume_penalty", 0.0),
        "surface_flow_enabled": surface_flow_enabled,
        "semantic_transition_count": sdf_summary.get("semantic_transition_count", 0),
        "surface_continuity_score": sdf_summary.get("surface_continuity_score", 0.0),
        "semantic_seam_score": sdf_summary.get("semantic_seam_score", 0.0),
        "oblique_surface_readability": sdf_summary.get("oblique_surface_readability", 0.0),
        "surface_fragmentation_score": sdf_summary.get("surface_fragmentation_score", 0.0),
        "staircase_artifact_score": sdf_summary.get("staircase_artifact_score", 0.0),
        "anatomical_flow_score": sdf_summary.get("anatomical_flow_score", 0.0),
        "fail_conditions": fail_conditions,
        "passed": not any(fail_conditions.values()),
    }
