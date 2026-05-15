extends Node3D

@export var target_path: NodePath = "HeroInstance"
@export var orbit_radius := 4.0
@export var orbit_height := 1.1
@export var orbit_speed := 0.55
@export var target_height := 0.9

var _target: Node3D
var _camera: Camera3D
var _angle := 0.0


func _ready() -> void:
    _target = get_node_or_null(target_path) as Node3D
    _camera = get_node_or_null("Camera3D") as Camera3D


func _process(delta: float) -> void:
    if not _target or not _camera:
        return

    _angle += delta * orbit_speed
    var target_position = _target.global_position + Vector3(0.0, target_height, 0.0)
    _camera.global_position = target_position + Vector3(
        sin(_angle) * orbit_radius,
        orbit_height,
        cos(_angle) * orbit_radius
    )
    _camera.look_at(target_position, Vector3.UP)
