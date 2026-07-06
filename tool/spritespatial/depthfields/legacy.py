from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from spritespatial.depthfields.composition import generate_depth_field
from spritespatial.depthfields.report import write_depth_result
from spritespatial.depthfields.schema import DepthConfig
from spritespatial.depthfields.visualise import write_heatmap, write_mask

Pixel = tuple[int, int]


def build_legacy_mylar_front_depth(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    output_dir: Path,
    max_total_depth: float = 0.60,
) -> dict[str, Any]:
    """Expose DepthFieldResult through the historical Mylar dictionary contract."""
    width, height = size
    output_dir.mkdir(parents=True, exist_ok=True)
    regions_dir = output_dir / "z_regions"
    regions_dir.mkdir(parents=True, exist_ok=True)
    alpha_mask = np.zeros((height, width), dtype=bool)
    label_by_pixel: dict[Pixel, str] = {}
    semantic_regions: list[dict[str, Any]] = []

    for index, part in enumerate(parts):
        label = str(part.get("semantic_label", part.get("name", "unknown")))
        mask = np.zeros((height, width), dtype=bool)
        for x, y in part.get("pixels", set()):
            if 0 <= int(x) < width and 0 <= int(y) < height:
                mask[int(y), int(x)] = True
                alpha_mask[int(y), int(x)] = True
                label_by_pixel[(int(x), int(y))] = label
        semantic_regions.append(
            {
                "region_id": f"{index:02d}_{_safe(label)}",
                "semantic_label": label,
                "mask": mask,
            }
        )

    result = generate_depth_field(
        {"asset_id": output_dir.name, "alpha_mask": alpha_mask},
        semantic_regions,
        DepthConfig(max_total_depth=max_total_depth),
    )
    write_depth_result(result, output_dir, emit_debug=True)
    z_front = result.pinned_depth_field
    z_body = result.global_depth_field
    seam_mask = result.silhouette_mask

    region_reports: list[dict[str, Any]] = []
    for index, (part, region) in enumerate(zip(parts, semantic_regions)):
        region_id = str(region["region_id"])
        label = str(part.get("semantic_label", part.get("name", "unknown")))
        profile = result.region_profiles[region_id]
        field = result.region_depth_fields[region_id]
        mask = np.asarray(region["mask"], dtype=bool)
        region_path = regions_dir / f"{index:02d}_{_safe(label)}.png"
        write_heatmap(field, region_path)
        values = field[mask]
        region_reports.append(
            {
                "index": index,
                "name": part.get("name", label),
                "semantic_label": label,
                "profile": profile.profile,
                "max_depth": profile.max_depth_factor,
                "pixel_count": int(mask.sum()),
                "explicit_profile": profile.explicit,
                "actual_max_depth": float(values.max()) if values.size else 0.0,
                "actual_mean_depth": float(values.mean()) if values.size else 0.0,
                "debug": str(region_path),
            }
        )

    z_front_path = output_dir / "z_front.npy"
    z_body_path = output_dir / "z_body.png"
    z_front_png = output_dir / "z_front.png"
    pin_debug = output_dir / "silhouette_pin_debug.png"
    report_path = output_dir / "mylar_depth_report.json"
    np.save(z_front_path, z_front)
    write_heatmap(z_front, z_front_png)
    write_heatmap(z_body, z_body_path)
    write_mask(seam_mask, pin_debug)

    metadata = result.to_metadata_dict()
    report = {
        "schema": "spritespatial_mylar_depth_v2",
        "pipeline_version": result.pipeline_version,
        "semantic_version": result.semantic_version,
        "depth_version": result.depth_version,
        "profile_pack": result.profile_pack,
        "max_total_depth": max_total_depth,
        "z_min": float(z_front.min()) if z_front.size else 0.0,
        "z_max": float(z_front.max()) if z_front.size else 0.0,
        "silhouette_pin_confirmed": result.diagnostics.silhouette_pin_passed,
        "isolated_spike_count": result.diagnostics.isolated_spike_count,
        "opaque_semantic_pixels": int(alpha_mask.sum()),
        "valid_depth_pixels": int(((z_front > 0.0) | seam_mask)[alpha_mask].sum()),
        "outline_full_depth_slab": _outline_full_depth(label_by_pixel, z_front),
        "validation": result.validation.to_dict(),
        "diagnostics": metadata["diagnostics"],
        "regions": region_reports,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "z_front": z_front,
        "z_body": z_body,
        "alpha_mask": alpha_mask,
        "seam_mask": seam_mask,
        "label_by_pixel": label_by_pixel,
        "report": report,
        "depth_field_result": result,
        "paths": {
            "z_front": z_front_path,
            "z_front_png": z_front_png,
            "z_body": z_body_path,
            "z_regions": regions_dir,
            "silhouette_pin_debug": pin_debug,
            "mylar_depth_report": report_path,
            "depth_field_report": result.artifact_paths["depth_report"],
        },
    }


def _outline_full_depth(label_by_pixel: dict[Pixel, str], depth: np.ndarray) -> bool:
    values = [float(depth[y, x]) for (x, y), label in label_by_pixel.items() if label == "outline"]
    return bool(values and max(values) > 0.08)


def _safe(value: str) -> str:
    return value.replace("/", "_").replace(" ", "_")
