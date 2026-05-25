from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


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
    "nose": "face",
    "cape": "equipment/shield/sword",
    "tail": "equipment/shield/sword",
}


@dataclass(frozen=True)
class DirectionalMorphologyRule:
    profile_type: str
    forward_bias: float = 0.0
    backward_bias: float = 0.0
    lateral_bias: float = 0.0
    upward_bias: float = 0.0
    downward_bias: float = 0.0
    taper_direction: str = "none"
    asymmetry_strength: float = 0.0
    curvature_bias: float = 0.0
    trailing_profile: str = "none"
    compression_profile: str = "none"
    front_profile: str = "inherit"
    back_profile: str = "inherit"
    front_scale: float = 1.0
    back_scale: float = 1.0
    front_taper: float = 0.0
    back_taper: float = 0.0
    suppress_front_projection: bool = False
    rear_extension_bias: float = 0.0


DEFAULT_RULES: dict[str, DirectionalMorphologyRule] = {
    "hair/hat": DirectionalMorphologyRule(
        profile_type="HAT_POINTED_BACK",
        forward_bias=0.0,
        backward_bias=0.78,
        lateral_bias=-0.42,
        upward_bias=0.05,
        downward_bias=0.28,
        taper_direction="back",
        asymmetry_strength=0.72,
        curvature_bias=0.25,
        trailing_profile="curved_down_tail",
        compression_profile="compressed_front",
        front_profile="rounded_compressed",
        back_profile="elongated_taper",
        front_scale=0.25,
        back_scale=1.20,
        front_taper=0.12,
        back_taper=0.82,
        suppress_front_projection=True,
        rear_extension_bias=0.80,
    ),
    "face": DirectionalMorphologyRule(
        profile_type="NOSE_FORWARD",
        forward_bias=0.42,
        backward_bias=0.03,
        lateral_bias=-0.08,
        upward_bias=0.0,
        downward_bias=0.0,
        taper_direction="front",
        asymmetry_strength=0.45,
        curvature_bias=0.18,
        trailing_profile="none",
        compression_profile="flat_back",
    ),
    "equipment/shield/sword": DirectionalMorphologyRule(
        profile_type="SHIELD_SIDE",
        forward_bias=0.10,
        backward_bias=0.15,
        lateral_bias=0.38,
        upward_bias=0.0,
        downward_bias=0.0,
        taper_direction="side",
        asymmetry_strength=0.40,
        curvature_bias=0.05,
        trailing_profile="rigid_side",
        compression_profile="rigid",
    ),
}


SUPPORTED_PROFILE_TYPES = {
    "HAT_POINTED_BACK",
    "HAIR_LONG_BACK",
    "NOSE_FORWARD",
    "CAPE_BACK",
    "SHIELD_SIDE",
    "SHOULDER_PAD",
    "TAIL",
}


def load_morphology_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "fantasy_humanoid")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "morphology_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = dict(DEFAULT_RULES)
    for label, payload in data.get("rules", {}).items():
        canonical = canonical_label(label)
        base = rules.get(canonical, DirectionalMorphologyRule(profile_type=str(payload.get("profile_type", "TAIL"))))
        rules[canonical] = DirectionalMorphologyRule(
            profile_type=str(payload.get("profile_type", base.profile_type)),
            forward_bias=float(payload.get("forward_bias", base.forward_bias)),
            backward_bias=float(payload.get("backward_bias", base.backward_bias)),
            lateral_bias=float(payload.get("lateral_bias", base.lateral_bias)),
            upward_bias=float(payload.get("upward_bias", base.upward_bias)),
            downward_bias=float(payload.get("downward_bias", base.downward_bias)),
            taper_direction=str(payload.get("taper_direction", base.taper_direction)),
            asymmetry_strength=float(payload.get("asymmetry_strength", base.asymmetry_strength)),
            curvature_bias=float(payload.get("curvature_bias", base.curvature_bias)),
            trailing_profile=str(payload.get("trailing_profile", base.trailing_profile)),
            compression_profile=str(payload.get("compression_profile", base.compression_profile)),
            front_profile=str(payload.get("front_profile", base.front_profile)),
            back_profile=str(payload.get("back_profile", base.back_profile)),
            front_scale=float(payload.get("front_scale", base.front_scale)),
            back_scale=float(payload.get("back_scale", base.back_scale)),
            front_taper=float(payload.get("front_taper", base.front_taper)),
            back_taper=float(payload.get("back_taper", base.back_taper)),
            suppress_front_projection=bool(payload.get("suppress_front_projection", base.suppress_front_projection)),
            rear_extension_bias=float(payload.get("rear_extension_bias", base.rear_extension_bias)),
        )
    return {
        "name": data.get("name", path.stem),
        "path": str(path),
        "rules": rules,
        "raw": data,
        "supported_profile_types": sorted(SUPPORTED_PROFILE_TYPES),
    }


