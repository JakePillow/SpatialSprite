from __future__ import annotations

from pathlib import Path


def write_front_back_model_test_scene(
    scene_path: Path,
    model_data_path: Path,
    viewer_script_path: Path,
) -> None:
    model_res = _to_res_path(model_data_path)
    script_res = _to_res_path(viewer_script_path)
    scene_text = f"""[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="{script_res}" id="1_viewer"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_floor"]
albedo_color = Color(0.33, 0.34, 0.33, 1)
roughness = 1.0

[sub_resource type="PlaneMesh" id="PlaneMesh_floor"]
size = Vector2(4.5, 4.5)

[node name="FrontBackModelTest" type="Node3D"]
script = ExtResource("1_viewer")
model_data_path = "{model_res}"
capture_output_dir = "res://outputs/front_back_model/captures"

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
    scene_path.write_text(scene_text, encoding="utf-8")


def _to_res_path(path: Path) -> str:
    relative = path.resolve().relative_to(Path.cwd().resolve())
    return "res://" + relative.as_posix()
