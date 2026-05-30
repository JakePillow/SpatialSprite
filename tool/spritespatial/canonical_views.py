from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonical_view_records(source_coverage: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    source_coverage = source_coverage or {}
    side_authority = side_profile_authority(source_coverage)
    back_authority = back_view_authority(source_coverage)
    return [
        {"yaw": 0, "view": "front", "authority": "source_sprite", "target_type": "front_alpha"},
        {"yaw": 45, "view": "oblique", "authority": "interpolated_prior", "target_type": "front_to_side_transition"},
        {"yaw": 90, "view": "side", "authority": side_authority, "target_type": "side_profile"},
        {"yaw": 135, "view": "side_135", "authority": "interpolated_prior", "target_type": "side_to_back_transition"},
        {
            "yaw": 180,
            "view": "back",
            "authority": back_authority,
            "target_type": "back_alpha_or_inferred",
        },
    ]


def side_profile_authority(source_coverage: dict[str, Any] | None = None) -> str:
    source_coverage = source_coverage or {}
    left = str(source_coverage.get("left", "missing"))
    right = str(source_coverage.get("right", "missing"))
    if left in {"authored", "authored_left", "authored_right", "authored_side"} or right in {
        "authored",
        "authored_left",
        "authored_right",
        "authored_side",
    }:
        return "authored"
    if left == "missing" and right == "missing":
        return "missing"
    return "primitive_prior"


def back_view_authority(source_coverage: dict[str, Any] | None = None) -> str:
    source_coverage = source_coverage or {}
    back = str(source_coverage.get("back", "missing"))
    if back == "authored":
        return "authored"
    if back == "missing":
        return "missing"
    return "inferred"


def write_canonical_view_records(records: list[dict[str, Any]], path: Path) -> Path:
    path.write_text(json.dumps({"canonical_views": records}, indent=2) + "\n", encoding="utf-8")
    return path
