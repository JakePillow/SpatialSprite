from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from spritespatial.primitives import PrimitiveAssignment

Pixel = tuple[int, int]


@dataclass(frozen=True)
class ZFieldRegionReport:
    part_id: int
    name: str
    primitive_type: str
    zfield_profile: str
    pixel_count: int
    min_depth: float
    max_depth: float
    average_depth: float
    occupied_voxels: int
    malformed: bool


def build_semantic_zfield(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    total_depth_slices: int,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    width, height = size
    depth_by_pixel: dict[Pixel, float] = {}
    owner_by_pixel: dict[Pixel, int] = {}
    reports: list[ZFieldRegionReport] = []
    assignment_by_id = {item.part_id: item for item in assignments}

    for part_id, part in enumerate(parts):
        assignment = assignment_by_id[part_id]
        pixels = set(part.get("pixels", set()))
        bbox = list(part.get("bbox", [0, 0, 0, 0]))
        values: list[float] = []
        malformed = not pixels or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]
        for x, y in pixels:
            if not (0 <= x < width and 0 <= y < height):
                malformed = True
                continue
            depth = _depth_for_pixel(x, y, bbox, assignment.zfield_profile, assignment.local_depth)
            depth_by_pixel[(x, y)] = depth
            owner_by_pixel[(x, y)] = part_id
            values.append(depth)
        occupied_voxels = sum(_depth_to_cells(value, total_depth_slices, assignment) for value in values)
        reports.append(
            ZFieldRegionReport(
                part_id=part_id,
                name=assignment.name,
                primitive_type=assignment.primitive_type,
                zfield_profile=assignment.zfield_profile,
                pixel_count=len(pixels),
                min_depth=min(values) if values else 0.0,
                max_depth=max(values) if values else 0.0,
                average_depth=sum(values) / len(values) if values else 0.0,
                occupied_voxels=occupied_voxels,
                malformed=malformed,
            )
        )

    occupancy, owner_by_voxel = build_occupancy_from_zfield(
        depth_by_pixel,
        owner_by_pixel,
        assignments,
        total_depth_slices,
    )
    debug_paths = {}
    if output_dir is not None:
        debug_paths = write_zfield_debug_outputs(
            size,
            depth_by_pixel,
            owner_by_pixel,
            occupancy,
            assignments,
            reports,
            output_dir,
        )

    return {
        "depth_by_pixel": depth_by_pixel,
        "owner_by_pixel": owner_by_pixel,
        "occupancy": occupancy,
        "owner_by_voxel": owner_by_voxel,
        "reports": reports,
        "debug_paths": debug_paths,
    }


def build_occupancy_from_zfield(
    depth_by_pixel: dict[Pixel, float],
    owner_by_pixel: dict[Pixel, int],
    assignments: list[PrimitiveAssignment],
    total_depth_slices: int,
) -> tuple[set[tuple[int, int, int]], dict[tuple[int, int, int], int]]:
    assignment_by_id = {item.part_id: item for item in assignments}
    occupied: set[tuple[int, int, int]] = set()
    owner_by_voxel: dict[tuple[int, int, int], int] = {}
    for pixel, depth in depth_by_pixel.items():
        part_id = owner_by_pixel[pixel]
        assignment = assignment_by_id[part_id]
        cells = _depth_to_cells(depth, total_depth_slices, assignment)
        for z in _z_range_for_assignment(cells, total_depth_slices, assignment):
            key = (pixel[0], pixel[1], z)
            occupied.add(key)
            owner_by_voxel[key] = part_id
    return occupied, owner_by_voxel


