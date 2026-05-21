from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from spritespatial.canonical_views import back_view_authority, canonical_view_records, side_profile_authority
from spritespatial.render_diagnostics import save_mask, silhouette_mask


VIEW_TO_CAPTURE = {
    "front": "front.png",
    "oblique": "oblique.png",
    "side": "side.png",
    "side_135": "side_135.png",
    "back": "back.png",
}


def compute_canonical_view_metrics(
    captures_dir: Path,
    output_dir: Path,
    front_sprite_path: Path,
    back_sprite_path: Path | None = None,
    side_sprite_path: Path | None = None,
    source_coverage: dict[str, Any] | None = None,
    render_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "silhouette_masks"
    masks_dir.mkdir(parents=True, exist_ok=True)
    source_coverage = source_coverage or {}
    records = canonical_view_records(source_coverage)
    front_alpha = _load_alpha_mask(front_sprite_path)
    back_alpha = _load_alpha_mask(back_sprite_path) if back_sprite_path and back_sprite_path.exists() else front_alpha
    side_alpha = _load_alpha_mask(side_sprite_path) if side_sprite_path and side_sprite_path.exists() else _primitive_side_profile(front_alpha)
    view_metrics: dict[str, Any] = {}
    iou_by_view: dict[str, float] = {}
    for record in records:
        view = str(record["view"])
        capture_path = captures_dir / VIEW_TO_CAPTURE[view]
        if not capture_path.exists():
            view_metrics[view] = {"missing_capture": True, "canonical_view": record}
            iou_by_view[view] = 0.0
            continue
        image = Image.open(capture_path).convert("RGBA")
        rendered = silhouette_mask(image)
        target_source = _target_source_for_view(view, front_alpha, side_alpha, back_alpha)
        target = _place_target(target_source, rendered.shape, _target_bbox_for_view(view, rendered))
        overlay_path = output_dir / f"silhouette_overlay_{int(record['yaw'])}.png"
        target_path = masks_dir / f"target_{view}.png"
        rendered_path = masks_dir / f"rendered_{view}.png"
        save_mask(target, target_path)
        save_mask(rendered, rendered_path)
        _write_overlay(rendered, target, overlay_path)
        metrics = _mask_metrics(rendered, target)
        metrics.update(
            {
                "canonical_view": record,
                "capture": str(capture_path),
                "rendered_mask": str(rendered_path),
                "target_mask": str(target_path),
                "overlay": str(overlay_path),
            }
        )
        view_metrics[view] = metrics
        iou_by_view[view] = float(metrics["silhouette_iou"])
    front_back_warning = False
    side_front_warning = False
    if render_diagnostics:
        front_back_warning = bool(render_diagnostics.get("front_back_visual_similarity_warning", False))
        side_front_warning = bool(render_diagnostics.get("side_front_visual_similarity_warning", False))
    worst_view = min(iou_by_view, key=lambda item: iou_by_view[item]) if iou_by_view else ""
    report = {
        "schema": "spritespatial_canonical_view_metrics_v1",
        "canonical_views": records,
        "view_metrics": view_metrics,
        "front_iou": iou_by_view.get("front", 0.0),
        "oblique_iou": iou_by_view.get("oblique", 0.0),
        "side_iou": iou_by_view.get("side", 0.0),
        "side_135_iou": iou_by_view.get("side_135", 0.0),
        "back_iou": iou_by_view.get("back", 0.0),
        "worst_view": worst_view,
        "front_back_similarity_warning": front_back_warning,
        "side_front_visual_similarity_warning": side_front_warning,
        "side_profile_authority": side_profile_authority(source_coverage),
        "back_view_authority": back_view_authority(source_coverage),
    }
    (output_dir / "canonical_view_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _load_alpha_mask(path: Path | None) -> np.ndarray:
    if path is None or not path.exists():
        return np.zeros((1, 1), dtype=bool)
    return np.asarray(Image.open(path).convert("RGBA").getchannel("A")) > 16


def _target_source_for_view(view: str, front: np.ndarray, side: np.ndarray, back: np.ndarray) -> np.ndarray:
    if view == "front":
        return front
    if view == "back":
        return back
    if view in {"side", "oblique", "side_135"}:
        return side
    return front


def _primitive_side_profile(front: np.ndarray) -> np.ndarray:
    if not front.any():
        return front
    x0, y0, x1, y1 = _bounds(front)
    height = max(y1 - y0, 1)
    width = max(3, int((x1 - x0) * 0.42))
    mask = np.zeros((height, width), dtype=bool)
    yy, xx = np.ogrid[:height, :width]
    body = ((yy - height * 0.52) / max(height * 0.48, 1.0)) ** 2 + ((xx - width * 0.55) / max(width * 0.55, 1.0)) ** 2 <= 1.0
    head = ((yy - height * 0.19) / max(height * 0.20, 1.0)) ** 2 + ((xx - width * 0.55) / max(width * 0.48, 1.0)) ** 2 <= 1.0
    mask[body | head] = True
    return mask


def _target_bbox_for_view(view: str, rendered: np.ndarray) -> list[int]:
    x0, y0, x1, y1 = _bounds(rendered)
    if x1 <= x0 or y1 <= y0:
        return [0, 0, rendered.shape[1], rendered.shape[0]]
    height = y1 - y0
    width = x1 - x0
    if view in {"side", "oblique", "side_135"}:
        target_width = max(1, int(width * 0.58))
        cx = (x0 + x1) // 2
        return [cx - target_width // 2, y0, cx + (target_width + 1) // 2, y1]
    return [x0, y0, x1, y1]


def _place_target(source: np.ndarray, shape: tuple[int, int], bbox: list[int]) -> np.ndarray:
    canvas = np.zeros(shape, dtype=bool)
    x0, y0, x1, y1 = [int(value) for value in bbox]
    x0 = max(0, min(shape[1] - 1, x0))
    x1 = max(x0 + 1, min(shape[1], x1))
    y0 = max(0, min(shape[0] - 1, y0))
    y1 = max(y0 + 1, min(shape[0], y1))
    image = Image.fromarray(np.where(source, 255, 0).astype(np.uint8), mode="L")
    image = image.resize((max(1, x1 - x0), max(1, y1 - y0)), Image.Resampling.NEAREST)
    canvas[y0:y1, x0:x1] = np.asarray(image) > 0
    return canvas


def _mask_metrics(rendered: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    intersection = int(np.count_nonzero(rendered & target))
    union = int(np.count_nonzero(rendered | target))
    rendered_count = int(np.count_nonzero(rendered))
    target_count = int(np.count_nonzero(target))
    return {
        "silhouette_iou": float(intersection) / float(union or 1),
        "silhouette_precision": float(intersection) / float(rendered_count or 1),
        "silhouette_recall": float(intersection) / float(target_count or 1),
        "bounding_box_drift": _bbox_drift(rendered, target),
        "centre_of_mass_drift": _center_drift(rendered, target),
        "rendered_pixel_count": rendered_count,
        "target_pixel_count": target_count,
    }


def _bbox_drift(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    ab = _bounds(a)
    bb = _bounds(b)
    return {
        "x": float(abs(ab[0] - bb[0]) + abs(ab[2] - bb[2])) * 0.5,
        "y": float(abs(ab[1] - bb[1]) + abs(ab[3] - bb[3])) * 0.5,
        "width": float(abs((ab[2] - ab[0]) - (bb[2] - bb[0]))),
        "height": float(abs((ab[3] - ab[1]) - (bb[3] - bb[1]))),
    }


def _center_drift(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    ac = _center(a)
    bc = _center(b)
    return {"x": abs(ac[0] - bc[0]), "y": abs(ac[1] - bc[1])}


def _center(mask: np.ndarray) -> tuple[float, float]:
    points = np.argwhere(mask)
    if points.size == 0:
        return (0.0, 0.0)
    y, x = points.mean(axis=0)
    return (float(x), float(y))


def _bounds(mask: np.ndarray) -> list[int]:
    points = np.argwhere(mask)
    if points.size == 0:
        return [0, 0, 0, 0]
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return [int(x0), int(y0), int(x1), int(y1)]


def _write_overlay(rendered: np.ndarray, target: np.ndarray, path: Path) -> None:
    h, w = rendered.shape
    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[:, :, :3] = 52
    overlay[:, :, 3] = 255
    overlay[target] = [30, 160, 255, 255]
    overlay[rendered] = [255, 70, 60, 255]
    overlay[rendered & target] = [80, 230, 120, 255]
    Image.fromarray(overlay, mode="RGBA").save(path, format="PNG")
