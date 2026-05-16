from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from spritespatial.alpha import has_alpha, load_rgba_png


REGION_NAMES = (
    "head",
    "torso",
    "left_arm",
    "right_arm",
    "legs",
    "shield",
    "sword",
    "hat",
    "hair",
    "clothing",
)


@dataclass(frozen=True)
class DepthValidationReport:
    dimensions_match: bool
    transparent_pixels_zero: bool
    opaque_pixels_nonzero: bool
    values_in_range: bool
    coverage_matches_alpha: bool
    depth_layers_used: int

    @property
    def passed(self) -> bool:
        return (
            self.dimensions_match
            and self.transparent_pixels_zero
            and self.opaque_pixels_nonzero
            and self.values_in_range
            and self.coverage_matches_alpha
        )


def generate_depth_assets(
    front_path: Path,
    output_dir: Path,
    back_path: Path | None = None,
    manual_front_depth: Path | None = None,
    manual_back_depth: Path | None = None,
    alpha_threshold: int = 16,
) -> dict[str, Any]:
    front = load_rgba_png(front_path)
    _validate_source_sprite(front, front_path)
    back = load_rgba_png(back_path) if back_path else None
    if back is not None:
        _validate_source_sprite(back, back_path)
        front, back = _pad_to_shared_canvas(front, back)

    output_dir.mkdir(parents=True, exist_ok=True)
    front_depth = _load_manual_or_generate(front, manual_front_depth, "front", alpha_threshold)
    back_depth = _load_manual_or_generate(back, manual_back_depth, "back", alpha_threshold) if back else None

    front_report = validate_depth_map(front, front_depth, alpha_threshold)
    if not front_report.passed:
        raise ValueError(f"front depth validation failed: {front_report}")

    back_report = None
    if back is not None and back_depth is not None:
        back_report = validate_depth_map(back, back_depth, alpha_threshold)
        if not back_report.passed:
            raise ValueError(f"back depth validation failed: {back_report}")

    regions = _build_regions(front, back, alpha_threshold)
    front_depth_path = output_dir / "front_depth.png"
    back_depth_path = output_dir / "back_depth.png"
    regions_path = output_dir / "regions.json"
    overlay_path = output_dir / "depth_debug_overlay.png"
    volume_debug_path = output_dir / "volume_debug.json"

    front_depth.save(front_depth_path, format="PNG")
    if back_depth is not None:
        back_depth.save(back_depth_path, format="PNG")
    else:
        Image.new("L", front_depth.size, 0).save(back_depth_path, format="PNG")

    _write_json(regions_path, regions)
    _depth_overlay(front, front_depth).save(overlay_path, format="PNG")

    volume_debug = {
        "front_sprite": str(front_path),
        "back_sprite": str(back_path) if back_path else None,
        "front_depth": str(front_depth_path),
        "back_depth": str(back_depth_path),
        "regions": str(regions_path),
        "manual_front_depth": str(manual_front_depth) if manual_front_depth else None,
        "manual_back_depth": str(manual_back_depth) if manual_back_depth else None,
        "ai_assistance": {
            "enabled": False,
            "accepted_without_validation": False,
            "note": "External AI suggestions may populate proposed_regions, but deterministic validation must pass before use.",
        },
        "validation": {
            "front": front_report.__dict__,
            "back": back_report.__dict__ if back_report else None,
        },
    }
    _write_json(volume_debug_path, volume_debug)
    volume_debug.update(
        {
            "front_depth": str(front_depth_path),
            "back_depth": str(back_depth_path),
            "regions": str(regions_path),
            "depth_debug_overlay": str(overlay_path),
            "volume_debug": str(volume_debug_path),
        }
    )
    return volume_debug


