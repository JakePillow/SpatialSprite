import numpy as np

from spritespatial.depthfields.anisotropic import anisotropic_edt


def test_anisotropy_changes_depth_topology() -> None:
    mask = np.zeros((11, 11), dtype=bool)
    mask[1:10, 1:10] = True
    horizontal = anisotropic_edt(mask, (2.0, 0.5))
    vertical = anisotropic_edt(mask, (0.5, 2.0))
    assert not np.allclose(horizontal, vertical)
    assert horizontal[5, 3] != vertical[5, 3]
