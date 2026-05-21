# Depth Contract

Depth generation is deterministic and profile-controlled. The accepted closed-body backend uses semantic Mylar EDT fields, derived back hemisphere rules, and silhouette seam closure.

Required behaviour:
- Front silhouette pixels are pinned to zero depth.
- Back depth must meet the same seam.
- Semantic depth must stay within profile budget.
- Inferred back and side depth must be marked as inferred or primitive-prior authority.

Phase 6 may correct view silhouettes, but must not hide missing view authority. Authored back/side references must remain distinguishable from inferred geometry.
