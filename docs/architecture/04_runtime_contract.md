# Runtime Contract

Runtime rendering is NPR-first and non-generative.

Required behaviour:
- Godot loads explicit mesh JSON and material metadata.
- Vertex colour or semantic material groups drive the baseline look.
- Toon/NPR shading preserves sprite readability.
- Inverted-hull outline restores silhouette readability at distance.
- Runtime does not call AI, modify art, or infer missing views.

Advanced rendering can be introduced only after the baseline remains measurable from canonical captures.
