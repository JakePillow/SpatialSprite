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

from spritespatial.colour_field import build_colour_field  # noqa: E402
from spritespatial.depth_map import (  # noqa: E402
    alpha_mask,
    load_or_generate_depth,
    load_rgba_sprite,
    pad_to_shared_canvas,
    write_depth_outputs,
)
from spritespatial.mesh_surface import MeshBuildConfig, build_surface_mesh  # noqa: E402
from spritespatial.volume_builder import VolumeConfig, build_filled_volume  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Track C2 front/back depth-field volume.")
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--back", type=Path, required=True)
    parser.add_argument("-o", "--output-dir", type=Path, default=WORKSPACE_ROOT / "outputs" / "link_depth_volume")
    parser.add_argument("--front-depth", type=Path)
    parser.add_argument("--back-depth", type=Path)
    parser.add_argument("--regions", type=Path)
    parser.add_argument("--total-depth-slices", type=int, default=12)
    parser.add_argument("--front-relief-ratio", type=float, default=0.30)
    parser.add_argument("--core-ratio", type=float, default=0.40)
    parser.add_argument("--back-relief-ratio", type=float, default=0.30)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--model-depth-units", type=float, default=0.60)
    parser.add_argument("--simplify-mesh", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--side-colour-mode", choices=("nearest_front", "nearest_back", "blend_front_back", "nearest_valid_edge"), default="blend_front_back")
    parser.add_argument("--cleanup-mode", choices=("raw_debug", "merged_faces", "low_poly_soften"), default="merged_faces")
    parser.add_argument("--debug-show-zones", action="store_true")
    parser.add_argument("--alpha-threshold", type=int, default=16)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = build_depth_volume(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Built Track C2 depth-field volume")
    print(f"  Model: {result['model_json']}")
    print(f"  Scene: {WORKSPACE_ROOT / 'scenes' / 'link_depth_volume_test.tscn'}")
    print(f"  Validation: {result['validation_report']}")
    print(f"  Vertices: {result['mesh_report']['vertex_count']}")
    print(f"  Triangles: {result['mesh_report']['triangle_count']}")
    return 0


def build_depth_volume(args: argparse.Namespace) -> dict:
    front = load_rgba_sprite(args.front.resolve())
    back = load_rgba_sprite(args.back.resolve())
    front, back = pad_to_shared_canvas(front, back, args.alpha_threshold)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    front_path = output_dir / "front_aligned.png"
    back_path = output_dir / "back_aligned.png"
    front.save(front_path, format="PNG")
    back.save(back_path, format="PNG")

    front_depth = load_or_generate_depth(front, args.front_depth.resolve() if args.front_depth else None, args.alpha_threshold)
    back_depth = load_or_generate_depth(back, args.back_depth.resolve() if args.back_depth else None, args.alpha_threshold)
    depth_report = write_depth_outputs(front, back, front_depth, back_depth, output_dir, args.alpha_threshold)

    front_mask = alpha_mask(front, args.alpha_threshold)
    back_mask = alpha_mask(back, args.alpha_threshold)
    volume_config = VolumeConfig(
        total_depth_slices=args.total_depth_slices,
        front_relief_ratio=args.front_relief_ratio,
        core_ratio=args.core_ratio,
        back_relief_ratio=args.back_relief_ratio,
        voxel_size=args.voxel_size,
        alpha_threshold=args.alpha_threshold,
    )
    volume, volume_report = build_filled_volume(front_mask, back_mask, front_depth, back_depth, volume_config)
    colour_field, colour_report = build_colour_field(front, back, volume, mode=args.side_colour_mode, alpha_threshold=args.alpha_threshold)
    mesh, mesh_report = build_surface_mesh(
        volume,
        colour_field,
        MeshBuildConfig(
            voxel_size=args.voxel_size,
            model_depth_units=args.model_depth_units,
            simplify_mesh=args.simplify_mesh,
            cleanup_mode=args.cleanup_mode,
        ),
    )

    model_json = output_dir / "depth_volume_model.json"
    model_data = {
        "schema": "spritespatial_depth_volume_v1",
        "front_texture": _res_path(front_path),
        "back_texture": _res_path(back_path),
        "front_depth": _res_path(output_dir / "front_depth.png"),
        "back_depth": _res_path(output_dir / "back_depth.png"),
        "canvas_size": [front.width, front.height],
        "config": {
            "total_depth_slices": args.total_depth_slices,
            "front_relief_ratio": args.front_relief_ratio,
            "core_ratio": args.core_ratio,
            "back_relief_ratio": args.back_relief_ratio,
            "voxel_size": args.voxel_size,
            "model_depth_units": args.model_depth_units,
            "simplify_mesh": args.simplify_mesh,
            "side_colour_mode": args.side_colour_mode,
            "cleanup_mode": args.cleanup_mode,
            "debug_show_zones": args.debug_show_zones,
        },
        "vertices": mesh["vertices"],
        "normals": mesh["normals"],
        "colors": mesh["colors"],
        "indices": mesh["indices"],
    }
    _write_json(model_json, model_data)

    if args.regions:
        regions_data = json.loads(args.regions.read_text(encoding="utf-8"))
    else:
        regions_data = {"regions": [], "note": "Manual region masks supported later; depth maps are active now."}
    _write_json(output_dir / "regions.json", regions_data)

    validation_report = _validation_report(
        front,
        back,
        depth_report,
        volume_report,
        colour_report,
        mesh_report,
        output_dir,
    )
    validation_path = output_dir / "validation_report.json"
    _write_json(validation_path, validation_report)

    _write_scene(WORKSPACE_ROOT / "scenes" / "link_depth_volume_test.tscn", model_json)
    return {
        "model_json": model_json,
        "validation_report": validation_path,
        "mesh_report": mesh_report,
    }


def _validation_report(
    front: Image.Image,
    back: Image.Image,
    depth_report: dict,
    volume_report: dict,
    colour_report: dict,
    mesh_report: dict,
    output_dir: Path,
) -> dict:
    side_black = mesh_report["black_side_face_percentage"]
    fail_conditions = {
        "side_faces_default_black_above_5_percent": side_black > 0.05,
        "large_hollow_gaps": volume_report["hollow_gap_ratio"] > 0.20,
        "generated_mesh_has_zero_faces": mesh_report["exposed_face_count"] == 0,
        "front_back_dimensions_mismatch_without_padding": front.size != back.size,
    }
    return {
        "front_alpha_coverage": _alpha_coverage(front),
        "back_alpha_coverage": _alpha_coverage(back),
        "depth_map_coverage": {
            "front": depth_report["front"]["depth_coverage_ratio"],
            "back": depth_report["back"]["depth_coverage_ratio"],
        },
        "occupied_voxel_count": volume_report["occupied_voxel_count"],
        "exposed_face_count": mesh_report["exposed_face_count"],
        "internal_faces_removed": mesh_report["internal_faces_removed"],
        "percentage_of_black_side_faces": side_black,
        "number_of_side_faces_using_fallback_colour": colour_report["fallback_colour_count"],
        "material_colour_count": mesh_report["material_colour_count"],
        "bounding_box_dimensions": mesh_report["bounding_box_dimensions"],
        "front_back_projection_dimensions": [front.width, front.height],
        "hollow_gap_ratio": volume_report["hollow_gap_ratio"],
        "fail_conditions": fail_conditions,
        "passed": not any(fail_conditions.values()),
        "outputs": {
            "model": str(output_dir / "depth_volume_model.json"),
            "front_depth": str(output_dir / "front_depth.png"),
            "back_depth": str(output_dir / "back_depth.png"),
            "depth_debug_overlay": str(output_dir / "depth_debug_overlay.png"),
        },
    }


def _alpha_coverage(image: Image.Image) -> float:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    opaque = sum(1 for value in alpha.getdata() if value > 0)
    return opaque / (rgba.width * rgba.height)


def _write_scene(scene_path: Path, model_json: Path) -> None:
    text = f"""[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://scripts/depth_volume_viewer.gd" id="1_viewer"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_floor"]
albedo_color = Color(0.33, 0.34, 0.33, 1)
roughness = 1.0

[sub_resource type="PlaneMesh" id="PlaneMesh_floor"]
size = Vector2(4.5, 4.5)

[node name="LinkDepthVolumeTest" type="Node3D"]
script = ExtResource("1_viewer")
model_data_path = "{_res_path(model_json)}"
capture_output_dir = "res://outputs/link_depth_volume/captures"

[node name="Floor" type="MeshInstance3D" parent="."]
mesh = SubResource("PlaneMesh_floor")
surface_material_override/0 = SubResource("StandardMaterial3D_floor")

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.966235, -0.257663, 0, 0.257663, 0.966235, 0, 1.65, 4)
current = true
fov = 38.0

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.707107, -0.353553, 0.612372, 0, 0.866025, 0.5, -0.707107, -0.353553, 0.612372, 0, 5, 3)
light_energy = 1.35
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
