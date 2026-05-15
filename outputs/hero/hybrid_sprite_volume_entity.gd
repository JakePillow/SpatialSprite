extends Node3D

@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D
@export var pixel_size := 0.06
@export var proxy_depth := 0.18
@export var proxy_visibility := 0.46
@export var side_material_color := Color(0.08, 0.09, 0.08, 1.0)
@export var angle_fade_strength := 1.0
@export_range(0, 255, 1) var alpha_threshold := 16
@export var canonical_hide_angle := 0.86

var _proxy: MeshInstance3D
var _front_card: Sprite3D
var _back_card: Sprite3D
var _left_card: Sprite3D
var _right_card: Sprite3D
var _cards: Dictionary = {}
var _proxy_material: StandardMaterial3D


func _ready() -> void:
    _build_proxy()
    _build_cards()
    _update_visuals()


func _process(_delta: float) -> void:
    _update_visuals()


func _build_proxy() -> void:
    _proxy = MeshInstance3D.new()
    _proxy.name = "AlphaSilhouetteProxy"
    _proxy.mesh = _build_silhouette_mesh()
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
    _proxy.material_override = _proxy_material
    add_child(_proxy)


func _build_cards() -> void:
    _front_card = _create_card("FrontCard", front_texture, proxy_depth * -0.5 - 0.002, 0.0)
    _back_card = _create_card("BackCard", back_texture, proxy_depth * 0.5 + 0.002, PI)
    _left_card = _create_card("LeftCard", left_texture, 0.0, PI * 0.5)
    _right_card = _create_card("RightCard", right_texture, 0.0, -PI * 0.5)

    _cards = {
        "front": _front_card,
        "back": _back_card,
        "left": _left_card,
        "right": _right_card,
    }


func _create_card(card_name: String, texture: Texture2D, z_offset: float, y_rotation: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = texture
    card.pixel_size = pixel_size
    card.centered = true
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = Vector3(0.0, _sprite_y_offset(texture), z_offset)
    card.rotation.y = y_rotation
    add_child(card)
    return card


func _build_silhouette_mesh() -> ArrayMesh:
    var mesh := ArrayMesh.new()
    if not front_texture:
        return mesh

    var image := front_texture.get_image()
    if not image:
        return mesh

    image.convert(Image.FORMAT_RGBA8)
    var width = image.get_width()
    var height = image.get_height()
    var half_depth = proxy_depth * 0.5
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var indices := PackedInt32Array()

    for y in range(height):
        for x in range(width):
            if not _is_opaque(image, x, y):
                continue

            var x0 = (float(x) - float(width) * 0.5) * pixel_size
            var x1 = x0 + pixel_size
            var y1 = (float(height) - float(y)) * pixel_size
            var y0 = y1 - pixel_size

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
    var start = vertices.size()
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
    var camera = _get_active_camera()
    if not camera:
        return

    var weights = _direction_weights(camera)
    var strongest = max(weights["front"], weights["back"], weights["left"], weights["right"])
    var canonical_closeness = clamp((strongest - 0.5) / 0.5, 0.0, 1.0)
    var oblique_visibility = 1.0 - smoothstep(canonical_hide_angle, 1.0, canonical_closeness)
    var proxy_alpha = proxy_visibility * pow(oblique_visibility, max(angle_fade_strength, 0.001))
    _proxy_material.albedo_color = Color(
        side_material_color.r,
        side_material_color.g,
        side_material_color.b,
        proxy_alpha
    )

    for direction in _cards.keys():
        var card = _cards[direction] as Sprite3D
        var alpha = smoothstep(0.18, 0.82, weights[direction])
        card.modulate = Color(1.0, 1.0, 1.0, alpha)
        card.visible = alpha > 0.02


func _direction_weights(camera: Camera3D) -> Dictionary:
    var to_camera = (camera.global_position - global_position).normalized()
    var front_dot = max(0.0, to_camera.dot(-global_transform.basis.z.normalized()))
    var back_dot = max(0.0, to_camera.dot(global_transform.basis.z.normalized()))
    var right_dot = max(0.0, to_camera.dot(global_transform.basis.x.normalized()))
    var left_dot = max(0.0, to_camera.dot(-global_transform.basis.x.normalized()))
    var total = max(front_dot + back_dot + left_dot + right_dot, 0.0001)

    return {
        "front": front_dot / total,
        "back": back_dot / total,
        "left": left_dot / total,
        "right": right_dot / total,
    }


func _sprite_y_offset(texture: Texture2D) -> float:
    if not texture:
        return 0.0
    return texture.get_height() * pixel_size * 0.5


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
