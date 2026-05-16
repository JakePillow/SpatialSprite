extends CharacterBody3D

@export var front_texture: Texture2D
@export var back_texture: Texture2D
@export var left_texture: Texture2D
@export var right_texture: Texture2D

@export var sprite_width_units := 1.15
@export var sprite_height_units := 1.9
@export var body_depth_units := 0.46
@export_range(0.0, 1.0, 0.01) var sprite_opacity := 0.92
@export_range(0.0, 1.0, 0.01) var proxy_opacity := 0.72
@export var canonical_snap_strength := 2.2
@export var texture_projection_mode := "keyview_cards"
@export var show_proxy_geometry := true
@export var show_keyview_cards := true
@export var side_material_color := Color(0.09, 0.10, 0.09, 1.0)
@export_range(0, 255, 1) var alpha_threshold := 16
@export var debug_overlay := true
@export var debug_log := false
@export var debug_log_interval := 0.35
@export_range(0.0, 1.0, 0.01) var canonical_proxy_visibility := 0.24

var _proxy_parts: Array[MeshInstance3D] = []
var _proxy_material: StandardMaterial3D
var _cards := {}
var _debug_label: Label3D
var _last_log_time := 0.0
var _metrics := {
    "pixel_width": 24.0,
    "pixel_height": 32.0,
    "bounds": Rect2i(0, 0, 24, 32),
}


func _ready() -> void:
    _metrics = _estimate_sprite_metrics(front_texture)
    _build_proxy_material()
    _build_proxy_body()
    _build_keyview_cards()
    _build_debug_label()
    _update_visuals(0.0)


func _process(delta: float) -> void:
    _update_visuals(delta)


func _build_proxy_material() -> void:
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


func _build_proxy_body() -> void:
    var height: float = sprite_height_units
    var alpha_width: float = _metrics["pixel_width"]
    var alpha_height: float = max(_metrics["pixel_height"], 1.0)
    var estimated_width: float = clamp(sprite_height_units * (alpha_width / alpha_height), sprite_width_units * 0.55, sprite_width_units)
    var width: float = estimated_width
    var depth: float = body_depth_units

    var head_height := height * 0.25
    var torso_height := height * 0.36
    var leg_height := height * 0.34
    var foot_height := height * 0.08

    var leg_width := width * 0.22
    var torso_width := width * 0.58
    var head_width := width * 0.48
    var arm_width := width * 0.17
    var shoulder_y := leg_height + torso_height * 0.62

    _add_part("TorsoProxy", Vector3(torso_width, torso_height, depth * 0.72), Vector3(0.0, leg_height + torso_height * 0.5, 0.0))
    _add_part("HeadProxy", Vector3(head_width, head_height, depth * 0.62), Vector3(0.0, leg_height + torso_height + head_height * 0.5, 0.0))
    _add_part("LeftLegProxy", Vector3(leg_width, leg_height, depth * 0.48), Vector3(-leg_width * 0.62, leg_height * 0.5, 0.0))
    _add_part("RightLegProxy", Vector3(leg_width, leg_height, depth * 0.48), Vector3(leg_width * 0.62, leg_height * 0.5, 0.0))
    _add_part("LeftFootProxy", Vector3(leg_width * 1.28, foot_height, depth * 0.68), Vector3(-leg_width * 0.7, foot_height * 0.5, -depth * 0.06))
    _add_part("RightFootProxy", Vector3(leg_width * 1.28, foot_height, depth * 0.68), Vector3(leg_width * 0.7, foot_height * 0.5, depth * 0.06))
    _add_part("LeftArmProxy", Vector3(arm_width, torso_height * 0.85, depth * 0.52), Vector3(-torso_width * 0.62, shoulder_y, 0.0))
    _add_part("RightArmProxy", Vector3(arm_width, torso_height * 0.85, depth * 0.52), Vector3(torso_width * 0.62, shoulder_y, 0.0))


func _add_part(part_name: String, size: Vector3, position: Vector3) -> void:
    var mesh := BoxMesh.new()
    mesh.size = size

    var instance := MeshInstance3D.new()
    instance.name = part_name
    instance.mesh = mesh
    instance.position = position
    instance.material_override = _proxy_material
    add_child(instance)
    _proxy_parts.append(instance)


func _build_keyview_cards() -> void:
    var card_y := sprite_height_units * 0.5
    var front_z := -body_depth_units * 0.5 - 0.004
    var back_z := body_depth_units * 0.5 + 0.004
    var side_x := body_depth_units * 0.5 + 0.004

    _cards = {
        "front": _create_key_card("FrontKeyView", front_texture, Vector3(0.0, card_y, front_z), 0.0),
        "back": _create_key_card("BackKeyView", back_texture, Vector3(0.0, card_y, back_z), PI),
        "left": _create_key_card("LeftKeyView", left_texture, Vector3(-side_x, card_y, 0.0), PI * 0.5),
        "right": _create_key_card("RightKeyView", right_texture, Vector3(side_x, card_y, 0.0), -PI * 0.5),
    }


func _create_key_card(card_name: String, texture: Texture2D, position: Vector3, y_rotation: float) -> Sprite3D:
    var card := Sprite3D.new()
    card.name = card_name
    card.texture = texture
    card.centered = true
    card.pixel_size = _pixel_size_for_texture(texture)
    card.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
    card.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
    card.billboard = BaseMaterial3D.BILLBOARD_DISABLED
    card.position = position
    card.rotation.y = y_rotation
    add_child(card)
    return card


