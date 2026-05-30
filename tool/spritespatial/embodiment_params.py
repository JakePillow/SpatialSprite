from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from spritespatial.directional_morphology import DirectionalMorphologyRule, canonical_label as morphology_label
from spritespatial.semantic_depth_profiles import SemanticDepthProfile, canonical_label as depth_label


EDITABLE_FIELDS = (
    "part_id",
    "enabled",
    "z_center_offset",
    "thickness_scale",
    "front_bias",
    "back_bias",
    "side_width_scale",
    "silhouette_weight",
    "front_authority_weight",
    "back_authority_weight",
    "side_authority_weight",
    "topology_preservation_weight",
    "taper_strength",
    "preserve_silhouette",
    "lock_part",
    "notes",
)


def load_embodiment_params(path: Path | None, workspace_root: Path) -> dict[str, Any]:
    if path is None:
        return {
            "schema": "spritespatial_embodiment_params_v1",
            "enabled": True,
            "path": "",
            "name": "default_embodiment_params",
            "parts": {},
            "raw": {"schema": "spritespatial_embodiment_params_v1", "parts": {}},
            "using_defaults": True,
        }
    resolved = path if path.is_absolute() else workspace_root / path
    data = json.loads(resolved.read_text(encoding="utf-8"))
    raw_parts = data.get("parts", data.get("semantic_parts", {}))
    if isinstance(raw_parts, list):
        raw_parts = {
            str(item.get("part_id", item.get("semantic_label", item.get("label", f"part_{index}")))): item
            for index, item in enumerate(raw_parts)
            if isinstance(item, dict)
        }
    elif not isinstance(raw_parts, dict):
        raw_parts = {}
    parts: dict[str, dict[str, Any]] = {}
    for label, payload in raw_parts.items():
        if not isinstance(payload, dict):
            continue
        canonical = depth_label(str(payload.get("part_id", label)))
        normalised = _normalise_part_payload(payload)
        normalised["part_id"] = canonical
        parts[canonical] = normalised
    return {
        "schema": data.get("schema", "spritespatial_embodiment_params_v1"),
        "enabled": True,
        "path": str(resolved),
        "name": data.get("name", resolved.stem),
        "parts": parts,
        "raw": data,
        "using_defaults": False,
    }


