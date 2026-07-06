from __future__ import annotations

from collections import defaultdict

import numpy as np

from spritespatial.depthfields.schema import BlendJunction


def blend_semantic_junctions(
    depth: np.ndarray,
    labels: np.ndarray,
    alpha_mask: np.ndarray,
    radii: dict[str, int],
    constraints: np.ndarray | None = None,
) -> tuple[np.ndarray, list[BlendJunction]]:
    source = np.asarray(depth, dtype=np.float32)
    blended = source.copy()
    alpha = np.asarray(alpha_mask, dtype=bool)
    blocked = (
        np.asarray(constraints, dtype=bool)
        if constraints is not None
        else np.zeros(alpha.shape, dtype=bool)
    )
    boundary: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    before: dict[tuple[str, str], float] = defaultdict(float)

    for y, x in np.argwhere(alpha & ~blocked):
        label = str(labels[y, x])
        if not label:
            continue
        for ny, nx in ((y, x + 1), (y + 1, x)):
            if (
                ny >= alpha.shape[0]
                or nx >= alpha.shape[1]
                or not alpha[ny, nx]
                or blocked[ny, nx]
            ):
                continue
            other = str(labels[ny, nx])
            if not other or other == label:
                continue
            key = tuple(sorted((label, other)))
            boundary[key].update(((int(y), int(x)), (int(ny), int(nx))))
            before[key] = max(before[key], abs(float(source[y, x]) - float(source[ny, nx])))

    for key, pixels in boundary.items():
        radius = max(radii.get(key[0], 1), radii.get(key[1], 1))
        if radius <= 0:
            continue
        for y, x in pixels:
            y0, y1 = max(0, y - radius), min(source.shape[0], y + radius + 1)
            x0, x1 = max(0, x - radius), min(source.shape[1], x + radius + 1)
            valid = alpha[y0:y1, x0:x1] & ~blocked[y0:y1, x0:x1]
            values = source[y0:y1, x0:x1][valid]
            if values.size:
                blended[y, x] = 0.55 * source[y, x] + 0.45 * float(values.mean())

    junctions: list[BlendJunction] = []
    for key, pixels in sorted(boundary.items()):
        after = 0.0
        for y, x in pixels:
            for ny, nx in ((y, x + 1), (y + 1, x)):
                if (ny, nx) in pixels and str(labels[y, x]) != str(labels[ny, nx]):
                    after = max(after, abs(float(blended[y, x]) - float(blended[ny, nx])))
        junctions.append(BlendJunction(key[0], key[1], len(pixels), before[key], after))
    return blended, junctions
