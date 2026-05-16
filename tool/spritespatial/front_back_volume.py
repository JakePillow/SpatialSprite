from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw

from spritespatial.alpha import has_alpha, load_rgba_png
from spritespatial.depth_annotation import (
    validate_depth_map,
    write_depth_assets_from_images,
)
from spritespatial.upscale import upscale_image

SideColourMode = Literal["nearest_front", "nearest_back", "blended"]
SmoothingMode = Literal["none", "merge_faces", "low_poly"]
UpscaleMode = Literal["none", "nearest_integer", "scale2x", "scale3x"]


@dataclass(frozen=True)
class FrontBackConfig:
    model_depth_units: float = 0.48
    depth_slices: int = 7
    voxel_size: float = 0.06
    side_colour_mode: SideColourMode = "blended"
    smoothing_mode: SmoothingMode = "merge_faces"
    upscale_mode: UpscaleMode = "none"
    ml_cleanup_enabled: bool = False
    alpha_threshold: int = 16
    front_depth_path: str | None = None
    back_depth_path: str | None = None


@dataclass(frozen=True)
class FrontBackBuildResult:
    output_scene_data: Path
    metadata_path: Path
    debug_dir: Path
    vertex_count: int
    triangle_count: int
    canvas_size: tuple[int, int]
    depth_slices: int


def build_front_back_model(
    front_path: Path,
    back_path: Path,
    output_dir: Path,
    config: FrontBackConfig,
) -> FrontBackBuildResult:
    if config.ml_cleanup_enabled:
        raise ValueError("ml_cleanup_enabled must remain false for this deterministic prototype.")

    front = _load_and_optionally_upscale(front_path, config)
    back = _load_and_optionally_upscale(back_path, config)
    _validate_rgba_sprite(front, front_path)
    _validate_rgba_sprite(back, back_path)

    front, back = align_front_back(front, back, config.alpha_threshold)
    front_mask = alpha_mask(front, config.alpha_threshold)
    back_mask = alpha_mask(back, config.alpha_threshold)
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    front_aligned_path = output_dir / "front_aligned.png"
    back_aligned_path = output_dir / "back_aligned.png"
    front.save(front_aligned_path, format="PNG")
    back.save(back_aligned_path, format="PNG")

    depth_assets = write_depth_assets_from_images(
        front,
        output_dir,
        back=back,
        manual_front_depth=Path(config.front_depth_path) if config.front_depth_path else None,
        manual_back_depth=Path(config.back_depth_path) if config.back_depth_path else None,
        alpha_threshold=config.alpha_threshold,
    )
    front_depth = Image.open(depth_assets["front_depth"]).convert("L")
    back_depth = Image.open(depth_assets["back_depth"]).convert("L")
    _validate_depth_for_sprite(front, front_depth, "front", config.alpha_threshold)
    _validate_depth_for_sprite(back, back_depth, "back", config.alpha_threshold)

    occupied = interpolate_occupancy(
        front_mask,
        back_mask,
        config.depth_slices,
        front_depth=front_depth,
        back_depth=back_depth,
    )
    mesh = voxel_volume_to_mesh(front, back, occupied, config)
    _write_debug_images(front_mask, back_mask, occupied, debug_dir)

    scene_data_path = output_dir / "front_back_model.json"
    metadata_path = output_dir / "metadata.json"
    scene_data = {
        "schema": "spritespatial_front_back_model_v1",
        "config": asdict(config),
        "front_texture": _res_path(front_aligned_path),
        "back_texture": _res_path(back_aligned_path),
        "canvas_size": [front.width, front.height],
        "vertices": mesh["vertices"],
        "normals": mesh["normals"],
        "colors": mesh["colors"],
        "indices": mesh["indices"],
    }
    _write_json(scene_data_path, scene_data)

    metadata = {
        "front_source": str(front_path),
        "back_source": str(back_path),
        "front_texture": str(front_aligned_path),
        "back_texture": str(back_aligned_path),
        "front_depth": depth_assets["front_depth"],
        "back_depth": depth_assets["back_depth"],
        "regions": depth_assets["regions"],
        "depth_debug_overlay": depth_assets["depth_debug_overlay"],
        "volume_debug": depth_assets["volume_debug"],
        "canvas_size": [front.width, front.height],
        "depth_slices": config.depth_slices,
        "voxel_size": config.voxel_size,
        "model_depth_units": config.model_depth_units,
        "side_colour_mode": config.side_colour_mode,
        "smoothing_mode": config.smoothing_mode,
        "upscale_mode": config.upscale_mode,
        "ml_cleanup_enabled": config.ml_cleanup_enabled,
        "vertex_count": len(mesh["vertices"]),
        "triangle_count": len(mesh["indices"]) // 3,
        "debug_dir": str(debug_dir),
    }
    _write_json(metadata_path, metadata)

    return FrontBackBuildResult(
        output_scene_data=scene_data_path,
        metadata_path=metadata_path,
        debug_dir=debug_dir,
        vertex_count=len(mesh["vertices"]),
        triangle_count=len(mesh["indices"]) // 3,
        canvas_size=(front.width, front.height),
        depth_slices=config.depth_slices,
    )


