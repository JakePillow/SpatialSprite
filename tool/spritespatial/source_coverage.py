from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.asset_schema import AssetSchema, SOURCE_DIRECTIONS


def analyze_source_coverage(
    asset: AssetSchema | None,
    profile: dict[str, Any] | None = None,
    back_mode: str = "semantic_rules",
) -> dict[str, Any]:
    profile = profile or {}
    if asset is None:
        return {
            "front": "missing",
            "back": "missing",
            "left": "missing",
            "right": "missing",
            "back_reference_recommended": True,
            "side_reference_recommended": True,
            "fidelity_limit": "front_missing",
            "back_geometry_authority": "missing",
            "warnings": ["No spriteasset schema was provided; source authority cannot be established."],
            "details": {},
            "fail_conditions": _fail_conditions(profile, "missing", "missing", "missing"),
        }

    details = {direction: _sprite_signature(asset.sprite_path(direction)) for direction in SOURCE_DIRECTIONS}
    metadata = getattr(asset, "source_coverage_metadata", {}) or {}
    front_status = "authored" if details["front"]["exists"] else "missing"
    back_status = str(metadata.get("back", _classify_back(details, back_mode)))
    left_status = str(metadata.get("left", _classify_side(details, "left", back_mode)))
    right_status = str(metadata.get("right", _classify_side(details, "right", back_mode)))
    back_recommended = back_status != "authored"
    side_recommended = not (_is_authored_side(left_status) or _is_authored_side(right_status))
    fidelity = _fidelity_limit(front_status, back_status, left_status, right_status)
    back_geometry_authority = _back_geometry_authority(back_mode, details["back"].get("exists", False))
    warnings = []
    if back_recommended and back_mode == "semantic_rules":
        warnings.append("Back view is inferred from semantic rules. This is structurally valid but not artistically authoritative.")
    if back_status == "authored" and back_mode == "semantic_rules":
        warnings.append("Authored back sprite is available but semantic_rules uses it only as optional comparison, not geometry authority.")
    if side_recommended:
        warnings.append("Side profile is generated from primitive/SDF priors. Provide side sprite for higher fidelity.")
    fail_conditions = _fail_conditions(profile, back_status, left_status, right_status)
    return {
        "front": front_status,
        "back": back_status,
        "left": left_status,
        "right": right_status,
        "side_geometry_authority": str(metadata.get("side_geometry_authority", _side_geometry_authority(left_status, right_status))),
        "back_reference_recommended": back_recommended,
        "side_reference_recommended": side_recommended,
        "fidelity_limit": fidelity,
        "back_geometry_authority": back_geometry_authority,
        "warnings": warnings,
        "details": details,
        "fail_conditions": fail_conditions,
        "passed": not any(fail_conditions.values()),
    }


