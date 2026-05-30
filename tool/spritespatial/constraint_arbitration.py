from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def arbitrate_constraints(
    constraints: dict[str, Any],
    embodiment_params: dict[str, Any] | None,
    output_dir: Path,
    emit_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    front = _mask(constraints.get("front_alpha"))
    if front is None:
        return {"constraints": constraints, "report": _disabled_report(), "paths": {}}
    back = _mask(constraints.get("back_alpha"), front.shape)
    side = _mask(constraints.get("side_alpha"), front.shape)
    support = front | (back if back is not None else front)
    front_back_conflict = (front ^ back) if back is not None else np.zeros_like(front, dtype=bool)
    side_row_conflict = np.zeros_like(front, dtype=bool)
    rejected_side_rows: list[int] = []
    if side is not None and bool(constraints.get("side_authority_used", False)):
        side_rows = side.any(axis=1)
        support_rows = support.any(axis=1)
        risky_rows = side_rows & ~support_rows
        rejected_side_rows = [int(index) for index in np.flatnonzero(risky_rows)]
        side_row_conflict = np.repeat((side_rows ^ support_rows)[:, None], front.shape[1], axis=1) & (side | support)
    conflict_zones = front_back_conflict | side_row_conflict
    topology_risk = _topology_risk_zones(support, conflict_zones)
    for row in rejected_side_rows:
        if 0 <= row < topology_risk.shape[0]:
            topology_risk[row, :] = True
    weights = _authority_weights(embodiment_params)
    front_weight = weights["front_authority_weight"]
    back_weight = weights["back_authority_weight"]
    side_weight = weights["side_authority_weight"]
    blend_margin = 0.20
    weighted_blend = np.zeros_like(front, dtype=bool)
    if back is not None:
        weighted_blend |= front_back_conflict & (abs(front_weight - back_weight) <= blend_margin)
    if side is not None and bool(constraints.get("side_authority_used", False)):
        weighted_blend |= side_row_conflict & (side_weight > 0.0) & ~topology_risk
    rejected_count = int(len(rejected_side_rows))
    report = {
        "schema": "spritespatial_constraint_arbitration_v1",
        "constraint_arbitration_enabled": True,
        "source_shape": [int(front.shape[0]), int(front.shape[1])],
        "policy": [
            "preserve topology first",
            "preserve authored silhouettes second",
            "preserve inferred priors last",
            "blend only where constraints disagree and topology risk is low",
        ],
        "authority_weights": weights,
        "front_pixel_count": int(np.count_nonzero(front)),
        "back_pixel_count": int(np.count_nonzero(back)) if back is not None else 0,
        "side_pixel_count": int(np.count_nonzero(side)) if side is not None else 0,
        "conflict_zone_count": int(np.count_nonzero(conflict_zones)),
        "front_back_conflict_count": int(np.count_nonzero(front_back_conflict)),
        "side_row_conflict_count": int(np.count_nonzero(side_row_conflict)),
        "topology_risk_zone_count": int(np.count_nonzero(topology_risk)),
        "weighted_blend_region_count": int(np.count_nonzero(weighted_blend)),
        "rejected_constraint_count": rejected_count,
        "rejected_side_rows": rejected_side_rows,
        "authority_winner_counts": _authority_winner_counts(front, back, side, topology_risk, weighted_blend),
        "passed": True,
    }
    paths = {
        "constraint_arbitration_report": output_dir / "constraint_arbitration_report.json",
        "constraint_conflict_map": output_dir / "constraint_conflict_map.png",
        "authority_zone_map": output_dir / "authority_zone_map.png",
        "topology_risk_map": output_dir / "topology_risk_map.png",
        "weighted_blend_regions": output_dir / "weighted_blend_regions.png",
        "rejected_constraints": output_dir / "rejected_constraints.json",
    }
    paths["constraint_arbitration_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["rejected_constraints"].write_text(
        json.dumps({"rejected_side_rows": rejected_side_rows, "rejected_constraint_count": rejected_count}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_bool_map(conflict_zones, paths["constraint_conflict_map"], (255, 90, 60, 255))
    _write_bool_map(topology_risk, paths["topology_risk_map"], (255, 30, 30, 255))
    _write_bool_map(weighted_blend, paths["weighted_blend_regions"], (250, 210, 60, 255))
    _write_authority_map(front, back, side, topology_risk, weighted_blend, paths["authority_zone_map"])
    if not emit_debug:
        pass
    next_constraints = dict(constraints)
    report_fields = {key: value for key, value in report.items() if key != "schema"}
    next_constraints["report"] = {
        **dict(constraints.get("report", {})),
        **report_fields,
        "constraint_arbitration_report": report,
    }
    next_constraints["constraint_arbitration_enabled"] = True
    next_constraints["constraint_arbitration"] = {
        "report": report,
        "rejected_side_rows": rejected_side_rows,
        "source_shape": report["source_shape"],
        "authority_weights": weights,
    }
    return {"constraints": next_constraints, "report": report, "paths": paths}


def _disabled_report() -> dict[str, Any]:
    return {
        "schema": "spritespatial_constraint_arbitration_v1",
        "constraint_arbitration_enabled": False,
        "conflict_zone_count": 0,
        "topology_risk_zone_count": 0,
        "weighted_blend_region_count": 0,
        "rejected_constraint_count": 0,
        "passed": True,
    }


def _mask(value: Any, shape: tuple[int, int] | None = None) -> np.ndarray | None:
    if value is None:
        return None
    result = np.asarray(value, dtype=bool)
    if shape is not None and result.shape != shape:
        image = Image.fromarray(result.astype(np.uint8) * 255, mode="L")
        image = image.resize((int(shape[1]), int(shape[0])), Image.Resampling.NEAREST)
        result = np.asarray(image, dtype=np.uint8) > 0
    return result


def _authority_weights(embodiment_params: dict[str, Any] | None) -> dict[str, float]:
    fields = (
        "silhouette_weight",
        "front_authority_weight",
        "back_authority_weight",
        "side_authority_weight",
        "topology_preservation_weight",
    )
    totals = {field: 0.0 for field in fields}
    count = 0
    parts = (embodiment_params or {}).get("parts", {})
    if isinstance(parts, dict):
        for payload in parts.values():
            if not isinstance(payload, dict) or not bool(payload.get("enabled", True)):
                continue
            count += 1
            for field in fields:
                totals[field] += float(payload.get(field, 1.0))
    if count <= 0:
        return {field: 1.0 for field in fields}
    return {field: _clamp(totals[field] / float(count), 0.0, 3.0) for field in fields}


def _topology_risk_zones(support: np.ndarray, conflict: np.ndarray) -> np.ndarray:
    risk = np.zeros_like(support, dtype=bool)
    height, width = support.shape
    for y, x in np.argwhere(conflict):
        neighbours = 0
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = int(y) + dy, int(x) + dx
            if 0 <= ny < height and 0 <= nx < width and bool(support[ny, nx]):
                neighbours += 1
        risk[int(y), int(x)] = neighbours <= 1
    return risk


def _authority_winner_counts(
    front: np.ndarray,
    back: np.ndarray | None,
    side: np.ndarray | None,
    topology_risk: np.ndarray,
    weighted_blend: np.ndarray,
) -> dict[str, int]:
    back_only = (back & ~front) if back is not None else np.zeros_like(front, dtype=bool)
    front_only = front & ~(back if back is not None else np.zeros_like(front, dtype=bool))
    side_only = (side & ~front & ~(back if back is not None else np.zeros_like(front, dtype=bool))) if side is not None else np.zeros_like(front, dtype=bool)
    return {
        "topology": int(np.count_nonzero(topology_risk)),
        "front": int(np.count_nonzero(front_only & ~topology_risk)),
        "back": int(np.count_nonzero(back_only & ~topology_risk)),
        "side": int(np.count_nonzero(side_only & ~topology_risk)),
        "weighted_blend": int(np.count_nonzero(weighted_blend)),
    }


def _write_bool_map(mask: np.ndarray, path: Path, color: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", (int(mask.shape[1]), int(mask.shape[0])), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = color
    image.save(path, format="PNG")


def _write_authority_map(
    front: np.ndarray,
    back: np.ndarray | None,
    side: np.ndarray | None,
    topology_risk: np.ndarray,
    weighted_blend: np.ndarray,
    path: Path,
) -> None:
    image = Image.new("RGBA", (int(front.shape[1]), int(front.shape[0])), (0, 0, 0, 0))
    pixels = image.load()
    back_mask = back if back is not None else np.zeros_like(front, dtype=bool)
    side_mask = side if side is not None else np.zeros_like(front, dtype=bool)
    for y, x in np.argwhere(front | back_mask | side_mask | topology_risk | weighted_blend):
        xi, yi = int(x), int(y)
        color = (70, 200, 90, 210) if front[yi, xi] else (0, 0, 0, 0)
        if back_mask[yi, xi] and not front[yi, xi]:
            color = (80, 120, 255, 210)
        if side_mask[yi, xi] and not front[yi, xi] and not back_mask[yi, xi]:
            color = (190, 80, 255, 210)
        if weighted_blend[yi, xi]:
            color = (250, 210, 60, 240)
        if topology_risk[yi, xi]:
            color = (255, 30, 30, 255)
        pixels[xi, yi] = color
    image.save(path, format="PNG")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
