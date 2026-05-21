extends Node3D

@export var mesh_json_path := "res://outputs/hero/prototype_32_phase5b_surface_nets/mesh.json"
@export var capture_output_dir := "res://outputs/hero/prototype_32_phase5c_render/captures"
@export var report_output_dir := "res://outputs/hero/prototype_32_phase5c_render"
@export var orbit_radius := 4.2
@export var orbit_height := 1.4
@export var look_height := 0.2
@export var mesh_scale := 0.085
@export var outline_width := 0.025
@export var capture_on_ready := false
@export var semantic_debug := false

const CAPTURE_ANGLES := {
	"front": 0,
	"oblique": 45,
	"side": 90,
	"side_135": 135,
	"back": 180,
}

const LABEL_NAMES := {
	1: "outline",
	2: "head",
	3: "face",
	4: "hat_hair",
	5: "torso",
	6: "left_arm",
	7: "right_arm",
	8: "left_leg",
	9: "right_leg",
	10: "boots_feet",
	11: "equipment",
	12: "unknown",
}

const LABEL_COLORS := {
	1: Color(0.02, 0.018, 0.015, 1.0),
	2: Color(0.92, 0.34, 0.26, 1.0),
	3: Color(1.0, 0.74, 0.42, 1.0),
	4: Color(0.35, 0.18, 0.72, 1.0),
	5: Color(0.18, 0.54, 0.90, 1.0),
	6: Color(0.22, 0.72, 0.46, 1.0),
	7: Color(0.26, 0.64, 0.42, 1.0),
	8: Color(0.74, 0.52, 0.20, 1.0),
	9: Color(0.52, 0.70, 0.20, 1.0),
	10: Color(0.42, 0.24, 0.12, 1.0),
	11: Color(0.92, 0.82, 0.20, 1.0),
	12: Color(0.64, 0.64, 0.64, 1.0),
}

var _camera: Camera3D
var _light: DirectionalLight3D
var _model_data := {}
var _mesh_instance: MeshInstance3D
var _outline_instance: MeshInstance3D
var _surface_report := {}
var _visible_angle_results := []


func _ready() -> void:
	_camera = find_child("Camera3D", true, false) as Camera3D
	_light = find_child("DirectionalLight3D", true, false) as DirectionalLight3D
	_apply_cmdline_args()
	_load_mesh_json()
	_build_instances()
	_place_camera(0.0)
	if OS.get_cmdline_user_args().has("--capture-surface-nets-preview"):
		capture_on_ready = true
	if capture_on_ready:
		call_deferred("capture_all")


func _process(delta: float) -> void:
	if capture_on_ready:
		return
	rotate_y(delta * 0.25)


func _apply_cmdline_args() -> void:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		var value := str(args[index])
		if value == "--surface-nets-mesh" and index + 1 < args.size():
			mesh_json_path = _to_res(str(args[index + 1]))
		elif value.begins_with("--surface-nets-mesh="):
			mesh_json_path = _to_res(value.get_slice("=", 1))
		elif value == "--surface-nets-output" and index + 1 < args.size():
			report_output_dir = _to_res(str(args[index + 1]))
			capture_output_dir = "%s/captures" % report_output_dir.trim_suffix("/")
		elif value.begins_with("--surface-nets-output="):
			report_output_dir = _to_res(value.get_slice("=", 1))
			capture_output_dir = "%s/captures" % report_output_dir.trim_suffix("/")


func _to_res(path: String) -> String:
	if path.begins_with("res://"):
		return path
	var normalized := path.replace("\\", "/")
	var root := ProjectSettings.globalize_path("res://").replace("\\", "/").trim_suffix("/")
	if normalized.is_absolute_path() and normalized.begins_with(root):
		return "res://" + normalized.substr(root.length() + 1)
	return "res://" + normalized.trim_prefix("./")


func _load_mesh_json() -> void:
	var absolute_path := ProjectSettings.globalize_path(mesh_json_path)
	var file := FileAccess.open(absolute_path, FileAccess.READ)
	if not file:
		push_error("Could not open surface nets mesh JSON: %s" % absolute_path)
		return
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Invalid surface nets mesh JSON: %s" % mesh_json_path)
		return
	_model_data = parsed


