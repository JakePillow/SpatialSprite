from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

Pixel = tuple[int, int]

SEMANTIC_DEPTH_PROFILES: dict[str, tuple[str, float]] = {
    "head": ("cosine", 0.45),
    "face": ("cosine", 0.18),
    "torso": ("cosine", 0.40),
    "left_arm": ("convex", 0.30),
    "right_arm": ("convex", 0.30),
    "left_leg": ("convex", 0.35),
    "right_leg": ("convex", 0.35),
    "boots/feet": ("plateau", 0.18),
    "hair/hat": ("concave", 0.12),
    "outline": ("linear", 0.04),
    "equipment/shield/sword": ("linear", 0.12),
    "unknown": ("linear", 0.16),
}


def build_mylar_front_depth(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    output_dir: Path,
    max_total_depth: float = 0.60,
) -> dict[str, Any]:
    width, height = size
    output_dir.mkdir(parents=True, exist_ok=True)
    regions_dir = output_dir / "z_regions"
    regions_dir.mkdir(parents=True, exist_ok=True)

    alpha_mask = np.zeros((height, width), dtype=bool)
    label_by_pixel: dict[Pixel, str] = {}
    for part in parts:
        label = str(part.get("semantic_label", part.get("name", "unknown")))
        for x, y in part.get("pixels", set()):
            if 0 <= x < width and 0 <= y < height:
                alpha_mask[y, x] = True
                label_by_pixel[(x, y)] = label

    seam_mask = silhouette_seam(alpha_mask)
    body_edt = euclidean_distance_transform(alpha_mask)
    body_norm = _normalise(body_edt)
    z_body = _profile(body_norm, "cosine") * max_total_depth

    z_regions = np.zeros((height, width), dtype=np.float32)
    region_reports = []
    for index, part in enumerate(parts):
        label = str(part.get("semantic_label", part.get("name", "unknown")))
        profile_name, max_depth = SEMANTIC_DEPTH_PROFILES.get(label, SEMANTIC_DEPTH_PROFILES["unknown"])
        mask = _part_mask(size, part.get("pixels", set()))
        edt = euclidean_distance_transform(mask)
        norm = _normalise(edt)
        local_z = (_profile(norm, profile_name) * max_depth).astype(np.float32)
        local_z[~mask] = 0.0
        if label == "outline":
            local_z = np.minimum(local_z, 0.04).astype(np.float32)
        z_regions = np.maximum(z_regions, local_z)
        region_path = regions_dir / f"{index:02d}_{_safe_label(label)}.png"
        _write_heatmap(local_z, region_path)
        values = local_z[mask]
        region_reports.append(
            {
                "index": index,
                "name": part.get("name", label),
                "semantic_label": label,
                "profile": profile_name,
                "max_depth": max_depth,
                "pixel_count": int(mask.sum()),
                "actual_max_depth": float(values.max()) if values.size else 0.0,
                "actual_mean_depth": float(values.mean()) if values.size else 0.0,
                "debug": str(region_path),
            }
        )

    z_front = (0.25 * z_body + 0.75 * z_regions).astype(np.float32)
    z_front[~alpha_mask] = 0.0
    for (x, y), label in label_by_pixel.items():
        if label == "outline":
            z_front[y, x] = min(float(z_front[y, x]), 0.04)
    z_front[seam_mask] = 0.0
    np.clip(z_front, 0.0, max_total_depth, out=z_front)

    z_front_path = output_dir / "z_front.npy"
    z_body_path = output_dir / "z_body.png"
    z_front_png = output_dir / "z_front.png"
    pin_debug = output_dir / "silhouette_pin_debug.png"
    report_path = output_dir / "mylar_depth_report.json"
    np.save(z_front_path, z_front)
    _write_heatmap(z_front, z_front_png)
    _write_heatmap(z_body.astype(np.float32), z_body_path)
    _write_mask(seam_mask, pin_debug, (255, 80, 30, 255))

    report = {
        "schema": "spritespatial_mylar_depth_v1",
        "max_total_depth": max_total_depth,
        "z_min": float(z_front.min()) if z_front.size else 0.0,
        "z_max": float(z_front.max()) if z_front.size else 0.0,
        "silhouette_pin_confirmed": bool(np.all(z_front[seam_mask] == 0.0)),
        "isolated_spike_count": isolated_spike_count(z_front, alpha_mask),
        "opaque_semantic_pixels": int(alpha_mask.sum()),
        "valid_depth_pixels": int(((z_front > 0.0) | seam_mask)[alpha_mask].sum()),
        "outline_full_depth_slab": _outline_full_depth(label_by_pixel, z_front),
        "regions": region_reports,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "z_front": z_front,
        "z_body": z_body.astype(np.float32),
        "alpha_mask": alpha_mask,
        "seam_mask": seam_mask,
        "label_by_pixel": label_by_pixel,
        "report": report,
        "paths": {
            "z_front": z_front_path,
            "z_front_png": z_front_png,
            "z_body": z_body_path,
            "z_regions": regions_dir,
            "silhouette_pin_debug": pin_debug,
            "mylar_depth_report": report_path,
        },
    }


