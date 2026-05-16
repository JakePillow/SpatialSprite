extends CharacterBody3D

@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D

@export var cell_width := 0.08
@export var cell_height := 0.08
@export var cell_depth := 0.14
@export_range(0.0, 1.0, 0.01) var proxy_max_opacity := 0.36
@export_range(0.0, 45.0, 0.5) var canonical_hold_degrees := 10.0
@export_range(1.0, 45.0, 0.5) var transition_width_degrees := 35.0
@export_range(0.0, 1.0, 0.01) var sprite_fade_min := 0.58
@export var side_material_color := Color(0.08, 0.09, 0.08, 1.0)

@export var sprite_scale := 0.06
@export_range(0, 255, 1) var alpha_threshold := 16
@export var debug_overlay := true
@export var debug_log := false
@export var debug_log_interval := 0.25

const CANONICAL_ANGLES := {
    "front": 0.0,
    "right": 90.0,
    "back": 180.0,
    "left": 270.0,
}

var _cards := {}
var _proxy: MeshInstance3D
var _proxy_material: StandardMaterial3D
var _debug_label: Label3D
var _nearest_view := "front"
var _last_proxy_view := ""
var _last_log_time := 0.0


func _ready() -> void:
    _build_cards()
    _build_proxy()
    _build_debug_label()
    _update_visuals(0.0)


func _process(delta: float) -> void:
    _update_visuals(delta)


func _build_cards() -> void:
    _cards = {
        "front": _create_card("FrontKeyView", front_texture, 0.0),
        "right": _create_card("RightKeyView", right_texture, -PI * 0.5),
        "back": _create_card("BackKeyView", back_texture, PI),
        "left": _create_card("LeftKeyView", left_texture, PI * 0.5),
    }


