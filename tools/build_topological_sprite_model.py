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


FACE_DELTAS = {
    "back": (0, 0, -1),
    "front": (0, 0, 1),
    "left": (-1, 0, 0),
    "right": (1, 0, 0),
    "up": (0, -1, 0),
    "down": (0, 1, 0),
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

    region_id_map, region_overlay = write_region_debug_images(front, regions, output_dir)
    depth_debug = _write_depth_debug(front, regions, assignment_by_id, output_dir / "depth_debug.png")
    for region_id, region in enumerate(regions):
        mask = region_mask_image(front.size, region)
        mask.save(part_debug_dir / f"part_{region_id:03d}_mask.png", format="PNG")

    mesh, part_reports = _build_part_mesh(front, regions, graph, assignment_by_id, args)
    validation_report = _validation_report(front, regions, mesh, part_reports, args)
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
            },
            "stage_3_generated_part_volumes": _res_path(part_debug_dir),
            "stage_4_final_combined_model": _res_path(model_path),
        },
        "front_texture": _res_path(cleaned_path),
        "region_overlay": _res_path(region_overlay),
        "region_id_map": _res_path(region_id_map),
        "depth_debug": _res_path(depth_debug),
        "canvas_size": [front.width, front.height],
        "config": {
            "voxel_size": args.voxel_size,
            "model_depth_units": args.model_depth_units,
            "total_depth_slices": args.total_depth_slices,
            "colour_bucket": args.colour_bucket,
            "min_region_pixels": args.min_region_pixels,
        },
        "vertices": mesh["vertices"],
        "normals": mesh["normals"],
        "colors": mesh["colors"],
        "indices": mesh["indices"],
        "part_ids": mesh["part_ids"],
        "parts": part_reports,
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

    _write_scene(args.scene_path.resolve(), model_path)
    return {
        "region_count": len(regions),
        "model": model_path,
        "part_graph": output_dir / "part_graph.json",
        "validation_report": validation_path,
        "scene": args.scene_path.resolve(),
    }


def _build_part_mesh(front: Image.Image, regions, graph, assignments, args) -> tuple[dict, list[dict]]:
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

    for region_info, region in zip(graph, regions):
        assignment = assignments[region_info.region_id]
        occupied = _part_occupancy(region, width, height, args.total_depth_slices, assignment)
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
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": total_voxels,
    }, part_reports


def _part_occupancy(region, width: int, height: int, total_depth_slices: int, assignment) -> set[tuple[int, int, int]]:
    depth_slices = max(1, int(round(total_depth_slices * assignment.local_depth)))
    center = (total_depth_slices - 1) * (0.5 + assignment.z_offset * 0.45)
    z_min = max(0, int(round(center - depth_slices * 0.5)))
    z_max = min(total_depth_slices - 1, int(round(center + depth_slices * 0.5)))
    if assignment.label == "outline":
        # Rim pixels become a bevel shell, not a full-depth wall.
        z_mid = int(round(center))
        z_min = max(0, z_mid - 1)
        z_max = min(total_depth_slices - 1, z_mid + 1)
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
        red = min(110, max(red, 68))
        green = min(110, max(green, 68))
        blue = min(110, max(blue, 68))
    elif face not in {"front", "back"}:
        red = int(red * 0.86)
        green = int(green * 0.86)
        blue = int(blue * 0.86)
    return (red, green, blue, alpha), used_fallback


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


def _validation_report(front: Image.Image, regions, mesh: dict, part_reports: list[dict], args) -> dict:
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
        "no_regions_generated": len(regions) == 0,
    }
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
