import numpy as np

from spritespatial.depthfields import DepthConfig, generate_depth_field


def test_diagnostics_are_emitted_per_region() -> None:
    alpha = np.zeros((12, 10), dtype=bool)
    alpha[1:11, 1:9] = True
    head = np.zeros_like(alpha)
    torso = np.zeros_like(alpha)
    head[1:6, 1:9] = True
    torso[6:11, 1:9] = True
    result = generate_depth_field(
        {"asset_id": "diagnostic", "alpha_mask": alpha},
        [
            {"region_id": "head", "semantic_label": "head", "mask": head},
            {"region_id": "torso", "semantic_label": "torso", "mask": torso},
        ],
        DepthConfig(),
    )
    assert len(result.diagnostics.regions) == 2
    assert result.diagnostics.assigned_pixel_count == result.diagnostics.opaque_pixel_count
    assert result.diagnostics.silhouette_pin_passed
    assert {item.region_id for item in result.diagnostics.regions} == {"head", "torso"}