def write_zfield_debug_outputs(
    size: tuple[int, int],
    depth_by_pixel: dict[Pixel, float],
    owner_by_pixel: dict[Pixel, int],
    occupancy: set[tuple[int, int, int]],
    assignments: list[PrimitiveAssignment],
    reports: list[ZFieldRegionReport],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    heatmap_path = output_dir / "zfield_heatmap.png"
    primitive_path = output_dir / "primitive_assignment.png"
    outline_path = output_dir / "outline_shell.png"
    debug_path = output_dir / "zfield_debug.json"
    slices_dir = output_dir / "occupancy_slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = output_dir / "occupancy_slices.png"

    _write_heatmap(size, depth_by_pixel, heatmap_path)
    _write_primitive_assignment(size, owner_by_pixel, assignments, primitive_path)
    _write_outline_shell(size, owner_by_pixel, assignments, outline_path)
    _write_occupancy_slices(size, occupancy, slices_dir, sheet_path)
    debug = {
        "schema": "spritespatial_zfield_debug_v1",
        "regions": [asdict(report) for report in reports],
        "primitive_assignments": [asdict(item) for item in assignments],
        "total_occupied_voxels": len(occupancy),
    }
    debug_path.write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    return {
        "zfield_heatmap": heatmap_path,
        "primitive_assignment": primitive_path,
        "outline_shell": outline_path,
        "zfield_debug": debug_path,
        "occupancy_slices": slices_dir,
        "occupancy_slices_sheet": sheet_path,
    }


def reports_to_json(reports: list[ZFieldRegionReport]) -> list[dict[str, Any]]:
    return [asdict(report) for report in reports]


def _depth_for_pixel(x: int, y: int, bbox: list[int], profile: str, local_depth: float) -> float:
    x0, y0, x1, y1 = bbox
    width = max(x1 - x0, 1)
    height = max(y1 - y0, 1)
    nx = ((x + 0.5) - (x0 + width * 0.5)) / max(width * 0.5, 1e-6)
    ny = ((y + 0.5) - (y0 + height * 0.5)) / max(height * 0.5, 1e-6)
    radius = min(math.sqrt(nx * nx + ny * ny), 1.0)

    if profile == "flat":
        factor = 1.0
    elif profile in {"rounded", "rounded_cuboid"}:
        factor = 0.45 + 0.55 * (1.0 - radius ** 2)
    elif profile == "ellipsoid":
        factor = 0.18 + 0.82 * math.sqrt(max(0.0, 1.0 - radius ** 2))
    elif profile == "capsule":
        axis = abs(ny) if height >= width else abs(nx)
        cross = abs(nx) if height >= width else abs(ny)
        cap = 1.0 - max(axis - 0.45, 0.0) / 0.55
        factor = 0.25 + 0.75 * max(0.0, min(1.0, cap)) * math.sqrt(max(0.0, 1.0 - cross * cross))
    elif profile == "tapered":
        vertical = (y - y0) / max(height - 1, 1)
        taper = 1.0 - 0.38 * vertical
        factor = (0.30 + 0.70 * (1.0 - min(abs(nx), 1.0) ** 1.5)) * taper
    elif profile == "shell":
        factor = 0.18 + 0.22 * min(radius, 1.0)
    elif profile == "ridge":
        factor = 0.25 + 0.75 * (1.0 - min(abs(nx), 1.0))
    else:
        factor = 0.55
    return max(0.02, min(1.0, local_depth * factor))


def _depth_to_cells(depth: float, total_depth_slices: int, assignment: PrimitiveAssignment) -> int:
    if assignment.primitive_type == "shell":
        return max(1, min(2, total_depth_slices // 8))
    return max(1, int(round(depth * total_depth_slices)))


def _z_range_for_assignment(
    cells: int,
    total_depth_slices: int,
    assignment: PrimitiveAssignment,
) -> range:
    if assignment.primitive_type == "shell":
        start = max(0, total_depth_slices - cells)
        return range(start, total_depth_slices)
    center = (total_depth_slices - 1) * (0.5 + assignment.z_offset * 0.45)
    z_min = max(0, int(round(center - cells * 0.5)))
    z_max = min(total_depth_slices - 1, z_min + cells - 1)
    return range(z_min, z_max + 1)


def _write_heatmap(size: tuple[int, int], depth_by_pixel: dict[Pixel, float], path: Path) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    max_depth = max(depth_by_pixel.values(), default=1.0)
    for (x, y), depth in depth_by_pixel.items():
        value = int(255 * depth / max(max_depth, 1e-6))
        pixels[x, y] = (value, int(value * 0.45), 255 - value, 255)
    image.save(path, format="PNG")


def _write_primitive_assignment(
    size: tuple[int, int],
    owner_by_pixel: dict[Pixel, int],
    assignments: list[PrimitiveAssignment],
    path: Path,
) -> None:
    palette = {
        "cuboid": (150, 150, 150, 255),
        "rounded_cuboid": (90, 190, 235, 255),
        "ellipsoid": (255, 190, 80, 255),
        "capsule": (180, 220, 90, 255),
        "tapered_prism": (255, 120, 100, 255),
        "shell": (30, 30, 30, 255),
        "rigid_slab": (210, 210, 95, 255),
    }
    by_id = {item.part_id: item for item in assignments}
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for (x, y), part_id in owner_by_pixel.items():
        assignment = by_id[part_id]
        pixels[x, y] = palette.get(assignment.primitive_type, (255, 0, 255, 255))
    image.save(path, format="PNG")


def _write_outline_shell(
    size: tuple[int, int],
    owner_by_pixel: dict[Pixel, int],
    assignments: list[PrimitiveAssignment],
    path: Path,
) -> None:
    by_id = {item.part_id: item for item in assignments}
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for (x, y), part_id in owner_by_pixel.items():
        if by_id[part_id].primitive_type == "shell":
            pixels[x, y] = (255, 255, 255, 255)
    image.save(path, format="PNG")


def _write_occupancy_slices(
    size: tuple[int, int],
    occupancy: set[tuple[int, int, int]],
    slices_dir: Path,
    sheet_path: Path,
) -> None:
    if not occupancy:
        Image.new("RGBA", size, (0, 0, 0, 0)).save(sheet_path, format="PNG")
        return
    max_z = max(z for _x, _y, z in occupancy)
    frames = []
    for z in range(max_z + 1):
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for x, y, voxel_z in occupancy:
            if voxel_z == z:
                shade = 60 + int(180 * z / max(max_z, 1))
                draw.point((x, y), fill=(shade, shade, shade, 255))
        image.save(slices_dir / f"slice_{z:03d}.png", format="PNG")
        frames.append(image)
    sheet = Image.new("RGBA", (size[0] * len(frames), size[1]), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * size[0], 0))
    sheet.save(sheet_path, format="PNG")
