from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image


LABEL_ALIASES = {
    "hat_hair": "hair/hat",
    "hair": "hair/hat",
    "cap": "hair/hat",
    "boots_feet": "boots/feet",
    "feet": "boots/feet",
    "boots": "boots/feet",
    "equipment": "equipment/shield/sword",
    "shield": "equipment/shield/sword",
    "sword": "equipment/shield/sword",
}

DEFAULT_PART = {
    "enabled": False,
    "z_center_offset": 0.0,
    "thickness_scale": 1.0,
    "front_bias": 0.0,
    "back_bias": 0.0,
    "side_width_scale": 1.0,
    "silhouette_weight": 1.0,
    "front_authority_weight": 1.0,
    "back_authority_weight": 1.0,
    "side_authority_weight": 1.0,
    "topology_preservation_weight": 1.0,
    "taper_strength": 0.0,
    "preserve_silhouette": True,
    "lock_part": False,
    "notes": "",
}


def load_preset_profile(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    presets = data.get("presets", [])
    if isinstance(presets, dict):
        presets = list(presets.values())
    normalised = []
    for preset in presets:
        if not isinstance(preset, dict) or not preset.get("preset_id"):
            continue
        item = dict(preset)
        item["target_parts"] = [_canonical_label(part) for part in item.get("target_parts", [])]
        item["parameter_changes"] = {
            _canonical_label(label): payload
            for label, payload in item.get("parameter_changes", {}).items()
            if isinstance(payload, dict)
        }
        normalised.append(item)
    result = dict(data)
    result["path"] = str(resolved)
    result["presets"] = normalised
    result["preset_by_id"] = {str(item["preset_id"]): item for item in normalised}
    return result


def list_presets(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "preset_id": preset.get("preset_id", ""),
            "display_name": preset.get("display_name", preset.get("preset_id", "")),
            "description": preset.get("description", ""),
            "target_parts": preset.get("target_parts", []),
            "expected_effect": preset.get("expected_effect", ""),
            "risk_notes": preset.get("risk_notes", ""),
        }
        for preset in profile.get("presets", [])
        if isinstance(preset, dict)
    ]


def apply_preset(
    base_params: dict[str, Any],
    preset_id: str,
    intensity: float,
    preset_profile: dict[str, Any] | None = None,
    valid_parts: set[str] | None = None,
) -> dict[str, Any]:
    if preset_profile is None:
        preset_profile = base_params.get("_preset_profile", {})
    preset = preset_profile.get("preset_by_id", {}).get(preset_id)
    if not isinstance(preset, dict):
        raise ValueError(f"Preset not found: {preset_id}")
    intensity = _clamp(float(intensity), 0.0, 1.0)
    params = _normalise_params(base_params)
    report = {
        "schema": "spritespatial_preset_application_report_v1",
        "preset_id": preset_id,
        "display_name": preset.get("display_name", preset_id),
        "intensity": intensity,
        "target_parts": list(preset.get("target_parts", [])),
        "applied_parts": [],
        "skipped_parts": [],
        "parameter_changes": {},
        "warnings": [],
        "valid_for_asset": True,
        "expected_effect": preset.get("expected_effect", ""),
        "risk_notes": preset.get("risk_notes", ""),
    }
    validation = validate_preset_against_asset(preset, valid_parts or set(params.get("parts", {}).keys()))
    allowed_parts = set(validation.get("applied_parts", []))
    report["skipped_parts"].extend(validation.get("skipped_parts", []))
    report["warnings"].extend(validation.get("warnings", []))
    for part_id in preset.get("target_parts", []):
        part_id = _canonical_label(part_id)
        changes = preset.get("parameter_changes", {}).get(part_id, {})
        if not isinstance(changes, dict):
            continue
        if part_id not in allowed_parts:
            continue
        base_part = dict(params["parts"].get(part_id, _default_part(part_id)))
        next_part = dict(base_part)
        change_report: dict[str, list[Any]] = {}
        for field, target_value in changes.items():
            old_value = base_part.get(field, DEFAULT_PART.get(field))
            new_value = _scaled_value(old_value, target_value, intensity)
            new_value = _clamp_to_safe_range(field, new_value, preset.get("safe_ranges", {}))
            if old_value != new_value:
                next_part[field] = new_value
                change_report[field] = [old_value, new_value]
        if changes and "enabled" not in changes and intensity > 0.0:
            old_value = bool(base_part.get("enabled", False))
            next_part["enabled"] = True
            if old_value is not True:
                change_report["enabled"] = [old_value, True]
        next_part["part_id"] = part_id
        if preset.get("display_name"):
            next_part["notes"] = str(preset.get("description", preset.get("display_name", "")))
        params["parts"][part_id] = next_part
        if change_report:
            report["applied_parts"].append(part_id)
            report["parameter_changes"][part_id] = change_report
    report["applied_parts"] = sorted(set(report["applied_parts"]))
    report["valid_for_asset"] = bool(report["applied_parts"]) and not any(
        str(item.get("reason", "")) == "part_not_present" for item in report["skipped_parts"] if isinstance(item, dict)
    )
    if report["skipped_parts"] and report["applied_parts"]:
        report["valid_for_asset"] = True
    params["name"] = f"{params.get('name', 'embodiment_params')}_{preset_id}_{int(round(intensity * 100)):03d}"
    params["preset_application"] = report
    return {"params": params, "report": report}


