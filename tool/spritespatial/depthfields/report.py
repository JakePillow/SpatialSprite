from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from spritespatial.depthfields.schema import DepthFieldResult
from spritespatial.depthfields.visualise import write_visual_report


def write_depth_result(
    result: DepthFieldResult, output_dir: Path, *, emit_debug: bool = True
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays_dir = output_dir / "arrays"
    arrays_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "global_depth_field": arrays_dir / "global_depth_field.npy",
        "blended_depth_field": arrays_dir / "blended_depth_field.npy",
        "pinned_depth_field": arrays_dir / "pinned_depth_field.npy",
        "depth_report": output_dir / "depth_field_report.json",
    }
    np.save(paths["global_depth_field"], result.global_depth_field)
    np.save(paths["blended_depth_field"], result.blended_depth_field)
    np.save(paths["pinned_depth_field"], result.pinned_depth_field)

    region_arrays = arrays_dir / "regions"
    region_arrays.mkdir(parents=True, exist_ok=True)
    for region_id, field in result.region_depth_fields.items():
        np.save(region_arrays / f"{_safe(region_id)}.npy", field)
    paths["region_depth_fields"] = region_arrays
    if emit_debug:
        paths.update(write_visual_report(result, output_dir / "visuals"))
    result.artifact_paths.update(paths)
    paths["depth_report"].write_text(
        json.dumps(result.to_metadata_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return paths


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_").lower() or "region"
