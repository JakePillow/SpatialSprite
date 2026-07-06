import numpy as np

from spritespatial.depthfields.pinning import pin_silhouette, silhouette_mask


def test_pinning_is_enforced_after_blending() -> None:
    alpha = np.zeros((8, 8), dtype=bool)
    alpha[1:7, 1:7] = True
    depth = np.full(alpha.shape, 0.4, dtype=np.float32)
    pinned, seam = pin_silhouette(depth, alpha)
    assert np.array_equal(seam, silhouette_mask(alpha))
    assert np.all(pinned[seam] == 0.0)
    assert pinned[3, 3] == np.float32(0.4)
    assert np.all(pinned[~alpha] == 0.0)
