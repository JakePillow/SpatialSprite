from __future__ import annotations

import numpy as np


def euclidean_distance_transform(
    mask: np.ndarray, sampling: tuple[float, float] = (1.0, 1.0)
) -> np.ndarray:
    """Return exact foreground-to-background distances without a SciPy dependency."""
    source = np.asarray(mask, dtype=bool)
    result = np.zeros(source.shape, dtype=np.float32)
    if not source.any():
        return result
    padded = np.pad(source, 1, constant_values=False)
    outside = np.argwhere(~padded).astype(np.float32)
    inside = np.argwhere(padded)
    sy, sx = max(float(sampling[0]), 1e-6), max(float(sampling[1]), 1e-6)
    for y, x in inside:
        delta = outside - np.array([y, x], dtype=np.float32)
        squared = (delta[:, 0] * sy) ** 2 + (delta[:, 1] * sx) ** 2
        result[y - 1, x - 1] = float(np.sqrt(squared.min()))
    return result


def normalise_distance(values: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    data = np.asarray(values, dtype=np.float32)
    selected = data[np.asarray(mask, dtype=bool)] if mask is not None else data.reshape(-1)
    maximum = float(selected.max()) if selected.size else 0.0
    if maximum <= 1e-6:
        return np.zeros(data.shape, dtype=np.float32)
    return (data / maximum).astype(np.float32)