def emit_view_candidates(
    asset: AssetSchema,
    output_dir: Path,
    raw_search_root: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet = _find_source_sheet(asset, raw_search_root)
    report: dict[str, Any] = {
        "schema": "spritespatial_view_candidate_report_v1",
        "asset_name": asset.asset_name,
        "source_sheet": str(sheet) if sheet else "",
        "candidate_count": 0,
        "note": "Candidate extraction is heuristic; user selection is still authoritative.",
    }
    if not sheet:
        _blank_sheet(output_dir / "front_candidates.png", "No source sheet found")
        _blank_sheet(output_dir / "back_candidates.png", "No source sheet found")
        _blank_sheet(output_dir / "side_candidates.png", "No source sheet found")
        (output_dir / "candidate_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return {"report": report, "paths": _candidate_paths(output_dir)}

    image = Image.open(sheet).convert("RGBA")
    candidates = _extract_candidate_crops(image)
    report["candidate_count"] = len(candidates)
    for name in ("front", "back", "side"):
        _write_candidate_sheet(candidates, output_dir / f"{name}_candidates.png", name)
    (output_dir / "candidate_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"report": report, "paths": _candidate_paths(output_dir)}


def _sprite_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    alpha_bytes = alpha.tobytes()
    return {
        "exists": True,
        "path": str(path),
        "sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "alpha_sha256": hashlib.sha256(alpha_bytes).hexdigest(),
        "mirror_sha256": hashlib.sha256(image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()).hexdigest(),
        "mirror_alpha_sha256": hashlib.sha256(alpha.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()).hexdigest(),
        "alpha_coverage": sum(1 for value in alpha_bytes if value > 16) / max(image.width * image.height, 1),
        "size": list(image.size),
    }


def _classify_back(details: dict[str, dict[str, Any]], back_mode: str) -> str:
    front = details["front"]
    back = details["back"]
    if not back.get("exists"):
        return "inferred" if back_mode in {"semantic_rules", "symmetric"} and front.get("exists") else "missing"
    if not front.get("exists"):
        return "authored"
    if back.get("sha256") == front.get("sha256") or back.get("alpha_sha256") == front.get("alpha_sha256"):
        return "inferred" if back_mode in {"semantic_rules", "symmetric"} else "placeholder"
    if back.get("sha256") == front.get("mirror_sha256"):
        return "placeholder"
    return "authored"


def _classify_side(details: dict[str, dict[str, Any]], direction: str, back_mode: str) -> str:
    front = details["front"]
    back = details["back"]
    side = details[direction]
    opposite = details["right" if direction == "left" else "left"]
    if not side.get("exists"):
        return "inferred" if back_mode in {"semantic_rules", "symmetric"} and front.get("exists") else "missing"
    if not front.get("exists"):
        return f"authored_{direction}"
    if side.get("sha256") == front.get("sha256") or side.get("alpha_sha256") == front.get("alpha_sha256"):
        return "inferred"
    if side.get("sha256") == front.get("mirror_sha256"):
        return "mirrored_placeholder"
    if side.get("alpha_sha256") == front.get("mirror_alpha_sha256"):
        return "mirrored_placeholder"
    if back.get("exists"):
        if side.get("sha256") == back.get("sha256") or side.get("alpha_sha256") == back.get("alpha_sha256"):
            return "mirrored_placeholder"
        if side.get("sha256") == back.get("mirror_sha256") or side.get("alpha_sha256") == back.get("mirror_alpha_sha256"):
            return "mirrored_placeholder"
    if side.get("sha256") == opposite.get("mirror_sha256"):
        return "mirrored_placeholder"
    if side.get("alpha_sha256") == opposite.get("mirror_alpha_sha256"):
        return "mirrored_placeholder"
    if _alpha_similarity(side, front) > 0.96:
        return "inferred"
    if back.get("exists") and _alpha_similarity(side, back) > 0.96:
        return "mirrored_placeholder"
    return f"authored_{direction}"


def _fidelity_limit(front: str, back: str, left: str, right: str) -> str:
    if front != "authored":
        return "no_authoritative_front"
    if back != "authored" and not _is_authored_side(left) and not _is_authored_side(right):
        return "front_only_inferred_back"
    if back != "authored":
        return "back_inferred"
    if not (_is_authored_side(left) or _is_authored_side(right)):
        return "side_inferred"
    return "multi_view_authoritative"


def _fail_conditions(profile: dict[str, Any], back: str, left: str, right: str) -> dict[str, bool]:
    require_authored_back = bool(profile.get("require_authored_back_sprite", False))
    require_authored_sides = bool(profile.get("require_authored_side_sprites", False))
    return {
        "quality_requires_authored_back": require_authored_back and back != "authored",
        "quality_requires_authored_sides": require_authored_sides and not (_is_authored_side(left) or _is_authored_side(right)),
    }


def _back_geometry_authority(back_mode: str, back_exists: bool) -> str:
    if back_mode == "front_back_sprite":
        return "authored_back" if back_exists else "missing"
    if back_mode in {"semantic_rules", "symmetric"}:
        return back_mode
    return "missing"


def _is_authored_side(status: str) -> bool:
    return status in {"authored", "authored_left", "authored_right", "authored_side", "authored_side_fixture"}


def _side_geometry_authority(left: str, right: str) -> str:
    if _is_authored_side(left) or _is_authored_side(right):
        if "authored_side_fixture" in {left, right}:
            return "authored_side_fixture"
        return "authored_side"
    statuses = {left, right}
    if "mirrored_placeholder" in statuses:
        return "placeholder"
    if "inferred" in statuses:
        return "inferred"
    return "missing"


def _alpha_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    path_a = Path(str(a.get("path", "")))
    path_b = Path(str(b.get("path", "")))
    if not path_a.exists() or not path_b.exists():
        return 0.0
    image_a = Image.open(path_a).convert("RGBA")
    image_b = Image.open(path_b).convert("RGBA")
    if image_a.size != image_b.size:
        image_b = image_b.resize(image_a.size, Image.Resampling.NEAREST)
    alpha_a = np.asarray(image_a.getchannel("A"), dtype=np.uint8) > 16
    alpha_b = np.asarray(image_b.getchannel("A"), dtype=np.uint8) > 16
    union = int(np.count_nonzero(alpha_a | alpha_b))
    if union == 0:
        return 1.0
    return float(np.count_nonzero(alpha_a & alpha_b)) / float(union)


def _find_source_sheet(asset: AssetSchema, raw_search_root: Path) -> Path | None:
    if not raw_search_root.exists():
        return None
    tokens = [asset.asset_name.lower()]
    if asset.asset_name.lower() == "mario":
        tokens.append("mario")
    candidates = []
    for path in raw_search_root.glob("*.png"):
        name = path.name.lower()
        if any(token in name for token in tokens):
            candidates.append(path)
    return candidates[0] if candidates else None


def _extract_candidate_crops(image: Image.Image, limit: int = 24) -> list[Image.Image]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    mask = np.zeros((rgba.height, rgba.width), dtype=bool)
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 16 and not (red <= 12 and green >= 70 and blue >= 70 and abs(green - blue) <= 45):
                mask[y, x] = True
    components = _components(mask)
    crops = []
    for component in sorted(components, key=len, reverse=True):
        if len(component) < 20:
            continue
        xs = [x for x, _y in component]
        ys = [y for _x, y in component]
        x0, x1 = max(0, min(xs) - 3), min(rgba.width, max(xs) + 4)
        y0, y1 = max(0, min(ys) - 3), min(rgba.height, max(ys) + 4)
        crop = rgba.crop((x0, y0, x1, y1))
        if 6 <= crop.width <= 80 and 8 <= crop.height <= 90:
            crops.append(crop)
        if len(crops) >= limit:
            break
    return crops


def _components(mask: np.ndarray) -> list[set[tuple[int, int]]]:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    component.add((nx, ny))
                    stack.append((nx, ny))
        components.append(component)
    return components


def _write_candidate_sheet(candidates: list[Image.Image], path: Path, label: str) -> None:
    cell = 72
    cols = 8
    rows = max(1, (len(candidates) + cols - 1) // cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 120, 120, 255))
    draw = ImageDraw.Draw(sheet)
    for index, crop in enumerate(candidates):
        x = (index % cols) * cell
        y = (index // cols) * cell
        draw.rectangle((x, y, x + cell - 1, y + cell - 1), outline=(0, 70, 70, 255))
        sheet.alpha_composite(crop, (x + (cell - crop.width) // 2, y + (cell - crop.height) // 2))
        draw.text((x + 3, y + 3), f"{label}:{index}", fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _blank_sheet(path: Path, text: str) -> None:
    image = Image.new("RGBA", (320, 96), (0, 120, 120, 255))
    ImageDraw.Draw(image).text((10, 36), text, fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _candidate_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "front_candidates": output_dir / "front_candidates.png",
        "back_candidates": output_dir / "back_candidates.png",
        "side_candidates": output_dir / "side_candidates.png",
        "candidate_report": output_dir / "candidate_report.json",
    }
