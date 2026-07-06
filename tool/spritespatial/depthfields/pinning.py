from __future__ import annotations

import numpy as np


def silhouette_mask(alpha_mask: np.ndarray) -> np.ndarray:
    alpha = np.asarray(alpha_mask, dtype=bool)
    padded = np.pad(alpha, 1, constant_values=False)
    interior = (
        padded[1:-1, :-2] & padded[1:-1, 2:]
        & padded[:-2, 1:-1] & padded[2:, 1:-1]
    )
    return alpha & ~interior


def pin_silhouette(
    depth: np.ndarray, alpha_mask: np.ndarray, constraints: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    seam = silhouette_mask(alpha_mask)
    pinned = np.asarray(depth, dtype=np.float32).copy()
    pinned[~np.asarray(alpha_mask, dtype=bool)] = 0.0
    pinned[seam] = 0.0
    if constraints is not None:
        pinned[np.asarray(constraints, dtype=bool)] = 0.0
    return pinned, seam
