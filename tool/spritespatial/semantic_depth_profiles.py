from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.directional_morphology import (
    apply_directional_interval,
    build_directional_report,
    rule_for_label,
    write_directional_debug,
)

Pixel = tuple[int, int]


@dataclass(frozen=True)
class SemanticDepthProfile:
    z_center_fraction: float
    half_thickness_fraction: float
    profile_type: str
    taper_curve: str
    asymmetry: float
    depth_priority: int
    silhouette_preservation_weight: float


DEFAULT_PROFILE_SET: dict[str, SemanticDepthProfile] = {
    "head": SemanticDepthProfile(0.02, 0.46, "hemisphere", "round", 0.05, 90, 0.95),
    "face": SemanticDepthProfile(0.28, 0.22, "rounded_front", "front_pad", 0.35, 92, 0.98),
    "torso": SemanticDepthProfile(0.0, 0.40, "rounded_cuboid", "neck_waist", 0.0, 80, 0.92),
    "left_arm": SemanticDepthProfile(0.0, 0.30, "capsule_chain", "limb", 0.0, 70, 0.88),
    "right_arm": SemanticDepthProfile(0.0, 0.30, "capsule_chain", "limb", 0.0, 70, 0.88),
    "left_leg": SemanticDepthProfile(0.0, 0.32, "tapered_capsule_chain", "limb_taper", 0.0, 68, 0.88),
    "right_leg": SemanticDepthProfile(0.0, 0.32, "tapered_capsule_chain", "limb_taper", 0.0, 68, 0.88),
    "boots/feet": SemanticDepthProfile(0.06, 0.18, "flattened_rounded_box", "foot", 0.12, 74, 0.90),
    "hair/hat": SemanticDepthProfile(0.22, 0.14, "shell_offset", "layer", 0.20, 85, 0.96),
    "outline": SemanticDepthProfile(0.0, 0.04, "outline_shell", "shell", 0.0, 100, 1.0),
    "equipment/shield/sword": SemanticDepthProfile(0.18, 0.16, "shell_offset", "rigid", 0.20, 88, 0.96),
    "unknown": SemanticDepthProfile(0.0, 0.28, "rounded_cuboid", "neutral", 0.0, 40, 0.85),
}


LABEL_ALIASES = {
    "hat_hair": "hair/hat",
    "hair": "hair/hat",
    "cap": "hair/hat",
    "boots_feet": "boots/feet",
    "feet": "boots/feet",
    "boots": "boots/feet",
    "equipment": "equipment/shield/sword",
    "shield": "equipment/shield/sword",
    "sword": "equipment/shield/sword",
}


def load_profile_set(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "humanoid_voxel")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "depth_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = dict(DEFAULT_PROFILE_SET)
    for label, payload in data.get("profiles", {}).items():
        canonical = canonical_label(label)
        base = profiles.get(canonical, DEFAULT_PROFILE_SET["unknown"])
        profiles[canonical] = SemanticDepthProfile(
            z_center_fraction=float(payload.get("z_center_fraction", base.z_center_fraction)),
            half_thickness_fraction=float(payload.get("half_thickness_fraction", base.half_thickness_fraction)),
            profile_type=str(payload.get("profile_type", base.profile_type)),
            taper_curve=str(payload.get("taper_curve", base.taper_curve)),
            asymmetry=float(payload.get("asymmetry", base.asymmetry)),
            depth_priority=int(payload.get("depth_priority", base.depth_priority)),
            silhouette_preservation_weight=float(
                payload.get("silhouette_preservation_weight", base.silhouette_preservation_weight)
            ),
        )
    return {
        "name": data.get("name", path.stem),
        "path": str(path),
        "profiles": profiles,
        "raw": data,
    }


def canonical_label(label: str) -> str:
    value = str(label or "unknown")
    return LABEL_ALIASES.get(value, value if value in DEFAULT_PROFILE_SET else "unknown")


