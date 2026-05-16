extends Node

@export var camera_path: NodePath = "../Camera3D"
@export var orbit_controller_path: NodePath = ".."
@export var output_dir := "res://outputs/link/test_lab_captures"
@export var results_path := "res://outputs/link/test_results.json"
@export var capture_on_ready := false
@export var quit_after_capture := true
@export var look_height := 0.75
@export var camera_height := 2.2
@export var near_distance := 4.2
@export var mid_distance := 6.2
@export var far_distance := 8.6
@export var settle_frames := 3

const CAPTURE_ANGLES := [0, 45, 90, 135, 180, 225, 270, 315]
const REVIEW_CRITERIA := {
    "head_on": "PASS if player would not notice 3D scaffold.",
    "forty_five_degrees": "PASS if illusion breaks gracefully, not as paper-thin card.",
    "side": "PASS if side sprite resolves cleanly.",
    "back": "PASS if back sprite resolves cleanly.",
    "edges": "PASS if no background halo/fringe.",
    "motion": "PASS if no flicker or distracting popping.",
}

var _camera: Camera3D
var _orbit_controller: Node
var _results := []


func _ready() -> void:
    _camera = get_node_or_null(camera_path) as Camera3D
    _orbit_controller = get_node_or_null(orbit_controller_path)

    if OS.has_feature("headless") or OS.get_cmdline_user_args().has("--capture-test-lab"):
        capture_on_ready = true

    if capture_on_ready:
        call_deferred("capture_all")


func capture_all() -> void:
    if not _camera:
        push_error("CaptureAngles could not find Camera3D at %s" % camera_path)
        return

    if "paused" in _orbit_controller:
        _orbit_controller.paused = true

    _ensure_output_dir(output_dir)
    _ensure_parent_dir(results_path)
    _results.clear()

    var distances := {
        "near": near_distance,
        "mid": mid_distance,
        "far": far_distance,
    }

    for distance_name in distances.keys():
        var distance: float = distances[distance_name]
        for angle_degrees in CAPTURE_ANGLES:
            var image_path := await _capture_one(str(distance_name), int(angle_degrees), distance)
            _results.append({
                "distance": str(distance_name),
                "distance_value": distance,
                "angle_degrees": int(angle_degrees),
                "image": image_path,
            })

    _write_results()

    if quit_after_capture:
        get_tree().quit()


func _capture_one(distance_name: String, angle_degrees: int, distance: float) -> String:
    var angle_radians := deg_to_rad(float(angle_degrees))

    if _orbit_controller and _orbit_controller.has_method("set_camera_angle_distance"):
        _orbit_controller.set_camera_angle_distance(angle_radians, distance)
    else:
        _place_camera(angle_radians, distance)

    for _i in range(max(settle_frames, 1)):
        await get_tree().process_frame

    var viewport := get_viewport()
    var image := viewport.get_texture().get_image()
    if not image:
        push_error("Viewport capture returned no image. Run without --headless so Godot has a real renderer.")
        return ""

    var file_name := "%s_%03d.png" % [distance_name, angle_degrees]
    var resource_path := "%s/%s" % [output_dir.trim_suffix("/"), file_name]
    var absolute_path := ProjectSettings.globalize_path(resource_path)
    var error := image.save_png(absolute_path)
    if error != OK:
        push_error("Failed to save capture %s: %s" % [absolute_path, error])

    return resource_path


func _place_camera(angle_radians: float, distance: float) -> void:
    var look_target := Vector3(0.0, look_height, 0.0)
    _camera.global_position = Vector3(
        sin(angle_radians) * distance,
        camera_height,
        cos(angle_radians) * distance
    )
    _camera.look_at(look_target, Vector3.UP)


func _write_results() -> void:
    var payload := {
        "scene": "res://test_lab.tscn",
        "output_dir": output_dir,
        "angles_degrees": CAPTURE_ANGLES,
        "review_criteria": REVIEW_CRITERIA,
        "distances": {
            "near": near_distance,
            "mid": mid_distance,
            "far": far_distance,
        },
        "captures": _results,
    }

    var absolute_path := ProjectSettings.globalize_path(results_path)
    var file := FileAccess.open(absolute_path, FileAccess.WRITE)
    if not file:
        push_error("Failed to write results JSON: %s" % absolute_path)
        return

    file.store_string(JSON.stringify(payload, "  "))
    file.close()


func _ensure_output_dir(path: String) -> void:
    var absolute_path := ProjectSettings.globalize_path(path)
    DirAccess.make_dir_recursive_absolute(absolute_path)


func _ensure_parent_dir(path: String) -> void:
    var absolute_path := ProjectSettings.globalize_path(path)
    var parent := absolute_path.get_base_dir()
    DirAccess.make_dir_recursive_absolute(parent)
