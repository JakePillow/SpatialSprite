extends Node

@export var camera_path: NodePath = "../Camera3D"
@export var orbit_controller_path: NodePath = ".."
@export var output_dir := "res://outputs/front_3dfy_test"
@export var capture_on_ready := false
@export var quit_after_capture := true
@export var camera_distance := 4.0

const CAPTURE_ANGLES := [0, 30, 45, 60, 90]

var _camera: Camera3D
var _orbit_controller: Node


func _ready() -> void:
    _camera = get_node_or_null(camera_path) as Camera3D
    _orbit_controller = get_node_or_null(orbit_controller_path)
    if OS.get_cmdline_user_args().has("--capture-front-3dfy"):
        capture_on_ready = true
    if capture_on_ready:
        call_deferred("capture_all")


func capture_all() -> void:
    if not _camera:
        push_error("Front 3DFY capture could not find Camera3D.")
        return

    if "paused" in _orbit_controller:
        _orbit_controller.paused = true

    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output_dir))

    for angle_degrees in CAPTURE_ANGLES:
        await _capture_angle(angle_degrees)

    if quit_after_capture:
        get_tree().quit()


func _capture_angle(angle_degrees: int) -> void:
    var angle_radians := deg_to_rad(float(angle_degrees))
    if _orbit_controller and _orbit_controller.has_method("set_camera_angle_distance"):
        _orbit_controller.set_camera_angle_distance(angle_radians, camera_distance)
    else:
        _camera.global_position = Vector3(sin(angle_radians) * camera_distance, 1.65, cos(angle_radians) * camera_distance)
        _camera.look_at(Vector3(0.0, 0.85, 0.0), Vector3.UP)

    for _i in range(3):
        await get_tree().process_frame

    var image := get_viewport().get_texture().get_image()
    if not image:
        push_error("Viewport capture returned no image. Run without --headless.")
        return

    var path := ProjectSettings.globalize_path("%s/front_3dfy_%03d.png" % [output_dir.trim_suffix("/"), angle_degrees])
    var error := image.save_png(path)
    if error != OK:
        push_error("Failed to save %s: %s" % [path, error])