def align_front_back(
    front: Image.Image,
    back: Image.Image,
    alpha_threshold: int,
) -> tuple[Image.Image, Image.Image]:
    front_bounds = alpha_bounds(front, alpha_threshold)
    back_bounds = alpha_bounds(back, alpha_threshold)
    if front_bounds is None or back_bounds is None:
        raise ValueError("Both front and back sprites must contain non-transparent pixels.")

    content_width = max(front_bounds[2] - front_bounds[0] + 1, back_bounds[2] - back_bounds[0] + 1)
    content_height = max(front_bounds[3] - front_bounds[1] + 1, back_bounds[3] - back_bounds[1] + 1)
    canvas_width = max(front.width, back.width, content_width)
    canvas_height = max(front.height, back.height, content_height)

    return (
        _paste_aligned(front, front_bounds, canvas_width, canvas_height),
        _paste_aligned(back, back_bounds, canvas_width, canvas_height),
    )


def alpha_mask(image: Image.Image, alpha_threshold: int) -> list[list[bool]]:
    pixels = image.convert("RGBA").load()
    return [
        [pixels[x, y][3] > alpha_threshold for x in range(image.width)]
        for y in range(image.height)
    ]


def interpolate_occupancy(
    front_mask: list[list[bool]],
    back_mask: list[list[bool]],
    depth_slices: int,
    front_depth: Image.Image | None = None,
    back_depth: Image.Image | None = None,
) -> list[list[list[bool]]]:
    if depth_slices < 2:
        raise ValueError("depth_slices must be at least 2.")

    height = len(front_mask)
    width = len(front_mask[0])
    front_bounds = _mask_bounds(front_mask)
    back_bounds = _mask_bounds(back_mask)
    volume: list[list[list[bool]]] = []

    for z in range(depth_slices):
        t = z / float(depth_slices - 1)
        slice_rows: list[list[bool]] = []
        bounds = _lerp_bounds(back_bounds, front_bounds, t)
        for y in range(height):
            row: list[bool] = []
            for x in range(width):
                occupied = front_mask[y][x] or back_mask[y][x]
                if not occupied:
                    occupied = _inside_bounds(x, y, bounds) and _near_any_mask(x, y, front_mask, back_mask)
                if front_depth is not None and _front_depth_occupies(front_depth, x, y, z, depth_slices):
                    occupied = True
                if back_depth is not None and _back_depth_occupies(back_depth, x, y, z, depth_slices):
                    occupied = True
                row.append(occupied)
            slice_rows.append(row)
        volume.append(slice_rows)

    volume[0] = [row[:] for row in back_mask]
    volume[-1] = [row[:] for row in front_mask]
    return volume


