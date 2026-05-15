extends Node3D

@export var camera_path: NodePath = "Camera3D"
@export var orbit_center := Vector3.ZERO
@export var orbit_radius := 7.5
@export var orbit_height := 2.2
@export var orbit_speed := 0.45
@export var look_height := 0.75
@export var start_angle := 0.0
@export var paused := false

var _camera: Camera3D
var _angle := 0.0


func _ready() -> void:
    _camera = get_node_or_null(camera_path) as Camera3D
    _angle = start_angle
    _update_camera()


func _process(delta: float) -> void:
    if paused:
        return

    _angle += orbit_speed * delta
    _update_camera()


func _update_camera() -> void:
    if not _camera:
        return

    var look_target = orbit_center + Vector3(0.0, look_height, 0.0)
    _camera.global_position = orbit_center + Vector3(
        sin(_angle) * orbit_radius,
        orbit_height,
        cos(_angle) * orbit_radius
    )
    _camera.look_at(look_target, Vector3.UP)
