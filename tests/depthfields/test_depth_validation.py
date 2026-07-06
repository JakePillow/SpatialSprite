import numpy as np

from spritespatial.depthfields import DepthConfig, generate_depth_field


def test_known_profile_passes_acceptance_criteria() -> None:
    alpha = np.zeros((9, 9), dtype=bool)
    alpha[1:8, 1:8] = True
    result = generate_depth_field(
        {"asset_id": "known", "alpha_mask": alpha},
        [{"region_id": "head", "semantic_label": "head", "mask": alpha}],
        DepthConfig(),
    )
    assert result.validation.passed
    assert np.all(result.pinned_depth_field[result.silhouette_mask] == 0.0)


def test_missing_profile_is_an_error() -> None:
    alpha = np.ones((5, 5), dtype=bool)
    result = generate_depth_field(
        {"asset_id": "unknown", "alpha_mask": alpha},
        [{"region_id": "mystery", "semantic_label": "mystery", "mask": alpha}],
    )
    assert not result.validation.passed
    assert any(issue.code == "implicit_profile_fallback" for issue in result.validation.issues)
