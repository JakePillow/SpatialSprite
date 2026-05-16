from __future__ import annotations

from pathlib import Path
from typing import Any

from spritespatial.asset_schema import AssetSchema
from spritespatial.validators import inspect_png


def _to_res_path(workspace_root: Path, target_path: Path) -> str:
    relative_path = target_path.resolve().relative_to(workspace_root.resolve())
    return f"res://{relative_path.as_posix()}"


def generate_gdscript(script_path: Path) -> None:
    script_path.write_text(_GDSCRIPT_TEMPLATE, encoding="utf-8")


def generate_scene_file(scene_path: Path, script_path: Path, asset: AssetSchema, workspace_root: Path) -> None:
    scene_data = _build_scene_text(scene_path, script_path, asset, workspace_root)
    scene_path.write_text(scene_data, encoding="utf-8")


def _build_scene_text(scene_path: Path, script_path: Path, asset: AssetSchema, workspace_root: Path) -> str:
    script_res_path = _to_res_path(workspace_root, script_path)
    script_id = "1_script"
    ext_resource_lines = [
        f"[ext_resource type=\"Script\" path=\"{script_res_path}\" id=\"{script_id}\"]"
    ]

    direction_textures: dict[str, str] = {}
    for index, direction in enumerate(asset.source_sprites, start=2):
        texture_path = _to_res_path(workspace_root, asset.sprite_path(direction))
        resource_id = f"{index}_{direction}"
        ext_resource_lines.append(
            f"[ext_resource type=\"Texture2D\" path=\"{texture_path}\" id=\"{resource_id}\"]"
        )
        direction_textures[direction] = resource_id

    collision = asset.collision
    height = float(collision.get("height", 1.6))
    radius = float(collision.get("radius", 0.35))
    pixel_scale = float(asset.pixel_scale)
    _, texture_height, _ = inspect_png(asset.sprite_path("front"))
    sprite_y_offset = texture_height * pixel_scale * 0.5
    collision_y_offset = height * 0.5

    body_name = asset.asset_name.capitalize()
    front_texture_id = direction_textures["front"]
    back_texture_id = direction_textures["back"]
    left_texture_id = direction_textures["left"]
    right_texture_id = direction_textures["right"]

    load_steps = len(ext_resource_lines) + 2

    lines: list[str] = []
    lines.append(f"[gd_scene load_steps={load_steps} format=3]")
    lines.extend(ext_resource_lines)
    lines.append("")
    lines.append("[sub_resource type=\"CapsuleShape3D\" id=\"CapsuleShape3D_hero\"]")
    lines.append(f"height = {height}")
    lines.append(f"radius = {radius}")
    lines.append("")
    lines.append(f"[node name=\"{body_name}\" type=\"CharacterBody3D\"]")
    lines.append(f"script = ExtResource(\"{script_id}\")")
    lines.append(f"front_texture = ExtResource(\"{front_texture_id}\")")
    lines.append(f"back_texture = ExtResource(\"{back_texture_id}\")")
    lines.append(f"left_texture = ExtResource(\"{left_texture_id}\")")
    lines.append(f"right_texture = ExtResource(\"{right_texture_id}\")")
    lines.append("transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0 )")
    lines.append("")
    lines.append("[node name=\"Sprite3D\" type=\"Sprite3D\" parent=\".\"]")
    lines.append(f"transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, {sprite_y_offset}, 0 )")
    lines.append(f"texture = ExtResource(\"{front_texture_id}\")")
    lines.append(f"pixel_size = {pixel_scale}")
    lines.append("billboard_mode = 2")
    lines.append("texture_filter = 0")
    lines.append("")
    lines.append("[node name=\"CollisionShape3D\" type=\"CollisionShape3D\" parent=\".\"]")
    lines.append(f"transform = Transform3D( 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, {collision_y_offset}, 0 )")
    lines.append("shape = SubResource(\"CapsuleShape3D_hero\")")
    return "\n".join(lines) + "\n"


_GDSCRIPT_TEMPLATE = '''extends CharacterBody3D

@export var sprite_path: NodePath = "Sprite3D"
@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D

var _sprite: Sprite3D

func _ready() -> void:
    _sprite = get_node_or_null(sprite_path)
    _apply_nearest_filter()
    _update_sprite()

func _physics_process(delta: float) -> void:
    _update_sprite()

func _get_active_camera() -> Camera3D:
    var viewport = get_viewport()
    if viewport:
        var cam = viewport.get_camera_3d()
        if cam:
            return cam

    var current_scene = get_tree().current_scene
    if current_scene:
        return current_scene.find_child("Camera3D", true, false) as Camera3D

    return null

func _update_sprite() -> void:
    if not _sprite:
        return

    var camera = _get_active_camera()
    if not camera:
        return

    var camera_direction = (global_transform.origin - camera.global_transform.origin).normalized()
    var forward = -global_transform.basis.z.normalized()
    var right = global_transform.basis.x.normalized()

    var forward_dot = forward.dot(camera_direction)
    var right_dot = right.dot(camera_direction)
    var selected_texture: Texture2D = front_texture

    if abs(right_dot) > abs(forward_dot):
        selected_texture = right_texture if right_dot > 0 else left_texture
    else:
        selected_texture = front_texture if forward_dot > 0 else back_texture

    if _sprite.texture != selected_texture:
        _sprite.texture = selected_texture

func _apply_nearest_filter() -> void:
    if _sprite:
        _sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
'''
