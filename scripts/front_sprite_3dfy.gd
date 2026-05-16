extends Node3D

@export var front_texture: Texture2D
@export var sprite_width_units := 1.15
@export var sprite_height_units := 1.9
@export var body_depth_units := 0.42
@export var show_front_sprite := true
@export var show_proxy_volume := true
@export var proxy_depth := 0.42
@export_range(0.0, 1.0, 0.01) var proxy_opacity := 0.68
@export var simplify_proxy := true
@export var side_material_color := Color(0.12, 0.14, 0.12, 1.0)
@export var front_projection_offset := 0.006
@export_range(0, 255, 1) var alpha_threshold := 16
@export_range(1, 8, 1) var simplified_band_pixels := 3

var _front_card: Sprite3D
var _proxy: MeshInstance3D
var _proxy_material: StandardMaterial3D


func _ready() -> void:
    _build_proxy()
    _build_front_projection()
    _apply_debug_controls()


func _process(_delta: float) -> void:
    _apply_debug_controls()


func _build_proxy() -> void:
    _proxy = MeshInstance3D.new()
    _proxy.name = "AlphaDerivedProxyVolume"
    _proxy.mesh = _build_extruded_silhouette_mesh()

    _proxy_material = StandardMaterial3D.new()
    _proxy_material.albedo_color = Color(
        side_material_color.r,
        side_material_color.g,
        side_material_color.b,
        proxy_opacity
    )
    _proxy_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    _proxy_material.roughness = 1.0
    _proxy_material.cull_mode = BaseMaterial3D.CULL_DISABLED
    _proxy.material_override = _proxy_material

    add_child(_proxy)


func _build_front_projection() -> void:
    _front_card = Sprite3D.new()
    _front_card.name = "AuthoredFrontProjection"
    _front_card.texture = front_texture
    _front_card.centered = true
    _front_card.pixel_size = _front_pixel_size()
    _front_card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    _front_card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    _front_card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    _front_card.position = Vector3(0.0, sprite_height_units * 0.5, -_active_depth() * 0.5 - front_projection_offset)
    add_child(_front_card)


func _apply_debug_controls() -> void:
    if _front_card:
        _front_card.visible = show_front_sprite
        _front_card.pixel_size = _front_pixel_size()
        _front_card.position = Vector3(0.0, sprite_height_units * 0.5, -_active_depth() * 0.5 - front_projection_offset)

    if _proxy:
        _proxy.visible = show_proxy_volume

    if _proxy_material:
        _proxy_material.albedo_color = Color(
            side_material_color.r,
            side_material_color.g,
            side_material_color.b,
            proxy_opacity
        )


func _build_extruded_silhouette_mesh() -> ArrayMesh:
    var mesh := ArrayMesh.new()
    if not front_texture:
        return mesh

    var image := front_texture.get_image()
    if not image:
        return mesh

    image.convert(Image.FORMAT_RGBA8)
    var bands := _extract_silhouette_bands(image)
    if bands.is_empty():
        return mesh

    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var indices := PackedInt32Array()
    var half_depth := _active_depth() * 0.5

    for band in bands:
        var x0: float = band["x0"]
        var x1: float = band["x1"]
        var y0: float = band["y0"]
        var y1: float = band["y1"]

        _add_box_shell(
            vertices,
            normals,
            indices,
            x0,
            x1,
            y0,
            y1,
            -half_depth,
            half_depth
        )

    var arrays := []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_INDEX] = indices
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    return mesh


func _extract_silhouette_bands(image: Image) -> Array:
    var width := image.get_width()
    var height := image.get_height()
    var band_pixels := simplified_band_pixels if simplify_proxy else 1
    var bands := []
    var previous_band := {}
    var units_per_pixel := _front_pixel_size()

    for y_start in range(0, height, band_pixels):
        var y_end: int = min(y_start + band_pixels, height)
        var min_x := width
        var max_x := -1

        for y in range(y_start, y_end):
            for x in range(width):
                if image.get_pixel(x, y).a8 <= alpha_threshold:
                    continue
                min_x = min(min_x, x)
                max_x = max(max_x, x)

        if max_x < min_x:
            if not previous_band.is_empty():
                bands.append(previous_band)
                previous_band = {}
            continue

        var x0 := (float(min_x) - float(width) * 0.5) * units_per_pixel
        var x1 := (float(max_x + 1) - float(width) * 0.5) * units_per_pixel
        var y1 := (float(height) - float(y_start)) * units_per_pixel
        var y0 := (float(height) - float(y_end)) * units_per_pixel
        var current_band := {
            "x0": x0,
            "x1": x1,
            "y0": y0,
            "y1": y1,
        }

        if simplify_proxy and _can_merge_bands(previous_band, current_band, units_per_pixel * 1.75):
            previous_band["x0"] = min(previous_band["x0"], current_band["x0"])
            previous_band["x1"] = max(previous_band["x1"], current_band["x1"])
            previous_band["y0"] = current_band["y0"]
        else:
            if not previous_band.is_empty():
                bands.append(previous_band)
            previous_band = current_band

    if not previous_band.is_empty():
        bands.append(previous_band)

    return bands


func _can_merge_bands(previous_band: Dictionary, current_band: Dictionary, tolerance: float) -> bool:
    if previous_band.is_empty():
        return false
    return abs(previous_band["x0"] - current_band["x0"]) <= tolerance and abs(previous_band["x1"] - current_band["x1"]) <= tolerance


func _add_box_shell(
    vertices: PackedVector3Array,
    normals: PackedVector3Array,
    indices: PackedInt32Array,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float
) -> void:
    _add_quad(vertices, normals, indices, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x0, y1, z0), Vector3.FORWARD)
    _add_quad(vertices, normals, indices, Vector3(x1, y0, z1), Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x1, y1, z1), Vector3.BACK)
    _add_quad(vertices, normals, indices, Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x0, y1, z0), Vector3(x0, y0, z0), Vector3.LEFT)
    _add_quad(vertices, normals, indices, Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x1, y0, z1), Vector3.RIGHT)
    _add_quad(vertices, normals, indices, Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1), Vector3.UP)
    _add_quad(vertices, normals, indices, Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3(x1, y0, z0), Vector3(x0, y0, z0), Vector3.DOWN)


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


func _front_pixel_size() -> float:
    if not front_texture:
        return sprite_height_units / 32.0
    return sprite_height_units / max(float(front_texture.get_height()), 1.0)


func _active_depth() -> float:
    return proxy_depth if proxy_depth > 0.0 else body_depth_units
