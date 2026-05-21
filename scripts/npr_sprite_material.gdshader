shader_type spatial;
render_mode cull_back, specular_disabled;

uniform float shadow_threshold : hint_range(-1.0, 1.0) = 0.18;
uniform float shadow_strength : hint_range(0.0, 1.0) = 0.42;
uniform float rim_strength : hint_range(0.0, 1.0) = 0.12;

void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = 1.0;
}

void light() {
	float ndotl = dot(NORMAL, LIGHT);
	float band = ndotl > shadow_threshold ? 1.0 : shadow_strength;
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0) * rim_strength;
	DIFFUSE_LIGHT += ALBEDO * LIGHT_COLOR * ATTENUATION * (band + rim);
}
