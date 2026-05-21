# Semantic Contract

Semantic labels are the authority for part identity. Heuristics may propose labels, but authored masks and validation reports decide the accepted semantic state.

Required behaviour:
- Authored overrides must preserve opaque sprite coverage.
- Critical labels such as head, torso, limbs, boots/feet, outline, and equipment must remain traceable.
- Semantic boundaries must be preserved through primitive assignment, SDF volume, surface nets, and material grouping.
- Unknown labels are allowed only as measured fallback, not as silent authority.

Runtime rule:
Semantic data is not inferred in Godot. Godot consumes mesh metadata and material groups already emitted by the build pipeline.
