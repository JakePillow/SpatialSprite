import numpy as np

from spritespatial.depthfields.edt import euclidean_distance_transform, normalise_distance


def test_plain_edt_peaks_inside_region() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[1:8, 1:8] = True
    edt = euclidean_distance_transform(mask)
    assert edt[4, 4] > edt[1, 1] > 0
    normalised = normalise_distance(edt, mask)
    assert normalised[4, 4] == 1.0
    assert np.all(normalised[~mask] == 0.0)