def synthesize_semantic_occupancy(
    z_front: np.ndarray,
    z_back: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    z_axis: np.ndarray,
    profile_set: dict[str, Any],
    output_dir: Path | None = None,
    emit_debug: bool = False,
    directional_morphology: dict[str, Any] | None = None,
    directional_output_dir: Path | None = None,
    emit_directional_debug: bool = False,
) -> dict[str, Any]:
    profiles: dict[str, SemanticDepthProfile] = profile_set["profiles"]
    height, width = alpha_mask.shape
    z_samples = int(len(z_axis))
    dz = float(np.min(np.diff(z_axis))) if z_samples > 1 else 1.0
    dz = abs(dz) if abs(dz) > 1e-6 else 1.0
    labels = _label_grid(alpha_mask, label_by_pixel)
    label_norms = _label_distance_norms(alpha_mask, labels)
    label_bounds = _label_bounds(alpha_mask, labels)
    occupancy = np.zeros((height, width, z_samples), dtype=bool)
    thickness_map = np.zeros((height, width), dtype=np.float32)
    center_map = np.zeros((height, width), dtype=np.float32)
    rule_map = np.full((height, width), "", dtype=object)
    directional_bias_map = np.zeros((height, width), dtype=np.float32)
    front_extent_map = np.zeros((height, width), dtype=np.float32)
    back_extent_map = np.zeros((height, width), dtype=np.float32)
    center_shift_map = np.zeros((height, width), dtype=np.float32)
    profile_assignment: dict[str, int] = {}
    for y, x in np.argwhere(alpha_mask):
        label = labels[int(y), int(x)]
        profile = profiles.get(label, profiles["unknown"])
        span = max(float(z_front[y, x] - z_back[y, x]), dz)
        center = float(z_back[y, x]) + span * (0.5 + profile.z_center_fraction * 0.5) + profile.asymmetry * span * 0.08
        edge_norm = float(label_norms[label][y, x])
        taper = _taper_value(profile.taper_curve, int(x), int(y), labels == label)
        shape = _profile_shape(profile.profile_type, edge_norm, taper)
        half = max(dz * 0.55, span * profile.half_thickness_fraction * shape)
        if label == "outline" or profile.profile_type == "outline_shell":
            nearest = int(np.argmin(np.abs(z_axis - center)))
            occupancy[y, x, nearest] = True
            thickness_map[y, x] = dz
            front_extent_map[y, x] = dz * 0.5
            back_extent_map[y, x] = dz * 0.5
        else:
            rule = rule_for_label(str(label), directional_morphology)
            if rule is not None:
                local_x, local_y = _local_axes(int(x), int(y), label_bounds.get(str(label)))
                interval = apply_directional_interval(
                    z_axis,
                    center,
                    half,
                    span,
                    rule,
                    local_x,
                    local_y,
                    edge_norm,
                    dz,
                )
                center = float(interval["center"])
                inside = interval["inside"]
                front_extent_map[y, x] = float(interval["front_extent"])
                back_extent_map[y, x] = float(interval["back_extent"])
                center_shift_map[y, x] = float(interval["center_shift"])
                rule_map[y, x] = rule.profile_type
                directional_bias_map[y, x] = float(interval["back_extent"]) - float(interval["front_extent"])
            else:
                inside = np.abs(z_axis - center) <= half
                front_extent_map[y, x] = float(half)
                back_extent_map[y, x] = float(half)
            if not bool(np.any(inside)):
                inside[int(np.argmin(np.abs(z_axis - center)))] = True
            occupancy[y, x, inside] = True
            thickness_map[y, x] = float(np.count_nonzero(inside)) * dz
        center_map[y, x] = center
        profile_assignment[label] = profile_assignment.get(label, 0) + 1

    # Keep the outer seam closed at the shared centre line without inflating it into a slab.
    seam = _silhouette_seam(alpha_mask)
    center_index = int(np.argmin(np.abs(z_axis)))
    occupancy[seam, :] = False
    occupancy[seam, center_index] = True

    report = _metrics(occupancy, alpha_mask, labels, thickness_map, z_axis, profiles)
    report.update(
        {
            "schema": "spritespatial_semantic_depth_profiles_v1",
            "profile_set": profile_set.get("name", "unknown"),
            "profile_assignment_counts": profile_assignment,
            "profiles": {label: asdict(profile) for label, profile in profiles.items()},
        }
    )
    embodiment_report = profile_set.get("embodiment_params_report")
    if isinstance(embodiment_report, dict):
        report.update(
            {
                "embodiment_params_enabled": bool(embodiment_report.get("embodiment_params_enabled", False)),
                "embodiment_params_loaded": bool(embodiment_report.get("embodiment_params_loaded", False)),
                "embodiment_params_using_defaults": bool(embodiment_report.get("embodiment_params_using_defaults", False)),
                "embodiment_params_path": embodiment_report.get("embodiment_params_path", ""),
                "embodiment_param_parts_requested": embodiment_report.get("embodiment_param_parts_requested", []),
                "embodiment_param_parts_applied": embodiment_report.get("embodiment_param_parts_applied", []),
                "embodiment_param_parts_skipped": embodiment_report.get("embodiment_param_parts_skipped", {}),
                "embodiment_param_locked_parts": embodiment_report.get("embodiment_param_locked_parts", []),
                "embodiment_param_applied_count": int(embodiment_report.get("embodiment_param_applied_count", 0)),
                "embodiment_parts_modified": int(embodiment_report.get("embodiment_parts_modified", 0)),
                "embodiment_param_report": embodiment_report,
            }
        )
    else:
        report.update(
            {
                "embodiment_params_enabled": False,
                "embodiment_params_loaded": False,
                "embodiment_params_using_defaults": False,
                "embodiment_params_path": "",
                "embodiment_param_parts_requested": [],
                "embodiment_param_parts_applied": [],
                "embodiment_param_parts_skipped": {},
                "embodiment_param_locked_parts": [],
                "embodiment_param_applied_count": 0,
                "embodiment_parts_modified": 0,
            }
        )
    directional_result: dict[str, Any] = {}
    if directional_morphology:
        directional_report = build_directional_report(
            alpha_mask,
            labels,
            rule_map,
            front_extent_map,
            back_extent_map,
            center_shift_map,
            directional_morphology.get("rules", {}),
            str(directional_morphology.get("name", "unknown")),
        )
        report.update(directional_report)
        directional_paths: dict[str, Path] = {}
        if directional_output_dir is not None:
            directional_paths = write_directional_debug(
                directional_output_dir,
                occupancy,
                alpha_mask,
                labels,
                rule_map,
                directional_bias_map,
                front_extent_map,
                back_extent_map,
                directional_report,
                emit_directional_debug,
            )
        directional_result = {"report": directional_report, "paths": directional_paths}
    else:
        report.update(
            {
                "directional_morphology_enabled": False,
                "directional_semantic_count": 0,
                "anisotropic_region_ratio": 0.0,
                "rearward_extension_score": 0.0,
                "front_compression_score": 0.0,
                "directional_readability_score": 0.0,
                "symmetric_volume_penalty": 0.0,
                "hat_pointed_back_present": False,
                "front_hat_extension_score": 0.0,
                "back_hat_extension_score": 0.0,
                "hat_asymmetry_ratio": 0.0,
            }
        )
    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = write_semantic_depth_debug(
            output_dir,
            occupancy,
            alpha_mask,
            labels,
            thickness_map,
            center_map,
            z_axis,
            report,
            emit_debug,
        )
    return {
        "occupancy": occupancy,
        "thickness_map": thickness_map,
        "center_map": center_map,
        "report": report,
        "paths": paths,
        "directional_morphology": directional_result,
    }


