from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.depthfields.schema import DepthFieldResult


def write_heatmap(values: np.ndarray, path: Path) -> None:
    data = np.asarray(values, dtype=np.float32)
    maximum = float(data.max()) if data.size else 0.0
    image = Image.new("RGBA", (data.shape[1], data.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(data > 0.0):
        t = float(data[y, x]) / max(maximum, 1e-6)
        pixels[int(x), int(y)] = (
            int(255 * t), int(180 * (1.0 - t)), int(255 * (1.0 - t * 0.65)), 255
        )
    image.save(path, format="PNG")


def write_mask(
    mask: np.ndarray,
    path: Path,
    colour: tuple[int, int, int, int] = (255, 80, 30, 255),
) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, x in np.argwhere(mask):
        draw.point((int(x), int(y)), fill=colour)
    image.save(path, format="PNG")


def write_region_overlay(result: DepthFieldResult, path: Path) -> None:
    image = Image.new(
        "RGBA", (result.alpha_mask.shape[1], result.alpha_mask.shape[0]), (0, 0, 0, 0)
    )
    pixels = image.load()
    for index, (region_id, field) in enumerate(sorted(result.region_depth_fields.items())):
        seed = sum(ord(value) for value in region_id) + index * 97
        colour = (
            50 + seed * 53 % 190,
            50 + seed * 89 % 190,
            50 + seed * 131 % 190,
            220,
        )
        for y, x in np.argwhere(field > 0.0):
            pixels[int(x), int(y)] = colour
    image.save(path, format="PNG")


def write_cross_section(
    result: DepthFieldResult, path: Path, row: int | None = None
) -> None:
    depth = result.pinned_depth_field
    row = int(row if row is not None else depth.shape[0] // 2)
    row = max(0, min(depth.shape[0] - 1, row))
    scale = max(24, depth.shape[0])
    height = scale * 2 + 1
    image = Image.new("RGBA", (depth.shape[1], height), (12, 18, 30, 255))
    draw = ImageDraw.Draw(image)
    centre = scale
    draw.line((0, centre, depth.shape[1], centre), fill=(70, 90, 120, 255))
    for x, value in enumerate(depth[row]):
        extent = int(round(float(value) * scale))
        if extent > 0:
            draw.line((x, centre - extent, x, centre + extent), fill=(72, 190, 255, 255))
    image.save(path, format="PNG")


def write_visual_report(result: DepthFieldResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "global_depth_heatmap": output_dir / "global_depth_field.png",
        "blended_depth_heatmap": output_dir / "blended_depth_field.png",
        "pinned_depth_heatmap": output_dir / "pinned_depth_field.png",
        "silhouette_pin_mask": output_dir / "silhouette_pin_mask.png",
        "region_overlay": output_dir / "region_depth_overlay.png",
        "cross_section": output_dir / "depth_cross_section.png",
    }
    write_heatmap(result.global_depth_field, paths["global_depth_heatmap"])
    write_heatmap(result.blended_depth_field, paths["blended_depth_heatmap"])
    write_heatmap(result.pinned_depth_field, paths["pinned_depth_heatmap"])
    write_mask(result.silhouette_mask, paths["silhouette_pin_mask"])
    write_region_overlay(result, paths["region_overlay"])
    write_cross_section(result, paths["cross_section"])
    regions_dir = output_dir / "regions"
    regions_dir.mkdir(parents=True, exist_ok=True)
    for region_id, field in result.region_depth_fields.items():
        write_heatmap(field, regions_dir / f"{_safe(region_id)}.png")
    paths["regions"] = regions_dir
    return paths


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_").lower() or "region"