def apply_embodiment_params(
    semantic_depth_profile: dict[str, Any] | None,
    directional_morphology: dict[str, Any] | None,
    embodiment_params: dict[str, Any],
    parts: list[dict[str, Any]],
    output_dir: Path | None = None,
    emit_debug: bool = False,
) -> dict[str, Any]:
    if not embodiment_params.get("enabled", False):
        return {
            "semantic_depth_profile": semantic_depth_profile,
            "directional_morphology": directional_morphology,
            "report": {
                "embodiment_params_enabled": False,
                "embodiment_params_path": "",
                "embodiment_param_parts_requested": [],
                "embodiment_param_parts_applied": [],
            },
            "paths": {},
        }

    depth_profile = _copy_depth_profile(semantic_depth_profile)
    morphology_profile = _copy_morphology_profile(directional_morphology)
    requested = embodiment_params.get("parts", {})
    part_labels_present = _part_label_set(parts)
    applied: list[str] = []
    skipped: dict[str, str] = {}
    locked: list[str] = []
    depth_deltas: dict[str, Any] = {}
    morphology_deltas: dict[str, Any] = {}
    notes: dict[str, str] = {}

    for label, payload in requested.items():
        canonical = depth_label(label)
        if not bool(payload.get("enabled", True)):
            skipped[canonical] = "disabled"
            continue
        if canonical not in part_labels_present:
            skipped[canonical] = "part_not_present"
            continue
        if bool(payload.get("lock_part", False)):
            locked.append(canonical)
            skipped[canonical] = "lock_part"
            continue

        base_depth = depth_profile["profiles"].get(canonical, depth_profile["profiles"].get("unknown"))
        if isinstance(base_depth, SemanticDepthProfile):
            next_depth = _merge_depth_profile(base_depth, payload)
            depth_profile["profiles"][canonical] = next_depth
            depth_deltas[canonical] = {
                "before": asdict(base_depth),
                "after": asdict(next_depth),
            }

        rules = morphology_profile.setdefault("rules", {})
        base_rule = rules.get(canonical)
        if isinstance(base_rule, DirectionalMorphologyRule) or _directional_rule_allowed(canonical, payload):
            if not isinstance(base_rule, DirectionalMorphologyRule):
                base_rule = _default_rule_for_label(canonical)
            next_rule = _merge_directional_rule(base_rule, payload)
            rules[canonical] = next_rule
            morphology_deltas[canonical] = {
                "before": asdict(base_rule),
                "after": asdict(next_rule),
            }

        if payload.get("notes"):
            notes[canonical] = str(payload.get("notes", ""))
        applied.append(canonical)

    report = {
        "schema": "spritespatial_embodiment_param_report_v1",
        "embodiment_params_enabled": True,
        "embodiment_params_path": embodiment_params.get("path", ""),
        "embodiment_params_name": embodiment_params.get("name", ""),
        "embodiment_params_loaded": True,
        "embodiment_params_using_defaults": bool(embodiment_params.get("using_defaults", False)),
        "embodiment_param_parts_requested": sorted(str(label) for label in requested.keys()),
        "embodiment_param_parts_applied": sorted(set(applied)),
        "embodiment_param_parts_skipped": skipped,
        "embodiment_param_locked_parts": sorted(set(locked)),
        "embodiment_param_applied_count": len(set(applied)),
        "embodiment_parts_modified": len(set(applied)),
        "embodiment_param_depth_deltas": depth_deltas,
        "embodiment_param_morphology_deltas": morphology_deltas,
        "embodiment_param_notes": notes,
    }
    depth_profile["embodiment_params_report"] = report
    depth_profile["embodiment_params"] = embodiment_params
    morphology_profile["embodiment_params_report"] = report
    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = write_embodiment_param_debug(output_dir, parts, report, emit_debug)
    return {
        "semantic_depth_profile": depth_profile,
        "directional_morphology": morphology_profile,
        "report": report,
        "paths": paths,
    }


