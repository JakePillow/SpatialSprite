from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

Pixel = tuple[int, int]

DIRECTIONAL_PROFILE_TYPES = {
    "HAT_POINTED_BACK",
    "HAIR_LONG_BACK",
    "NOSE_FORWARD",
    "CAPE_BACK",
    "SHIELD_SIDE",
    "SHOULDER_PAD",
    "TAIL",
}

SEMANTIC_COLOURS = {
    "outline": (8, 8, 8, 255),
    "head": (245, 190, 126, 255),
    "face": (255, 214, 156, 255),
    "hair/hat": (118, 78, 190, 255),
    "torso": (48, 178, 220, 255),
    "left_arm": (255, 144, 74, 255),
    "right_arm": (252, 113, 109, 255),
    "left_leg": (62, 111, 226, 255),
    "right_leg": (91, 139, 255, 255),
    "boots/feet": (156, 80, 48, 255),
    "equipment/shield/sword": (220, 208, 92, 255),
    "unknown": (210, 70, 230, 255),
}


def validate_semantic_authority(
    source: Image.Image,
    parts: list[dict[str, Any]],
    override_masks: dict[str, set[Pixel]],
    override_report: dict[str, Any],
    morphology_profile: dict[str, Any] | None,
    profile: dict[str, Any],
    source_coverage: dict[str, Any],
    back_report: dict[str, Any],
    back_sprite_path: Path | None,
    back_mode: str,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    semantic_pixels = _semantic_pixels(parts)
    raw_masks = _raw_semantic_masks(override_masks, source.width)
    rules = dict(morphology_profile.get("rules", {})) if morphology_profile else {}
    required_directional_labels = sorted(
        str(label)
        for label, rule in rules.items()
        if str(getattr(rule, "profile_type", "")) in DIRECTIONAL_PROFILE_TYPES
    )
    hat_requested = any(
        str(label) == "hair/hat" and str(getattr(rule, "profile_type", "")) == "HAT_POINTED_BACK"
        for label, rule in rules.items()
    )

    override_pixels = int(override_report.get("override_pixels_applied", 0))
    override_overlap_count = int(override_report.get("override_overlap_count", 0))
    override_overlap_ratio = float(override_report.get("override_overlap_ratio", 0.0))
    if override_overlap_ratio <= 0.0 and override_pixels > 0:
        override_overlap_ratio = override_overlap_count / max(override_pixels, 1)
    warn_threshold, fail_threshold = _overlap_thresholds(profile)

    warnings: list[str] = []
    failures: list[str] = []
    if override_overlap_ratio > warn_threshold:
        warnings.append(
            f"Semantic override overlap ratio {override_overlap_ratio:.3f} exceeds warning threshold {warn_threshold:.2f}."
        )
    if override_overlap_ratio > fail_threshold:
        failures.append(
            f"Semantic override overlap ratio {override_overlap_ratio:.3f} exceeds failure threshold {fail_threshold:.2f}."
        )

    missing_directional_labels = [
        label for label in required_directional_labels if len(semantic_pixels.get(_canonical_label(label), set())) <= 0
    ]
    if missing_directional_labels:
        warnings.append(
            f"Directional labels are absent from this asset and will be gated: {', '.join(missing_directional_labels)}."
        )

    hat_metrics = _hat_authority_metrics(semantic_pixels, raw_masks, hat_requested)
    if hat_requested and not hat_metrics["hat_authority_passed"]:
        failures.extend(hat_metrics["hat_failures"])

    back_geometry_authority = str(back_report.get("back_geometry_authority", _back_geometry_authority(back_mode, back_sprite_path)))
    correspondence = _front_back_correspondence(
        source,
        parts,
        back_sprite_path,
        back_geometry_authority,
        required_directional_labels,
    )
    if not correspondence["passed"]:
        failures.append("Front/back semantic correspondence failed for authored back geometry.")

    gated_labels: list[str] = []
    gated_reasons: dict[str, str] = {}
    for label in missing_directional_labels:
        gated_labels.append(label)
        gated_reasons[label] = "missing directional semantic label"
    if hat_requested and not hat_metrics["hat_authority_passed"] and "hair/hat" not in gated_labels:
        gated_labels.append("hair/hat")
        gated_reasons["hair/hat"] = "HAT_POINTED_BACK semantic authority failed"
    if override_overlap_ratio > fail_threshold:
        for label in required_directional_labels:
            if label not in gated_labels:
                gated_labels.append(label)
                gated_reasons[label] = "override conflict ratio exceeded failure threshold"

    gated_profile = _gated_morphology_profile(morphology_profile, gated_labels)
    gate_report = {
        "directional_morphology_gated_labels": gated_labels,
        "gated_reasons": gated_reasons,
        "required_directional_labels": required_directional_labels,
        "hat_directional_morphology_allowed": bool(hat_metrics["hat_directional_morphology_allowed"]),
    }

    paths = {
        "semantic_authority_report": output_dir / "semantic_authority_report.json",
        "hair_hat_authority_debug": output_dir / "hair_hat_authority_debug.png",
        "override_priority_resolution": output_dir / "override_priority_resolution.png",
        "front_back_semantic_correspondence": output_dir / "front_back_semantic_correspondence.json",
        "directional_morphology_gate_debug": output_dir / "directional_morphology_gate_debug.json",
    }
    report = {
        "schema": "spritespatial_semantic_authority_v1",
        "semantic_authority_enabled": True,
        "profile": profile.get("name", ""),
        "morphology_profile": morphology_profile.get("name", "") if morphology_profile else "",
        "required_directional_labels": required_directional_labels,
        "missing_directional_labels": missing_directional_labels,
        "override_overlap_count": override_overlap_count,
        "override_pixels_applied": override_pixels,
        "override_overlap_ratio": override_overlap_ratio,
        "override_overlap_warning_threshold": warn_threshold,
        "override_overlap_failure_threshold": fail_threshold,
        "back_geometry_authority": back_geometry_authority,
        "directional_morphology_gated_labels": gated_labels,
        "front_back_semantic_correspondence_passed": bool(correspondence["passed"]),
        "warnings": warnings,
        "failures": failures,
        "passed": not failures,
        **{key: value for key, value in hat_metrics.items() if key != "hat_failures"},
    }

    _write_hair_hat_debug(source.size, semantic_pixels, raw_masks, paths["hair_hat_authority_debug"])
    _write_priority_resolution(source.size, parts, set(_overlap_pixels(override_report)), paths["override_priority_resolution"])
    _write_json(paths["front_back_semantic_correspondence"], correspondence)
    _write_json(paths["directional_morphology_gate_debug"], gate_report)
    _write_json(paths["semantic_authority_report"], report)
    return {
        "report": report,
        "paths": paths,
        "morphology_profile": gated_profile,
        "gate_report": gate_report,
        "correspondence": correspondence,
    }


def _hat_authority_metrics(
    semantic_pixels: dict[str, set[Pixel]],
    raw_masks: dict[str, set[Pixel]],
    hat_requested: bool,
) -> dict[str, Any]:
    hat_pixels = semantic_pixels.get("hair/hat", set())
    raw_hat = raw_masks.get("hair/hat", set())
    head_pixels = semantic_pixels.get("head", set()) | semantic_pixels.get("face", set())
    torso_pixels = semantic_pixels.get("torso", set())
    outline_pixels = semantic_pixels.get("outline", set())
    raw_torso = raw_masks.get("torso", set())
    raw_head = raw_masks.get("head", set()) | raw_masks.get("face", set())
    hat_component_count = _component_count(hat_pixels)
    attachment_pixels = _adjacent_pixels(hat_pixels, head_pixels | _upper_outline(outline_pixels, hat_pixels))
    attachment_score = min(1.0, len(attachment_pixels) / max(math.sqrt(max(len(hat_pixels), 1)), 1.0))
    hat_torso_overlap_count = len(raw_hat & raw_torso)
    hat_head_overlap_count = len(raw_hat & raw_head)
    min_pixels = 4
    torso_overlap_tolerance = max(2, int(len(raw_hat) * 0.25))
    head_overlap_tolerance = max(4, int(len(raw_hat) * 0.60))
    failures = []
    if hat_requested:
        if not raw_hat:
            failures.append("HAT_POINTED_BACK requires an authored hair/hat override mask.")
        if len(hat_pixels) < min_pixels:
            failures.append("Hair/hat semantic coverage is below the minimum directional threshold.")
        if hat_component_count > 2:
            failures.append("Hair/hat semantic authority is too fragmented for directional morphology.")
        if attachment_score <= 0.0:
            failures.append("Hair/hat semantic authority does not attach to head or upper outline.")
        if hat_torso_overlap_count > torso_overlap_tolerance:
            failures.append("Hair/hat override overlaps torso beyond tolerance.")
        if hat_head_overlap_count > head_overlap_tolerance:
            failures.append("Hair/hat override overlaps head/face beyond tolerance.")
    passed = not failures
    return {
        "hat_authority_requested": hat_requested,
        "hat_authority_passed": passed,
        "hat_pixel_count": len(hat_pixels),
        "hat_override_pixel_count": len(raw_hat),
        "hat_component_count": hat_component_count,
        "hat_head_attachment_score": attachment_score,
        "hat_torso_overlap_count": hat_torso_overlap_count,
        "hat_head_overlap_count": hat_head_overlap_count,
        "hat_directional_morphology_allowed": bool(hat_requested and passed),
        "hat_failures": failures,
    }


def _front_back_correspondence(
    source: Image.Image,
    parts: list[dict[str, Any]],
    back_sprite_path: Path | None,
    back_geometry_authority: str,
    required_directional_labels: list[str],
) -> dict[str, Any]:
    if not back_sprite_path or not back_sprite_path.exists():
        return {
            "schema": "spritespatial_front_back_semantic_correspondence_v1",
            "back_sprite_path": str(back_sprite_path) if back_sprite_path else "",
            "back_sprite_present": False,
            "back_geometry_authority": back_geometry_authority,
            "label_overlap": {},
            "front_labels_missing_in_back_alpha": [],
            "directional_labels_missing_in_back_alpha": required_directional_labels,
            "method": "canvas_alpha_overlap_heuristic",
            "passed": back_geometry_authority != "authored_back",
        }
    back = Image.open(back_sprite_path).convert("RGBA")
    back_alpha = back.getchannel("A")
    semantic_pixels = _semantic_pixels(parts)
    label_overlap: dict[str, Any] = {}
    missing = []
    directional_missing = []
    for label, pixels in sorted(semantic_pixels.items()):
        if not pixels:
            continue
        hits = 0
        for x, y in pixels:
            if x < back.width and y < back.height and back_alpha.getpixel((x, y)) > 16:
                hits += 1
        ratio = hits / max(len(pixels), 1)
        label_overlap[label] = {
            "front_pixel_count": len(pixels),
            "back_alpha_overlap": hits,
            "overlap_ratio": ratio,
        }
        if ratio <= 0.02:
            missing.append(label)
            if label in required_directional_labels:
                directional_missing.append(label)
    critical_missing = [label for label in missing if label in {"head", "torso", "left_leg", "right_leg"}]
    return {
        "schema": "spritespatial_front_back_semantic_correspondence_v1",
        "back_sprite_path": str(back_sprite_path),
        "back_sprite_present": True,
        "back_geometry_authority": back_geometry_authority,
        "label_overlap": label_overlap,
        "front_labels_missing_in_back_alpha": missing,
        "directional_labels_missing_in_back_alpha": directional_missing,
        "method": "canvas_alpha_overlap_heuristic",
        "passed": back_geometry_authority != "authored_back" or not critical_missing,
    }


def _gated_morphology_profile(
    morphology_profile: dict[str, Any] | None,
    gated_labels: list[str],
) -> dict[str, Any] | None:
    if morphology_profile is None:
        return None
    if not gated_labels:
        return morphology_profile
    result = dict(morphology_profile)
    rules = dict(result.get("rules", {}))
    for label in gated_labels:
        rules.pop(label, None)
    result["rules"] = rules
    result["gated_labels"] = gated_labels
    return result


def _semantic_pixels(parts: list[dict[str, Any]]) -> dict[str, set[Pixel]]:
    result: dict[str, set[Pixel]] = {}
    for part in parts:
        label = _canonical_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        result.setdefault(label, set()).update({(int(x), int(y)) for x, y in part.get("pixels", set())})
    return result


def _raw_semantic_masks(override_masks: dict[str, set[Pixel]], width: int) -> dict[str, set[Pixel]]:
    result: dict[str, set[Pixel]] = {}
    for name, pixels in override_masks.items():
        for pixel in pixels:
            label = _canonical_label(_semantic_for_part(_normalise_part_name(name, pixel, width)))
            result.setdefault(label, set()).add(pixel)
    return result


def _canonical_label(label: str) -> str:
    return {
        "hair": "hair/hat",
        "hat_hair": "hair/hat",
        "cap": "hair/hat",
        "left_foot": "boots/feet",
        "right_foot": "boots/feet",
        "boots_feet": "boots/feet",
        "equipment": "equipment/shield/sword",
    }.get(label, label)


def _normalise_part_name(name: str, pixel: Pixel, width: int) -> str:
    if name in {"hair/hat", "hat_hair"}:
        return "hair"
    if name in {"boots_feet", "boots/feet"}:
        return "left_foot" if pixel[0] < width * 0.5 else "right_foot"
    if name == "equipment/shield/sword":
        return "equipment"
    return name


def _semantic_for_part(name: str) -> str:
    return {
        "hair": "hair/hat",
        "left_foot": "boots/feet",
        "right_foot": "boots/feet",
        "equipment": "equipment/shield/sword",
    }.get(name, name)


def _component_count(pixels: set[Pixel]) -> int:
    remaining = set(pixels)
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in _neighbours(x, y):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    queue.append((nx, ny))
    return components


def _adjacent_pixels(source: set[Pixel], target: set[Pixel]) -> set[Pixel]:
    if not source or not target:
        return set()
    result = set()
    for x, y in source:
        if any((nx, ny) in target for nx, ny in _neighbours(x, y)):
            result.add((x, y))
    return result


def _upper_outline(outline: set[Pixel], hat: set[Pixel]) -> set[Pixel]:
    if not outline or not hat:
        return set()
    max_hat_y = max(y for _x, y in hat)
    return {(x, y) for x, y in outline if y <= max_hat_y + 2}


def _neighbours(x: int, y: int) -> tuple[Pixel, ...]:
    return (
        (x - 1, y - 1),
        (x, y - 1),
        (x + 1, y - 1),
        (x - 1, y),
        (x + 1, y),
        (x - 1, y + 1),
        (x, y + 1),
        (x + 1, y + 1),
    )


def _overlap_thresholds(profile: dict[str, Any]) -> tuple[float, float]:
    name = str(profile.get("name", "")).lower()
    if name == "quality_64":
        return 0.10, 0.10
    return 0.20, 0.60


def _back_geometry_authority(back_mode: str, back_sprite_path: Path | None) -> str:
    if back_mode == "front_back_sprite":
        return "authored_back" if back_sprite_path and back_sprite_path.exists() else "missing"
    if back_mode in {"semantic_rules", "symmetric"}:
        return back_mode
    return "missing"


def _overlap_pixels(override_report: dict[str, Any]) -> list[Pixel]:
    result = []
    for item in override_report.get("overlap_pixels", []):
        if isinstance(item, list) and len(item) == 2:
            result.append((int(item[0]), int(item[1])))
    return result


def _write_hair_hat_debug(
    size: tuple[int, int],
    semantic_pixels: dict[str, set[Pixel]],
    raw_masks: dict[str, set[Pixel]],
    path: Path,
) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for label in ("torso", "head", "face", "outline", "hair/hat"):
        for x, y in semantic_pixels.get(label, set()):
            pixels[x, y] = SEMANTIC_COLOURS.get(label, SEMANTIC_COLOURS["unknown"])
    draw = ImageDraw.Draw(image)
    for x, y in raw_masks.get("hair/hat", set()) & raw_masks.get("torso", set()):
        draw.point((x, y), fill=(255, 40, 40, 255))
    for x, y in raw_masks.get("hair/hat", set()) & (raw_masks.get("head", set()) | raw_masks.get("face", set())):
        draw.point((x, y), fill=(255, 210, 40, 255))
    image.save(path, format="PNG")


def _write_priority_resolution(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    overlap_pixels: set[Pixel],
    path: Path,
) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for part in parts:
        label = _canonical_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        colour = SEMANTIC_COLOURS.get(label, SEMANTIC_COLOURS["unknown"])
        for x, y in part.get("pixels", set()):
            pixels[int(x), int(y)] = colour
    draw = ImageDraw.Draw(image)
    for x, y in overlap_pixels:
        draw.point((x, y), fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
