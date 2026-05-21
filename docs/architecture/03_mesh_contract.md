# Mesh Contract

The mesh is an extracted representation of the validated semantic SDF, not a replacement source of truth.

Required behaviour:
- Surface nets input must be loadable and dtype-correct.
- Surface nets extraction must produce nonzero vertices/faces.
- Semantic labels present in volume must be preserved in mesh material groups unless explicitly exempted.
- Boundary metadata must mark semantic boundaries, silhouette vertices, and outline-related groups.
- Degenerate faces and disconnected components must be reported.

Mesh quality can improve later, but mesh generation remains validation-gated.