def write_embodiment_param_debug(
    output_dir: Path,
    parts: list[dict[str, Any]],
    report: dict[str, Any],
    emit_debug: bool,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "embodiment_param_report": output_dir / "embodiment_param_report.json",
        "embodiment_param_overlay": output_dir / "embodiment_param_overlay.png",
        "embodiment_params_applied": output_dir / "embodiment_params_applied.json",
        "part_depth_debug": output_dir / "part_depth_debug.png",
        "embodiment_delta_report": output_dir / "embodiment_delta_report.json",
    }
    paths["embodiment_param_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_overlay(parts, report, paths["embodiment_param_overlay"])
    paths["embodiment_params_applied"].write_text(json.dumps(_applied_params_summary(report), indent=2) + "\n", encoding="utf-8")
    paths["embodiment_delta_report"].write_text(json.dumps(_delta_summary(report), indent=2) + "\n", encoding="utf-8")
    _write_overlay(parts, report, paths["part_depth_debug"])
    if emit_debug:
        paths["embodiment_param_raw_applied"] = output_dir / "embodiment_param_raw_applied.json"
        paths["embodiment_param_raw_applied"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return paths


def _normalise_part_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in EDITABLE_FIELDS:
        if field in payload:
            result[field] = payload[field]
    result.setdefault("enabled", True)
    result.setdefault("z_center_offset", 0.0)
    result.setdefault("thickness_scale", 1.0)
    result.setdefault("front_bias", 0.0)
    result.setdefault("back_bias", 0.0)
    result.setdefault("side_width_scale", 1.0)
    result.setdefault("silhouette_weight", 1.0)
    result.setdefault("front_authority_weight", 1.0)
    result.setdefault("back_authority_weight", 1.0)
    result.setdefault("side_authority_weight", 1.0)
    result.setdefault("topology_preservation_weight", 1.0)
    result.setdefault("taper_strength", 0.0)
    result.setdefault("preserve_silhouette", True)
    result.setdefault("lock_part", False)
    result.setdefault("notes", "")
    return result


def _copy_depth_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if profile is None:
        return {"name": "", "path": "", "profiles": {}, "raw": {}}
    result = dict(profile)
    result["profiles"] = dict(profile.get("profiles", {}))
    return result


def _copy_morphology_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if profile is None:
        return {"name": "embodiment_params_generated", "path": "", "rules": {}, "raw": {}}
    result = dict(profile)
    result["rules"] = dict(profile.get("rules", {}))
    return result


def _part_label_set(parts: list[dict[str, Any]]) -> set[str]:
    labels = set()
    for part in parts:
        labels.add(depth_label(str(part.get("semantic_label", part.get("name", "unknown")))))
    return labels


def _merge_depth_profile(base: SemanticDepthProfile, payload: dict[str, Any]) -> SemanticDepthProfile:
    thickness_scale = _clamp(float(payload.get("thickness_scale", 1.0)), 0.05, 4.0)
    z_offset = _clamp(float(payload.get("z_center_offset", 0.0)), -1.0, 1.0)
    taper_strength = _clamp(float(payload.get("taper_strength", 0.0)), 0.0, 1.0)
    silhouette_param = _clamp(float(payload.get("silhouette_weight", 1.0)), 0.0, 2.0)
    silhouette_weight = base.silhouette_preservation_weight * silhouette_param
    if not bool(payload.get("preserve_silhouette", True)):
        silhouette_weight = max(0.5, silhouette_weight - 0.20)
    return replace(
        base,
        z_center_fraction=_clamp(base.z_center_fraction + z_offset, -1.0, 1.0),
        half_thickness_fraction=_clamp(base.half_thickness_fraction * thickness_scale, 0.01, 1.25),
        asymmetry=_clamp(base.asymmetry + 0.10 * (float(payload.get("front_bias", 0.0)) - float(payload.get("back_bias", 0.0))), -1.0, 1.0),
        taper_curve=_taper_curve(base.taper_curve, taper_strength),
        silhouette_preservation_weight=_clamp(silhouette_weight, 0.0, 2.0),
    )


def _merge_directional_rule(base: DirectionalMorphologyRule, payload: dict[str, Any]) -> DirectionalMorphologyRule:
    front_bias = float(payload.get("front_bias", 0.0))
    back_bias = float(payload.get("back_bias", 0.0))
    side_scale = float(payload.get("side_width_scale", 1.0))
    taper = _clamp(float(payload.get("taper_strength", 0.0)), 0.0, 1.0)
    return replace(
        base,
        forward_bias=_clamp(base.forward_bias + front_bias, -1.0, 2.0),
        backward_bias=_clamp(base.backward_bias + back_bias, -1.0, 2.0),
        lateral_bias=_clamp(base.lateral_bias + (side_scale - 1.0) * 0.75, -1.0, 1.5),
        asymmetry_strength=_clamp(base.asymmetry_strength + abs(front_bias - back_bias) * 0.25, 0.0, 1.0),
        front_scale=_clamp(base.front_scale * max(0.05, 1.0 + front_bias * 0.25), 0.05, 3.0),
        back_scale=_clamp(base.back_scale * max(0.05, 1.0 + back_bias * 0.35), 0.05, 3.0),
        front_taper=_clamp(base.front_taper + taper * 0.35, 0.0, 1.0),
        back_taper=_clamp(base.back_taper + taper, 0.0, 1.0),
        rear_extension_bias=_clamp(base.rear_extension_bias + max(0.0, back_bias) * 0.35, 0.0, 1.5),
    )


def _default_rule_for_label(label: str) -> DirectionalMorphologyRule:
    canonical = morphology_label(label)
    if canonical == "hair/hat":
        return DirectionalMorphologyRule(profile_type="HAT_POINTED_BACK", taper_direction="back")
    if canonical == "face":
        return DirectionalMorphologyRule(profile_type="NOSE_FORWARD", taper_direction="front")
    if canonical == "equipment/shield/sword":
        return DirectionalMorphologyRule(profile_type="SHIELD_SIDE", taper_direction="side")
    if canonical in {"left_arm", "right_arm"}:
        return DirectionalMorphologyRule(profile_type="SHOULDER_PAD", taper_direction="side")
    return DirectionalMorphologyRule(profile_type="NEUTRAL", taper_direction="none")


def _directional_rule_allowed(label: str, payload: dict[str, Any]) -> bool:
    canonical = morphology_label(label)
    if canonical in {"hair/hat", "face", "equipment/shield/sword", "left_arm", "right_arm"}:
        return True
    return bool(
        abs(float(payload.get("front_bias", 0.0))) > 1.0e-6
        or abs(float(payload.get("back_bias", 0.0))) > 1.0e-6
        or abs(float(payload.get("side_width_scale", 1.0)) - 1.0) > 0.15
        or float(payload.get("taper_strength", 0.0)) > 0.20
    )


def _taper_curve(curve: str, strength: float) -> str:
    if strength <= 0.0:
        return curve
    if curve in {"layer", "shell", "rigid"}:
        return curve
    if strength >= 0.65:
        return "limb_taper"
    return curve


def _write_overlay(parts: list[dict[str, Any]], report: dict[str, Any], path: Path) -> None:
    applied = set(report.get("embodiment_param_parts_applied", []))
    locked = set(report.get("embodiment_param_locked_parts", []))
    skipped = set(report.get("embodiment_param_parts_skipped", {}).keys())
    width = 1
    height = 1
    for part in parts:
        for x, y in part.get("pixels", []):
            width = max(width, int(x) + 1)
            height = max(height, int(y) + 1)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    for part in parts:
        label = depth_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        color = (80, 90, 100, 110)
        if label in applied:
            color = (255, 190, 70, 255)
        elif label in locked:
            color = (90, 160, 255, 255)
        elif label in skipped:
            color = (255, 70, 90, 220)
        for x, y in part.get("pixels", []):
            pixels[int(x), int(y)] = color
    draw = ImageDraw.Draw(image)
    draw.text((1, 1), "orange=edited blue=locked red=skipped", fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _applied_params_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "spritespatial_embodiment_params_applied_v1",
        "embodiment_params_loaded": bool(report.get("embodiment_params_loaded", False)),
        "embodiment_params_path": report.get("embodiment_params_path", ""),
        "embodiment_params_using_defaults": bool(report.get("embodiment_params_using_defaults", False)),
        "parts_applied": report.get("embodiment_param_parts_applied", []),
        "parts_skipped": report.get("embodiment_param_parts_skipped", {}),
        "parts_locked": report.get("embodiment_param_locked_parts", []),
        "embodiment_parts_modified": int(report.get("embodiment_parts_modified", 0)),
        "notes": report.get("embodiment_param_notes", {}),
    }


def _delta_summary(report: dict[str, Any]) -> dict[str, Any]:
    depth_deltas = report.get("embodiment_param_depth_deltas", {})
    morphology_deltas = report.get("embodiment_param_morphology_deltas", {})
    return {
        "schema": "spritespatial_embodiment_delta_report_v1",
        "modified_part_count": int(report.get("embodiment_parts_modified", 0)),
        "depth_delta_parts": sorted(depth_deltas.keys()) if isinstance(depth_deltas, dict) else [],
        "morphology_delta_parts": sorted(morphology_deltas.keys()) if isinstance(morphology_deltas, dict) else [],
        "depth_deltas": depth_deltas,
        "morphology_deltas": morphology_deltas,
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