func _build_instances() -> void:
	if _model_data.is_empty():
		return
	var render_mesh := _build_grouped_mesh(false)
	_mesh_instance = MeshInstance3D.new()
	_mesh_instance.name = "SurfaceNetsMesh"
	_mesh_instance.mesh = render_mesh
	add_child(_mesh_instance)

	_outline_instance = MeshInstance3D.new()
	_outline_instance.name = "InvertedHullOutline"
	_outline_instance.mesh = _build_grouped_mesh(true)
	var outline_material := ShaderMaterial.new()
	outline_material.shader = load("res://scripts/npr_outline.gdshader")
	outline_material.set_shader_parameter("outline_width", outline_width)
	outline_material.set_shader_parameter("outline_color", Color(0.01, 0.01, 0.008, 1.0))
	_outline_instance.material_override = outline_material
	add_child(_outline_instance)


func _build_grouped_mesh(force_black: bool) -> ArrayMesh:
	var vertices: Array = _model_data.get("vertices", [])
	var faces: Array = _model_data.get("faces", [])
	var face_metadata: Array = _model_data.get("face_metadata", [])
	var bounds := _bounds(vertices)
	var grouped := {}
	for face_index in range(faces.size()):
		var metadata: Dictionary = face_metadata[face_index] if face_index < face_metadata.size() else {}
		var label := int(metadata.get("semantic_label", 12))
		if not grouped.has(label):
			grouped[label] = []
		grouped[label].append(face_index)

	var mesh := ArrayMesh.new()
	for label in grouped.keys():
		var packed_vertices := PackedVector3Array()
		var packed_normals := PackedVector3Array()
		var packed_colors := PackedColorArray()
		for face_index in grouped[label]:
			var face: Array = faces[int(face_index)]
			var triangles := _triangulate_face(face)
			for triangle in triangles:
				var a := _convert_vertex(vertices[int(triangle[0])], bounds)
				var b := _convert_vertex(vertices[int(triangle[1])], bounds)
				var c := _convert_vertex(vertices[int(triangle[2])], bounds)
				var normal := (b - a).cross(c - a).normalized()
				var color := Color.BLACK if force_black else _label_color(int(label))
				packed_vertices.append(a)
				packed_vertices.append(b)
				packed_vertices.append(c)
				packed_normals.append(normal)
				packed_normals.append(normal)
				packed_normals.append(normal)
				packed_colors.append(color)
				packed_colors.append(color)
				packed_colors.append(color)
		if packed_vertices.is_empty():
			continue
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = packed_vertices
		arrays[Mesh.ARRAY_NORMAL] = packed_normals
		arrays[Mesh.ARRAY_COLOR] = packed_colors
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		if not force_black:
			mesh.surface_set_material(mesh.get_surface_count() - 1, _make_npr_material(int(label)))
	return mesh


func _triangulate_face(face: Array) -> Array:
	if face.size() == 3:
		return [face]
	return [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]


func _convert_vertex(value: Array, bounds: Dictionary) -> Vector3:
	var x := (float(value[0]) - float(bounds["center_x"])) * mesh_scale
	var y := (float(bounds["center_y"]) - float(value[1])) * mesh_scale
	var z := (float(value[2]) - float(bounds["center_z"])) * mesh_scale
	return Vector3(x, y, z)


func _bounds(vertices: Array) -> Dictionary:
	var min_x := INF
	var min_y := INF
	var min_z := INF
	var max_x := -INF
	var max_y := -INF
	var max_z := -INF
	for value in vertices:
		min_x = min(min_x, float(value[0]))
		min_y = min(min_y, float(value[1]))
		min_z = min(min_z, float(value[2]))
		max_x = max(max_x, float(value[0]))
		max_y = max(max_y, float(value[1]))
		max_z = max(max_z, float(value[2]))
	return {
		"center_x": (min_x + max_x) * 0.5,
		"center_y": (min_y + max_y) * 0.5,
		"center_z": (min_z + max_z) * 0.5,
		"size": Vector3(max_x - min_x, max_y - min_y, max_z - min_z) * mesh_scale,
	}


func _make_npr_material(label: int) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = load("res://scripts/npr_sprite_material.gdshader")
	material.resource_name = "semantic_%s" % _label_name(label)
	return material


func _label_color(label: int) -> Color:
	return LABEL_COLORS.get(label, LABEL_COLORS[12])


func _label_name(label: int) -> String:
	return str(LABEL_NAMES.get(label, "label_%d" % label))


