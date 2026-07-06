from __future__ import annotations

from pathlib import Path
from typing import Any

from spritespatial.depthfields.legacy import build_legacy_mylar_front_depth


def build_mylar_front_depth(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    output_dir: Path,
    max_total_depth: float = 0.60,
) -> dict[str, Any]:
    """Compatibility entrypoint for callers that still import mylar_depth."""
    return build_legacy_mylar_front_depth(size, parts, output_dir, max_total_depth)