def canonical_label(label: str) -> str:
    value = str(label or "unknown")
    return LABEL_ALIASES.get(value, value)


def rule_for_label(label: str, morphology_profile: dict[str, Any] | None) -> DirectionalMorphologyRule | None:
    if not morphology_profile:
        return None
    rules = morphology_profile.get("rules", {})
    if not isinstance(rules, dict):
        return None
    rule = rules.get(canonical_label(label))
    return rule if isinstance(rule, DirectionalMorphologyRule) else None


def apply_directional_interval(
    z_axis: np.ndarray,
    center: float,
    half: float,
    span: float,
    rule: DirectionalMorphologyRule,
    local_x: float,
    local_y: float,
    edge_norm: float,
    dz: float,
) -> dict[str, Any]:
    asymmetry = _clamp(rule.asymmetry_strength, 0.0, 1.0)
    front_scale = max(0.05, rule.front_scale) * (1.0 + max(0.0, rule.forward_bias) * 0.45)
    back_scale = max(0.05, rule.back_scale) * (1.0 + max(0.0, rule.backward_bias) * 0.75)

    compression = _compression_amount(rule.compression_profile) * max(0.20, asymmetry)
    if rule.profile_type in {"HAT_POINTED_BACK", "HAIR_LONG_BACK", "CAPE_BACK"}:
        front_scale -= 0.45 * compression
    elif rule.profile_type == "NOSE_FORWARD":
        back_scale -= 0.25 * compression

    x_abs = abs(_clamp(local_x, -1.0, 1.0))
    y_down = (_clamp(local_y, -1.0, 1.0) + 1.0) * 0.5
    y_up = 1.0 - y_down
    if rule.lateral_bias < 0.0 and rule.taper_direction in {"back", "tail"}:
        back_scale *= max(0.45, 1.0 + rule.lateral_bias * x_abs * 0.70)
    elif rule.lateral_bias > 0.0:
        half *= 1.0 + rule.lateral_bias * x_abs * 0.20
    if rule.downward_bias > 0.0:
        back_scale *= 1.0 + rule.downward_bias * y_down * 0.28
    if rule.upward_bias > 0.0:
        back_scale *= 1.0 + rule.upward_bias * y_up * 0.16
    if rule.rear_extension_bias > 0.0:
        back_scale *= 1.0 + rule.rear_extension_bias * (0.20 + 0.40 * edge_norm + 0.10 * y_down)

    edge_fullness = 0.65 + 0.35 * _clamp(edge_norm, 0.0, 1.0)
    front_profile_fullness = _hemisphere_fullness(rule.front_profile, rule.front_taper, edge_norm, x_abs, y_down)
    back_profile_fullness = _hemisphere_fullness(rule.back_profile, rule.back_taper, edge_norm, x_abs, y_down)
    front_extent = max(dz * 0.55, half * max(0.05, front_scale) * edge_fullness * front_profile_fullness)
    back_extent = max(dz * 0.55, half * max(0.05, back_scale) * edge_fullness * back_profile_fullness)
    if rule.suppress_front_projection:
        front_extent = max(dz * 0.55, front_extent * max(0.20, 1.0 - 0.55 * max(0.25, asymmetry)))
    center_shift = span * (rule.forward_bias * 0.10 - rule.backward_bias * 0.18) * max(0.15, asymmetry)
    center_shift -= span * rule.rear_extension_bias * max(0.15, asymmetry) * 0.04
    if rule.trailing_profile == "curved_down_tail":
        center_shift -= span * rule.curvature_bias * y_down * 0.06
        back_extent *= 1.0 + rule.curvature_bias * y_down * 0.18
    center += center_shift

    z_rel = z_axis - center
    inside = ((z_rel >= 0.0) & (z_rel <= front_extent)) | ((z_rel < 0.0) & ((-z_rel) <= back_extent))
    if not bool(np.any(inside)):
        inside[int(np.argmin(np.abs(z_axis - center)))] = True
    return {
        "center": center,
        "front_extent": float(front_extent),
        "back_extent": float(back_extent),
        "center_shift": float(center_shift),
        "inside": inside,
    }