def validate_preset_against_asset(preset: dict[str, Any], semantic_part_graph: Any) -> dict[str, Any]:
    available = _available_parts(semantic_part_graph)
    target_parts = [_canonical_label(part) for part in preset.get("target_parts", [])]
    applied = []
    skipped = []
    warnings = []
    for part in target_parts:
        if part in available:
            applied.append(part)
        else:
            skipped.append({"part_id": part, "reason": "part_not_present"})
            warnings.append(f"Preset target '{part}' is not present for this asset.")
    return {
        "preset_id": preset.get("preset_id", ""),
        "target_parts": target_parts,
        "applied_parts": sorted(set(applied)),
        "skipped_parts": skipped,
        "warnings": warnings,
        "valid_for_asset": bool(applied) and not skipped,
        "available_parts": sorted(available),
    }


def write_preset_params(out_path: str | Path, params: dict[str, Any], report: dict[str, Any] | None = None) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(params)
    payload.pop("_preset_profile", None)
    if report is not None:
        payload["preset_application"] = report
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def semantic_part_graph_from_overrides(semantic_overrides: str | Path | None) -> dict[str, Any]:
    root = Path(semantic_overrides) if semantic_overrides else Path()
    parts = []
    if root and root.exists():
        for path in sorted(root.glob("*.png")):
            label = _canonical_label(path.stem)
            pixel_count = _alpha_count(path)
            if pixel_count > 0:
                parts.append({"part_id": label, "semantic_label": label, "pixel_count": pixel_count})
    return {"schema": "spritespatial_lightweight_semantic_part_graph_v1", "parts": parts}


def _normalise_params(params: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(params)
    result.setdefault("schema", "spritespatial_embodiment_params_v1")
    result.setdefault("parts", {})
    if isinstance(result["parts"], list):
        result["parts"] = {
            _canonical_label(str(item.get("part_id", item.get("semantic_label", index)))): item
            for index, item in enumerate(result["parts"])
            if isinstance(item, dict)
        }
    normalised = {}
    for label, payload in result.get("parts", {}).items():
        if not isinstance(payload, dict):
            continue
        part_id = _canonical_label(str(payload.get("part_id", label)))
        part = _default_part(part_id)
        part.update(payload)
        part["part_id"] = part_id
        normalised[part_id] = part
    result["parts"] = normalised
    return result


def _default_part(part_id: str) -> dict[str, Any]:
    part = dict(DEFAULT_PART)
    part["part_id"] = part_id
    return part


def _scaled_value(old_value: Any, target_value: Any, intensity: float) -> Any:
    if isinstance(target_value, bool):
        return bool(target_value) if intensity > 0.0 else old_value
    if isinstance(target_value, (int, float)) and isinstance(old_value, (int, float)) and not isinstance(old_value, bool):
        return old_value + (float(target_value) - float(old_value)) * intensity
    if isinstance(target_value, (int, float)):
        default_old = 0.0 if str(target_value).startswith("-") else 1.0
        return default_old + (float(target_value) - default_old) * intensity
    if intensity >= 1.0:
        return target_value
    return old_value


def _clamp_to_safe_range(field: str, value: Any, safe_ranges: dict[str, Any]) -> Any:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    bounds = safe_ranges.get(field)
    if not isinstance(bounds, list) or len(bounds) != 2:
        return value
    return _clamp(float(value), float(bounds[0]), float(bounds[1]))


def _available_parts(semantic_part_graph: Any) -> set[str]:
    if semantic_part_graph is None:
        return set()
    if isinstance(semantic_part_graph, set):
        return {_canonical_label(str(item)) for item in semantic_part_graph}
    if isinstance(semantic_part_graph, list):
        return {_canonical_label(str(item)) for item in semantic_part_graph}
    if not isinstance(semantic_part_graph, dict):
        return set()
    parts = semantic_part_graph.get("parts", semantic_part_graph.get("semantic_parts", []))
    if isinstance(parts, dict):
        parts = list(parts.values())
    result = set()
    for part in parts:
        if isinstance(part, dict):
            label = part.get("part_id", part.get("semantic_label", part.get("label", "")))
            if int(part.get("pixel_count", 1)) > 0:
                result.add(_canonical_label(str(label)))
        elif isinstance(part, str):
            result.add(_canonical_label(part))
    return result


def _alpha_count(path: Path) -> int:
    try:
        image = Image.open(path).convert("RGBA")
    except OSError:
        return 0
    alpha = image.getchannel("A")
    data = alpha.get_flattened_data() if hasattr(alpha, "get_flattened_data") else alpha.getdata()
    return sum(1 for value in data if int(value) > 16)


def _canonical_label(label: str) -> str:
    return LABEL_ALIASES.get(str(label or "unknown"), str(label or "unknown"))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
