extends Node3D

@export var model_data_path := "res://outputs/link_topological/topological_model.json"
@export_enum("final_model", "semantic_regions", "semantic_depth", "occupancy", "raw_voxels", "merged_cuboids", "outline_only", "unknown_regions") var render_mode := "final_model"
@export var show_source_reference := true
@export var show_region_debug := false
@export var show_depth_debug := false
@export var show_raw_voxels := false
@export var show_final_model := true
@export var orbit_speed := 0.035
@export var orbit_radius := 4.6
@export var orbit_height := 1.65
@export var look_height := 0.85

var _camera: Camera3D
var _angle := 0.0
var _model_data := {}
var _raw_voxels: MeshInstance3D
var _generated_model: Node3D
var _final_mesh: MeshInstance3D
var _source_card: Sprite3D
var _region_card: Sprite3D
var _depth_card: Sprite3D
var _semantic_region_card: Sprite3D
var _semantic_depth_card: Sprite3D
var _occupancy_card: Sprite3D
var _outline_card: Sprite3D
var _unknown_card: Sprite3D


func _ready() -> void:
    _camera = find_child("Camera3D", true, false) as Camera3D
    _load_model()
    _build_view()
    _update_camera()


func _process(delta: float) -> void:
    _angle += orbit_speed * delta
    _update_camera()
    _apply_toggles()


func _load_model() -> void:
    var file := FileAccess.open(ProjectSettings.globalize_path(model_data_path), FileAccess.READ)
    if not file:
        push_error("Could not load topological model: %s" % model_data_path)
        return
    var parsed = JSON.parse_string(file.get_as_text())
    file.close()
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid topological model JSON.")
        return
    _model_data = parsed


func _build_view() -> void:
    if _model_data.is_empty():
        return
    var canvas: Array = _model_data.get("canvas_size", [24, 32])
    var pixel_size: float = 1.9 / max(float(canvas[1]), 1.0)
    var y_offset: float = float(canvas[1]) * pixel_size * 0.5

    _source_card = _create_card("Stage0SourceReference", str(_model_data.get("front_texture", "")), Vector3(-1.25, y_offset, 0.0), pixel_size)
    _region_card = _create_card("Stage2RegionDebug", str(_model_data.get("region_overlay", "")), Vector3(0.0, y_offset, -1.2), pixel_size)
    _depth_card = _create_card("Stage2DepthDebug", str(_model_data.get("depth_debug", "")), Vector3(0.0, y_offset, 1.2), pixel_size)
    _semantic_region_card = _create_card("SemanticRegions", str(_model_data.get("semantic_region_overlay", "")), Vector3(1.25, y_offset, 0.0), pixel_size)
    _semantic_depth_card = _create_card("SemanticDepth", str(_model_data.get("semantic_depth_overlay", "")), Vector3(1.25, y_offset, 0.0), pixel_size)
    _occupancy_card = _create_card("SemanticOccupancy", str(_model_data.get("semantic_occupancy", "")), Vector3(1.25, y_offset, 0.0), pixel_size)
    _outline_card = _create_card("SemanticOutlineOnly", str(_model_data.get("semantic_outline_only", "")), Vector3(1.25, y_offset, 0.0), pixel_size)
    _unknown_card = _create_card("SemanticUnknownRegions", str(_model_data.get("semantic_unknown_regions", "")), Vector3(1.25, y_offset, 0.0), pixel_size)

    _raw_voxels = _create_mesh_instance("Stage3RawPartVolumes", Vector3(0.0, 0.0, 0.0), 0.42)
    _generated_model = Node3D.new()
    _generated_model.name = "GeneratedSpriteModel"
    _generated_model.position = Vector3(1.25, 0.0, 0.0)
    add_child(_generated_model)
    _final_mesh = _create_mesh_instance("Stage4FinalCombinedModel", Vector3.ZERO, 1.0, _generated_model)
    _apply_toggles()


func _create_mesh_instance(instance_name: String, position: Vector3, opacity: float, parent: Node = null) -> MeshInstance3D:
    var instance := MeshInstance3D.new()
    instance.name = instance_name
    instance.mesh = _build_array_mesh()
    instance.position = position
    var material := StandardMaterial3D.new()
    material.vertex_color_use_as_albedo = true
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    material.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED if opacity >= 1.0 else BaseMaterial3D.TRANSPARENCY_ALPHA
    material.albedo_color = Color(1, 1, 1, opacity)
    instance.material_override = material
    if parent:
        parent.add_child(instance)
    else:
        add_child(instance)
    return instance


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


func _create_card(card_name: String, texture_path: String, position: Vector3, pixel_size: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = _load_texture(texture_path)
    card.centered = true
    card.pixel_size = pixel_size
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = position
    add_child(card)
    return card


func _load_texture(texture_path: String) -> Texture2D:
    if texture_path.is_empty():
        return null
    var image := Image.new()
    var error := image.load(ProjectSettings.globalize_path(texture_path))
    if error != OK:
        push_error("Failed to load texture %s: %s" % [texture_path, error])
        return null
    return ImageTexture.create_from_image(image)


func _apply_toggles() -> void:
    if _source_card:
        _source_card.visible = show_source_reference
    if _region_card:
        _region_card.visible = show_region_debug
    if _depth_card:
        _depth_card.visible = show_depth_debug
    if _semantic_region_card:
        _semantic_region_card.visible = render_mode == "semantic_regions"
    if _semantic_depth_card:
        _semantic_depth_card.visible = render_mode == "semantic_depth"
    if _occupancy_card:
        _occupancy_card.visible = render_mode == "occupancy"
    if _outline_card:
        _outline_card.visible = render_mode == "outline_only"
    if _unknown_card:
        _unknown_card.visible = render_mode == "unknown_regions"
    if _raw_voxels:
        _raw_voxels.visible = show_raw_voxels or render_mode == "raw_voxels"
        _raw_voxels.rotation.y = _angle
    if _generated_model:
        _generated_model.visible = show_final_model and render_mode in ["final_model", "merged_cuboids"]
        _generated_model.rotation.y = _angle
    if _final_mesh:
        _final_mesh.visible = show_final_model and render_mode in ["final_model", "merged_cuboids"]


func _update_camera() -> void:
    if not _camera:
        return
    _camera.global_position = Vector3(0.0, orbit_height, orbit_radius)
    _camera.look_at(Vector3(0.0, look_height, 0.0), Vector3.UP)