def write_depth_assets_from_images(
    front: Image.Image,
    output_dir: Path,
    back: Image.Image | None = None,
    manual_front_depth: Path | None = None,
    manual_back_depth: Path | None = None,
    alpha_threshold: int = 16,
) -> dict[str, Any]:
    _validate_source_sprite(front, None)
    if back is not None:
        _validate_source_sprite(back, None)
    output_dir.mkdir(parents=True, exist_ok=True)

    front_depth = _load_manual_or_generate(front, manual_front_depth, "front", alpha_threshold)
    back_depth = _load_manual_or_generate(back, manual_back_depth, "back", alpha_threshold) if back else Image.new("L", front.size, 0)
    front_report = validate_depth_map(front, front_depth, alpha_threshold)
    back_report = validate_depth_map(back, back_depth, alpha_threshold) if back else None
    if not front_report.passed:
        raise ValueError(f"front depth validation failed: {front_report}")
    if back_report is not None and not back_report.passed:
        raise ValueError(f"back depth validation failed: {back_report}")

    regions = _build_regions(front, back, alpha_threshold)
    front_depth_path = output_dir / "front_depth.png"
    back_depth_path = output_dir / "back_depth.png"
    regions_path = output_dir / "regions.json"
    overlay_path = output_dir / "depth_debug_overlay.png"
    volume_debug_path = output_dir / "volume_debug.json"

    front_depth.save(front_depth_path, format="PNG")
    back_depth.save(back_depth_path, format="PNG")
    _write_json(regions_path, regions)
    _depth_overlay(front, front_depth).save(overlay_path, format="PNG")

    volume_debug = {
        "front_depth": str(front_depth_path),
        "back_depth": str(back_depth_path),
        "regions": str(regions_path),
        "depth_debug_overlay": str(overlay_path),
        "volume_debug": str(volume_debug_path),
        "manual_front_depth": str(manual_front_depth) if manual_front_depth else None,
        "manual_back_depth": str(manual_back_depth) if manual_back_depth else None,
        "ai_assistance": {
            "enabled": False,
            "accepted_without_validation": False,
            "note": "AI hook is available but not used by deterministic baseline.",
        },
        "validation": {
            "front": front_report.__dict__,
            "back": back_report.__dict__ if back_report else None,
        },
    }
    _write_json(volume_debug_path, volume_debug)
    return volume_debug


def deterministic_depth_map(
    sprite: Image.Image,
    view: str = "front",
    alpha_threshold: int = 16,
) -> Image.Image:
    rgba = sprite.convert("RGBA")
    alpha_mask = _alpha_mask(rgba, alpha_threshold)
    bounds = _mask_bounds(alpha_mask)
    depth = Image.new("L", rgba.size, 0)
    pixels = depth.load()
    if bounds is None:
        return depth

    max_distance = max(1.0, _max_edge_distance(alpha_mask))
    min_x, min_y, max_x, max_y = bounds
    center_x = (min_x + max_x) * 0.5
    height = max(1, max_y - min_y + 1)

    for y in range(rgba.height):
        for x in range(rgba.width):
            if not alpha_mask[y][x]:
                continue

            edge_distance = _edge_distance(alpha_mask, x, y)
            rim_factor = min(edge_distance / max_distance, 1.0)
            center_factor = 1.0 - min(abs(x - center_x) / max((max_x - min_x) * 0.5, 1.0), 1.0)
            vertical = (y - min_y) / height
            body_factor = _body_depth_factor(vertical, view)
            value = 34 + 126 * rim_factor + 58 * center_factor + 37 * body_factor

            if edge_distance <= 1.25:
                value *= 0.58
            pixels[x, y] = max(1, min(255, int(round(value))))

    return depth