func _create_card(card_name: String, texture: Texture2D, y_rotation: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = texture
    card.pixel_size = sprite_scale
    card.centered = true
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = Vector3(0.0, _sprite_y_offset(texture), 0.0)
    card.rotation.y = y_rotation
    add_child(card)
    return card


func _build_proxy() -> void:
    _proxy = MeshInstance3D.new()
    _proxy.name = "TransitionVoxelProxy"

    _proxy_material = StandardMaterial3D.new()
    _proxy_material.albedo_color = Color(
        side_material_color.r,
        side_material_color.g,
        side_material_color.b,
        0.0
    )
    _proxy_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    _proxy_material.cull_mode = BaseMaterial3D.CULL_DISABLED
    _proxy_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
    _proxy_material.roughness = 1.0
    _proxy.material_override = _proxy_material

    add_child(_proxy)
    _rebuild_proxy_for_view(_nearest_view)


func _build_debug_label() -> void:
    _debug_label = Label3D.new()
    _debug_label.name = "DebugOverlay"
    _debug_label.visible = debug_overlay
    _debug_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    _debug_label.font_size = 20
    _debug_label.pixel_size = 0.004
    _debug_label.outline_size = 4
    _debug_label.position = Vector3(0.0, 2.25, 0.0)
    add_child(_debug_label)


func _update_visuals(delta: float) -> void:
    var camera := _get_active_camera()
    if not camera:
        return

    var angle_degrees := _camera_angle_degrees(camera)
    var state := _angle_state(angle_degrees)
    _nearest_view = state["nearest_view"]

    if _nearest_view != _last_proxy_view:
        _rebuild_proxy_for_view(_nearest_view)

    var canonical_weight: float = state["canonical_weight"]
    var proxy_weight: float = state["proxy_weight"]
    var proxy_opacity: float = proxy_max_opacity * proxy_weight
    var key_alpha: float = lerp(sprite_fade_min, 1.0, canonical_weight)

    if _proxy_material:
        _proxy_material.albedo_color = Color(
            side_material_color.r,
            side_material_color.g,
            side_material_color.b,
            proxy_opacity
        )
    if _proxy:
        _proxy.visible = proxy_opacity > 0.01

    var visible_sprite: String = _nearest_view
    for direction in _cards.keys():
        var card := _cards[direction] as Sprite3D
        var is_visible: bool = direction == _nearest_view
        card.visible = is_visible
        card.modulate = Color(1.0, 1.0, 1.0, key_alpha if is_visible else 0.0)

    _update_debug(angle_degrees, _nearest_view, canonical_weight, proxy_weight, visible_sprite, proxy_opacity, delta)


func _angle_state(angle_degrees: float) -> Dictionary:
    var nearest_index: int = int(round(angle_degrees / 90.0)) % 4
    var nearest_angle: float = float(nearest_index) * 90.0
    var nearest_view: String = _view_for_angle(nearest_angle)
    var distance: float = abs(_shortest_angle_delta(angle_degrees, nearest_angle))
    var fade_width: float = max(transition_width_degrees, 0.001)
    var canonical_weight: float = 1.0 - smoothstep(canonical_hold_degrees, canonical_hold_degrees + fade_width, distance)
    var proxy_weight: float = smoothstep(canonical_hold_degrees, 45.0, distance)

    return {
        "nearest_view": nearest_view,
        "canonical_weight": canonical_weight,
        "proxy_weight": proxy_weight,
        "distance_to_canonical": distance,
    }


func _camera_angle_degrees(camera: Camera3D) -> float:
    var camera_direction := (global_position - camera.global_position).normalized()
    var local_x := global_transform.basis.x.normalized()
    var local_front := -global_transform.basis.z.normalized()
    var x := camera_direction.dot(local_x)
    var z := camera_direction.dot(local_front)
    return fposmod(rad_to_deg(atan2(x, z)), 360.0)


func _view_for_angle(angle_degrees: float) -> String:
    var snapped := int(round(fposmod(angle_degrees, 360.0) / 90.0)) % 4
    match snapped:
        0:
            return "front"
        1:
            return "left"
        2:
            return "back"
        _:
            return "right"


func _shortest_angle_delta(a: float, b: float) -> float:
    return fposmod(a - b + 180.0, 360.0) - 180.0


func _rebuild_proxy_for_view(view_name: String) -> void:
    if not _proxy:
        return

    var texture := _texture_for_view(view_name)
    _proxy.mesh = _build_voxel_proxy_mesh(texture)
    _proxy.rotation.y = _card_rotation_for_view(view_name)
    _last_proxy_view = view_name


func _build_voxel_proxy_mesh(texture: Texture2D) -> ArrayMesh:
    var mesh := ArrayMesh.new()
    if not texture:
        return mesh

    var image := texture.get_image()
    if not image:
        return mesh

    image.convert(Image.FORMAT_RGBA8)
    var width := image.get_width()
    var height := image.get_height()
    var pixels_per_cell_x: int = max(1, int(round(cell_width / sprite_scale)))
    var pixels_per_cell_y: int = max(1, int(round(cell_height / sprite_scale)))
    var columns := int(ceil(float(width) / float(pixels_per_cell_x)))
    var rows := int(ceil(float(height) / float(pixels_per_cell_y)))
    var occupied := []

    for row in range(rows):
        var row_values := []
        for column in range(columns):
            row_values.append(_cell_has_alpha(image, column, row, pixels_per_cell_x, pixels_per_cell_y))
        occupied.append(row_values)

    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var indices := PackedInt32Array()
    var half_depth := cell_depth * 0.5
    var proxy_width := float(width) * sprite_scale
    var proxy_height := float(height) * sprite_scale

    for row in range(rows):
        for column in range(columns):
            if not occupied[row][column]:
                continue

            var x0: float = float(column * pixels_per_cell_x) * sprite_scale - proxy_width * 0.5
            var x1: float = min(float((column + 1) * pixels_per_cell_x) * sprite_scale, proxy_width) - proxy_width * 0.5
            var y1: float = proxy_height - float(row * pixels_per_cell_y) * sprite_scale
            var y0: float = max(proxy_height - float((row + 1) * pixels_per_cell_y) * sprite_scale, 0.0)

            _add_soft_box(vertices, normals, indices, x0, x1, y0, y1, -half_depth, half_depth, occupied, column, row)

    if vertices.size() == 0:
        return mesh

    var arrays := []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = indices
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    return mesh


func _add_soft_box(
    vertices: PackedVector3Array,
    normals: PackedVector3Array,
    indices: PackedInt32Array,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    occupied: Array,
    column: int,
    row: int
) -> void:
    # Front/back faces are intentionally omitted. This keeps the sprite key view authoritative.
    if not _is_occupied_cell(occupied, column - 1, row):
        _add_quad(vertices, normals, indices, Vector3(x0, y0, z0), Vector3(x0, y1, z0), Vector3(x0, y1, z1), Vector3(x0, y0, z1), Vector3.LEFT)
    if not _is_occupied_cell(occupied, column + 1, row):
        _add_quad(vertices, normals, indices, Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x1, y1, z0), Vector3(x1, y0, z0), Vector3.RIGHT)
    if not _is_occupied_cell(occupied, column, row - 1):
        _add_quad(vertices, normals, indices, Vector3(x0, y1, z1), Vector3(x1, y1, z1), Vector3(x1, y1, z0), Vector3(x0, y1, z0), Vector3.UP)
    if not _is_occupied_cell(occupied, column, row + 1):
        _add_quad(vertices, normals, indices, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1), Vector3.DOWN)


