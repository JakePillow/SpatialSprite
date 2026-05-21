# SpriteSpatial Master Blueprint

SpriteSpatial is a deterministic sprite-to-spatial-model pipeline. The system treats the authored sprite as the source of truth, then builds semantic depth, closed volume, mesh, and render artefacts through validation-gated stages.

Locked principles:
- Deterministic: every stage must be reproducible from explicit assets, profiles, and authored overrides.
- Silhouette-first: front readability and canonical-view silhouettes outrank local surface prettiness.
- Semantic-authoritative: labels, overrides, and semantic boundaries guide geometry and materials.
- NPR-first: runtime rendering starts from low-poly, toon/NPR readability rather than realism.
- Non-generative runtime: generated or AI-assisted suggestions may help authoring, but runtime assets are explicit files.
- Validation-gated: every promoted path must produce measurable reports before visual refinement.

Current canonical path:
2D sprite -> semantic decomposition -> authored semantic overrides -> semantic depth/continuity -> Mylar EDT closed SDF -> surface nets mesh -> Godot NPR preview -> visual diagnostics.

Phase 6 work should use the diagnostics layer to decide where canonical-view correction is needed before changing geometry.