func _build_debug_label() -> void:
    _debug_label = Label3D.new()
    _debug_label.name = "DebugOverlay"
    _debug_label.visible = debug_overlay
    _debug_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    _debug_label.font_size = 18
    _debug_label.pixel_size = 0.004
    _debug_label.outline_size = 4
    _debug_label.position = Vector3(0.0, sprite_height_units + 0.35, 0.0)
    add_child(_debug_label)


func _update_visuals(delta: float) -> void:
    var camera := _get_active_camera()
    if not camera:
        return

    var angle := _camera_angle_degrees(camera)
    var weights := _keyview_weights(camera)
    var nearest_view := _nearest_view(weights)
    var visible_sprite := nearest_view
    var strongest_weight: float = max(weights["front"], weights["back"], weights["left"], weights["right"])
    var transition_weight: float = 1.0 - strongest_weight
    var proxy_visibility: float = proxy_opacity * lerp(canonical_proxy_visibility, 1.0, transition_weight) if show_proxy_geometry else 0.0

    if _proxy_material:
        _proxy_material.albedo_color = Color(
            side_material_color.r,
            side_material_color.g,
            side_material_color.b,
            proxy_visibility
        )

    for part in _proxy_parts:
        part.visible = show_proxy_geometry and proxy_visibility > 0.01

    for direction in _cards.keys():
        var card := _cards[direction] as Sprite3D
        var weight: float = weights[direction]
        var alpha: float = sprite_opacity * pow(weight, max(canonical_snap_strength, 0.001))
        card.visible = show_keyview_cards and alpha > 0.01
        card.modulate = Color(1.0, 1.0, 1.0, alpha)

    _update_debug(angle, nearest_view, weights, visible_sprite, proxy_visibility, delta)


func _keyview_weights(camera: Camera3D) -> Dictionary:
    var camera_direction := (global_position - camera.global_position).normalized()
    var basis := global_transform.basis
    var front_dot: float = max(0.0, camera_direction.dot(-basis.z.normalized()))
    var back_dot: float = max(0.0, camera_direction.dot(basis.z.normalized()))
    var right_dot: float = max(0.0, camera_direction.dot(-basis.x.normalized()))
    var left_dot: float = max(0.0, camera_direction.dot(basis.x.normalized()))

    var front := pow(front_dot, max(canonical_snap_strength, 0.001))
    var back := pow(back_dot, max(canonical_snap_strength, 0.001))
    var right := pow(right_dot, max(canonical_snap_strength, 0.001))
    var left := pow(left_dot, max(canonical_snap_strength, 0.001))
    var total: float = max(front + back + left + right, 0.0001)

    return {
        "front": front / total,
        "back": back / total,
        "left": left / total,
        "right": right / total,
    }


func _nearest_view(weights: Dictionary) -> String:
    var best := "front"
    var best_weight: float = weights["front"]
    for direction in ["back", "left", "right"]:
        if weights[direction] > best_weight:
            best = direction
            best_weight = weights[direction]
    return best


func _camera_angle_degrees(camera: Camera3D) -> float:
    var camera_direction := (global_position - camera.global_position).normalized()
    var local_x := global_transform.basis.x.normalized()
    var local_front := -global_transform.basis.z.normalized()
    var x := camera_direction.dot(local_x)
    var z := camera_direction.dot(local_front)
    return fposmod(rad_to_deg(atan2(x, z)), 360.0)


func _estimate_sprite_metrics(texture: Texture2D) -> Dictionary:
    if not texture:
        return _metrics

    var image := texture.get_image()
    if not image:
        return _metrics

    image.convert(Image.FORMAT_RGBA8)
    var min_x := image.get_width()
    var min_y := image.get_height()
    var max_x := 0
    var max_y := 0
    var found := false

    for y in range(image.get_height()):
        for x in range(image.get_width()):
            if image.get_pixel(x, y).a8 <= alpha_threshold:
                continue
            found = true
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    if not found:
        return _metrics

    var bounds := Rect2i(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    return {
        "pixel_width": float(bounds.size.x),
        "pixel_height": float(bounds.size.y),
        "bounds": bounds,
    }


func _pixel_size_for_texture(texture: Texture2D) -> float:
    if not texture:
        return 0.06
    return sprite_height_units / max(float(texture.get_height()), 1.0)


func _update_debug(
    angle: float,
    nearest_view: String,
    weights: Dictionary,
    visible_sprite: String,
    proxy_visibility: float,
    delta: float
) -> void:
    var message := "Track C proxy model\nangle: %06.2f\nnearest: %s\nweights F/B/L/R: %.2f %.2f %.2f %.2f\nvisible_sprite: %s\nproxy_visibility: %.2f\nmode: %s" % [
        angle,
        nearest_view,
        weights["front"],
        weights["back"],
        weights["left"],
        weights["right"],
        visible_sprite,
        proxy_visibility,
        texture_projection_mode,
    ]

    if _debug_label:
        _debug_label.visible = debug_overlay
        _debug_label.text = message

    if debug_log:
        _last_log_time += delta
        if _last_log_time >= debug_log_interval:
            print(message.replace("\n", " | "))
            _last_log_time = 0.0


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