func _add_quad(
    vertices: PackedVector3Array,
    normals: PackedVector3Array,
    indices: PackedInt32Array,
    a: Vector3,
    b: Vector3,
    c: Vector3,
    d: Vector3,
    normal: Vector3
) -> void:
    var start := vertices.size()
    vertices.append(a)
    vertices.append(b)
    vertices.append(c)
    vertices.append(d)
    normals.append(normal)
    normals.append(normal)
    normals.append(normal)
    normals.append(normal)
    indices.append(start)
    indices.append(start + 1)
    indices.append(start + 2)
    indices.append(start)
    indices.append(start + 2)
    indices.append(start + 3)


func _cell_has_alpha(image: Image, column: int, row: int, pixels_per_cell_x: int, pixels_per_cell_y: int) -> bool:
    var x_start := column * pixels_per_cell_x
    var y_start := row * pixels_per_cell_y
    var x_end: int = min(x_start + pixels_per_cell_x, image.get_width())
    var y_end: int = min(y_start + pixels_per_cell_y, image.get_height())

    for y in range(y_start, y_end):
        for x in range(x_start, x_end):
            if image.get_pixel(x, y).a8 > alpha_threshold:
                return true
    return false


func _is_occupied_cell(occupied: Array, column: int, row: int) -> bool:
    if row < 0 or column < 0 or row >= occupied.size():
        return false
    var row_values: Array = occupied[row]
    if column >= row_values.size():
        return false
    return bool(row_values[column])


func _texture_for_view(view_name: String) -> Texture2D:
    match view_name:
        "front":
            return front_texture
        "right":
            return right_texture
        "back":
            return back_texture
        _:
            return left_texture


func _card_rotation_for_view(view_name: String) -> float:
    match view_name:
        "front":
            return 0.0
        "right":
            return -PI * 0.5
        "back":
            return PI
        _:
            return PI * 0.5


func _update_debug(
    angle_degrees: float,
    nearest_view: String,
    canonical_weight: float,
    proxy_weight: float,
    visible_sprite: String,
    proxy_opacity: float,
    delta: float
) -> void:
    var message := "angle: %06.2f\nnearest: %s\ncanonical_weight: %.2f\nproxy_weight: %.2f\nvisible_sprite: %s\nproxy_opacity: %.2f" % [
        angle_degrees,
        nearest_view,
        canonical_weight,
        proxy_weight,
        visible_sprite,
        proxy_opacity,
    ]

    if _debug_label:
        _debug_label.visible = debug_overlay
        _debug_label.text = message

    if debug_log:
        _last_log_time += delta
        if _last_log_time >= debug_log_interval:
            print(message.replace("\n", " | "))
            _last_log_time = 0.0


func _sprite_y_offset(texture: Texture2D) -> float:
    if not texture:
        return 0.0
    return texture.get_height() * sprite_scale * 0.5


func _get_active_camera() -> Camera3D:
    var viewport := get_viewport()
    if viewport:
        var camera := viewport.get_camera_3d()
        if camera:
            return camera

    var current_scene := get_tree().current_scene
    if current_scene:
        return current_scene.find_child("Camera3D", true, false) as Camera3D

    return null