def euclidean_distance_transform(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    distances = np.zeros(mask.shape, dtype=np.float32)
    if not mask.any():
        return distances
    outside = np.argwhere(~mask)
    if outside.size == 0:
        outside = np.array([[0, 0]], dtype=np.int32)
    for y, x in np.argwhere(mask):
        delta = outside - np.array([y, x])
        distances[y, x] = float(np.sqrt((delta * delta).sum(axis=1).min()))
    return distances


def silhouette_seam(alpha_mask: np.ndarray) -> np.ndarray:
    height, width = alpha_mask.shape
    seam = np.zeros_like(alpha_mask, dtype=bool)
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height or not alpha_mask[ny, nx]:
                    seam[y, x] = True
                    break
    return seam


def isolated_spike_count(z_field: np.ndarray, mask: np.ndarray) -> int:
    spikes = 0
    ys, xs = np.where(mask & (z_field > 0))
    for y, x in zip(ys, xs):
        y0, y1 = max(0, y - 1), min(z_field.shape[0], y + 2)
        x0, x1 = max(0, x - 1), min(z_field.shape[1], x + 2)
        local = z_field[y0:y1, x0:x1]
        if local.size <= 1:
            continue
        mean = float(local.mean())
        std = float(local.std())
        if std > 1e-6 and z_field[y, x] > mean + 3.0 * std:
            spikes += 1
    return spikes


def _normalise(values: np.ndarray) -> np.ndarray:
    max_value = float(values.max()) if values.size else 0.0
    if max_value <= 1e-6:
        return np.zeros(values.shape, dtype=np.float32)
    return (values / max_value).astype(np.float32)


def _profile(values: np.ndarray, profile: str) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    if profile == "linear":
        return clipped
    if profile == "convex":
        return clipped ** 0.65
    if profile == "concave":
        return clipped ** 1.8
    if profile == "cosine":
        return 0.5 - 0.5 * np.cos(np.pi * clipped)
    if profile == "plateau":
        return np.minimum(1.0, clipped * 1.8)
    return clipped


def _part_mask(size: tuple[int, int], pixels: set[Pixel]) -> np.ndarray:
    width, height = size
    mask = np.zeros((height, width), dtype=bool)
    for x, y in pixels:
        if 0 <= x < width and 0 <= y < height:
            mask[y, x] = True
    return mask


def _write_heatmap(values: np.ndarray, path: Path) -> None:
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
            pixels[x, y] = (shade, int(shade * 0.55), 255 - shade, 255)
    image.save(path, format="PNG")


def _write_mask(mask: np.ndarray, path: Path, colour: tuple[int, int, int, int]) -> None:
    height, width = mask.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, x in np.argwhere(mask):
        draw.point((int(x), int(y)), fill=colour)
    image.save(path, format="PNG")


def _outline_full_depth(label_by_pixel: dict[Pixel, str], z_front: np.ndarray) -> bool:
    values = [float(z_front[y, x]) for (x, y), label in label_by_pixel.items() if label == "outline"]
    return bool(values and max(values) > 0.08)


def _safe_label(label: str) -> str:
    return label.replace("/", "_").replace(" ", "_")