def voxel_volume_to_mesh(
    front: Image.Image,
    back: Image.Image,
    occupied: list[list[list[bool]]],
    config: FrontBackConfig,
) -> dict[str, list]:
    depth_slices = len(occupied)
    height = len(occupied[0])
    width = len(occupied[0][0])
    voxel_x = config.voxel_size
    voxel_y = config.voxel_size
    voxel_z = config.model_depth_units / max(depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -config.model_depth_units * 0.5
    front_pixels = front.convert("RGBA").load()
    back_pixels = back.convert("RGBA").load()
    front_nearest = _nearest_opaque_colour_grid(front, config.alpha_threshold)
    back_nearest = _nearest_opaque_colour_grid(back, config.alpha_threshold)

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []

    def is_occupied(x: int, y: int, z: int) -> bool:
        if x < 0 or y < 0 or z < 0 or x >= width or y >= height or z >= depth_slices:
            return False
        return occupied[z][y][x]

    for z in range(depth_slices):
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        for y in range(height):
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            for x in range(width):
                if not occupied[z][y][x]:
                    continue
                x0 = x * voxel_x - total_width * 0.5
                x1 = x0 + voxel_x

                front_colour = _rgba_float(front_pixels[x, y])
                back_colour = _rgba_float(back_pixels[x, y])
                nearest_front_colour = _rgba_float(front_nearest[y][x])
                nearest_back_colour = _rgba_float(back_nearest[y][x])
                side_colour = _side_colour(nearest_front_colour, nearest_back_colour, config.side_colour_mode)

                if not is_occupied(x, y, z - 1):
                    _add_quad(vertices, normals, colors, indices, [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [0, 0, -1], back_colour)
                if not is_occupied(x, y, z + 1):
                    _add_quad(vertices, normals, colors, indices, [x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1], [0, 0, 1], front_colour)
                if not is_occupied(x - 1, y, z):
                    _add_quad(vertices, normals, colors, indices, [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0], [-1, 0, 0], side_colour)
                if not is_occupied(x + 1, y, z):
                    _add_quad(vertices, normals, colors, indices, [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [1, 0, 0], side_colour)
                if not is_occupied(x, y - 1, z):
                    _add_quad(vertices, normals, colors, indices, [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1], [0, 1, 0], side_colour)
                if not is_occupied(x, y + 1, z):
                    _add_quad(vertices, normals, colors, indices, [x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0], [0, -1, 0], side_colour)

    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
    }


def alpha_bounds(image: Image.Image, alpha_threshold: int) -> tuple[int, int, int, int] | None:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    min_x = rgba.width
    min_y = rgba.height
    max_x = -1
    max_y = -1
    for y in range(rgba.height):
        for x in range(rgba.width):
            if pixels[x, y][3] <= alpha_threshold:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x:
        return None
    return min_x, min_y, max_x, max_y


def _validate_depth_for_sprite(
    sprite: Image.Image,
    depth: Image.Image,
    label: str,
    alpha_threshold: int,
) -> None:
    report = validate_depth_map(sprite, depth, alpha_threshold)
    if not report.passed:
        raise ValueError(f"{label} depth map failed validation: {report}")


def _front_depth_occupies(
    depth: Image.Image,
    x: int,
    y: int,
    z: int,
    depth_slices: int,
) -> bool:
    value = depth.getpixel((x, y))
    if value <= 0:
        return False
    relief = max(1, int(round((value / 255.0) * max(depth_slices // 2, 1))))
    return z >= depth_slices - relief


def _back_depth_occupies(
    depth: Image.Image,
    x: int,
    y: int,
    z: int,
    depth_slices: int,
) -> bool:
    value = depth.getpixel((x, y))
    if value <= 0:
        return False
    relief = max(1, int(round((value / 255.0) * max(depth_slices // 2, 1))))
    return z < relief


def _load_and_optionally_upscale(path: Path, config: FrontBackConfig) -> Image.Image:
    image = load_rgba_png(path)
    if config.upscale_mode == "none":
        return image
    scale = 3 if config.upscale_mode == "scale3x" else 2
    return upscale_image(image, scale_factor=scale, mode=config.upscale_mode)


def _validate_rgba_sprite(image: Image.Image, path: Path) -> None:
    if image.mode != "RGBA" or not has_alpha(image):
        raise ValueError(f"{path} must be RGBA with an alpha channel.")
    corners = [
        image.getpixel((0, 0))[3],
        image.getpixel((image.width - 1, 0))[3],
        image.getpixel((0, image.height - 1))[3],
        image.getpixel((image.width - 1, image.height - 1))[3],
    ]
    if sum(1 for alpha in corners if alpha > 0) > 1:
        raise ValueError(f"{path} appears to have opaque background corners.")


def _paste_aligned(
    image: Image.Image,
    bounds: tuple[int, int, int, int],
    canvas_width: int,
    canvas_height: int,
) -> Image.Image:
    result = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    min_x, min_y, max_x, max_y = bounds
    content = image.crop((min_x, min_y, max_x + 1, max_y + 1))
    x = (canvas_width - content.width) // 2
    y = canvas_height - content.height
    result.alpha_composite(content, (x, y))
    return result


def _mask_bounds(mask: list[list[bool]]) -> tuple[int, int, int, int]:
    height = len(mask)
    width = len(mask[0])
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if not value:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    return min_x, min_y, max_x, max_y


def _lerp_bounds(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[float, float, float, float]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))  # type: ignore[return-value]


def _inside_bounds(x: int, y: int, bounds: tuple[float, float, float, float]) -> bool:
    return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]


def _near_any_mask(x: int, y: int, front: list[list[bool]], back: list[list[bool]], radius: int = 1) -> bool:
    height = len(front)
    width = len(front[0])
    for yy in range(max(0, y - radius), min(height, y + radius + 1)):
        for xx in range(max(0, x - radius), min(width, x + radius + 1)):
            if front[yy][xx] or back[yy][xx]:
                return True
    return False


def _add_quad(
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    a: list[float],
    b: list[float],
    c: list[float],
    d: list[float],
    normal: list[float],
    colour: list[float],
) -> None:
    start = len(vertices)
    vertices.extend([a, b, c, d])
    normals.extend([normal, normal, normal, normal])
    colors.extend([colour, colour, colour, colour])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])


def _rgba_float(pixel: tuple[int, int, int, int]) -> list[float]:
    red, green, blue, alpha = pixel
    return [red / 255.0, green / 255.0, blue / 255.0, alpha / 255.0]


def _nearest_opaque_colour_grid(
    image: Image.Image,
    alpha_threshold: int,
) -> list[list[tuple[int, int, int, int]]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    opaque: list[tuple[int, int, tuple[int, int, int, int]]] = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            pixel = pixels[x, y]
            if pixel[3] > alpha_threshold:
                opaque.append((x, y, pixel))

    if not opaque:
        return [[(32, 32, 32, 255) for _x in range(rgba.width)] for _y in range(rgba.height)]

    grid: list[list[tuple[int, int, int, int]]] = []
    for y in range(rgba.height):
        row: list[tuple[int, int, int, int]] = []
        for x in range(rgba.width):
            pixel = pixels[x, y]
            if pixel[3] > alpha_threshold:
                row.append(pixel)
                continue
            nearest = min(opaque, key=lambda item: (item[0] - x) ** 2 + (item[1] - y) ** 2)
            row.append(nearest[2])
        grid.append(row)
    return grid


def _side_colour(front: list[float], back: list[float], mode: SideColourMode) -> list[float]:
    if mode == "nearest_front":
        base = front if front[3] > 0 else back
    elif mode == "nearest_back":
        base = back if back[3] > 0 else front
    else:
        if front[3] > 0 and back[3] > 0:
            base = [(front[i] + back[i]) * 0.5 for i in range(4)]
        else:
            base = front if front[3] > 0 else back
    return [base[0] * 0.72, base[1] * 0.72, base[2] * 0.72, 1.0]


def _write_debug_images(
    front_mask: list[list[bool]],
    back_mask: list[list[bool]],
    occupied: list[list[list[bool]]],
    debug_dir: Path,
) -> None:
    _mask_image(front_mask).save(debug_dir / "front_mask.png", format="PNG")
    _mask_image(back_mask).save(debug_dir / "back_mask.png", format="PNG")
    frames = [_mask_image(occupied[index]) for index in range(len(occupied))]
    sheet = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame.width, 0))
    sheet.save(debug_dir / "depth_slices.png", format="PNG")


def _mask_image(mask: list[list[bool]]) -> Image.Image:
    height = len(mask)
    width = len(mask[0])
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if value:
                draw.point((x, y), fill=(255, 255, 255, 255))
    return image


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def _res_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
        return "res://" + relative.as_posix()
    except ValueError:
        return path.as_posix()
