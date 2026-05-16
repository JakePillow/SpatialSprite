extends Node3D

@export var model_data_path := "res://outputs/front_back_model/front_back_model.json"
@export var show_generated_mesh := true
@export var show_keyview_cards := true
@export_range(0.0, 1.0, 0.01) var keyview_opacity := 0.98
@export var orbit_speed := 0.045
@export var orbit_radius := 4.0
@export var orbit_height := 1.65
@export var look_height := 0.85
@export var capture_output_dir := "res://outputs/front_back_model/captures"
@export var capture_on_ready := false

const CAPTURE_ANGLES := [0, 45, 90, 135, 180]

var _camera: Camera3D
var _angle := 0.0
var _mesh_instance: MeshInstance3D
var _front_card: Sprite3D
var _back_card: Sprite3D
var _model_data := {}


func _ready() -> void:
    _camera = find_child("Camera3D", true, false) as Camera3D
    _load_model()
    _build_runtime_model()
    _update_camera()
    if OS.get_cmdline_user_args().has("--capture-front-back-model"):
        capture_on_ready = true
    if capture_on_ready:
        call_deferred("capture_all")


func _process(delta: float) -> void:
    if capture_on_ready:
        return
    _angle += orbit_speed * delta
    _update_camera()
    _apply_debug_controls()


func _load_model() -> void:
    var absolute_path := ProjectSettings.globalize_path(model_data_path)
    var file := FileAccess.open(absolute_path, FileAccess.READ)
    if not file:
        push_error("Could not open front/back model data: %s" % absolute_path)
        return
    var parsed = JSON.parse_string(file.get_as_text())
    file.close()
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid front/back model JSON: %s" % absolute_path)
        return
    _model_data = parsed


func _build_runtime_model() -> void:
    if _model_data.is_empty():
        return

    _mesh_instance = MeshInstance3D.new()
    _mesh_instance.name = "GeneratedFrontBackVolume"
    _mesh_instance.mesh = _build_array_mesh()
    var material := StandardMaterial3D.new()
    material.vertex_color_use_as_albedo = true
    material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    material.roughness = 1.0
    _mesh_instance.material_override = material
    add_child(_mesh_instance)

    var config: Dictionary = _model_data.get("config", {})
    var depth: float = float(config.get("model_depth_units", 0.48))
    var canvas: Array = _model_data.get("canvas_size", [24, 32])
    var pixel_size: float = 1.9 / max(float(canvas[1]), 1.0)
    var y_offset: float = float(canvas[1]) * pixel_size * 0.5

    _front_card = _create_card("FrontProjectedKeyView", str(_model_data.get("front_texture", "")), Vector3(0.0, y_offset, depth * 0.5 + 0.006), 0.0, pixel_size)
    _back_card = _create_card("BackProjectedKeyView", str(_model_data.get("back_texture", "")), Vector3(0.0, y_offset, -depth * 0.5 - 0.006), PI, pixel_size)
    _apply_debug_controls()


func _build_array_mesh() -> ArrayMesh:
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var colors := PackedColorArray()
    var indices := PackedInt32Array()

    for value in _model_data.get("vertices", []):
        vertices.append(Vector3(float(value[0]), float(value[1]), float(value[2])))
    for value in _model_data.get("normals", []):
        normals.append(Vector3(float(value[0]), float(value[1]), float(value[2])))
    for value in _model_data.get("colors", []):
        colors.append(Color(float(value[0]), float(value[1]), float(value[2]), float(value[3])))
    for value in _model_data.get("indices", []):
        indices.append(int(value))

    var arrays := []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_COLOR] = colors
    arrays[Mesh.ARRAY_INDEX] = indices

    var mesh := ArrayMesh.new()
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    return mesh


func _create_card(card_name: String, texture_path: String, position: Vector3, y_rotation: float, pixel_size: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = _load_texture(texture_path)
    card.centered = true
    card.pixel_size = pixel_size
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = position
    card.rotation.y = y_rotation
    add_child(card)
    return card


func _load_texture(texture_path: String) -> Texture2D:
    var image := Image.new()
    var error := image.load(ProjectSettings.globalize_path(texture_path))
    if error != OK:
        push_error("Failed to load texture %s: %s" % [texture_path, error])
        return null
    return ImageTexture.create_from_image(image)


func _apply_debug_controls() -> void:
    if _mesh_instance:
        _mesh_instance.visible = show_generated_mesh
    if _front_card:
        _front_card.visible = show_keyview_cards
        _front_card.modulate = Color(1.0, 1.0, 1.0, keyview_opacity)
    if _back_card:
        _back_card.visible = show_keyview_cards
        _back_card.modulate = Color(1.0, 1.0, 1.0, keyview_opacity)


func _update_camera() -> void:
    if not _camera:
        return
    set_camera_angle_distance(_angle, orbit_radius)


func set_camera_angle_distance(angle_radians: float, distance: float) -> void:
    if not _camera:
        return
    _camera.global_position = Vector3(
        sin(angle_radians) * distance,
        orbit_height,
        cos(angle_radians) * distance
    )
    _camera.look_at(Vector3(0.0, look_height, 0.0), Vector3.UP)


func capture_all() -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(capture_output_dir))
    for angle_degrees in CAPTURE_ANGLES:
        await _capture_angle(angle_degrees)
    get_tree().quit()


func _capture_angle(angle_degrees: int) -> void:
    set_camera_angle_distance(deg_to_rad(float(angle_degrees)), orbit_radius)
    for _i in range(3):
        await get_tree().process_frame

    var image := get_viewport().get_texture().get_image()
    if not image:
        push_error("Viewport capture returned no image. Run without --headless.")
        return

    var path := ProjectSettings.globalize_path("%s/front_back_%03d.png" % [capture_output_dir.trim_suffix("/"), angle_degrees])
    var error := image.save_png(path)
    if error != OK:
        push_error("Failed to save capture %s: %s" % [path, error])
