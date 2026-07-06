import json

import numpy as np

from spritespatial.depthfields import DepthConfig, generate_depth_field


def test_depth_result_is_versioned_and_serialised(tmp_path) -> None:
    alpha = np.zeros((8, 8), dtype=bool)
    alpha[1:7, 1:7] = True
    output = tmp_path / "depth"
    result = generate_depth_field(
        {"asset_id": "serial", "alpha_mask": alpha},
        [{"region_id": "torso", "semantic_label": "torso", "mask": alpha}],
        DepthConfig(output_dir=output),
    )
    report = json.loads((output / "depth_field_report.json").read_text(encoding="utf-8"))
    assert report["asset_id"] == "serial"
    assert report["depth_version"] == result.depth_version
    assert report["validation"]["passed"]
    assert (output / "arrays" / "pinned_depth_field.npy").exists()
    assert (output / "visuals" / "depth_cross_section.png").exists()