def validate_depth_map(
    sprite: Image.Image,
    depth: Image.Image,
    alpha_threshold: int = 16,
) -> DepthValidationReport:
    rgba = sprite.convert("RGBA")
    depth_l = depth.convert("L")
    dimensions_match = rgba.size == depth_l.size
    if not dimensions_match:
        return DepthValidationReport(False, False, False, False, False, 0)

    rgba_pixels = rgba.load()
    depth_pixels = depth_l.load()
    transparent_zero = True
    opaque_nonzero = True
    values: set[int] = set()
    alpha_coverage = 0
    depth_coverage = 0

    for y in range(rgba.height):
        for x in range(rgba.width):
            alpha_opaque = rgba_pixels[x, y][3] > alpha_threshold
            value = int(depth_pixels[x, y])
            values.add(value)
            if alpha_opaque:
                alpha_coverage += 1
                if value == 0:
                    opaque_nonzero = False
            else:
                if value != 0:
                    transparent_zero = False
            if value > 0:
                depth_coverage += 1

    return DepthValidationReport(
        dimensions_match=True,
        transparent_pixels_zero=transparent_zero,
        opaque_pixels_nonzero=opaque_nonzero,
        values_in_range=all(0 <= value <= 255 for value in values),
        coverage_matches_alpha=alpha_coverage == depth_coverage,
        depth_layers_used=len(values - {0}),
    )


