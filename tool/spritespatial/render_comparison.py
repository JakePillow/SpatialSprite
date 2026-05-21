from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.canonical_views import back_view_authority, side_profile_authority
from spritespatial.metrics.silhouette_iou import _primitive_side_profile
from spritespatial.render_diagnostics import save_mask, silhouette_mask


VIEW_SPECS = [
    ("0", "front", 0),
    ("45", "oblique", 45),
    ("90", "side", 90),
    ("135", "side_135", 135),
    ("180", "back", 180),
]

CAPTURE_FILE_BY_VIEW = {
    "front": "front.png",
    "oblique": "oblique.png",
    "side": "side.png",
    "side_135": "side_135.png",
    "back": "back.png",
}

SEMANTIC_COLOURS = {
    "outline": (8, 8, 8),
    "head": (235, 87, 66),
    "face": (255, 189, 107),
    "hat_hair": (89, 46, 184),
    "torso": (46, 138, 230),
    "left_arm": (56, 184, 117),
    "right_arm": (66, 163, 107),
    "left_leg": (189, 133, 51),
    "right_leg": (133, 179, 51),
    "boots_feet": (107, 61, 31),
    "equipment": (235, 209, 51),
    "unknown": (163, 163, 163),
}


def build_visual_mapping(
    captures_dir: Path,
    output_dir: Path,
    front_sprite: Path,
    back_sprite: Path | None,
    side_sprite: Path | None,
    semantic_override_dir: Path | None,
    source_coverage: dict[str, Any] | None = None,
    canonical_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_coverage = source_coverage or {}
    canonical_metrics = canonical_metrics or {}
    semantic_masks = _load_semantic_masks(semantic_override_dir)
    front = Image.open(front_sprite).convert("RGBA")
    back = Image.open(back_sprite).convert("RGBA") if back_sprite and back_sprite.exists() else front
    side = _side_target_sprite(side_sprite, front, source_coverage)
    metrics_by_view: dict[str, Any] = {}
    compare_paths: list[Path] = []
    for suffix, view, angle in VIEW_SPECS:
        capture_path = captures_dir / CAPTURE_FILE_BY_VIEW[view]
        target, authority = _target_for_view(view, front, back, side, source_coverage)
        compare_path = output_dir / f"compare_{suffix}.png"
        view_metrics = _build_compare_image(
            capture_path,
            target,
            authority,
            angle,
            view,
            semantic_masks,
            compare_path,
            canonical_metrics,
        )
        metrics_by_view[view] = view_metrics
        compare_paths.append(compare_path)
    contact_sheet = output_dir / "comparison_contact_sheet.png"
    _write_contact_sheet(compare_paths, contact_sheet)
    worst_view = min(metrics_by_view, key=lambda key: float(metrics_by_view[key]["silhouette_iou"]))
    report = {
        "schema": "spritespatial_visual_mapping_report_v1",
        "captures_dir": str(captures_dir),
        "comparison_contact_sheet": str(contact_sheet),
        "views": metrics_by_view,
        "front_visual_mapping_iou": metrics_by_view["front"]["silhouette_iou"],
        "worst_visual_mapping_view": worst_view,
        "worst_visual_mapping_score": metrics_by_view[worst_view]["silhouette_iou"],
        "front_back_similarity_warning": bool(canonical_metrics.get("front_back_similarity_warning", False)),
        "side_front_similarity_warning": bool(
            canonical_metrics.get("side_front_visual_similarity_warning", canonical_metrics.get("side_front_similarity_warning", False))
        ),
    }
    (output_dir / "visual_mapping_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _build_compare_image(
    capture_path: Path,
    target: Image.Image,
    authority: str,
    angle: int,
    view: str,
    semantic_masks: dict[str, np.ndarray],
    output_path: Path,
    canonical_metrics: dict[str, Any],
) -> dict[str, Any]:
    if not capture_path.exists():
        raise FileNotFoundError(f"Missing render capture: {capture_path}")
    capture = Image.open(capture_path).convert("RGBA")
    render_mask = silhouette_mask(capture)
    target_mask_source = np.asarray(target.getchannel("A")) > 16
    flattened, flattened_mask, transform = _flatten_render_to_target(capture, render_mask, target.size)
    target_mask = np.asarray(target.getchannel("A")) > 16
    overlap = flattened_mask & target_mask
    overfill = flattened_mask & ~target_mask
    underfill = target_mask & ~flattened_mask
    silhouette_overlay = _silhouette_overlay(overlap, overfill, underfill)
    semantic_overlay, semantic_report = _semantic_overlay(flattened, flattened_mask, semantic_masks, target.size)
    error_map = _error_map(overfill, underfill)
    panel_size = (160, 192)
    panels = [
        _panel(target, "A target / " + authority, panel_size),
        _panel(flattened, "B flattened 3D", panel_size),
        _panel(silhouette_overlay, "C silhouette", panel_size),
        _panel(semantic_overlay, "D semantics", panel_size),
        _panel(error_map, "E error map", panel_size),
    ]
    sheet = Image.new("RGBA", (panel_size[0] * len(panels), panel_size[1] + 28), (38, 38, 38, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 6), f"view {angle} deg - {view}", fill=(245, 245, 245, 255))
    for index, panel in enumerate(panels):
        sheet.alpha_composite(panel, (index * panel_size[0], 28))
    sheet.save(output_path, format="PNG")
    metrics = _mapping_metrics(flattened_mask, target_mask)
    worst_region = max(
        semantic_report.get("regions", {}).items(),
        key=lambda item: 1.0 - float(item[1].get("semantic_match_ratio", 0.0)),
        default=("", {}),
    )[0]
    canonical_summary = canonical_metrics.get("view_metrics", {}).get(view, {})
    metrics.update(
        {
            "view_angle": angle,
            "view": view,
            "target_authority": authority,
            "semantic_match_ratio": semantic_report.get("overall_semantic_match_ratio", 0.0),
            "worst_semantic_region": worst_region,
            "semantic_regions": semantic_report.get("regions", {}),
            "front_back_similarity_warning": bool(canonical_metrics.get("front_back_similarity_warning", False)),
            "side_front_similarity_warning": bool(
                canonical_metrics.get("side_front_visual_similarity_warning", canonical_metrics.get("side_front_similarity_warning", False))
            ),
            "recommended_next_action": _recommended_action(view, authority, metrics["silhouette_iou"]),
            "compare_image": str(output_path),
            "normalisation": transform,
            "canonical_metric_reference": {
                "silhouette_iou": canonical_summary.get("silhouette_iou"),
                "target_type": canonical_summary.get("canonical_view", {}).get("target_type"),
            },
        }
    )
    return metrics


def _flatten_render_to_target(
    capture: Image.Image,
    mask: np.ndarray,
    target_size: tuple[int, int],
) -> tuple[Image.Image, np.ndarray, dict[str, Any]]:
    bounds = _bounds(mask)
    x0, y0, x1, y1 = bounds
    if x1 <= x0 or y1 <= y0:
        return Image.new("RGBA", target_size, (0, 0, 0, 0)), np.zeros((target_size[1], target_size[0]), dtype=bool), {
            "scale": 0.0,
            "offset": [0, 0],
            "source_bounds": bounds,
        }
    crop = capture.crop((x0, y0, x1, y1)).convert("RGBA")
    crop_mask = Image.fromarray(np.where(mask[y0:y1, x0:x1], 255, 0).astype(np.uint8), mode="L")
    crop.putalpha(crop_mask)
    scale = min(target_size[0] / max(crop.width, 1), target_size[1] / max(crop.height, 1))
    new_size = (max(1, int(crop.width * scale)), max(1, int(crop.height * scale)))
    resized = crop.resize(new_size, Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    offset = ((target_size[0] - resized.width) // 2, (target_size[1] - resized.height) // 2)
    canvas.alpha_composite(resized, offset)
    return canvas, np.asarray(canvas.getchannel("A")) > 16, {
        "scale": float(scale),
        "offset": [int(offset[0]), int(offset[1])],
        "source_bounds": bounds,
    }


def _mapping_metrics(render_mask: np.ndarray, target_mask: np.ndarray) -> dict[str, Any]:
    overlap = int(np.count_nonzero(render_mask & target_mask))
    rendered_count = int(np.count_nonzero(render_mask))
    target_count = int(np.count_nonzero(target_mask))
    union = int(np.count_nonzero(render_mask | target_mask))
    overfill = int(np.count_nonzero(render_mask & ~target_mask))
    underfill = int(np.count_nonzero(target_mask & ~render_mask))
    return {
        "silhouette_iou": float(overlap) / float(union or 1),
        "overfill_ratio": float(overfill) / float(rendered_count or 1),
        "underfill_ratio": float(underfill) / float(target_count or 1),
        "bounding_box_drift": _bbox_drift(render_mask, target_mask),
        "centre_drift": _centre_drift(render_mask, target_mask),
    }


def _load_semantic_masks(path: Path | None) -> dict[str, np.ndarray]:
    if path is None or not path.exists():
        return {}
    masks = {}
    for file_path in sorted(path.glob("*.png")):
        masks[file_path.stem] = np.asarray(Image.open(file_path).convert("RGBA").getchannel("A")) > 16
    return masks


def _semantic_overlay(
    flattened: Image.Image,
    flattened_mask: np.ndarray,
    semantic_masks: dict[str, np.ndarray],
    target_size: tuple[int, int],
) -> tuple[Image.Image, dict[str, Any]]:
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
    pixels = overlay.load()
    source = np.asarray(flattened.convert("RGBA"))[:, :, :3]
    regions: dict[str, Any] = {}
    total_visible = 0
    total_match = 0
    for name, mask in semantic_masks.items():
        resized = _resize_mask(mask, target_size)
        color = np.array(SEMANTIC_COLOURS.get(name, SEMANTIC_COLOURS["unknown"]), dtype=np.int16)
        visible = flattened_mask & resized
        missing = resized & ~flattened_mask
        overflow = flattened_mask & ~resized
        if resized.any():
            distance = np.sqrt(np.sum((source.astype(np.float32) - color.astype(np.float32)) ** 2, axis=2))
            match = visible & (distance < 95)
            visible_area = int(np.count_nonzero(visible))
            match_area = int(np.count_nonzero(match))
            total_visible += visible_area
            total_match += match_area
            regions[name] = {
                "visible_area": visible_area,
                "missing_area": int(np.count_nonzero(missing)),
                "overflow_area": int(np.count_nonzero(overflow)),
                "semantic_match_ratio": float(match_area) / float(visible_area or 1),
                "colour_confusion_ratio": 1.0 - (float(match_area) / float(visible_area or 1)),
            }
            for y, x in np.argwhere(missing):
                pixels[int(x), int(y)] = (40, 90, 255, 190)
            for y, x in np.argwhere(match):
                pixels[int(x), int(y)] = (255, 220, 30, 210)
    return overlay, {
        "overall_semantic_match_ratio": float(total_match) / float(total_visible or 1),
        "regions": regions,
    }


def _resize_mask(mask: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    return np.asarray(image.resize(target_size, Image.Resampling.NEAREST)) > 0


def _silhouette_overlay(overlap: np.ndarray, overfill: np.ndarray, underfill: np.ndarray) -> Image.Image:
    h, w = overlap.shape
    data = np.zeros((h, w, 4), dtype=np.uint8)
    data[:, :, 3] = 0
    data[overlap] = [40, 220, 95, 255]
    data[overfill] = [255, 65, 55, 255]
    data[underfill] = [50, 120, 255, 255]
    return Image.fromarray(data, mode="RGBA")


def _error_map(overfill: np.ndarray, underfill: np.ndarray) -> Image.Image:
    h, w = overfill.shape
    data = np.zeros((h, w, 4), dtype=np.uint8)
    data[:, :, :3] = 255
    data[:, :, 3] = 255
    data[overfill] = [255, 65, 55, 255]
    data[underfill] = [50, 120, 255, 255]
    return Image.fromarray(data, mode="RGBA")


def _panel(image: Image.Image, title: str, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (24, 24, 24, 255))
    draw = ImageDraw.Draw(panel)
    draw.text((4, 4), title[:28], fill=(245, 245, 245, 255))
    content = image.convert("RGBA")
    content.thumbnail((size[0] - 12, size[1] - 28), Image.Resampling.NEAREST)
    panel.alpha_composite(content, ((size[0] - content.width) // 2, 24 + (size[1] - 28 - content.height) // 2))
    return panel


def _write_contact_sheet(paths: list[Path], output_path: Path) -> None:
    images = [Image.open(path).convert("RGBA") for path in paths if path.exists()]
    if not images:
        Image.new("RGBA", (1, 1), (0, 0, 0, 255)).save(output_path)
        return
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    sheet = Image.new("RGBA", (width, height * len(images)), (34, 34, 34, 255))
    for index, image in enumerate(images):
        sheet.alpha_composite(image, (0, index * height))
    sheet.save(output_path, format="PNG")


def _target_for_view(
    view: str,
    front: Image.Image,
    back: Image.Image,
    side: Image.Image,
    source_coverage: dict[str, Any],
) -> tuple[Image.Image, str]:
    if view == "front":
        return front, "authored_front"
    if view == "back":
        authority = "authored_back" if back_view_authority(source_coverage) == "authored" else "inferred_back"
        return back, authority
    if view in {"side", "side_135"}:
        authority = "authored_side" if side_profile_authority(source_coverage) == "authored" else "primitive_prior"
        return side, authority
    return _blend_target(front, side), "inferred_oblique"


def _side_target_sprite(side_sprite: Path | None, front: Image.Image, source_coverage: dict[str, Any]) -> Image.Image:
    if side_sprite and side_sprite.exists() and side_profile_authority(source_coverage) == "authored":
        return Image.open(side_sprite).convert("RGBA")
    primitive = _primitive_side_profile(np.asarray(front.getchannel("A")) > 16)
    canvas = Image.new("RGBA", front.size, (0, 0, 0, 0))
    mask_image = Image.fromarray(np.where(primitive, 255, 0).astype(np.uint8), mode="L")
    mask_image = mask_image.resize((max(1, int(front.width * 0.48)), front.height), Image.Resampling.NEAREST)
    sprite = Image.new("RGBA", mask_image.size, (255, 255, 255, 255))
    sprite.putalpha(mask_image)
    canvas.alpha_composite(sprite, ((front.width - sprite.width) // 2, 0))
    return canvas


def _blend_target(front: Image.Image, side: Image.Image) -> Image.Image:
    front_mask = np.asarray(front.getchannel("A")) > 16
    side_mask = np.asarray(side.getchannel("A")) > 16
    combined = front_mask | side_mask
    image = Image.new("RGBA", front.size, (255, 255, 255, 0))
    image.putalpha(Image.fromarray(np.where(combined, 220, 0).astype(np.uint8), mode="L"))
    return image


def _recommended_action(view: str, authority: str, iou: float) -> str:
    if iou >= 0.65:
        return "keep as diagnostic baseline"
    if view in {"side", "side_135"} and authority != "authored_side":
        return "provide or promote authored side view before Phase 6 correction"
    if view == "back" and authority != "authored_back":
        return "provide authored back view or keep inferred-back limitation explicit"
    return "use this view as a Phase 6 silhouette correction target"


def _bounds(mask: np.ndarray) -> list[int]:
    points = np.argwhere(mask)
    if points.size == 0:
        return [0, 0, 0, 0]
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return [int(x0), int(y0), int(x1), int(y1)]


def _bbox_drift(a: np.ndarray, b: np.ndarray) -> list[float]:
    ab = _bounds(a)
    bb = _bounds(b)
    return [
        float(abs(ab[0] - bb[0]) + abs(ab[2] - bb[2])) * 0.5,
        float(abs(ab[1] - bb[1]) + abs(ab[3] - bb[3])) * 0.5,
    ]


def _centre_drift(a: np.ndarray, b: np.ndarray) -> list[float]:
    ac = _centre(a)
    bc = _centre(b)
    return [abs(ac[0] - bc[0]), abs(ac[1] - bc[1])]


def _centre(mask: np.ndarray) -> tuple[float, float]:
    points = np.argwhere(mask)
    if points.size == 0:
        return (0.0, 0.0)
    y, x = points.mean(axis=0)
    return (float(x), float(y))
