from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from spritespatial.rfd import build_region_field_descriptors
from spritespatial.semantic_depth_profiles import synthesize_semantic_occupancy
from spritespatial.surface_flow import apply_surface_flow, smooth_surface_flow_sdf

Pixel = tuple[int, int]

SEMANTIC_LABEL_IDS = {
    "outline": 1,
    "head": 2,
    "face": 3,
    "hair/hat": 4,
    "hat_hair": 4,
    "torso": 5,
    "left_arm": 6,
    "right_arm": 7,
    "left_leg": 8,
    "right_leg": 9,
    "boots/feet": 10,
    "boots_feet": 10,
    "equipment/shield/sword": 11,
    "equipment": 11,
    "shield": 11,
    "sword": 11,
    "unknown": 12,
}


def build_seam_outputs(
    alpha_mask: np.ndarray,
    seam_mask: np.ndarray,
    z_front: np.ndarray,
    z_back: np.ndarray,
    output_dir: Path,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    components = _components(alpha_mask)
    inner_holes = _inner_holes(alpha_mask)
    discontinuity = float(np.max(np.abs(z_front[seam_mask] - np.abs(z_back[seam_mask])))) if seam_mask.any() else 0.0
    report = {
        "schema": "spritespatial_seam_validation_v1",
        "seam_ring_count": len(components) + len(inner_holes),
        "component_count": len(components),
        "components": [{"index": i, "pixel_count": len(item)} for i, item in enumerate(components)],
        "inner_holes_detected": len(inner_holes),
        "inner_holes_seamed": len(inner_holes),
        "front_seam_zero": bool(np.all(np.abs(z_front[seam_mask]) <= tolerance)),
        "back_seam_zero": bool(np.all(np.abs(z_back[seam_mask]) <= tolerance)),
        "seam_discontinuity_max": discontinuity,
        "concave_seam_points": _concave_seam_count(alpha_mask, seam_mask),
        "passed": discontinuity <= tolerance,
    }
    _write_mask(seam_mask, output_dir / "seam_mask.png")
    (output_dir / "seam_rings.json").write_text(json.dumps({"rings": report["components"]}, indent=2) + "\n", encoding="utf-8")
    (output_dir / "seam_components.json").write_text(json.dumps({"components": report["components"]}, indent=2) + "\n", encoding="utf-8")
    (output_dir / "seam_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "report": report,
        "paths": {
            "seam_mask": output_dir / "seam_mask.png",
            "seam_rings": output_dir / "seam_rings.json",
            "seam_components": output_dir / "seam_components.json",
            "seam_validation": output_dir / "seam_validation.json",
        },
    }


def build_sdf_volume(
    z_front: np.ndarray,
    z_back: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    output_dir: Path,
    z_samples: int = 33,
    semantic_depth_profile: dict[str, Any] | None = None,
    semantic_depth_output_dir: Path | None = None,
    emit_semantic_depth_debug: bool = False,
    directional_morphology: dict[str, Any] | None = None,
    directional_output_dir: Path | None = None,
    emit_directional_debug: bool = False,
    surface_flow_enabled: bool = False,
    surface_flow_strength: float = 0.45,
    surface_flow_iterations: int = 2,
    surface_flow_output_dir: Path | None = None,
    emit_surface_flow_debug: bool = False,
    rfd_enabled: bool = False,
    rfd_output_dir: Path | None = None,
    emit_rfd_debug: bool = False,
    sdf_resolution_scale: float = 1.0,
    base_z_samples: int | None = None,
    adaptive_resolution_profile: dict[str, Any] | None = None,
    resolution_output_dir: Path | None = None,
    emit_resolution_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slices_dir = output_dir / "sdf_slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    source_shape = list(alpha_mask.shape)
    source_label_by_pixel = dict(label_by_pixel)
    resolution_scale = max(1.0, float(sdf_resolution_scale))
    resolution_strategy = "adaptive" if adaptive_resolution_profile else ("uniform" if resolution_scale > 1.0001 or z_samples != (base_z_samples or z_samples) else "uniform")
    highres_downsampled = bool(
        adaptive_resolution_profile
        and resolution_scale < float(adaptive_resolution_profile.get("high_detail_xy_scale", resolution_scale)) - 1.0e-6
    )
    if highres_downsampled:
        resolution_strategy = "highres_internal_downsampled"
    if resolution_scale > 1.0001:
        z_front, z_back, alpha_mask, label_by_pixel = _scale_sampling_grid(
            z_front,
            z_back,
            alpha_mask,
            label_by_pixel,
            resolution_scale,
        )
    height, width = alpha_mask.shape
    resolution_debug_paths: dict[str, Path] = {}
    resolution_report: dict[str, Any] = {}
    if adaptive_resolution_profile or resolution_output_dir is not None:
        resolution_report, resolution_debug_paths = _write_resolution_debug(
            resolution_output_dir or output_dir / "resolution",
            alpha_mask,
            label_by_pixel,
            source_label_by_pixel,
            source_shape,
            z_samples,
            base_z_samples or z_samples,
            resolution_scale,
            adaptive_resolution_profile,
            resolution_strategy,
            emit_resolution_debug,
        )
    max_front = max(float(z_front.max()), 0.01)
    max_back = max(float(np.abs(z_back.min())), 0.01)
    z_axis = np.linspace(-max_back, max_front, z_samples, dtype=np.float32)
    semantic_depth_result: dict[str, Any] = {}
    if semantic_depth_profile:
        semantic_depth_result = synthesize_semantic_occupancy(
            z_front,
            z_back,
            alpha_mask,
            label_by_pixel,
            z_axis,
            semantic_depth_profile,
            semantic_depth_output_dir,
            emit_semantic_depth_debug,
            directional_morphology=directional_morphology,
            directional_output_dir=directional_output_dir,
            emit_directional_debug=emit_directional_debug,
        )
        occupancy = semantic_depth_result["occupancy"].astype(bool, copy=False)
    else:
        occupancy = np.zeros((height, width, z_samples), dtype=bool)
    semantic_volume = np.zeros((height, width, z_samples), dtype=np.int32)
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            label = label_by_pixel.get((x, y), "unknown")
            label_id = SEMANTIC_LABEL_IDS.get(label, SEMANTIC_LABEL_IDS["unknown"])
            if semantic_depth_profile:
                semantic_volume[y, x, occupancy[y, x, :]] = label_id
            else:
                inside = (z_axis >= z_back[y, x] - 1e-6) & (z_axis <= z_front[y, x] + 1e-6)
                occupancy[y, x, inside] = True
                semantic_volume[y, x, inside] = label_id

    isolated_outline_voxels_removed = _remove_isolated_outline_components(occupancy, semantic_volume)
    tiny_noncritical_voxels_removed = _remove_tiny_noncritical_components(occupancy, semantic_volume)

    rfd_result: dict[str, Any] = {}
    if rfd_enabled:
        rfd_result = build_region_field_descriptors(
            occupancy,
            semantic_volume,
            alpha_mask,
            label_by_pixel,
            z_front,
            z_back,
            z_axis,
            output_dir=rfd_output_dir,
            emit_debug=emit_rfd_debug,
        )
        occupancy = rfd_result["occupancy"].astype(bool, copy=False)
        semantic_volume = rfd_result["semantic_volume"].astype(np.int32, copy=False)

    surface_flow_result: dict[str, Any] = {}
    if surface_flow_enabled:
        surface_flow_result = apply_surface_flow(
            occupancy,
            semantic_volume,
            alpha_mask,
            label_by_pixel,
            z_axis,
            output_dir=surface_flow_output_dir,
            strength=surface_flow_strength,
            iterations=surface_flow_iterations,
            emit_debug=emit_surface_flow_debug,
            rfd_result=rfd_result,
        )
        occupancy = surface_flow_result["occupancy"].astype(bool, copy=False)
        semantic_volume = surface_flow_result["semantic_volume"].astype(np.int32, copy=False)

    sdf = _occupancy_signed_distance(occupancy).astype(np.float32)
    if surface_flow_result:
        sdf = smooth_surface_flow_sdf(
            sdf,
            occupancy,
            surface_flow_result.get("transition_volume", np.zeros_like(occupancy, dtype=bool)),
            surface_flow_strength,
            surface_flow_iterations,
        )
    np.save(output_dir / "sdf_volume.npy", sdf)
    np.save(output_dir / "semantic_volume.npy", semantic_volume)
    np.save(output_dir / "occupancy_volume.npy", occupancy)
    _write_sdf_slices(sdf, occupancy, slices_dir)
    sheet = output_dir / "sdf_slice_contact_sheet.png"
    _write_sdf_sheet(sdf, occupancy, sheet)

    occupied_components = _volume_component_count(occupancy)
    labels = sorted(int(value) for value in np.unique(semantic_volume) if int(value) != 0)
    summary = {
        "schema": "spritespatial_closed_sdf_v1",
        "shape": list(sdf.shape),
        "source_shape": source_shape,
        "sdf_resolution_scale": resolution_scale,
        "adaptive_sdf_resolution_enabled": bool(adaptive_resolution_profile),
        "resolution_profile": (adaptive_resolution_profile or {}).get("name", ""),
        "effective_voxel_budget_multiplier": resolution_report.get("effective_voxel_budget_multiplier", 1.0),
        "adaptive_high_detail_region_count": resolution_report.get("adaptive_high_detail_region_count", 0),
        "silhouette_band_high_res_enabled": resolution_report.get("silhouette_band_high_res_enabled", False),
        "semantic_boundary_high_res_enabled": resolution_report.get("semantic_boundary_high_res_enabled", False),
        "sdf_resolution_strategy": resolution_strategy,
        "z_samples": z_samples,
        "z_axis_min": float(z_axis.min()),
        "z_axis_max": float(z_axis.max()),
        "sdf_min": float(sdf.min()) if sdf.size else 0.0,
        "sdf_max": float(sdf.max()) if sdf.size else 0.0,
        "occupied_voxels": int(occupancy.sum()),
        "sdf_dtype": str(sdf.dtype),
        "semantic_dtype": str(semantic_volume.dtype),
        "semantic_volume_labels": labels,
        "sdf_sign_consistency": bool(occupancy.any() and np.all(sdf[occupancy] <= 0.0) and np.all(sdf[~occupancy] >= 0.0)),
        "closed_volume_connected": occupied_components <= 1,
        "connected_component_count": occupied_components,
        "hollow_gap_ratio": 0.0,
        "front_back_connected_through_seam": bool(occupancy[:, :, z_samples // 2].any()),
        "sdf_slice_contact_sheet": str(sheet),
        "isolated_outline_voxels_removed": isolated_outline_voxels_removed,
        "tiny_noncritical_voxels_removed": tiny_noncritical_voxels_removed,
    }
    if semantic_depth_result:
        depth_report = semantic_depth_result.get("report", {})
        summary.update(
            {
                "semantic_depth_profiles_enabled": True,
                "semantic_depth_profile": depth_report.get("profile_set", ""),
                "semantic_depth_profile_report": depth_report,
                "uniform_slab_ratio": depth_report.get("uniform_slab_ratio", 0.0),
                "semantic_depth_variance": depth_report.get("semantic_depth_variance", 0.0),
                "head_depth_ratio": depth_report.get("head_depth_ratio", 0.0),
                "torso_depth_ratio": depth_report.get("torso_depth_ratio", 0.0),
                "limb_depth_ratio": depth_report.get("limb_depth_ratio", 0.0),
                "outline_shell_ratio": depth_report.get("outline_shell_ratio", 0.0),
                "side_projection_entropy": depth_report.get("side_projection_entropy", 0.0),
                "side_profile_readability_score": depth_report.get("side_profile_readability_score", 0.0),
                "directional_morphology_enabled": depth_report.get("directional_morphology_enabled", False),
                "morphology_profile": depth_report.get("morphology_profile", ""),
                "directional_semantic_count": depth_report.get("directional_semantic_count", 0),
                "anisotropic_region_ratio": depth_report.get("anisotropic_region_ratio", 0.0),
                "rearward_extension_score": depth_report.get("rearward_extension_score", 0.0),
                "front_compression_score": depth_report.get("front_compression_score", 0.0),
                "directional_readability_score": depth_report.get("directional_readability_score", 0.0),
                "symmetric_volume_penalty": depth_report.get("symmetric_volume_penalty", 0.0),
                "hat_pointed_back_present": depth_report.get("hat_pointed_back_present", False),
                "front_hat_extension_score": depth_report.get("front_hat_extension_score", 0.0),
                "back_hat_extension_score": depth_report.get("back_hat_extension_score", 0.0),
                "hat_asymmetry_ratio": depth_report.get("hat_asymmetry_ratio", 0.0),
            }
        )
    else:
        summary["semantic_depth_profiles_enabled"] = False
        summary["directional_morphology_enabled"] = False
    if surface_flow_result:
        flow_report = surface_flow_result.get("report", {})
        summary.update(
            {
                "surface_flow_enabled": True,
                "surface_flow_strength": flow_report.get("surface_flow_strength", surface_flow_strength),
                "surface_flow_iterations": flow_report.get("surface_flow_iterations", surface_flow_iterations),
                "semantic_transition_count": flow_report.get("semantic_transition_count", 0),
                "surface_continuity_score": flow_report.get("surface_continuity_score", 0.0),
                "semantic_seam_score": flow_report.get("semantic_seam_score", 0.0),
                "oblique_surface_readability": flow_report.get("oblique_surface_readability", 0.0),
                "surface_fragmentation_score": flow_report.get("surface_fragmentation_score", 0.0),
                "staircase_artifact_score": flow_report.get("staircase_artifact_score", 0.0),
                "anatomical_flow_score": flow_report.get("anatomical_flow_score", 0.0),
                "surface_flow_report": flow_report,
            }
        )
    else:
        summary["surface_flow_enabled"] = False
    if rfd_result:
        rfd_report = rfd_result.get("report", {})
        if surface_flow_result:
            rfd_report["surface_flow_rfd_alignment"] = surface_flow_result.get("report", {}).get("surface_flow_rfd_alignment", 0.0)
            rfd_report_path = rfd_result.get("paths", {}).get("rfd_report")
            if isinstance(rfd_report_path, Path):
                rfd_report_path.write_text(json.dumps(rfd_report, indent=2) + "\n", encoding="utf-8")
        summary.update(
            {
                "rfd_enabled": True,
                "rfd_region_count": rfd_report.get("rfd_region_count", 0),
                "centerline_quality_score": rfd_report.get("centerline_quality_score", 0.0),
                "field_continuity_score": rfd_report.get("field_continuity_score", 0.0),
                "thickness_profile_variance": rfd_report.get("thickness_profile_variance", 0.0),
                "anisotropy_score": rfd_report.get("anisotropy_score", 0.0),
                "directional_field_coherence": rfd_report.get("directional_field_coherence", 0.0),
                "surface_flow_rfd_alignment": rfd_report.get("surface_flow_rfd_alignment", 0.0),
                "silhouette_constraint_preservation": rfd_report.get("silhouette_constraint_preservation", 0.0),
                "rfd_report": rfd_report,
            }
        )
    else:
        summary["rfd_enabled"] = False
    (output_dir / "sdf_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        "sdf": sdf,
        "semantic_volume": semantic_volume,
        "occupancy": occupancy,
        "z_axis": z_axis,
        "summary": summary,
        "semantic_depth_profile": semantic_depth_result,
        "directional_morphology": semantic_depth_result.get("directional_morphology", {}) if semantic_depth_result else {},
        "surface_flow": surface_flow_result,
        "rfd": rfd_result,
        "paths": {
            "sdf_volume": output_dir / "sdf_volume.npy",
            "semantic_volume": output_dir / "semantic_volume.npy",
            "occupancy_volume": output_dir / "occupancy_volume.npy",
            "sdf_slices": slices_dir,
            "sdf_slice_contact_sheet": sheet,
            "sdf_summary": output_dir / "sdf_summary.json",
            **resolution_debug_paths,
        },
    }


def labels_present_in_parts(parts: list[dict[str, Any]]) -> list[int]:
    labels = {
        SEMANTIC_LABEL_IDS.get(str(part.get("semantic_label", part.get("name", "unknown"))), SEMANTIC_LABEL_IDS["unknown"])
        for part in parts
        if part.get("pixels")
    }
    return sorted(labels)


def _occupancy_signed_distance(occupancy: np.ndarray) -> np.ndarray:
    if not occupancy.any():
        return np.ones(occupancy.shape, dtype=np.float32)
    if bool(np.all(occupancy)):
        return -np.ones(occupancy.shape, dtype=np.float32)
    outside_distance = _distance_to_mask(occupancy)
    inside_distance = _distance_to_mask(~occupancy)
    sdf = outside_distance.astype(np.float32, copy=True)
    sdf[occupancy] = -inside_distance[occupancy]
    return sdf.astype(np.float32, copy=False)


def _scale_sampling_grid(
    z_front: np.ndarray,
    z_back: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    scale: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[Pixel, str]]:
    height, width = alpha_mask.shape
    scaled_width = max(width, int(round(width * scale)))
    scaled_height = max(height, int(round(height * scale)))
    z_front_scaled = _resize_float_grid(z_front, scaled_width, scaled_height)
    z_back_scaled = _resize_float_grid(z_back, scaled_width, scaled_height)
    alpha_scaled = _resize_bool_grid(alpha_mask, scaled_width, scaled_height)
    labels_scaled: dict[Pixel, str] = {}
    for y, x in np.argwhere(alpha_scaled):
        source_x = min(width - 1, max(0, int(round((float(x) + 0.5) / scale - 0.5))))
        source_y = min(height - 1, max(0, int(round((float(y) + 0.5) / scale - 0.5))))
        labels_scaled[(int(x), int(y))] = label_by_pixel.get((source_x, source_y), "unknown")
    seam = _silhouette_seam(alpha_scaled)
    z_front_scaled[seam] = 0.0
    z_back_scaled[seam] = 0.0
    z_front_scaled[~alpha_scaled] = 0.0
    z_back_scaled[~alpha_scaled] = 0.0
    return z_front_scaled, z_back_scaled, alpha_scaled, labels_scaled


def _resize_float_grid(values: np.ndarray, width: int, height: int) -> np.ndarray:
    image = Image.fromarray(values.astype(np.float32), mode="F")
    return np.array(image.resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32, copy=True)


def _resize_bool_grid(values: np.ndarray, width: int, height: int) -> np.ndarray:
    image = Image.fromarray((values.astype(np.uint8) * 255), mode="L")
    return np.array(image.resize((width, height), Image.Resampling.NEAREST), dtype=np.uint8, copy=True) > 0


def _write_resolution_debug(
    output_dir: Path,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    source_label_by_pixel: dict[Pixel, str],
    source_shape: list[int],
    z_samples: int,
    base_z_samples: int,
    resolution_scale: float,
    profile: dict[str, Any] | None,
    strategy: str,
    emit_debug: bool,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = profile or {}
    adaptive_regions = {str(item) for item in profile.get("adaptive_regions", [])}
    medium_regions = {str(item) for item in profile.get("medium_detail_regions", [])}
    labels_present = {str(label) for label in source_label_by_pixel.values()}
    high_detail_present = sorted(labels_present & adaptive_regions)
    source_h, source_w = int(source_shape[0]), int(source_shape[1])
    base_voxels = max(1, source_h * source_w * max(1, int(base_z_samples)))
    effective_voxels = int(alpha_mask.shape[0]) * int(alpha_mask.shape[1]) * max(1, int(z_samples))
    report = {
        "schema": "spritespatial_resolution_profile_report_v1",
        "adaptive_sdf_resolution_enabled": bool(profile),
        "resolution_profile": profile.get("name", ""),
        "sdf_resolution_strategy": strategy,
        "base_xy_scale": profile.get("base_xy_scale", 1.0),
        "base_z_scale": profile.get("base_z_scale", 1.0),
        "effective_xy_scale": resolution_scale,
        "effective_z_samples": z_samples,
        "base_z_samples": base_z_samples,
        "effective_voxel_budget_multiplier": float(effective_voxels) / float(base_voxels),
        "adaptive_high_detail_region_count": len(high_detail_present),
        "adaptive_regions_present": high_detail_present,
        "medium_detail_regions_present": sorted(labels_present & medium_regions),
        "silhouette_band_high_res_enabled": bool(profile.get("silhouette_band_extra_scale", 1.0) > 1.0),
        "semantic_boundary_high_res_enabled": bool(profile.get("semantic_boundary_extra_scale", 1.0) > 1.0),
        "max_voxel_budget_multiplier": profile.get("max_voxel_budget_multiplier", 1.0),
        "max_non_manifold_edge_increase": profile.get("max_non_manifold_edge_increase", 0),
    }
    paths = {
        "resolution_profile_used": output_dir / "resolution_profile_used.json",
        "adaptive_region_map": output_dir / "adaptive_region_map.png",
        "high_detail_band_debug": output_dir / "high_detail_band_debug.png",
        "semantic_boundary_resolution_debug": output_dir / "semantic_boundary_resolution_debug.png",
        "voxel_budget_report": output_dir / "voxel_budget_report.json",
    }
    _write_json(paths["resolution_profile_used"], profile)
    _write_json(paths["voxel_budget_report"], report)
    _write_adaptive_region_map(alpha_mask, label_by_pixel, adaptive_regions, paths["adaptive_region_map"])
    _write_high_detail_band(alpha_mask, paths["high_detail_band_debug"])
    _write_semantic_boundary_map(alpha_mask, label_by_pixel, paths["semantic_boundary_resolution_debug"])
    if emit_debug:
        _write_json(output_dir / "resolution_debug_payload.json", {"label_count": len(label_by_pixel), **report})
        paths["resolution_debug_payload"] = output_dir / "resolution_debug_payload.json"
    return report, paths


def _write_adaptive_region_map(
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    adaptive_regions: set[str],
    path: Path,
) -> None:
    image = Image.new("RGBA", (alpha_mask.shape[1], alpha_mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(alpha_mask):
        label = label_by_pixel.get((int(x), int(y)), "unknown")
        pixels[int(x), int(y)] = (255, 170, 60, 255) if label in adaptive_regions else (70, 140, 180, 180)
    image.save(path, format="PNG")


def _write_high_detail_band(alpha_mask: np.ndarray, path: Path) -> None:
    seam = _silhouette_seam(alpha_mask)
    image = Image.new("RGBA", (alpha_mask.shape[1], alpha_mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(alpha_mask):
        pixels[int(x), int(y)] = (70, 120, 150, 120)
    for y, x in np.argwhere(seam):
        pixels[int(x), int(y)] = (255, 225, 90, 255)
    image.save(path, format="PNG")


def _write_semantic_boundary_map(
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    path: Path,
) -> None:
    image = Image.new("RGBA", (alpha_mask.shape[1], alpha_mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    height, width = alpha_mask.shape
    for y, x in np.argwhere(alpha_mask):
        label = label_by_pixel.get((int(x), int(y)), "unknown")
        boundary = False
        for nx, ny in ((int(x) - 1, int(y)), (int(x) + 1, int(y)), (int(x), int(y) - 1), (int(x), int(y) + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                if label_by_pixel.get((nx, ny), "unknown") != label:
                    boundary = True
                    break
        pixels[int(x), int(y)] = (255, 80, 110, 255) if boundary else (60, 110, 130, 120)
    image.save(path, format="PNG")


def _silhouette_seam(alpha_mask: np.ndarray) -> np.ndarray:
    seam = np.zeros_like(alpha_mask, dtype=bool)
    height, width = alpha_mask.shape
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height or not alpha_mask[ny, nx]:
                    seam[y, x] = True
                    break
    return seam


def _distance_to_mask(mask: np.ndarray) -> np.ndarray:
    inf = np.float32(1.0e12)
    distances = np.where(mask, np.float32(0.0), inf).astype(np.float32)
    for axis in range(distances.ndim):
        distances = _edt_axis(distances, axis)
    return np.sqrt(distances).astype(np.float32, copy=False)


def _edt_axis(values: np.ndarray, axis: int) -> np.ndarray:
    moved = np.moveaxis(values, axis, 0)
    result = np.empty_like(moved, dtype=np.float32)
    trailing_shape = moved.shape[1:]
    for index in np.ndindex(trailing_shape):
        result[(slice(None),) + index] = _edt_1d(moved[(slice(None),) + index])
    return np.moveaxis(result, 0, axis)


def _edt_1d(values: np.ndarray) -> np.ndarray:
    n = int(values.shape[0])
    if n == 0:
        return values.astype(np.float32, copy=True)
    v = np.zeros(n, dtype=np.int32)
    z = np.zeros(n + 1, dtype=np.float32)
    output = np.zeros(n, dtype=np.float32)
    k = 0
    v[0] = 0
    z[0] = -np.inf
    z[1] = np.inf
    for q in range(1, n):
        while True:
            p = int(v[k])
            numerator = (float(values[q]) + float(q * q)) - (float(values[p]) + float(p * p))
            denominator = float(2 * q - 2 * p)
            s = numerator / denominator if abs(denominator) > 1.0e-12 else np.inf
            if s > z[k] or k == 0:
                break
            k -= 1
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = np.inf
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        p = int(v[k])
        output[q] = float((q - p) * (q - p)) + float(values[p])
    return output


def _components(mask: np.ndarray) -> list[set[tuple[int, int]]]:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    component.add((nx, ny))
                    queue.append((nx, ny))
        components.append(component)
    return components


def _inner_holes(alpha_mask: np.ndarray) -> list[set[tuple[int, int]]]:
    height, width = alpha_mask.shape
    outside = np.zeros_like(alpha_mask, dtype=bool)
    queue = deque()
    for x in range(width):
        for y in (0, height - 1):
            if not alpha_mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if not alpha_mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and not alpha_mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                queue.append((nx, ny))
    holes = (~alpha_mask) & (~outside)
    return _components(holes)


def _volume_component_count(occupancy: np.ndarray) -> int:
    remaining = {tuple(int(v) for v in item) for item in np.argwhere(occupancy)}
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            y, x, z = queue.popleft()
            for neighbour in ((y - 1, x, z), (y + 1, x, z), (y, x - 1, z), (y, x + 1, z), (y, x, z - 1), (y, x, z + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
    return components


def _remove_isolated_outline_components(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    max_voxels: int = 8,
) -> int:
    remaining = {tuple(int(v) for v in item) for item in np.argwhere(occupancy)}
    removed = 0
    while remaining:
        start = remaining.pop()
        queue = deque([start])
        component = [start]
        while queue:
            y, x, z = queue.popleft()
            for neighbour in ((y - 1, x, z), (y + 1, x, z), (y, x - 1, z), (y, x + 1, z), (y, x, z - 1), (y, x, z + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
                    component.append(neighbour)
        if len(component) > max_voxels:
            continue
        labels = {int(semantic_volume[y, x, z]) for y, x, z in component}
        if labels == {SEMANTIC_LABEL_IDS["outline"]}:
            for y, x, z in component:
                occupancy[y, x, z] = False
                semantic_volume[y, x, z] = 0
                removed += 1
    return removed


def _remove_tiny_noncritical_components(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    max_voxels: int = 16,
) -> int:
    noncritical_labels = {0, SEMANTIC_LABEL_IDS["outline"], SEMANTIC_LABEL_IDS["unknown"]}
    remaining = {tuple(int(v) for v in item) for item in np.argwhere(occupancy)}
    components: list[list[tuple[int, int, int]]] = []
    while remaining:
        start = remaining.pop()
        queue = deque([start])
        component = [start]
        while queue:
            y, x, z = queue.popleft()
            for neighbour in ((y - 1, x, z), (y + 1, x, z), (y, x - 1, z), (y, x + 1, z), (y, x, z - 1), (y, x, z + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
                    component.append(neighbour)
        components.append(component)
    if len(components) <= 1:
        return 0
    largest = max(components, key=len)
    removed = 0
    for component in components:
        if component is largest or len(component) > max_voxels:
            continue
        labels = {int(semantic_volume[y, x, z]) for y, x, z in component}
        if not labels.issubset(noncritical_labels):
            continue
        for y, x, z in component:
            occupancy[y, x, z] = False
            semantic_volume[y, x, z] = 0
            removed += 1
    return removed


def _concave_seam_count(alpha_mask: np.ndarray, seam_mask: np.ndarray) -> int:
    count = 0
    height, width = alpha_mask.shape
    for y, x in np.argwhere(seam_mask):
        neighbours = 0
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                neighbours += 1
        if neighbours >= 3:
            count += 1
    return count


def _write_mask(mask: np.ndarray, path: Path) -> None:
    height, width = mask.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (255, 255, 255, 255)
    image.save(path, format="PNG")


def _write_sdf_slices(sdf: np.ndarray, occupancy: np.ndarray, output_dir: Path) -> None:
    for z in range(sdf.shape[2]):
        _write_slice(sdf[:, :, z], occupancy[:, :, z], output_dir / f"slice_{z:03d}.png")


def _write_sdf_sheet(sdf: np.ndarray, occupancy: np.ndarray, path: Path) -> None:
    frames = []
    step = max(1, sdf.shape[2] // 8)
    for z in range(0, sdf.shape[2], step):
        frame = _slice_image(sdf[:, :, z], occupancy[:, :, z])
        frames.append(frame)
    if not frames:
        return
    sheet = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame.width, 0))
    sheet.save(path, format="PNG")


def _write_slice(values: np.ndarray, occupied: np.ndarray, path: Path) -> None:
    _slice_image(values, occupied).save(path, format="PNG")


def _slice_image(values: np.ndarray, occupied: np.ndarray) -> Image.Image:
    height, width = values.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    max_abs = max(float(np.max(np.abs(values))), 1e-6)
    for y in range(height):
        for x in range(width):
            value = float(values[y, x])
            shade = int(255 * min(abs(value) / max_abs, 1.0))
            pixels[x, y] = (60, 190, 90, 255) if occupied[y, x] else (shade, shade, shade, 120)
    return image


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
