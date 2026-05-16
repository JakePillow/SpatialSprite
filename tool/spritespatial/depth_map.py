from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from spritespatial.alpha import has_alpha, load_rgba_png


@dataclass(frozen=True)
class DepthReport:
    dimensions_match: bool
    transparent_pixels_zero: bool
    opaque_coverage_ratio: float
    depth_coverage_ratio: float
    min_depth: int
    max_depth: int
    mean_depth: float
    unique_depth_levels: int

    @property
    def passed(self) -> bool:
        return (
            self.dimensions_match
            and self.transparent_pixels_zero
            and abs(self.opaque_coverage_ratio - self.depth_coverage_ratio) <= 0.01
            and self.max_depth > 0
        )


def load_rgba_sprite(path: Path) -> Image.Image:
    image = load_rgba_png(path)
    if image.mode != "RGBA" or not has_alpha(image):
        raise ValueError(f"{path} must be RGBA with alpha.")
    return image


def alpha_mask(image: Image.Image, alpha_threshold: int = 16) -> list[list[bool]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    return [[pixels[x, y][3] > alpha_threshold for x in range(rgba.width)] for y in range(rgba.height)]


def generate_depth_map(
    sprite: Image.Image,
    alpha_threshold: int = 16,
    centre_bias: float = 0.35,
) -> Image.Image:
    rgba = sprite.convert("RGBA")
    mask = alpha_mask(rgba, alpha_threshold)
    bounds = mask_bounds(mask)
    depth = Image.new("L", rgba.size, 0)
    if bounds is None:
        return depth

    pixels = depth.load()
    max_distance = max(1.0, max_edge_distance(mask))
    min_x, min_y, max_x, max_y = bounds
    centre_x = (min_x + max_x) * 0.5
    half_width = max((max_x - min_x + 1) * 0.5, 1.0)

    for y in range(rgba.height):
        for x in range(rgba.width):
            if not mask[y][x]:
                continue
            edge_distance = edge_distance_to_empty(mask, x, y)
            edge_norm = min(edge_distance / max_distance, 1.0)
            centre_norm = 1.0 - min(abs(x - centre_x) / half_width, 1.0)
            value = 24 + 178 * edge_norm + 53 * centre_norm * centre_bias
            if edge_distance <= 1.1:
                value = max(18, value * 0.42)
            pixels[x, y] = max(1, min(255, int(round(value))))
    return depth


def load_or_generate_depth(
    sprite: Image.Image,
    depth_path: Path | None,
    alpha_threshold: int = 16,
) -> Image.Image:
    if depth_path:
        depth = Image.open(depth_path).convert("L")
        if depth.size != sprite.size:
            raise ValueError(f"Depth map {depth_path} dimensions {depth.size} do not match sprite {sprite.size}.")
        return mask_depth_to_alpha(sprite, depth, alpha_threshold)
    return generate_depth_map(sprite, alpha_threshold)


def mask_depth_to_alpha(sprite: Image.Image, depth: Image.Image, alpha_threshold: int = 16) -> Image.Image:
    rgba = sprite.convert("RGBA")
    result = depth.convert("L")
    rgba_pixels = rgba.load()
    depth_pixels = result.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            if rgba_pixels[x, y][3] <= alpha_threshold:
                depth_pixels[x, y] = 0
            elif depth_pixels[x, y] == 0:
                depth_pixels[x, y] = 1
    return result


def validate_depth(sprite: Image.Image, depth: Image.Image, alpha_threshold: int = 16) -> DepthReport:
    rgba = sprite.convert("RGBA")
    depth_l = depth.convert("L")
    if rgba.size != depth_l.size:
        return DepthReport(False, False, 0.0, 0.0, 0, 0, 0.0, 0)

    rgba_pixels = rgba.load()
    depth_pixels = depth_l.load()
    total = rgba.width * rgba.height
    opaque = 0
    depth_nonzero = 0
    transparent_zero = True
    values: list[int] = []
    unique_values: set[int] = set()

    for y in range(rgba.height):
        for x in range(rgba.width):
            alpha_opaque = rgba_pixels[x, y][3] > alpha_threshold
            value = int(depth_pixels[x, y])
            if alpha_opaque:
                opaque += 1
                values.append(value)
                if value > 0:
                    depth_nonzero += 1
                    unique_values.add(value)
            elif value != 0:
                transparent_zero = False

    return DepthReport(
        dimensions_match=True,
        transparent_pixels_zero=transparent_zero,
        opaque_coverage_ratio=opaque / total if total else 0.0,
        depth_coverage_ratio=depth_nonzero / total if total else 0.0,
        min_depth=min(values) if values else 0,
        max_depth=max(values) if values else 0,
        mean_depth=sum(values) / len(values) if values else 0.0,
        unique_depth_levels=len(unique_values),
    )


def write_depth_outputs(
    front: Image.Image,
    back: Image.Image,
    front_depth: Image.Image,
    back_depth: Image.Image,
    output_dir: Path,
    alpha_threshold: int = 16,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    front_depth_path = output_dir / "front_depth.png"
    back_depth_path = output_dir / "back_depth.png"
    overlay_path = output_dir / "depth_debug_overlay.png"
    report_path = output_dir / "depth_report.json"

    front_depth.save(front_depth_path, format="PNG")
    back_depth.save(back_depth_path, format="PNG")
    depth_debug_overlay(front, front_depth).save(overlay_path, format="PNG")

    front_report = validate_depth(front, front_depth, alpha_threshold)
    back_report = validate_depth(back, back_depth, alpha_threshold)
    report = {
        "front": asdict(front_report),
        "back": asdict(back_report),
        "passed": front_report.passed and back_report.passed,
        "files": {
            "front_depth": str(front_depth_path),
            "back_depth": str(back_depth_path),
            "depth_debug_overlay": str(overlay_path),
        },
    }
    with report_path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    if not report["passed"]:
        raise ValueError(f"Depth validation failed. See {report_path}")
    return report


def depth_debug_overlay(sprite: Image.Image, depth: Image.Image) -> Image.Image:
    rgba = sprite.convert("RGBA")
    depth_l = depth.convert("L")
    result = rgba.copy()
    result_pixels = result.load()
    depth_pixels = depth_l.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = result_pixels[x, y]
            if alpha == 0:
                continue
            value = depth_pixels[x, y]
            result_pixels[x, y] = (
                min(255, int(red * 0.55 + value * 0.45)),
                int(green * 0.55),
                int(blue * 0.55),
                alpha,
            )
    return result


def mask_bounds(mask: list[list[bool]]) -> tuple[int, int, int, int] | None:
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


def max_edge_distance(mask: list[list[bool]]) -> float:
    best = 1.0
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if value:
                best = max(best, edge_distance_to_empty(mask, x, y))
    return best


def edge_distance_to_empty(mask: list[list[bool]], x: int, y: int) -> float:
    height = len(mask)
    width = len(mask[0])
    best = min(x + 1, y + 1, width - x, height - y)
    radius = 1
    while radius <= max(width, height):
        found = False
        for yy in range(max(0, y - radius), min(height, y + radius + 1)):
            for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                if not mask[yy][xx]:
                    dist = ((xx - x) ** 2 + (yy - y) ** 2) ** 0.5
                    best = min(best, dist)
                    found = True
        if found:
            return best
        radius += 1
    return best


def pad_to_shared_canvas(front: Image.Image, back: Image.Image, alpha_threshold: int = 16) -> tuple[Image.Image, Image.Image]:
    front_bounds = mask_bounds(alpha_mask(front, alpha_threshold))
    back_bounds = mask_bounds(alpha_mask(back, alpha_threshold))
    if front_bounds is None or back_bounds is None:
        raise ValueError("Front and back sprites must contain opaque pixels.")
    content_width = max(front_bounds[2] - front_bounds[0] + 1, back_bounds[2] - back_bounds[0] + 1)
    content_height = max(front_bounds[3] - front_bounds[1] + 1, back_bounds[3] - back_bounds[1] + 1)
    width = max(front.width, back.width, content_width)
    height = max(front.height, back.height, content_height)
    return _paste_aligned(front, front_bounds, width, height), _paste_aligned(back, back_bounds, width, height)


def _paste_aligned(image: Image.Image, bounds: tuple[int, int, int, int], width: int, height: int) -> Image.Image:
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    min_x, min_y, max_x, max_y = bounds
    content = image.crop((min_x, min_y, max_x + 1, max_y + 1))
    result.alpha_composite(content, ((width - content.width) // 2, height - content.height))
    return result
