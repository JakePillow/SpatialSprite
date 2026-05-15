extends Node3D

@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D
@export var pixel_size := 0.014
@export var billboard_mode := 2
@export var parallax_strength := 1.0

const FRAME_SIZE := Vector2(128.0, 128.0)

const REGIONS := {
    "front": {
        "torso": Rect2(39, 27, 48, 45),
        "head": Rect2(50, 6, 28, 26),
        "left_arm": Rect2(29, 33, 26, 51),
        "right_arm": Rect2(72, 31, 24, 55),
        "left_leg": Rect2(35, 69, 31, 55),
        "right_leg": Rect2(58, 69, 33, 55),
        "accessory": Rect2(81, 47, 18, 63),
    },
    "back": {
        "torso": Rect2(35, 34, 64, 45),
        "head": Rect2(48, 13, 34, 25),
        "left_arm": Rect2(13, 42, 34, 56),
        "right_arm": Rect2(91, 42, 26, 54),
        "left_leg": Rect2(28, 75, 43, 49),
        "right_leg": Rect2(63, 73, 50, 51),
        "accessory": Rect2(39, 47, 34, 76),
    },
    "left": {
        "torso": Rect2(39, 27, 48, 45),
        "head": Rect2(50, 6, 28, 26),
        "left_arm": Rect2(29, 33, 26, 51),
        "right_arm": Rect2(72, 31, 24, 55),
        "left_leg": Rect2(35, 69, 31, 55),
        "right_leg": Rect2(58, 69, 33, 55),
        "accessory": Rect2(29, 47, 18, 63),
    },
    "right": {
        "torso": Rect2(39, 27, 48, 45),
        "head": Rect2(50, 6, 28, 26),
        "left_arm": Rect2(29, 33, 26, 51),
        "right_arm": Rect2(72, 31, 24, 55),
        "left_leg": Rect2(35, 69, 31, 55),
        "right_leg": Rect2(58, 69, 33, 55),
        "accessory": Rect2(81, 47, 18, 63),
    },
}

const LAYERS := [
    {"name": "left_leg", "depth": -0.12},
    {"name": "right_leg", "depth": 0.08},
    {"name": "torso", "depth": 0.0},
    {"name": "left_arm", "depth": -0.16},
    {"name": "right_arm", "depth": 0.16},
    {"name": "head", "depth": 0.05},
    {"name": "accessory", "depth": 0.24},
]

var _sprites: Dictionary = {}
var _current_direction := ""


func _ready() -> void:
    _build_layers()
    _update_layers()


func _process(_delta: float) -> void:
    _update_layers()


func _build_layers() -> void:
    for layer in LAYERS:
        var sprite := Sprite3D.new()
        var layer_name = layer["name"]
        sprite.name = _to_title_case(layer_name)
        sprite.centered = true
        sprite.region_enabled = true
        sprite.pixel_size = pixel_size
        sprite.billboard = billboard_mode
        sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
        sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
        add_child(sprite)
        _sprites[layer_name] = sprite


func _update_layers() -> void:
    var direction = _get_view_direction()
    if direction == _current_direction:
        return

    _current_direction = direction
    var texture = _texture_for_direction(direction)
    var regions = REGIONS[direction]

    for layer in LAYERS:
        var layer_name = layer["name"]
        var sprite = _sprites[layer_name] as Sprite3D
        var region = regions[layer_name] as Rect2
        sprite.texture = texture
        sprite.region_rect = region
        sprite.position = _position_for_region(region, float(layer["depth"]) * parallax_strength)


func _position_for_region(region: Rect2, depth: float) -> Vector3:
    var center = region.position + region.size * 0.5
    return Vector3(
        (center.x - FRAME_SIZE.x * 0.5) * pixel_size,
        (FRAME_SIZE.y - center.y) * pixel_size,
        depth
    )


func _texture_for_direction(direction: String) -> Texture2D:
    match direction:
        "front":
            return front_texture
        "back":
            return back_texture
        "left":
            return left_texture
        "right":
            return right_texture
        _:
            return front_texture


func _get_view_direction() -> String:
    var camera = _get_active_camera()
    if not camera:
        return "front"

    var camera_direction = (global_transform.origin - camera.global_transform.origin).normalized()
    var forward = -global_transform.basis.z.normalized()
    var right = global_transform.basis.x.normalized()

    var forward_dot = forward.dot(camera_direction)
    var right_dot = right.dot(camera_direction)

    if abs(right_dot) > abs(forward_dot):
        return "right" if right_dot > 0.0 else "left"

    return "front" if forward_dot > 0.0 else "back"


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


func _to_title_case(value: String) -> String:
    var pieces = value.split("_")
    for i in pieces.size():
        pieces[i] = pieces[i].capitalize()
    return "".join(pieces)
