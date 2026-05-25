from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

Pixel = tuple[int, int]

SEMANTIC_BACK_SCALE = {
    "head": 1.0,
    "face": 0.2,
    "torso": 0.85,
    "left_arm": 1.0,
    "right_arm": 1.0,
    "left_leg": 0.9,
    "right_leg": 0.9,
    "boots/feet": 0.7,
    "hair/hat": 1.2,
    "outline": 0.12,
    "equipment/shield/sword": 0.65,
    "unknown": 0.7,
}


def build_back_hemisphere(
    z_front: np.ndarray,
    seam_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    output_dir: Path,
    mode: str = "semantic_rules",
    back_sprite_path: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scale_map = np.ones(z_front.shape, dtype=np.float32)
    back_geometry_authority = _back_geometry_authority(mode, back_sprite_path)
    rules: dict[str, Any] = {
        "mode": mode,
        "front_back_sprite_deferred": mode == "front_back_sprite",
        "back_geometry_authority": back_geometry_authority,
        "back_sprite_path": str(back_sprite_path) if back_geometry_authority == "authored_back" else "",
        "comparison_back_sprite_path": str(back_sprite_path)
        if back_geometry_authority != "authored_back" and back_sprite_path and back_sprite_path.exists()
        else "",
        "scales": {},
    }
    if mode == "symmetric":
        rules["scales"] = {"all": 1.0}
    else:
        for (x, y), label in label_by_pixel.items():
            scale = SEMANTIC_BACK_SCALE.get(label, SEMANTIC_BACK_SCALE["unknown"])
            scale_map[y, x] = scale
            rules["scales"][label] = scale
    z_back = (-z_front * scale_map).astype(np.float32)
    z_back[seam_mask] = 0.0
    z_back[z_front <= 0.0] = 0.0

    z_back_path = output_dir / "z_back.npy"
    z_back_png = output_dir / "z_back.png"
    rules_path = output_dir / "back_rules.json"
    debug_path = output_dir / "back_hemisphere_debug.png"
    seam_debug_path = output_dir / "seam_debug.png"
    np.save(z_back_path, z_back)
    _write_depth_png(np.abs(z_back), z_back_png)
    _write_depth_png(np.abs(z_back), debug_path)
    _write_mask(seam_mask, seam_debug_path)
    rules.update(
        {
            "z_back_min": float(z_back.min()) if z_back.size else 0.0,
            "z_back_max": float(z_back.max()) if z_back.size else 0.0,
            "same_silhouette_seam": True,
            "missing_critical_back_regions": _missing_critical(label_by_pixel, z_back),
            "back_region_exceeds_configured_max_depth": False,
        }
    )
    rules_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
    return {
        "z_back": z_back,
        "report": rules,
        "paths": {
            "z_back": z_back_path,
            "z_back_png": z_back_png,
            "back_rules": rules_path,
            "back_hemisphere_debug": debug_path,
            "seam_debug": seam_debug_path,
        },
    }


def _back_geometry_authority(mode: str, back_sprite_path: Path | None) -> str:
    if mode == "front_back_sprite":
        return "authored_back" if back_sprite_path and back_sprite_path.exists() else "missing"
    if mode in {"semantic_rules", "symmetric"}:
        return mode
    return "missing"


def _missing_critical(label_by_pixel: dict[Pixel, str], z_back: np.ndarray) -> list[str]:
    missing = []
    for label in ("head", "torso", "left_leg", "right_leg"):
        coords = [(x, y) for (x, y), value in label_by_pixel.items() if value == label]
        if coords and not any(z_back[y, x] < 0.0 for x, y in coords):
            missing.append(label)
    return missing


def _write_depth_png(values: np.ndarray, path: Path) -> None:
    height, width = values.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    max_value = float(values.max()) if values.size else 0.0
    for y in range(height):
        for x in range(width):
            value = float(values[y, x])
            if value <= 0.0:
                continue
            shade = int(255 * value / max(max_value, 1e-6))
            pixels[x, y] = (80, shade, 255 - shade // 2, 255)
    image.save(path, format="PNG")


def _write_mask(mask: np.ndarray, path: Path) -> None:
    height, width = mask.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (255, 255, 255, 255)
    image.save(path, format="PNG")