def build_directional_report(
    alpha_mask: np.ndarray,
    labels: np.ndarray,
    rule_map: np.ndarray,
    front_extent_map: np.ndarray,
    back_extent_map: np.ndarray,
    center_shift_map: np.ndarray,
    rules: dict[str, DirectionalMorphologyRule],
    profile_name: str,
) -> dict[str, Any]:
    directional_mask = alpha_mask & (rule_map != "")
    directional_pixels = int(np.count_nonzero(directional_mask))
    alpha_pixels = int(np.count_nonzero(alpha_mask))
    if directional_pixels:
        front = front_extent_map[directional_mask].astype(np.float32)
        back = back_extent_map[directional_mask].astype(np.float32)
        denom = np.maximum(front + back, 1e-6)
        anisotropy = np.abs(back - front) / denom
        rearward = np.maximum(0.0, (back - front) / denom)
        compression = np.maximum(0.0, (back - front) / np.maximum(back, 1e-6))
        symmetric_penalty = float(np.mean(1.0 - anisotropy))
        rearward_score = float(np.mean(rearward))
        compression_score = float(np.mean(compression))
        anisotropy_score = float(np.mean(anisotropy))
    else:
        symmetric_penalty = 1.0
        rearward_score = 0.0
        compression_score = 0.0
        anisotropy_score = 0.0
    semantic_labels = sorted(str(value) for value in set(labels[directional_mask].tolist()) if value)
    profile_types = sorted(str(value) for value in set(rule_map[directional_mask].tolist()) if value)
    hat_mask = alpha_mask & (labels == "hair/hat") & (rule_map == "HAT_POINTED_BACK")
    if bool(np.any(hat_mask)):
        front_hat = float(np.mean(front_extent_map[hat_mask]))
        back_hat = float(np.mean(back_extent_map[hat_mask]))
        hat_ratio = float(back_hat / max(front_hat, 1e-6))
    else:
        front_hat = 0.0
        back_hat = 0.0
        hat_ratio = 0.0
    readability = max(0.0, min(1.0, 0.45 * anisotropy_score + 0.35 * rearward_score + 0.20 * compression_score))
    return {
        "directional_morphology_enabled": True,
        "morphology_profile": profile_name,
        "directional_semantic_count": len(semantic_labels),
        "directional_semantic_labels": semantic_labels,
        "directional_profile_types": profile_types,
        "anisotropic_region_ratio": float(directional_pixels / max(alpha_pixels, 1)),
        "rearward_extension_score": rearward_score,
        "front_compression_score": compression_score,
        "directional_readability_score": readability,
        "symmetric_volume_penalty": symmetric_penalty,
        "mean_center_shift": float(np.mean(center_shift_map[directional_mask])) if directional_pixels else 0.0,
        "hat_pointed_back_present": bool(np.any(hat_mask)),
        "front_hat_extension_score": front_hat,
        "back_hat_extension_score": back_hat,
        "hat_asymmetry_ratio": hat_ratio,
        "rules": {label: asdict(rule) for label, rule in rules.items()},
    }