def ai_depth_suggestion_hook(sprite: Image.Image, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Placeholder interface for external AI/agent depth suggestions.

    The base pipeline never calls an AI model. A caller may pass proposed output
    through validate_ai_depth_suggestions before using it.
    """
    raise NotImplementedError("AI-assisted depth suggestions are a hook only; no generative model is implemented.")


def validate_ai_depth_suggestions(suggestions: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(suggestions, dict):
        raise ValueError("AI suggestions must be a JSON object.")
    regions = suggestions.get("regions", [])
    if not isinstance(regions, list):
        raise ValueError("AI suggestions must contain a regions list.")
    validated = []
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError("Each AI region suggestion must be an object.")
        name = str(region.get("name", ""))
        if name not in REGION_NAMES:
            raise ValueError(f"Unsupported AI region name: {name}")
        depth = int(region.get("depth", -1))
        if depth < 0 or depth > 255:
            raise ValueError(f"Invalid depth for {name}: {depth}")
        validated.append({"name": name, "depth": depth, "source": "ai_suggestion_validated"})
    return {"regions": validated, "accepted_without_validation": False}


def _load_manual_or_generate(
    sprite: Image.Image | None,
    manual_path: Path | None,
    view: str,
    alpha_threshold: int,
) -> Image.Image:
    if sprite is None:
        raise ValueError("Cannot generate or validate depth without a sprite.")
    if manual_path:
        manual = Image.open(manual_path).convert("L")
        _preserve_alpha_depth_mask(sprite, manual, alpha_threshold)
        return manual
    return deterministic_depth_map(sprite, view=view, alpha_threshold=alpha_threshold)


def _preserve_alpha_depth_mask(sprite: Image.Image, depth: Image.Image, alpha_threshold: int) -> None:
    if sprite.size != depth.size:
        raise ValueError(f"Manual depth dimensions {depth.size} do not match sprite {sprite.size}.")
    rgba = sprite.convert("RGBA")
    rgba_pixels = rgba.load()
    depth_pixels = depth.load()
    for y in range(sprite.height):
        for x in range(sprite.width):
            if rgba_pixels[x, y][3] <= alpha_threshold:
                depth_pixels[x, y] = 0


def _build_regions(front: Image.Image, back: Image.Image | None, alpha_threshold: int) -> dict[str, Any]:
    front_mask = _alpha_mask(front, alpha_threshold)
    bounds = _mask_bounds(front_mask)
    if bounds is None:
        regions = []
    else:
        min_x, min_y, max_x, max_y = bounds
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        center_x = (min_x + max_x) * 0.5
        regions = [
            _region("hat", 196, min_x, min_y, max_x, min_y + int(height * 0.18)),
            _region("head", 226, min_x + int(width * 0.22), min_y + int(height * 0.10), max_x - int(width * 0.18), min_y + int(height * 0.42)),
            _region("torso", 204, min_x + int(width * 0.20), min_y + int(height * 0.40), max_x - int(width * 0.16), min_y + int(height * 0.72)),
            _region("left_arm", 176, min_x, min_y + int(height * 0.34), int(center_x - width * 0.20), min_y + int(height * 0.76)),
            _region("right_arm", 176, int(center_x + width * 0.20), min_y + int(height * 0.34), max_x, min_y + int(height * 0.76)),
            _region("legs", 160, min_x + int(width * 0.18), min_y + int(height * 0.68), max_x - int(width * 0.12), max_y),
            _region("clothing", 188, min_x, min_y, max_x, max_y),
            _region("shield", 180, min_x, min_y + int(height * 0.25), min_x + int(width * 0.32), min_y + int(height * 0.70)),
            _region("sword", 168, max_x - int(width * 0.18), min_y + int(height * 0.10), max_x, min_y + int(height * 0.90)),
            _region("hair", 214, min_x + int(width * 0.18), min_y + int(height * 0.08), max_x - int(width * 0.10), min_y + int(height * 0.34)),
        ]

    return {
        "schema": "spritespatial_regions_v1",
        "source": "deterministic_baseline",
        "regions": regions,
        "ai_assistance": {
            "enabled": False,
            "hook": "ai_depth_suggestion_hook",
            "accepted_without_validation": False,
        },
        "back_sprite_present": back is not None,
    }


def _region(name: str, depth: int, x0: int, y0: int, x1: int, y1: int) -> dict[str, Any]:
    return {
        "name": name,
        "depth": max(0, min(255, depth)),
        "bbox": [int(x0), int(y0), int(x1), int(y1)],
        "editable": True,
    }


def _depth_overlay(sprite: Image.Image, depth: Image.Image) -> Image.Image:
    rgba = sprite.convert("RGBA")
    result = rgba.copy()
    result_pixels = result.load()
    depth_pixels = depth.convert("L").load()
    for y in range(result.height):
        for x in range(result.width):
            red, green, blue, alpha = result_pixels[x, y]
            if alpha == 0:
                continue
            value = depth_pixels[x, y]
            result_pixels[x, y] = (
                min(255, int(red * 0.60 + value * 0.40)),
                int(green * 0.60),
                int(blue * 0.60),
                alpha,
            )
    return result


def _validate_source_sprite(image: Image.Image, path: Path | None) -> None:
    if image.mode != "RGBA" or not has_alpha(image):
        raise ValueError(f"{path} must be RGBA and include alpha.")


def _pad_to_shared_canvas(front: Image.Image, back: Image.Image) -> tuple[Image.Image, Image.Image]:
    width = max(front.width, back.width)
    height = max(front.height, back.height)
    return _paste_bottom_center(front, width, height), _paste_bottom_center(back, width, height)


def _paste_bottom_center(image: Image.Image, width: int, height: int) -> Image.Image:
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.alpha_composite(image, ((width - image.width) // 2, height - image.height))
    return result


def _alpha_mask(image: Image.Image, alpha_threshold: int) -> list[list[bool]]:
    pixels = image.convert("RGBA").load()
    return [[pixels[x, y][3] > alpha_threshold for x in range(image.width)] for y in range(image.height)]


def _mask_bounds(mask: list[list[bool]]) -> tuple[int, int, int, int] | None:
    height = len(mask)
    width = len(mask[0])
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if not value:
                continue
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < min_x:
        return None
    return min_x, min_y, max_x, max_y


def _max_edge_distance(mask: list[list[bool]]) -> float:
    best = 1.0
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if value:
                best = max(best, _edge_distance(mask, x, y))
    return best


def _edge_distance(mask: list[list[bool]], x: int, y: int) -> float:
    height = len(mask)
    width = len(mask[0])
    best = float(width + height)
    for yy in range(height):
        for xx in range(width):
            if 0 <= xx < width and 0 <= yy < height and mask[yy][xx]:
                continue
            best = min(best, ((xx - x) ** 2 + (yy - y) ** 2) ** 0.5)
    best = min(best, x + 1, y + 1, width - x, height - y)
    return best


def _body_depth_factor(vertical: float, view: str) -> float:
    if view == "back":
        return 0.58 if 0.15 <= vertical <= 0.72 else 0.28
    if vertical < 0.18:
        return 0.72
    if vertical < 0.45:
        return 1.0
    if vertical < 0.74:
        return 0.82
    return 0.45


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
