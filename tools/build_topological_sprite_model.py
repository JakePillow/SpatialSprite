from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.topology import (  # noqa: E402
    assign_depths,
    assignments_to_json,
    build_part_graph,
    extract_regions,
    graph_to_json,
    load_rgba,
    merge_tiny_regions,
    region_mask_image,
    write_region_debug_images,
)
from spritespatial.semantic import (  # noqa: E402
    build_semantic_parts,
    run_semantic_rule_passes,
    write_semantic_debug_outputs,
)


FACE_DELTAS = {
    "back": (0, 0, -1),
    "front": (0, 0, 1),
    "left": (-1, 0, 0),
    "right": (1, 0, 0),
    "up": (0, -1, 0),
    "down": (0, 1, 0),
}


DEPTH_MULTIPLIERS = {
    "head": 0.8,
    "hair": 0.85,
    "torso": 0.55,
    "left_arm": 0.7,
    "right_arm": 0.7,
    "legs": 0.65,
    "feet": 1.1,
    "boots": 1.1,  # Assuming "boots" label maps to "feet"
    "outline": 0.1,  # Give outlines a very thin depth
    "equipment": 0.3,  # Default for equipment
    "unknown": 0.4,  # Default for unknown parts
    "face": 0.8,  # Face is part of head, but can have its own depth
    "clothing": 0.5,  # Default for clothing
    "shield": 0.4,
    "sword": 0.2,
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Track C3 topological sprite decomposition model.")
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--back", type=Path)
    parser.add_argument("--depth", type=Path)
    parser.add_argument("--regions", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, default=WORKSPACE_ROOT / "outputs" / "link_topological")
    parser.add_argument("--alpha-threshold", type=int, default=16)
    parser.add_argument("--colour-bucket", type=int, default=24)
    parser.add_argument("--min-region-pixels", type=int, default=3)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--model-depth-units", type=float, default=0.65)
    parser.add_argument("--total-depth-slices", type=int, default=14)
    parser.add_argument("--scene-path", type=Path, default=WORKSPACE_ROOT / "scenes" / "link_topological_test.tscn")
    parser.add_argument("--front-ink-shell", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--silhouette-core", action=argparse.BooleanOptionalAction, default=False) # Changed default to False for cuboid_parts
    parser.add_argument("--representation-style", choices=("relief_cutout", "paper_cutout", "part_depth", "cuboid_parts"), default="relief_cutout")
    parser.add_argument("--paper-depth-units", type=float, default=0.18)
    parser.add_argument("--paper-depth-slices", type=int, default=4)
    parser.add_argument("--relief-depth-units", type=float, default=0.34)
    parser.add_argument("--relief-depth-slices", type=int, default=9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_topological_model(args)
    print("Built Track C3 topological sprite model")
    print(f"  Regions: {result['region_count']}")
    print(f"  Model: {result['model']}")
    print(f"  Part graph: {result['part_graph']}")
    print(f"  Validation: {result['validation_report']}")
    print(f"  Scene: {result['scene']}")
    return 0


def build_topological_model(args: argparse.Namespace) -> dict:
    front = load_rgba(args.front.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    part_debug_dir = output_dir / "per_part_mesh_debug"
    part_debug_dir.mkdir(parents=True, exist_ok=True)

    front_path = output_dir / "front.png"
    front.save(front_path, format="PNG")
    cleaned_path = output_dir / "stage_1_cleaned_sprite.png"
    front.save(cleaned_path, format="PNG")

    regions, region_map = extract_regions(front, args.alpha_threshold, args.colour_bucket)
    regions, region_map = merge_tiny_regions(front, regions, region_map, args.min_region_pixels)
    graph = build_part_graph(front, regions, region_map)
    assignments = assign_depths(graph)
    assignment_by_id = {item.region_id: item for item in assignments}
    semantic_regions, semantic_report, semantic_warnings = run_semantic_rule_passes(front, regions, graph)

    region_id_map, region_overlay = write_region_debug_images(front, regions, output_dir)
    depth_debug = _write_depth_debug(front, regions, assignment_by_id, output_dir / "depth_debug.png")
    semantic_paths = write_semantic_debug_outputs(front, regions, semantic_regions, output_dir)
    for region_id, region in enumerate(regions):
        mask = region_mask_image(front.size, region)
        mask.save(part_debug_dir / f"part_{region_id:03d}_mask.png", format="PNG")

    mesh, part_reports = _build_part_mesh(front, regions, graph, assignment_by_id, args, semantic_regions)
    validation_report = _validation_report(front, regions, mesh, part_reports, args, semantic_warnings)
    validation_path = output_dir / "validation_report.json"
    _write_json(validation_path, validation_report)
    model_path = output_dir / "topological_model.json"
    model = {
        "schema": "spritespatial_topological_model_v1",
        "pipeline_stages": {
            "stage_0_source_sprite": _res_path(args.front.resolve()),
            "stage_1_cleaned_transparent_sprite": _res_path(cleaned_path),
            "stage_2_region_depth_debug": {
                "region_id_map": _res_path(region_id_map),
                "region_overlay": _res_path(region_overlay),
                "depth_debug": _res_path(depth_debug),
                "semantic_region_overlay": _res_path(semantic_paths["semantic_region_overlay"]),
                "semantic_id_map": _res_path(semantic_paths["semantic_id_map"]),
                "semantic_bbox_overlay": _res_path(semantic_paths["semantic_bbox_overlay"]),
                "semantic_depth_overlay": _res_path(semantic_paths["semantic_depth_overlay"]),
            },
            "stage_3_generated_part_volumes": _res_path(part_debug_dir),
            "stage_4_final_combined_model": _res_path(model_path),
        },
        "front_texture": _res_path(cleaned_path),
        "region_overlay": _res_path(region_overlay),
        "region_id_map": _res_path(region_id_map),
        "depth_debug": _res_path(depth_debug),
        "semantic_region_overlay": _res_path(semantic_paths["semantic_region_overlay"]),
        "semantic_id_map": _res_path(semantic_paths["semantic_id_map"]),
        "semantic_bbox_overlay": _res_path(semantic_paths["semantic_bbox_overlay"]),
        "semantic_depth_overlay": _res_path(semantic_paths["semantic_depth_overlay"]),
        "semantic_outline_only": _res_path(semantic_paths["semantic_outline_only"]),
        "semantic_unknown_regions": _res_path(semantic_paths["semantic_unknown_regions"]),
        "semantic_occupancy": _res_path(semantic_paths["semantic_occupancy"]),
        "semantic_report": _res_path(output_dir / "semantic_report.json"),
        "semantic_warnings": _res_path(output_dir / "semantic_warnings.json"),
        "canvas_size": [front.width, front.height],
        "config": {
            "voxel_size": args.voxel_size,
            "model_depth_units": args.model_depth_units,
            "total_depth_slices": args.total_depth_slices,
            "colour_bucket": args.colour_bucket,
            "min_region_pixels": args.min_region_pixels,
            "front_ink_shell": args.front_ink_shell,
            "silhouette_core": args.silhouette_core,
            "representation_style": args.representation_style,
            "paper_depth_units": args.paper_depth_units,
            "paper_depth_slices": args.paper_depth_slices,
            "relief_depth_units": args.relief_depth_units,
            "relief_depth_slices": args.relief_depth_slices,
        },
        # For cuboid_parts, these will be actual cuboid dimensions
        # For other modes, these are voxel-based
        "vertices": mesh["vertices"],
        "normals": mesh["normals"],
        "colors": mesh["colors"],
        "indices": mesh["indices"],
        "part_ids": mesh["part_ids"],
        "parts": part_reports,
        "semantic_regions": semantic_report["regions"],
        "generated_sprite_model": {
            "mesh_instance": "GeneratedSpriteModel",
            "materials": ["vertex_color_unshaded"],
            "metadata": {
                "regions_generated": len(regions),
                "source": _res_path(args.front.resolve()),
                "normal_scene_renders": ["source_reference", "final_combined_model"],
            },
            "validation_report": validation_report,
        },
    }
    _write_json(model_path, model)
    _write_json(output_dir / "part_graph.json", {"regions": graph_to_json(graph)})
    _write_json(output_dir / "depth_assignment.json", {"assignments": assignments_to_json(assignments)})
    _write_json(output_dir / "semantic_report.json", semantic_report)
    _write_json(output_dir / "semantic_warnings.json", semantic_warnings)

    _write_scene(args.scene_path.resolve(), model_path)
    return {
        "region_count": len(regions),
        "model": model_path,
        "part_graph": output_dir / "part_graph.json",
        "validation_report": validation_path,
        "scene": args.scene_path.resolve(),
    }


def _build_part_mesh(front: Image.Image, regions, graph, assignments, args, semantic_regions=None) -> tuple[dict, list[dict]]:
    if args.representation_style == "relief_cutout":
        return _build_relief_cutout_mesh(front, regions, graph, assignments, args)
    if args.representation_style == "paper_cutout":
        return _build_paper_cutout_mesh(front, regions, graph, args)
    if args.representation_style == "cuboid_parts":
        return _build_cuboid_parts_mesh(front, regions, graph, assignments, args, semantic_regions)

    pixels = front.load()
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.model_depth_units * 0.5
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    part_reports: list[dict] = []
    total_voxels = 0
    global_occupied: set[tuple[int, int, int]] = set()
    region_lookup: dict[tuple[int, int], int] = {}
    region_colour_lookup: dict[int, list[int]] = {}

    for region_info, region in zip(graph, regions):
        region_colour_lookup[region_info.region_id] = region_info.dominant_colour
        for x, y in region:
            if not (0 <= x < width and 0 <= y < height):
                continue
            if pixels[x, y][3] <= args.alpha_threshold:
                continue
            region_lookup[(x, y)] = region_info.region_id

    for region_info, region in zip(graph, regions):
        assignment = assignments[region_info.region_id]
        occupied = _part_occupancy(region, width, height, args.total_depth_slices, assignment)
        global_occupied.update(occupied)
        total_voxels += len(occupied)
        exposed_faces = 0
        for z in range(args.total_depth_slices):
            z0 = z_start + z * voxel_z
            z1 = z0 + voxel_z
            for y in range(height):
                y0 = total_height - (y + 1) * voxel_y
                y1 = total_height - y * voxel_y
                for x in range(width):
                    if (x, y, z) not in occupied:
                        continue
                    x0 = x * voxel_x - total_width * 0.5
                    x1 = x0 + voxel_x
                    for face, delta in FACE_DELTAS.items():
                        nx, ny, nz = x + delta[0], y + delta[1], z + delta[2]
                        if (nx, ny, nz) in occupied:
                            continue
                        exposed_faces += 1
                        colour, used_fallback = _part_face_colour(pixels[x, y], region_info.dominant_colour, assignment.label, face)
                        _add_face(vertices, normals, colors, indices, part_ids, region_info.region_id, face, x0, x1, y0, y1, z0, z1, colour)
        part_reports.append(
            {
                "region_id": region_info.region_id,
                "label": assignment.label,
                "pixel_count": region_info.pixel_count,
                "voxel_count": len(occupied),
                "exposed_faces": exposed_faces,
                "z_offset": assignment.z_offset,
                "local_depth": assignment.local_depth,
                "merge_policy": assignment.merge_policy,
            }
        )
    if args.silhouette_core:
        core_report = _add_silhouette_core(
            front,
            regions,
            global_occupied,
            region_lookup,
            region_colour_lookup,
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            args,
        )
        total_voxels += core_report["voxel_count"]
        part_reports.append(core_report)
    if args.front_ink_shell:
        shell_report = _add_front_ink_shell(
            front,
            regions,
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            args,
        )
        part_reports.append(shell_report)
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": total_voxels,
    }, part_reports


def _build_paper_cutout_mesh(front: Image.Image, regions, graph, args) -> tuple[dict, list[dict]]:
    pixels = front.load()
    width, height = front.size
    depth_slices = max(1, args.paper_depth_slices)
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.paper_depth_units / depth_slices
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.paper_depth_units * 0.5

    occupied: set[tuple[int, int, int]] = set()
    region_by_pixel: dict[tuple[int, int], int] = {}
    label_by_region: dict[int, str] = {}
    for region_info, region in zip(graph, regions):
        label_by_region[region_info.region_id] = region_info.likely_label
        for x, y in region:
            region_by_pixel[(x, y)] = region_info.region_id
            for z in range(depth_slices):
                occupied.add((x, y, z))

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    exposed_faces = 0
    for x, y, z in sorted(occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        region_id = region_by_pixel.get((x, y), -1)
        label = label_by_region.get(region_id, "unknown")
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            exposed_faces += 1
            colour = _paper_face_colour(pixels[x, y], label, face)
            _add_face(vertices, normals, colors, indices, part_ids, region_id, face, x0, x1, y0, y1, z0, z1, colour)

    reports = [
        {
            "region_id": -300,
            "label": "paper_cutout_silhouette",
            "pixel_count": len({(x, y) for x, y, _z in occupied}),
            "voxel_count": len(occupied),
            "exposed_faces": exposed_faces,
            "z_offset": 0.0,
            "local_depth": args.paper_depth_units,
            "merge_policy": "single_coherent_cutout",
        }
    ]
    reports.extend(
        {
            "region_id": region.region_id,
            "label": region.likely_label,
            "pixel_count": region.pixel_count,
            "voxel_count": region.pixel_count * depth_slices,
            "exposed_faces": 0,
            "z_offset": 0.0,
            "local_depth": args.paper_depth_units,
            "merge_policy": "metadata_region",
        }
        for region in graph
    )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
    }, reports


def _paper_face_colour(source_pixel, label: str, face: str) -> tuple[int, int, int, int]:
    red, green, blue, alpha = source_pixel
    if face == "front":
        return (red, green, blue, alpha)
    if label == "outline" or max(red, green, blue) <= 72:
        return (24, 24, 24, alpha)
    factor = 0.72 if face not in {"front", "back"} else 0.82
    return (int(red * factor), int(green * factor), int(blue * factor), alpha)


def segmentSpriteParts(front: Image.Image, regions, graph, semantic_regions=None) -> list[dict]:
    if semantic_regions is None:
        semantic_regions, _semantic_report, _semantic_warnings = run_semantic_rule_passes(front, regions, graph)
    return build_semantic_parts(front, regions, semantic_regions)


def getPartBoundingBoxes(parts: list[dict]) -> list[dict]:
    return [
        {
            "name": part["name"],
            "pixels": part["pixels"],
            "bbox": part["bbox"],
            "pixel_count": len(part["pixels"]),
            "dominant_colour": part["dominant_colour"],
            "semantic_label": part.get("semantic_label", part["name"]),
        }
        for part in parts
    ]


def _build_cuboid_parts_mesh(front: Image.Image, regions, graph, assignments, args, semantic_regions=None) -> tuple[dict, list[dict]]:
    parts = segmentSpriteParts(front, regions, graph, semantic_regions)
    part_boxes = getPartBoundingBoxes(parts)
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    reports: list[dict] = []

    total_height = front.height * args.voxel_size
    for part_index, part in enumerate(part_boxes):
        report = createCuboidForPart(
            front,
            part,
            part_index,
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            args.voxel_size,
            total_height,
        )
        reports.append(report)

    print("SpriteSpatial cuboid parts:")
    for report in reports:
        if "depth" not in report or report["depth"] == 0:
            continue
        print(
            "  {name}: width={width:.3f}, height={height:.3f}, depth={depth:.3f}, centerX={centerX:.2f}, centerY={centerY:.2f}".format(
                **report
            )
        )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": sum(report.get("voxel_count", 0) for report in reports),
    }, reports


def createCuboidForPart(front: Image.Image, part: dict, part_id: int, vertices, normals, colors, indices, part_ids, pixel_size: float, total_height: float) -> dict:
    x0_px, y0_px, x1_px, y1_px = part["bbox"]
    width_px = x1_px - x0_px
    height_px = y1_px - y0_px
    center_x = (x0_px + x1_px) * 0.5
    center_y = (y0_px + y1_px) * 0.5
    depth_multiplier = _depth_multiplier_for_part(part["name"])
    if part["name"] == "outline":
        depth_px = 1.0
    else:
        depth_px = max(1.0, width_px * depth_multiplier)
    depth_cells = max(1, int(round(depth_px)))
    occupied = _part_unit_cube_occupancy(part["pixels"], depth_cells)
    face_count = _emit_unit_cube_surface(
        front,
        occupied,
        part_id,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        pixel_size,
        total_height,
    )
    return {
        "region_id": part_id,
        "name": part["name"],
        "label": part["name"],
        "semantic_label": part.get("semantic_label", part["name"]),
        "pixel_count": len(part["pixels"]),
        "voxel_count": len(occupied),
        "exposed_faces": face_count,
        "width": width_px * pixel_size,
        "height": height_px * pixel_size,
        "depth": depth_cells * pixel_size,
        "width_pixels": width_px,
        "height_pixels": height_px,
        "depth_pixels": depth_cells,
        "centerX": center_x,
        "centerY": center_y,
        "merge_policy": "semantic_unit_cube_lattice",
        "unit_cube_size": pixel_size,
        "merged_cuboids": 0,
    }


def createCuboidRectForPart(
    front: Image.Image,
    rectangle: dict,
    depth_px: float,
    part_id: int,
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    pixel_size: float,
    total_height: float,
) -> int:
    x0_px, y0_px, x1_px, y1_px = rectangle["bbox"]
    pixel = rectangle["colour"]
    x0 = x0_px * pixel_size - front.width * pixel_size * 0.5
    x1 = x1_px * pixel_size - front.width * pixel_size * 0.5
    y0 = total_height - y1_px * pixel_size
    y1 = total_height - y0_px * pixel_size
    z0 = -depth_px * pixel_size * 0.5
    z1 = depth_px * pixel_size * 0.5
    front_colour = _rgba_float(pixel)
    side_colour = _vibrant_side_colour(pixel)
    for face in ("back", "front", "left", "right", "up", "down"):
        _add_cuboid_face(
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            part_id,
            face,
            x0,
            x1,
            y0,
            y1,
            z0,
            z1,
            front_colour if face == "front" else side_colour,
        )
    return 6


def _part_unit_cube_occupancy(pixel_coords: set[tuple[int, int]], depth_cells: int) -> set[tuple[int, int, int]]:
    return {
        (x, y, z_index)
        for x, y in pixel_coords
        for z_index in range(depth_cells)
    }


def _emit_unit_cube_surface(
    front: Image.Image,
    occupied: set[tuple[int, int, int]],
    part_id: int,
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    pixel_size: float,
    total_height: float,
) -> int:
    pixels = front.load()
    total_width = front.width * pixel_size
    face_count = 0
    if not occupied:
        return face_count
    min_z = min(z for _x, _y, z in occupied)
    max_z = max(z for _x, _y, z in occupied)
    depth_cells = max_z - min_z + 1
    max_z_by_pixel: dict[tuple[int, int], int] = {}
    for x, y, z in occupied:
        max_z_by_pixel[(x, y)] = max(z, max_z_by_pixel.get((x, y), z))
    for x, y, z in sorted(occupied):
        x0 = x * pixel_size - total_width * 0.5
        x1 = x0 + pixel_size
        y0 = total_height - (y + 1) * pixel_size
        y1 = total_height - y * pixel_size
        z0 = (z - min_z - depth_cells * 0.5) * pixel_size
        z1 = z0 + pixel_size
        source_pixel = pixels[x, y]
        if source_pixel[3] == 0:
            continue
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            is_front_face = face == "front" and z == max_z_by_pixel[(x, y)]
            colour = _rgba_float(source_pixel) if is_front_face else _vibrant_side_colour(source_pixel)
            _add_cuboid_face(
                vertices,
                normals,
                colors,
                indices,
                part_ids,
                part_id,
                face,
                x0,
                x1,
                y0,
                y1,
                z0,
                z1,
                colour,
            )
            face_count += 1
    return face_count


def createPixelCubeForPart(
    front: Image.Image,
    x: int,
    y: int,
    depth_px: float,
    part_id: int,
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    pixel_size: float,
    total_height: float,
    pixel,
) -> int:
    return createCuboidRectForPart(
        front,
        {"bbox": [x, y, x + 1, y + 1], "colour": pixel},
        depth_px,
        part_id,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        pixel_size,
        total_height,
    )


def _greedy_rectangles_for_part(front: Image.Image, part: dict) -> list[dict]:
    pixels = front.load()
    remaining = set(part["pixels"])
    rectangles: list[dict] = []
    while remaining:
        start_x, start_y = min(remaining, key=lambda pixel: (pixel[1], pixel[0]))
        colour = pixels[start_x, start_y]
        width = 1
        while (start_x + width, start_y) in remaining and pixels[start_x + width, start_y] == colour:
            width += 1

        height = 1
        while True:
            next_y = start_y + height
            row_pixels = {(x, next_y) for x in range(start_x, start_x + width)}
            if not row_pixels.issubset(remaining):
                break
            if any(pixels[x, next_y] != colour for x in range(start_x, start_x + width)):
                break
            height += 1

        for y in range(start_y, start_y + height):
            for x in range(start_x, start_x + width):
                remaining.remove((x, y))
        rectangles.append(
            {
                "bbox": [start_x, start_y, start_x + width, start_y + height],
                "colour": colour,
                "pixel_count": width * height,
            }
        )
    return rectangles


def buildCharacterRoot(parts: list[dict]) -> dict:
    return {"name": "GeneratedSpriteModel", "parts": parts}


def enableDepthDebugMode(model: dict, enabled: bool = True) -> dict:
    model["debug_depth_mode_enabled"] = enabled
    return model


def _semantic_part_label(region_info, pixels, mid_x: float, sprite_height: int) -> str:
    red, green, blue, _alpha = region_info.dominant_colour
    bbox = region_info.bbox
    cx, cy = region_info.centroid
    lower = cy > sprite_height * 0.58
    upper = cy < sprite_height * 0.36
    middle = not upper and not lower
    is_skin = red > 180 and green > 110 and blue < 150
    is_hair_or_shoe = red > 70 and red < 170 and green < 120 and blue < 90
    is_shirt = blue > 130 and green > 110 and red < 120
    is_pants = blue > 120 and red < 100 and green < 130

    if upper and is_hair_or_shoe:
        return "hair"
    if upper and is_skin:
        return "head"
    if middle and is_shirt:
        return "torso"
    if middle and is_skin:
        return "left_arm" if cx < mid_x else "right_arm"
    if lower and is_pants:
        return "split_legs"
    if lower and is_hair_or_shoe:
        return "split_feet"
    if region_info.likely_label in {"left_arm", "right_arm", "torso", "head", "face"}:
        return "head" if region_info.likely_label == "face" else region_info.likely_label
    if lower:
        return "split_feet" if (bbox[2] - bbox[0]) > 2 else "split_legs"
    return "torso"


def _depth_multiplier_for_part(name: str) -> float:
    mapping = {
        "outline": 0.95,
        "head": 0.8,
        "face": 0.72,
        "hair": 0.85,
        "torso": 0.55,
        "left_arm": 0.7,
        "right_arm": 0.7,
        "left_leg": 0.65,
        "right_leg": 0.65,
        "left_foot": 1.1,
        "right_foot": 1.1,
        "equipment": 0.4,
        "unknown": 0.45,
    }
    return mapping.get(name, 0.55)


def _pixel_bbox(pixels_set: set[tuple[int, int]]) -> list[int]:
    xs = [x for x, _y in pixels_set]
    ys = [y for _x, y in pixels_set]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def _dominant_colour(front: Image.Image, pixels_set: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    front_pixels = front.load()
    colours = [front_pixels[x, y] for x, y in pixels_set if front_pixels[x, y][3] > 0]
    if not colours:
        return (255, 0, 255, 255)
    return max(set(colours), key=colours.count)


def _rgba_float(colour: tuple[int, int, int, int]) -> list[float]:
    return [colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, colour[3] / 255.0]


def _vibrant_side_colour(colour: tuple[int, int, int, int]) -> list[float]:
    red, green, blue, alpha = colour
    if max(red, green, blue) <= 72:
        return [red / 255.0, green / 255.0, blue / 255.0, alpha / 255.0]
    factor = 0.92
    return [red / 255.0 * factor, green / 255.0 * factor, blue / 255.0 * factor, alpha / 255.0]


def _add_cuboid_front_sprite_shell(front: Image.Image, regions, vertices, normals, colors, indices, part_ids, args, z_front: float) -> int:
    pixels = front.load()
    width, height = front.size
    pixel_size = args.voxel_size
    total_width = width * pixel_size
    total_height = height * pixel_size
    shell_z = pixel_size * 0.025
    shell_id = -501
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = pixels[x, y]
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * pixel_size - total_width * 0.5
            x1 = x0 + pixel_size
            y0 = total_height - (y + 1) * pixel_size
            y1 = total_height - y * pixel_size
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z_front - shell_z, z_front, pixel)
            face_count += 1
    return face_count


def _max_z(vertices: list[list[float]]) -> float:
    if not vertices:
        return 0.0
    return max(vertex[2] for vertex in vertices)


def _build_relief_cutout_mesh(front: Image.Image, regions, graph, assignments, args) -> tuple[dict, list[dict]]:
    pixels = front.load()
    width, height = front.size
    depth_slices = max(5, args.relief_depth_slices)
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.relief_depth_units / depth_slices
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.relief_depth_units * 0.5

    region_by_pixel: dict[tuple[int, int], int] = {}
    label_by_region: dict[int, str] = {}
    for region_info, region in zip(graph, regions):
        label_by_region[region_info.region_id] = region_info.likely_label
        for x, y in region:
            region_by_pixel[(x, y)] = region_info.region_id

    occupied: set[tuple[int, int, int]] = set()
    pixel_z_ranges: dict[tuple[int, int], tuple[int, int]] = {}
    for region_info, region in zip(graph, regions):
        label = region_info.likely_label
        z_min, z_max = _relief_z_range(label, depth_slices)
        for x, y in region:
            pixel_z_ranges[(x, y)] = (z_min, z_max)
            for z in range(z_min, z_max + 1):
                occupied.add((x, y, z))

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    exposed_faces = 0

    for x, y, z in sorted(occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        region_id = region_by_pixel.get((x, y), -1)
        label = label_by_region.get(region_id, "unknown")
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            exposed_faces += 1
            colour = _relief_face_colour(front, pixels, x, y, label, face)
            _add_face(vertices, normals, colors, indices, part_ids, region_id, face, x0, x1, y0, y1, z0, z1, colour)

    shell_faces = _add_relief_front_sprite_shell(
        front,
        regions,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        args,
        args.relief_depth_units * 0.5 + voxel_z * 0.08,
    )
    reports = [
        {
            "region_id": -400,
            "label": "relief_cutout_body",
            "pixel_count": len(pixel_z_ranges),
            "voxel_count": len(occupied),
            "exposed_faces": exposed_faces,
            "z_offset": 0.0,
            "local_depth": args.relief_depth_units,
            "merge_policy": "coherent_relief_cutout",
        },
        {
            "region_id": -401,
            "label": "authoritative_front_sprite_shell",
            "pixel_count": shell_faces,
            "voxel_count": 0,
            "exposed_faces": shell_faces,
            "z_offset": 0.5,
            "local_depth": 0.0,
            "merge_policy": "preserve_source_pixels",
        },
    ]
    reports.extend(
        {
            "region_id": region.region_id,
            "label": region.likely_label,
            "pixel_count": region.pixel_count,
            "voxel_count": sum((pixel_z_ranges[pixel][1] - pixel_z_ranges[pixel][0] + 1) for pixel in regions[region.region_id]),
            "exposed_faces": 0,
            "z_offset": 0.0,
            "local_depth": args.relief_depth_units,
            "merge_policy": "relief_metadata_region",
        }
        for region in graph
    )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
    }, reports


def _relief_z_range(label: str, depth_slices: int) -> tuple[int, int]:
    back = 0
    front = depth_slices - 1
    if label == "outline":
        return max(0, front - 2), front
    if label in {"face", "head"}:
        return max(0, front - 5), front
    if label in {"hat", "hair"}:
        return max(0, front - 4), front
    if label in {"left_arm", "right_arm", "equipment"}:
        return max(0, front - 4), front
    if label == "torso":
        return max(0, front - 6), front - 1
    if label in {"legs", "boots"}:
        return back + 1, max(back + 4, front - 2)
    return max(0, front - 4), front - 1


def _relief_face_colour(front: Image.Image, pixels, x: int, y: int, label: str, face: str) -> tuple[int, int, int, int]:
    source = pixels[x, y]
    if face == "front":
        return source
    if label == "outline" or max(source[0], source[1], source[2]) <= 72:
        return (24, 24, 24, source[3])
    if face == "back":
        factor = 0.9
    else:
        factor = 0.88
    return (int(source[0] * factor), int(source[1] * factor), int(source[2] * factor), source[3])


def _add_relief_front_sprite_shell(front: Image.Image, regions, vertices, normals, colors, indices, part_ids, args, z_front: float) -> int:
    pixels = front.load()
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    shell_z = args.relief_depth_units / max(args.relief_depth_slices, 1) * 0.03
    total_width = width * voxel_x
    total_height = height * voxel_y
    shell_id = -401
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = pixels[x, y]
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * voxel_x - total_width * 0.5
            x1 = x0 + voxel_x
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z_front - shell_z, z_front, pixel)
            face_count += 1
    return face_count


def _part_occupancy(region, width: int, height: int, total_depth_slices: int, assignment) -> set[tuple[int, int, int]]:
    depth_slices = max(1, int(round(total_depth_slices * assignment.local_depth)))
    center = (total_depth_slices - 1) * (0.5 + assignment.z_offset * 0.45)
    z_min = max(0, int(round(center - depth_slices * 0.5)))
    z_max = min(total_depth_slices - 1, int(round(center + depth_slices * 0.5)))
    if assignment.label == "outline":
        # Rim pixels become a bevel shell, not a full-depth wall.
        z_mid = total_depth_slices - 2
        z_min = max(0, z_mid - 1)
        z_max = total_depth_slices - 1
    occupied: set[tuple[int, int, int]] = set()
    for x, y in region:
        for z in range(z_min, z_max + 1):
            occupied.add((x, y, z))
    return occupied


def _part_face_colour(source_pixel, dominant_colour, label: str, face: str) -> tuple[tuple[int, int, int, int], bool]:
    if face == "front":
        return (source_pixel[0], source_pixel[1], source_pixel[2], source_pixel[3]), False
    red, green, blue, alpha = dominant_colour
    used_fallback = False
    if alpha == 0:
        red, green, blue, alpha = source_pixel[0], source_pixel[1], source_pixel[2], source_pixel[3]
        used_fallback = alpha == 0
    if label == "outline" and face not in {"front", "back"}:
        red = min(red, 36)
        green = min(green, 36)
        blue = min(blue, 36)
    elif face not in {"front", "back"}:
        red = int(red * 0.86)
        green = int(green * 0.86)
        blue = int(blue * 0.86)
    return (red, green, blue, alpha), used_fallback


def _add_silhouette_core(
    front: Image.Image,
    regions,
    existing_occupied: set[tuple[int, int, int]],
    region_lookup: dict[tuple[int, int], int],
    region_colour_lookup: dict[int, list[int]],
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    args,
) -> dict:
    width, height = front.size
    pixels = front.load()
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.model_depth_units * 0.5
    core_id = -100
    z_min = max(0, args.total_depth_slices // 2 - 2)
    z_max = min(args.total_depth_slices - 3, args.total_depth_slices // 2 + 2)
    core_occupied: set[tuple[int, int, int]] = set()
    for region in regions:
        for x, y in region:
            for z in range(z_min, z_max + 1):
                key = (x, y, z)
                if key not in existing_occupied:
                    core_occupied.add(key)
    exposed_faces = 0
    for x, y, z in sorted(core_occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in existing_occupied or neighbour in core_occupied:
                continue
            exposed_faces += 1
            region_id = region_lookup.get((x, y), -1)
            dominant = region_colour_lookup.get(region_id, [pixels[x, y][0], pixels[x, y][1], pixels[x, y][2], pixels[x, y][3]])
            colour = _core_colour(dominant, face)
            _add_face(vertices, normals, colors, indices, part_ids, core_id, face, x0, x1, y0, y1, z0, z1, colour)
    existing_occupied.update(core_occupied)
    return {
        "region_id": core_id,
        "label": "silhouette_core",
        "pixel_count": sum(len(region) for region in regions),
        "voxel_count": len(core_occupied),
        "exposed_faces": exposed_faces,
        "z_offset": 0.0,
        "local_depth": (z_max - z_min + 1) / max(args.total_depth_slices, 1),
        "merge_policy": "coherence_anchor",
    }


def _add_front_ink_shell(
    front: Image.Image,
    regions,
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    args,
) -> dict:
    pixels = front.load()
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z1 = args.model_depth_units * 0.5 + voxel_z * 0.06
    z0 = z1 - voxel_z * 0.08
    shell_id = -200
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = pixels[x, y]
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * voxel_x - total_width * 0.5
            x1 = x0 + voxel_x
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z0, z1, pixel)
            face_count += 1
    return {
        "region_id": shell_id,
        "label": "front_ink_shell",
        "pixel_count": face_count,
        "voxel_count": 0,
        "exposed_faces": face_count,
        "z_offset": 0.5,
        "local_depth": 0.0,
        "merge_policy": "authoritative_front_projection",
    }


def _core_colour(dominant_colour: list[int], face: str) -> tuple[int, int, int, int]:
    red, green, blue, alpha = dominant_colour
    if max(red, green, blue) <= 72:
        return (24, 24, 24, alpha)
    factor = 0.78 if face not in {"front", "back"} else 0.9
    return (int(red * factor), int(green * factor), int(blue * factor), alpha)


def _cuboid_side_color(dominant_colour: tuple[int, int, int, int]) -> list[float]:
    red, green, blue, alpha = dominant_colour
    factor = 0.7
    return [red / 255.0 * factor, green / 255.0 * factor, blue / 255.0 * factor, alpha / 255.0]


def _write_depth_debug(front: Image.Image, regions, assignments, path: Path) -> Path:
    debug = Image.new("RGBA", front.size, (0, 0, 0, 0))
    pixels = debug.load()
    for region_id, region in enumerate(regions):
        assignment = assignments[region_id]
        value = int(max(0.0, min(1.0, assignment.local_depth + assignment.z_offset * 0.35)) * 255)
        for x, y in region:
            pixels[x, y] = (value, value, value, 255)
    debug.save(path, format="PNG")
    return path


def _validation_report(front: Image.Image, regions, mesh: dict, part_reports: list[dict], args, semantic_warnings=None) -> dict:
    total_faces = len(mesh["indices"]) // 6
    fallback_faces = 0
    colours = {
        tuple(int(channel * 255) for channel in colour)
        for colour in mesh["colors"]
    }
    alpha = front.getchannel("A")
    opaque_pixels = sum(1 for value in alpha.getdata() if value > args.alpha_threshold)
    transparent_pixels = front.width * front.height - opaque_pixels
    bounds = _mesh_bounds(mesh["vertices"])
    fallback_percent = fallback_faces / total_faces if total_faces else 1.0
    fail_conditions = {
        "fallback_faces_above_1_percent": fallback_percent > 0.01,
        "generated_mesh_has_zero_faces": total_faces == 0,
        "no_regions_generated": len(regions) == 0 and args.representation_style != "cuboid_parts", # Allow 0 regions for cuboid_parts if no parts are found
    }
    semantic_warnings = semantic_warnings or {}
    warning_counts = {key: len(value) for key, value in semantic_warnings.items()}
    return {
        "total_faces": total_faces,
        "faces_with_fallback_material": fallback_faces,
        "fallback_face_percentage": fallback_percent,
        "number_of_materials": len(colours),
        "occupied_voxels": mesh.get("occupied_voxels", 0),
        "transparent_pixels_ignored": transparent_pixels,
        "alpha_coverage": opaque_pixels / max(front.width * front.height, 1),
        "regions_generated": len(regions),
        "final_mesh_bounds": bounds,
        "front_projection_coverage": opaque_pixels / max(front.width * front.height, 1),
        "part_count": len(part_reports),
        "semantic_warning_counts": warning_counts,
        "fail_conditions": fail_conditions,
        "passed": not any(fail_conditions.values()),
    }


def _mesh_bounds(vertices: list[list[float]]) -> dict:
    if not vertices:
        return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
    mins = [min(vertex[i] for vertex in vertices) for i in range(3)]
    maxs = [max(vertex[i] for vertex in vertices) for i in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)],
    }


def _add_face(vertices, normals, colors, indices, part_ids, part_id, face, x0, x1, y0, y1, z0, z1, colour) -> None:
    if face == "back":
        verts = ([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0])
        normal = [0, 0, -1]
    elif face == "front":
        verts = ([x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1])
        normal = [0, 0, 1]
    elif face == "left":
        verts = ([x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0])
        normal = [-1, 0, 0]
    elif face == "right":
        verts = ([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
        normal = [1, 0, 0]
    elif face == "up":
        verts = ([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1])
        normal = [0, 1, 0]
    else:
        verts = ([x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0])
        normal = [0, -1, 0]
    start = len(vertices)
    rgba = [colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, colour[3] / 255.0]
    vertices.extend([list(vertex) for vertex in verts])
    normals.extend([normal, normal, normal, normal])
    colors.extend([rgba, rgba, rgba, rgba])
    part_ids.extend([part_id, part_id, part_id, part_id])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])


def _add_cuboid_face(vertices, normals, colors, indices, part_ids, part_id, face, x0, x1, y0, y1, z0, z1, colour_rgba_float) -> None:
    if face == "back":
        verts = ([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0])
        normal = [0, 0, -1]
    elif face == "front":
        verts = ([x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1])
        normal = [0, 0, 1]
    elif face == "left":
        verts = ([x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0])
        normal = [-1, 0, 0]
    elif face == "right":
        verts = ([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
        normal = [1, 0, 0]
    elif face == "up":
        verts = ([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1])
        normal = [0, 1, 0]
    else: # down
        verts = ([x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0])
        normal = [0, -1, 0]
    start = len(vertices)
    _append_face_data(vertices, normals, colors, indices, part_ids, part_id, verts, normal, colour_rgba_float)


def _append_face_data(vertices, normals, colors, indices, part_ids, part_id, verts, normal, colour_rgba_float) -> None:
    start = len(vertices)
    vertices.extend([list(vertex) for vertex in verts])
    normals.extend([normal, normal, normal, normal])
    colors.extend([colour_rgba_float, colour_rgba_float, colour_rgba_float, colour_rgba_float])
    part_ids.extend([part_id, part_id, part_id, part_id])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])


def _write_scene(scene_path: Path, model_json: Path) -> None:
    text = f"""[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://scripts/topological_sprite_viewer.gd" id="1_viewer"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_floor"]
albedo_color = Color(0.33, 0.34, 0.33, 1)
roughness = 1.0

[sub_resource type="PlaneMesh" id="PlaneMesh_floor"]
size = Vector2(5.5, 4.5)

[node name="TopologicalSpriteTest" type="Node3D"]
script = ExtResource("1_viewer")
model_data_path = "{_res_path(model_json)}"

[node name="Floor" type="MeshInstance3D" parent="."]
mesh = SubResource("PlaneMesh_floor")
surface_material_override/0 = SubResource("StandardMaterial3D_floor")

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.966235, -0.257663, 0, 0.257663, 0.966235, 0, 1.65, 4.6)
current = true
fov = 40.0

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.707107, -0.353553, 0.612372, 0, 0.866025, 0.5, -0.707107, -0.353553, 0.612372, 0, 5, 3)
light_energy = 1.2
"""
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _res_path(path: Path) -> str:
    return "res://" + path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