def write_semantic_depth_debug(
    output_dir: Path,
    occupancy: np.ndarray,
    alpha_mask: np.ndarray,
    labels: np.ndarray,
    thickness_map: np.ndarray,
    center_map: np.ndarray,
    z_axis: np.ndarray,
    report: dict[str, Any],
    emit_debug: bool,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "semantic_depth_map": output_dir / "semantic_depth_map.png",
        "semantic_z_slices": output_dir / "semantic_z_slices.png",
        "semantic_thickness_debug": output_dir / "semantic_thickness_debug.png",
        "occupancy_volume_slices": output_dir / "occupancy_volume_slices.png",
        "side_projection_debug": output_dir / "side_projection_debug.png",
        "top_projection_debug": output_dir / "top_projection_debug.png",
        "profile_assignment_overlay": output_dir / "profile_assignment_overlay.png",
        "semantic_depth_profile_report": output_dir / "semantic_depth_profile_report.json",
    }
    _write_heatmap(thickness_map, paths["semantic_depth_map"])
    _write_heatmap(np.abs(center_map), paths["semantic_thickness_debug"])
    _write_slice_sheet(occupancy, paths["semantic_z_slices"])
    _write_slice_sheet(occupancy, paths["occupancy_volume_slices"])
    _write_projection(occupancy.any(axis=1).T, paths["side_projection_debug"])
    _write_projection(occupancy.any(axis=0).T, paths["top_projection_debug"])
    _write_label_overlay(labels, alpha_mask, paths["profile_assignment_overlay"])
    paths["semantic_depth_profile_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if emit_debug:
        slices_dir = output_dir / "slices"
        slices_dir.mkdir(exist_ok=True)
        for index in range(occupancy.shape[2]):
            _write_projection(occupancy[:, :, index], slices_dir / f"slice_{index:03d}.png")
        paths["slices"] = slices_dir
    return paths


def _metrics(
    occupancy: np.ndarray,
    alpha_mask: np.ndarray,
    labels: np.ndarray,
    thickness_map: np.ndarray,
    z_axis: np.ndarray,
    profiles: dict[str, SemanticDepthProfile],
) -> dict[str, Any]:
    occupied_per_pixel = occupancy.sum(axis=2).astype(np.float32)
    full_columns = np.maximum(1.0, np.full(alpha_mask.shape, occupancy.shape[2], dtype=np.float32))
    uniform_slab_ratio = float(np.mean((occupied_per_pixel[alpha_mask] / full_columns[alpha_mask]) >= 0.82)) if alpha_mask.any() else 0.0
    depth_by_label: dict[str, float] = {}
    variance_by_label: dict[str, float] = {}
    for label in sorted(set(labels[alpha_mask].tolist())):
        mask = alpha_mask & (labels == label)
        if not mask.any():
            continue
        depth_by_label[label] = float(np.mean(occupied_per_pixel[mask]) / max(float(occupancy.shape[2]), 1.0))
        variance_by_label[label] = float(np.var(occupied_per_pixel[mask]))
    side_projection = occupancy.any(axis=1)
    side_entropy = _entropy(side_projection.sum(axis=0))
    outline_mask = alpha_mask & (labels == "outline")
    outline_shell_ratio = float(np.max(occupied_per_pixel[outline_mask])) if outline_mask.any() else 0.0
    return {
        "semantic_depth_profiles_enabled": True,
        "uniform_slab_ratio": uniform_slab_ratio,
        "semantic_depth_variance": float(np.var(occupied_per_pixel[alpha_mask])) if alpha_mask.any() else 0.0,
        "head_depth_ratio": depth_by_label.get("head", 0.0),
        "torso_depth_ratio": depth_by_label.get("torso", 0.0),
        "limb_depth_ratio": _mean_present(depth_by_label, ("left_arm", "right_arm", "left_leg", "right_leg")),
        "outline_shell_ratio": outline_shell_ratio,
        "side_projection_entropy": side_entropy,
        "side_profile_readability_score": max(0.0, min(1.0, 0.55 * (1.0 - uniform_slab_ratio) + 0.45 * side_entropy)),
        "depth_ratio_by_label": depth_by_label,
        "depth_variance_by_label": variance_by_label,
        "z_axis_min": float(z_axis.min()) if z_axis.size else 0.0,
        "z_axis_max": float(z_axis.max()) if z_axis.size else 0.0,
        "outline_max_voxel_thickness": outline_shell_ratio,
    }


def _label_grid(alpha_mask: np.ndarray, label_by_pixel: dict[Pixel, str]) -> np.ndarray:
    labels = np.full(alpha_mask.shape, "unknown", dtype=object)
    for (x, y), label in label_by_pixel.items():
        if 0 <= y < labels.shape[0] and 0 <= x < labels.shape[1]:
            labels[y, x] = canonical_label(label)
    labels[~alpha_mask] = "transparent"
    return labels


def _label_distance_norms(alpha_mask: np.ndarray, labels: np.ndarray) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for label in sorted(set(labels[alpha_mask].tolist())):
        mask = alpha_mask & (labels == label)
        result[label] = _normalise(_edt(mask))
    result["unknown"] = result.get("unknown", _normalise(_edt(alpha_mask)))
    return result


def _label_bounds(alpha_mask: np.ndarray, labels: np.ndarray) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for label in sorted(set(labels[alpha_mask].tolist())):
        points = np.argwhere(alpha_mask & (labels == label))
        if points.size == 0:
            continue
        ys = points[:, 0]
        xs = points[:, 1]
        result[str(label)] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return result


def _local_axes(x: int, y: int, bounds: tuple[int, int, int, int] | None) -> tuple[float, float]:
    if bounds is None:
        return 0.0, 0.0
    x0, y0, x1, y1 = bounds
    local_x = ((x - x0) / max(float(x1 - x0), 1.0)) * 2.0 - 1.0
    local_y = ((y - y0) / max(float(y1 - y0), 1.0)) * 2.0 - 1.0
    return max(-1.0, min(1.0, local_x)), max(-1.0, min(1.0, local_y))


def _edt(mask: np.ndarray) -> np.ndarray:
    values = np.zeros(mask.shape, dtype=np.float32)
    points = np.argwhere(mask)
    if points.size == 0:
        return values
    outside = np.argwhere(~mask)
    if outside.size == 0:
        outside = np.array([[0, 0]], dtype=np.int32)
    for y, x in points:
        delta = outside - np.array([y, x])
        values[y, x] = float(np.sqrt((delta * delta).sum(axis=1).min()))
    return values


def _normalise(values: np.ndarray) -> np.ndarray:
    max_value = float(values.max()) if values.size else 0.0
    if max_value <= 1e-6:
        return np.zeros(values.shape, dtype=np.float32)
    return (values / max_value).astype(np.float32)


def _profile_shape(profile_type: str, edge_norm: float, taper: float) -> float:
    e = max(0.0, min(1.0, edge_norm))
    if profile_type in {"hemisphere", "rounded_front"}:
        value = math.sin(e * math.pi * 0.5) ** 0.8
    elif profile_type == "rounded_cuboid":
        value = 0.42 + 0.58 * min(1.0, e * 1.55)
    elif profile_type == "capsule_chain":
        value = 0.32 + 0.68 * math.sqrt(e)
    elif profile_type == "tapered_capsule_chain":
        value = 0.22 + 0.78 * math.sqrt(e)
    elif profile_type == "flattened_rounded_box":
        value = 0.20 + 0.45 * min(1.0, e * 1.7)
    elif profile_type == "shell_offset":
        value = 0.24 + 0.35 * min(1.0, e * 1.4)
    elif profile_type == "outline_shell":
        value = 0.05
    else:
        value = 0.32 + 0.68 * e
    return max(0.05, min(1.0, value * taper))


def _taper_value(curve: str, x: int, y: int, mask: np.ndarray) -> float:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 1.0
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    yn = (y - y0) / max(float(y1 - y0 - 1), 1.0)
    xn = (x - x0) / max(float(x1 - x0 - 1), 1.0)
    if curve == "neck_waist":
        return 0.68 + 0.32 * math.sin(math.pi * max(0.0, min(1.0, yn)))
    if curve == "limb":
        return 0.72 + 0.28 * math.sin(math.pi * max(0.0, min(1.0, yn)))
    if curve == "limb_taper":
        return 0.95 - 0.35 * max(0.0, min(1.0, yn))
    if curve == "foot":
        return 0.58 + 0.22 * (1.0 - abs(xn - 0.5) * 2.0)
    if curve in {"layer", "shell", "rigid", "front_pad", "round"}:
        return 1.0
    return 1.0


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


def _mean_present(values: dict[str, float], labels: tuple[str, ...]) -> float:
    present = [values[label] for label in labels if label in values]
    return float(sum(present) / len(present)) if present else 0.0


def _entropy(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=np.float32).reshape(-1)
    total = float(data.sum())
    if total <= 1e-6:
        return 0.0
    p = data[data > 0] / total
    entropy = -float(np.sum(p * np.log2(p)))
    return entropy / max(math.log2(len(data)), 1e-6)


def _write_heatmap(values: np.ndarray, path: Path) -> None:
    max_value = float(values.max()) if values.size else 0.0
    image = Image.new("RGBA", (values.shape[1], values.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(values.shape[0]):
        for x in range(values.shape[1]):
            value = float(values[y, x])
            if value <= 0.0:
                continue
            t = value / max(max_value, 1e-6)
            pixels[x, y] = (int(255 * t), int(210 * (1.0 - t)), int(120 + 100 * t), 255)
    image.save(path, format="PNG")


def _write_projection(mask: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (80, 220, 150, 255)
    image.save(path, format="PNG")


def _write_slice_sheet(occupancy: np.ndarray, path: Path) -> None:
    frames = []
    step = max(1, occupancy.shape[2] // 8)
    for z in range(0, occupancy.shape[2], step):
        mask = occupancy[:, :, z]
        image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
        pixels = image.load()
        for y, x in np.argwhere(mask):
            pixels[int(x), int(y)] = (75, 185, 255, 255)
        frames.append(image)
    if not frames:
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(path, format="PNG")
        return
    sheet = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame.width, 0))
    sheet.save(path, format="PNG")


def _write_label_overlay(labels: np.ndarray, alpha_mask: np.ndarray, path: Path) -> None:
    palette = {
        "outline": (8, 8, 8, 255),
        "head": (235, 87, 66, 255),
        "face": (255, 189, 107, 255),
        "hair/hat": (89, 46, 184, 255),
        "torso": (46, 138, 230, 255),
        "left_arm": (56, 184, 117, 255),
        "right_arm": (66, 163, 107, 255),
        "left_leg": (189, 133, 51, 255),
        "right_leg": (133, 179, 51, 255),
        "boots/feet": (107, 61, 31, 255),
        "equipment/shield/sword": (235, 209, 51, 255),
        "unknown": (163, 163, 163, 255),
    }
    image = Image.new("RGBA", (labels.shape[1], labels.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, x in np.argwhere(alpha_mask):
        draw.point((int(x), int(y)), fill=palette.get(str(labels[y, x]), palette["unknown"]))
    image.save(path, format="PNG")
