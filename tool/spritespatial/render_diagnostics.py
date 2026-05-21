from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


VIEW_FILES = {
    "front": "front.png",
    "oblique": "oblique.png",
    "side": "side.png",
    "side_135": "side_135.png",
    "back": "back.png",
    "wireframe": "wireframe.png",
}


def analyze_phase5c_captures(captures_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "silhouette_masks"
    masks_dir.mkdir(parents=True, exist_ok=True)
    views: dict[str, Any] = {}
    masks: dict[str, np.ndarray] = {}
    for view, file_name in VIEW_FILES.items():
        path = captures_dir / file_name
        if not path.exists():
            views[view] = {"missing": True, "path": str(path)}
            continue
        image = Image.open(path).convert("RGBA")
        mask = silhouette_mask(image)
        masks[view] = mask
        mask_path = masks_dir / f"{view}_mask.png"
        save_mask(mask, mask_path)
        views[view] = {
            "path": str(path),
            "silhouette_mask": str(mask_path),
            "visible_pixel_bounds": _bounds(mask),
            "visible_pixel_count": int(mask.sum()),
            "black_outline_pixel_ratio": _black_ratio(image, mask),
            "semantic_colour_coverage": _semantic_colour_coverage(image, mask),
            "empty_background_ratio": 1.0 - (float(mask.sum()) / float(mask.size or 1)),
            "fragmentation_count": _component_count(mask),
            "bounding_box_aspect_ratio": _aspect(mask),
        }
    front_back_similarity = _aligned_iou(masks.get("front"), masks.get("back"))
    side_front_similarity = _aligned_iou(masks.get("side"), masks.get("front"))
    report = {
        "schema": "spritespatial_render_diagnostics_v1",
        "captures_dir": str(captures_dir),
        "views": views,
        "front_back_aligned_iou": front_back_similarity,
        "side_front_aligned_iou": side_front_similarity,
        "front_back_visual_similarity_warning": front_back_similarity >= 0.72,
        "side_front_visual_similarity_warning": side_front_similarity >= 0.62,
    }
    (output_dir / "render_diagnostics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def silhouette_mask(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.int16)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    background = _background_rgb(rgb)
    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    saturated = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    dark_outline = np.max(rgb, axis=2) < 34
    return (alpha > 16) & ((distance > 24) | (saturated > 35) | dark_outline)


def save_mask(mask: np.ndarray, path: Path) -> None:
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    image.save(path, format="PNG")


def _background_rgb(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    samples = np.concatenate(
        [
            rgb[: max(1, height // 12), :, :].reshape(-1, 3),
            rgb[-max(1, height // 12) :, :, :].reshape(-1, 3),
            rgb[:, : max(1, width // 12), :].reshape(-1, 3),
            rgb[:, -max(1, width // 12) :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(samples, axis=0)


def _bounds(mask: np.ndarray) -> list[int]:
    points = np.argwhere(mask)
    if points.size == 0:
        return [0, 0, 0, 0]
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return [int(x0), int(y0), int(x1), int(y1)]


def _aspect(mask: np.ndarray) -> float:
    x0, y0, x1, y1 = _bounds(mask)
    return float(x1 - x0) / max(float(y1 - y0), 1.0)


def _black_ratio(image: Image.Image, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    rgb = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, :3]
    black = np.max(rgb, axis=2) < 42
    return float(np.count_nonzero(black & mask)) / float(np.count_nonzero(mask))


def _semantic_colour_coverage(image: Image.Image, mask: np.ndarray) -> dict[str, Any]:
    if not mask.any():
        return {"ratio": 0.0, "approximate_colour_buckets": 0}
    rgb = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, :3]
    visible = rgb[mask]
    non_black = np.max(visible, axis=1) >= 42
    saturated = (np.max(visible, axis=1) - np.min(visible, axis=1)) >= 25
    semantic = non_black & saturated
    buckets = {tuple((value // 32).tolist()) for value in visible[semantic]}
    return {
        "ratio": float(np.count_nonzero(semantic)) / float(len(visible)),
        "approximate_colour_buckets": len(buckets),
    }


def _component_count(mask: np.ndarray, min_area: int = 20) -> int:
    remaining = {tuple(int(v) for v in point) for point in np.argwhere(mask)}
    count = 0
    while remaining:
        start = remaining.pop()
        area = 1
        queue = deque([start])
        while queue:
            y, x = queue.popleft()
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if (ny, nx) in remaining:
                        remaining.remove((ny, nx))
                        queue.append((ny, nx))
                        area += 1
        if area >= min_area:
            count += 1
    return count


def _aligned_iou(a: np.ndarray | None, b: np.ndarray | None, size: int = 128) -> float:
    if a is None or b is None or not a.any() or not b.any():
        return 0.0
    aa = _normalised_mask(a, size)
    bb = _normalised_mask(b, size)
    intersection = np.count_nonzero(aa & bb)
    union = np.count_nonzero(aa | bb)
    return float(intersection) / float(union or 1)


def _normalised_mask(mask: np.ndarray, size: int) -> np.ndarray:
    x0, y0, x1, y1 = _bounds(mask)
    crop = mask[y0:y1, x0:x1]
    if crop.size == 0:
        return np.zeros((size, size), dtype=bool)
    image = Image.fromarray(np.where(crop, 255, 0).astype(np.uint8), mode="L")
    image.thumbnail((size - 8, size - 8), Image.Resampling.NEAREST)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    return np.asarray(canvas) > 0
