extends CharacterBody3D

@export var sprite_path: NodePath = "Sprite3D"
@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D

var _sprite: Sprite3D


func _ready() -> void:
    _sprite = get_node_or_null(sprite_path) as Sprite3D
    _apply_nearest_filter()
    _update_sprite()


func _physics_process(_delta: float) -> void:
    _update_sprite()


func _get_active_camera() -> Camera3D:
    var viewport = get_viewport()
    if viewport:
        var camera = viewport.get_camera_3d()
        if camera:
            return camera

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
        selected_texture = right_texture if right_dot > 0.0 else left_texture
    else:
        selected_texture = front_texture if forward_dot > 0.0 else back_texture

    if _sprite.texture != selected_texture:
        _sprite.texture = selected_texture


func _apply_nearest_filter() -> void:
    if _sprite:
        _sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