def write_directional_debug(
    output_dir: Path,
    occupancy: np.ndarray,
    alpha_mask: np.ndarray,
    labels: np.ndarray,
    rule_map: np.ndarray,
    bias_map: np.ndarray,
    front_extent_map: np.ndarray,
    back_extent_map: np.ndarray,
    report: dict[str, Any],
    emit_debug: bool,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "directional_field_map": output_dir / "directional_field_map.png",
        "semantic_axis_debug": output_dir / "semantic_axis_debug.png",
        "morphology_bias_overlay": output_dir / "morphology_bias_overlay.png",
        "directional_occupancy_slices": output_dir / "directional_occupancy_slices.png",
        "hat_direction_debug": output_dir / "hat_direction_debug.png",
        "hat_front_back_profile_debug": output_dir / "hat_front_back_profile_debug.png",
        "hat_asymmetry_debug": output_dir / "hat_asymmetry_debug.json",
        "side_hat_projection_debug": output_dir / "side_hat_projection_debug.png",
        "side_projection_debug": output_dir / "side_projection_debug.png",
        "top_projection_debug": output_dir / "top_projection_debug.png",
        "directional_morphology_report": output_dir / "directional_morphology_report.json",
    }
    _write_signed_heatmap(bias_map, paths["directional_field_map"])
    _write_axis_debug(alpha_mask, paths["semantic_axis_debug"])
    _write_rule_overlay(rule_map, alpha_mask, paths["morphology_bias_overlay"])
    _write_slice_sheet(occupancy, paths["directional_occupancy_slices"])
    _write_hat_debug(labels, alpha_mask, front_extent_map, back_extent_map, paths["hat_direction_debug"])
    _write_hat_profile_debug(labels, alpha_mask, front_extent_map, back_extent_map, paths["hat_front_back_profile_debug"])
    paths["hat_asymmetry_debug"].write_text(json.dumps(_hat_debug_report(report), indent=2) + "\n", encoding="utf-8")
    _write_hat_side_projection(occupancy, labels, alpha_mask, paths["side_hat_projection_debug"])
    _write_projection(occupancy.any(axis=1).T, paths["side_projection_debug"])
    _write_projection(occupancy.any(axis=0).T, paths["top_projection_debug"])
    paths["directional_morphology_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if emit_debug:
        slices_dir = output_dir / "slices"
        slices_dir.mkdir(exist_ok=True)
        for index in range(occupancy.shape[2]):
            _write_projection(occupancy[:, :, index], slices_dir / f"directional_slice_{index:03d}.png")
        paths["slices"] = slices_dir
    return paths


def _compression_amount(profile: str) -> float:
    if profile in {"compressed_front", "flat_back"}:
        return 0.65
    if profile in {"thin_front", "rigid"}:
        return 0.35
    return 0.0


def _hemisphere_fullness(profile: str, taper: float, edge_norm: float, x_abs: float, y_down: float) -> float:
    amount = _clamp(taper, 0.0, 1.0)
    core = _clamp(edge_norm, 0.0, 1.0)
    radial = max(0.0, min(1.0, 0.72 * core + 0.28 * (1.0 - x_abs)))
    if profile == "rounded_compressed":
        profile_fullness = 0.64 + 0.36 * math.sqrt(radial)
    elif profile in {"elongated_taper", "taper_to_point"}:
        profile_fullness = 0.24 + 0.76 * (radial**0.72)
        profile_fullness *= 1.0 + 0.10 * y_down
    elif profile == "rear_shell":
        profile_fullness = 0.42 + 0.58 * math.sqrt(radial)
    else:
        profile_fullness = 1.0
    return max(0.10, (1.0 - amount) + amount * profile_fullness)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _normalise_abs(values: np.ndarray) -> np.ndarray:
    max_abs = float(np.max(np.abs(values))) if values.size else 0.0
    if max_abs <= 1e-6:
        return np.zeros(values.shape, dtype=np.float32)
    return (values / max_abs).astype(np.float32)


def _write_signed_heatmap(values: np.ndarray, path: Path) -> None:
    normalised = _normalise_abs(values)
    image = Image.new("RGBA", (values.shape[1], values.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(np.abs(normalised) > 1e-6):
        value = float(normalised[y, x])
        if value >= 0:
            pixels[int(x), int(y)] = (255, int(120 + 100 * (1.0 - value)), 70, 255)
        else:
            pixels[int(x), int(y)] = (70, int(180 + 50 * (1.0 + value)), 255, 255)
    image.save(path, format="PNG")


def _write_axis_debug(alpha_mask: np.ndarray, path: Path) -> None:
    height, width = alpha_mask.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(alpha_mask):
        pixels[int(x), int(y)] = (55, 70, 85, 170)
    draw = ImageDraw.Draw(image)
    cx = width // 2
    cy = height // 2
    draw.line((cx, cy, width - 2, cy), fill=(255, 210, 85, 255), width=1)
    draw.line((cx, cy, 1, cy), fill=(95, 170, 255, 255), width=1)
    draw.line((cx, cy, cx, 1), fill=(160, 255, 170, 255), width=1)
    draw.line((cx, cy, cx, height - 2), fill=(255, 120, 120, 255), width=1)
    draw.text((max(0, width - 12), max(0, cy - 7)), "F", fill=(255, 230, 110, 255))
    draw.text((1, max(0, cy - 7)), "B", fill=(95, 170, 255, 255))
    draw.text((max(0, cx - 4), 1), "U", fill=(160, 255, 170, 255))
    draw.text((max(0, cx - 4), max(0, height - 10)), "D", fill=(255, 120, 120, 255))
    image.save(path, format="PNG")


def _write_rule_overlay(rule_map: np.ndarray, alpha_mask: np.ndarray, path: Path) -> None:
    palette = {
        "HAT_POINTED_BACK": (120, 80, 255, 255),
        "HAIR_LONG_BACK": (150, 90, 255, 255),
        "NOSE_FORWARD": (255, 190, 90, 255),
        "CAPE_BACK": (255, 60, 100, 255),
        "SHIELD_SIDE": (90, 210, 255, 255),
        "SHOULDER_PAD": (100, 230, 150, 255),
        "TAIL": (255, 145, 65, 255),
    }
    image = Image.new("RGBA", (rule_map.shape[1], rule_map.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(alpha_mask):
        pixels[int(x), int(y)] = palette.get(str(rule_map[y, x]), (70, 70, 70, 140))
    image.save(path, format="PNG")


def _write_hat_debug(
    labels: np.ndarray,
    alpha_mask: np.ndarray,
    front_extent_map: np.ndarray,
    back_extent_map: np.ndarray,
    path: Path,
) -> None:
    image = Image.new("RGBA", (labels.shape[1], labels.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    hat_mask = alpha_mask & (labels == "hair/hat")
    values = back_extent_map - front_extent_map
    max_value = float(np.max(values[hat_mask])) if np.any(hat_mask) else 1.0
    max_value = max(max_value, 1e-6)
    for y, x in np.argwhere(hat_mask):
        t = max(0.0, min(1.0, float(values[y, x]) / max_value))
        pixels[int(x), int(y)] = (int(100 + 120 * t), 70, 255, 255)
    image.save(path, format="PNG")


def _write_hat_profile_debug(
    labels: np.ndarray,
    alpha_mask: np.ndarray,
    front_extent_map: np.ndarray,
    back_extent_map: np.ndarray,
    path: Path,
) -> None:
    hat_mask = alpha_mask & (labels == "hair/hat")
    width = labels.shape[1]
    height = labels.shape[0]
    image = Image.new("RGBA", (width * 2, height), (0, 0, 0, 0))
    _alpha_composite_heatmap(image, front_extent_map, hat_mask, 0, (255, 196, 82))
    _alpha_composite_heatmap(image, back_extent_map, hat_mask, width, (82, 176, 255))
    draw = ImageDraw.Draw(image)
    draw.text((1, 1), "front", fill=(255, 235, 180, 255))
    draw.text((width + 1, 1), "back", fill=(184, 225, 255, 255))
    image.save(path, format="PNG")


def _alpha_composite_heatmap(
    image: Image.Image,
    values: np.ndarray,
    mask: np.ndarray,
    x_offset: int,
    tint: tuple[int, int, int],
) -> None:
    pixels = image.load()
    max_value = float(np.max(values[mask])) if bool(np.any(mask)) else 1.0
    for y, x in np.argwhere(mask):
        value = max(0.0, min(1.0, float(values[y, x]) / max(max_value, 1e-6)))
        pixels[int(x) + x_offset, int(y)] = (
            int(tint[0] * (0.35 + 0.65 * value)),
            int(tint[1] * (0.35 + 0.65 * value)),
            int(tint[2] * (0.35 + 0.65 * value)),
            255,
        )


def _hat_debug_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "hat_pointed_back_present": bool(report.get("hat_pointed_back_present", False)),
        "front_hat_extension_score": float(report.get("front_hat_extension_score", 0.0)),
        "back_hat_extension_score": float(report.get("back_hat_extension_score", 0.0)),
        "hat_asymmetry_ratio": float(report.get("hat_asymmetry_ratio", 0.0)),
        "pass_target": 2.0,
        "passed": not report.get("hat_pointed_back_present", False)
        or float(report.get("hat_asymmetry_ratio", 0.0)) > 2.0,
    }


def _write_hat_side_projection(occupancy: np.ndarray, labels: np.ndarray, alpha_mask: np.ndarray, path: Path) -> None:
    hat_occupancy = occupancy & (alpha_mask & (labels == "hair/hat"))[:, :, None]
    _write_projection(hat_occupancy.any(axis=1).T, path)


def _write_projection(mask: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (90, 230, 175, 255)
    image.save(path, format="PNG")


def _write_slice_sheet(occupancy: np.ndarray, path: Path) -> None:
    frames = []
    step = max(1, math.ceil(occupancy.shape[2] / 8))
    for z in range(0, occupancy.shape[2], step):
        mask = occupancy[:, :, z]
        image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
        pixels = image.load()
        for y, x in np.argwhere(mask):
            pixels[int(x), int(y)] = (90, 180, 255, 255)
        frames.append(image)
    if not frames:
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(path, format="PNG")
        return
    sheet = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame.width, 0))
    sheet.save(path, format="PNG")
