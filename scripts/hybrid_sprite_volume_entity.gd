extends CharacterBody3D

@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D

@export var proxy_depth := 0.16
@export_range(0.0, 1.0, 0.01) var proxy_visibility := 0.42
@export var angle_fade_strength := 1.0
@export var canonical_snap_strength := 1.35
@export var side_material_color := Color(0.08, 0.09, 0.08, 1.0)
@export var sprite_scale := 0.06
@export_range(0, 255, 1) var alpha_threshold := 16

var _proxy: MeshInstance3D
var _proxy_material: StandardMaterial3D
var _front_card: Sprite3D
var _back_card: Sprite3D
var _left_card: Sprite3D
var _right_card: Sprite3D
var _cards := {}


func _ready() -> void:
    _build_proxy()
    _build_cards()
    _update_visuals()


func _process(_delta: float) -> void:
    _update_visuals()


func _build_proxy() -> void:
    _proxy = MeshInstance3D.new()
    _proxy.name = "ShallowSilhouetteProxy"
    _proxy.mesh = _build_silhouette_sidewall_mesh()

    _proxy_material = StandardMaterial3D.new()
    _proxy_material.albedo_color = Color(
        side_material_color.r,
        side_material_color.g,
        side_material_color.b,
        0.0
    )
    _proxy_material.roughness = 1.0
    _proxy_material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
    _proxy_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    _proxy_material.cull_mode = BaseMaterial3D.CULL_DISABLED
    _proxy_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
    _proxy.material_override = _proxy_material

    add_child(_proxy)


func _build_cards() -> void:
    _front_card = _create_card("FrontCard", front_texture, Vector3(0.0, 0.0, -proxy_depth * 0.5 - 0.002), 0.0)
    _back_card = _create_card("BackCard", back_texture, Vector3(0.0, 0.0, proxy_depth * 0.5 + 0.002), PI)
    _left_card = _create_card("LeftCard", left_texture, Vector3(-proxy_depth * 0.5 - 0.002, 0.0, 0.0), PI * 0.5)
    _right_card = _create_card("RightCard", right_texture, Vector3(proxy_depth * 0.5 + 0.002, 0.0, 0.0), -PI * 0.5)

    _cards = {
        "front": _front_card,
        "back": _back_card,
        "left": _left_card,
        "right": _right_card,
    }


func _create_card(card_name: String, texture: Texture2D, local_offset: Vector3, y_rotation: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = texture
    card.pixel_size = sprite_scale
    card.centered = true
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = local_offset + Vector3(0.0, _sprite_y_offset(texture), 0.0)
    card.rotation.y = y_rotation
    add_child(card)
    return card


func _build_silhouette_sidewall_mesh() -> ArrayMesh:
    var mesh := ArrayMesh.new()
    if not front_texture:
        return mesh

    var image := front_texture.get_image()
    if not image:
        return mesh

    image.convert(Image.FORMAT_RGBA8)
    var width := image.get_width()
    var height := image.get_height()
    var half_depth := proxy_depth * 0.5
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var indices := PackedInt32Array()

    for y in range(height):
        for x in range(width):
            if not _is_opaque(image, x, y):
                continue

            var x0 := (float(x) - float(width) * 0.5) * sprite_scale
            var x1 := x0 + sprite_scale
            var y1 := (float(height) - float(y)) * sprite_scale
            var y0 := y1 - sprite_scale

            if not _is_opaque(image, x - 1, y):
                _add_quad(
                    vertices,
                    normals,
                    indices,
                    Vector3(x0, y0, -half_depth),
                    Vector3(x0, y1, -half_depth),
                    Vector3(x0, y1, half_depth),
                    Vector3(x0, y0, half_depth),
                    Vector3.LEFT
                )

            if not _is_opaque(image, x + 1, y):
                _add_quad(
                    vertices,
                    normals,
                    indices,
                    Vector3(x1, y0, half_depth),
                    Vector3(x1, y1, half_depth),
                    Vector3(x1, y1, -half_depth),
                    Vector3(x1, y0, -half_depth),
                    Vector3.RIGHT
                )

            if not _is_opaque(image, x, y - 1):
                _add_quad(
                    vertices,
                    normals,
                    indices,
                    Vector3(x0, y1, half_depth),
                    Vector3(x1, y1, half_depth),
                    Vector3(x1, y1, -half_depth),
                    Vector3(x0, y1, -half_depth),
                    Vector3.UP
                )

            if not _is_opaque(image, x, y + 1):
                _add_quad(
                    vertices,
                    normals,
                    indices,
                    Vector3(x0, y0, -half_depth),
                    Vector3(x1, y0, -half_depth),
                    Vector3(x1, y0, half_depth),
                    Vector3(x0, y0, half_depth),
                    Vector3.DOWN
                )

    if vertices.size() == 0:
        return mesh

    var arrays := []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = indices
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    return mesh


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


func _is_opaque(image: Image, x: int, y: int) -> bool:
    if x < 0 or y < 0 or x >= image.get_width() or y >= image.get_height():
        return false
    return image.get_pixel(x, y).a8 > alpha_threshold


func _update_visuals() -> void:
    var camera := _get_active_camera()
    if not camera:
        return

    var weights: Dictionary = _direction_weights(camera)
    var strongest: float = max(weights["front"], weights["back"], weights["left"], weights["right"])
    var canonical_closeness: float = clamp((strongest - 0.5) / 0.5, 0.0, 1.0)
    var proxy_alpha: float = proxy_visibility * pow(1.0 - canonical_closeness, max(angle_fade_strength, 0.001))

    if _proxy_material:
        _proxy_material.albedo_color = Color(
            side_material_color.r,
            side_material_color.g,
            side_material_color.b,
            proxy_alpha
        )

    for direction in _cards.keys():
        var card := _cards[direction] as Sprite3D
        var snapped_weight := pow(clamp(weights[direction], 0.0, 1.0), max(canonical_snap_strength, 0.001))
        var alpha := smoothstep(0.04, 0.78, snapped_weight)
        card.modulate = Color(1.0, 1.0, 1.0, alpha)
        card.visible = alpha > 0.01


func _direction_weights(camera: Camera3D) -> Dictionary:
    var camera_direction := (global_position - camera.global_position).normalized()
    var local_basis := global_transform.basis
    var front_dot: float = max(0.0, camera_direction.dot(-local_basis.z.normalized()))
    var back_dot: float = max(0.0, camera_direction.dot(local_basis.z.normalized()))
    var right_dot: float = max(0.0, camera_direction.dot(local_basis.x.normalized()))
    var left_dot: float = max(0.0, camera_direction.dot(-local_basis.x.normalized()))
    var total: float = max(front_dot + back_dot + left_dot + right_dot, 0.0001)

    return {
        "front": front_dot / total,
        "back": back_dot / total,
        "left": left_dot / total,
        "right": right_dot / total,
    }


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