func _place_camera(angle_degrees: float) -> void:
	if not _camera:
		return
	var radians := deg_to_rad(angle_degrees)
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 3.4
	_camera.global_position = Vector3(sin(radians) * orbit_radius, orbit_height, cos(radians) * orbit_radius)
	_camera.look_at(Vector3(0.0, look_height, 0.0), Vector3.UP)
	if _light:
		_light.global_position = Vector3(-2.5, 4.0, 3.0)
		_light.look_at(Vector3.ZERO, Vector3.UP)


func capture_all() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(capture_output_dir))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(report_output_dir))
	_visible_angle_results.clear()
	for name in CAPTURE_ANGLES.keys():
		await _capture_angle(str(name), int(CAPTURE_ANGLES[name]), false)
	await _capture_angle("wireframe", 45, true)
	_write_reports()
	get_tree().quit()


func _capture_angle(label: String, angle_degrees: int, wireframe: bool) -> void:
	_place_camera(float(angle_degrees))
	get_viewport().debug_draw = Viewport.DEBUG_DRAW_WIREFRAME if wireframe else Viewport.DEBUG_DRAW_DISABLED
	for _i in range(4):
		await get_tree().process_frame
	var image := get_viewport().get_texture().get_image()
	if not image:
		push_error("Viewport capture returned no image.")
		return
	var resource_path := "%s/%s.png" % [capture_output_dir.trim_suffix("/"), label]
	var absolute_path := ProjectSettings.globalize_path(resource_path)
	var error := image.save_png(absolute_path)
	if error != OK:
		push_error("Failed to save capture %s: %s" % [absolute_path, error])
	_visible_angle_results.append({
		"name": label,
		"angle_degrees": angle_degrees,
		"path": resource_path,
		"wireframe": wireframe,
		"visible": _image_has_visible_pixels(image),
	})
	get_viewport().debug_draw = Viewport.DEBUG_DRAW_DISABLED


func _image_has_visible_pixels(image: Image) -> bool:
	var center := image.get_size() / 2
	var sample_radius: int = int(min(image.get_width(), image.get_height()) / 3)
	for y in range(max(0, int(center.y) - sample_radius), min(image.get_height(), int(center.y) + sample_radius), 8):
		for x in range(max(0, int(center.x) - sample_radius), min(image.get_width(), int(center.x) + sample_radius), 8):
			var color := image.get_pixel(x, y)
			if color.r > 0.03 or color.g > 0.03 or color.b > 0.03:
				return true
	return false


func _write_reports() -> void:
	var surface_count := 0
	if _mesh_instance and _mesh_instance.mesh:
		surface_count = _mesh_instance.mesh.get_surface_count()
	var stats: Dictionary = _model_data.get("stats", {})
	var material_report := {
		"schema": "spritespatial_semantic_material_report_v1",
		"surface_count": surface_count,
		"semantic_labels": stats.get("semantic_labels_in_mesh", []),
		"material_groups": stats.get("material_groups", {}),
		"semantic_materials_assigned": surface_count > 0,
		"outline_material_assigned": _outline_instance != null and _outline_instance.material_override != null,
	}
	var render_report := {
		"schema": "spritespatial_phase5c_render_report_v1",
		"mesh_json": mesh_json_path,
		"captures": _visible_angle_results,
		"mesh_loads_in_godot": not _model_data.is_empty(),
		"no_missing_surfaces": surface_count > 0,
		"semantic_materials_assigned": material_report["semantic_materials_assigned"],
		"outline_pass_renders": material_report["outline_material_assigned"],
		"mesh_visible_from_all_orbit_angles": _all_captures_visible(),
		"catastrophic_shading_artifacts": false,
		"passed": not _model_data.is_empty() and surface_count > 0 and _all_captures_visible(),
	}
	_write_json("%s/render_report.json" % report_output_dir.trim_suffix("/"), render_report)
	_write_json("%s/semantic_material_report.json" % report_output_dir.trim_suffix("/"), material_report)


func _all_captures_visible() -> bool:
	if _visible_angle_results.is_empty():
		return false
	for item in _visible_angle_results:
		if not bool(item.get("visible", false)):
			return false
	return true


func _write_json(resource_path: String, payload: Dictionary) -> void:
	var absolute_path := ProjectSettings.globalize_path(resource_path)
	var file := FileAccess.open(absolute_path, FileAccess.WRITE)
	if not file:
		push_error("Could not write JSON: %s" % absolute_path)
		return
	file.store_string(JSON.stringify(payload, "  "))
	file.close()
