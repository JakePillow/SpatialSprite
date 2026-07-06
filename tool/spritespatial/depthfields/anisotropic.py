from __future__ import annotations

import numpy as np

from spritespatial.depthfields.edt import euclidean_distance_transform


def anisotropic_edt(mask: np.ndarray, anisotropy: tuple[float, float]) -> np.ndarray:
    """EDT with semantic x/y radii; larger radii preserve depth farther along that axis."""
    radius_x = max(float(anisotropy[0]), 1e-4)
    radius_y = max(float(anisotropy[1]), 1e-4)
    return euclidean_distance_transform(mask, sampling=(1.0 / radius_y, 1.0 / radius_x))
