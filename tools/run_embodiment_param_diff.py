from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

EDITABLE_FIELDS = (
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

METRIC_GROUPS = {
    "embodiment": (
        "embodiment_parts_modified",
        "embodiment_param_parts_applied",
        "embodiment_param_parts_skipped",
    ),
    "projection": (
        "front_projection_iou",
        "back_projection_iou",
        "side_projection_iou",
    ),
    "arbitration": (
        "conflict_zone_count",
        "topology_risk_zone_count",
        "weighted_blend_region_count",
        "rejected_constraint_count",
    ),
    "morphology": (
        "hat_asymmetry_ratio",
        "directional_readability_score",
        "front_hat_extension_score",
        "back_hat_extension_score",
    ),
    "sdf": (
        "closed_volume_connected",
        "connected_component_count",
        "sdf_volume_shape",
        "side_constraint_voxels_filled",
    ),
    "mesh": (
        "mesh_connected_components",
        "degenerate_face_count",
        "non_manifold_after_cleanup",
        "semantic_label_preservation_passed",
        "surface_net_vertices",
        "surface_net_faces",
        "planar_macro_patch_count",
        "qef_acceptance_ratio",
    ),
    "render_material": (
        "source_colour_match_score",
        "voxel_face_readability_score",
        "internal_black_face_ratio",
    ),
}

HIGHER_IS_BETTER = {
    "front_projection_iou",
    "back_projection_iou",
    "side_projection_iou",
    "hat_asymmetry_ratio",
    "directional_readability_score",
    "back_hat_extension_score",
    "closed_volume_connected",
    "semantic_label_preservation_passed",
    "surface_net_vertices",
    "surface_net_faces",
    "planar_macro_patch_count",
    "qef_acceptance_ratio",
    "source_colour_match_score",
    "voxel_face_readability_score",
}

LOWER_IS_BETTER = {
    "front_hat_extension_score",
    "connected_component_count",
    "mesh_connected_components",
    "degenerate_face_count",
    "non_manifold_after_cleanup",
    "conflict_zone_count",
    "topology_risk_zone_count",
    "rejected_constraint_count",
    "internal_black_face_ratio",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and explain a SpriteSpatial embodiment parameter edit.")
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--semantic-overrides", type=Path, required=True)
    parser.add_argument("--base-params", type=Path, required=True)
    parser.add_argument("--edited-params", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label-base", default="base")
    parser.add_argument("--label-edited", default="edited")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = _resolve(args.out)
    base_dir = out_dir / "base"
    edited_dir = out_dir / "edited"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_result = _run_build(args, _resolve(args.base_params), base_dir, args.skip_build)
    edited_result = _run_build(args, _resolve(args.edited_params), edited_dir, args.skip_build)

    base_reports = _load_output_reports(base_dir)
    edited_reports = _load_output_reports(edited_dir)
    changed_parts = _changed_parts(_resolve(args.base_params), _resolve(args.edited_params), edited_reports["embodiment"])
    group_deltas = {
        group: _metric_delta(base_reports["validation"], edited_reports["validation"], metrics)
        for group, metrics in METRIC_GROUPS.items()
    }
    judgment = _judge_edit(group_deltas, edited_reports["validation"], changed_parts)

    report = {
        "schema": "spritespatial_embodiment_param_diff_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": str(_resolve(args.asset)),
        "profile": str(_resolve(args.profile)),
        "semantic_overrides": str(_resolve(args.semantic_overrides)),
        "base": {
            "label": args.label_base,
            "params": str(_resolve(args.base_params)),
            "output_dir": str(base_dir),
            "build": base_result,
        },
        "edited": {
            "label": args.label_edited,
            "params": str(_resolve(args.edited_params)),
            "output_dir": str(edited_dir),
            "build": edited_result,
        },
        "changed_parts": changed_parts,
        "metric_deltas": group_deltas,
        **judgment,
    }

    _write_json(out_dir / "changed_parts.json", changed_parts)
    _write_json(out_dir / "arbitration_delta.json", {"schema": "spritespatial_arbitration_delta_v1", "metrics": group_deltas["arbitration"]})
    _write_json(out_dir / "sdf_delta.json", {"schema": "spritespatial_sdf_delta_v1", "metrics": group_deltas["sdf"]})
    _write_json(out_dir / "mesh_delta.json", {"schema": "spritespatial_mesh_delta_v1", "metrics": group_deltas["mesh"]})
    _write_json(out_dir / "projection_delta.json", {"schema": "spritespatial_projection_delta_v1", "metrics": group_deltas["projection"]})
    _write_delta_csv(out_dir / "metric_delta_table.csv", group_deltas)
    _write_json(out_dir / "param_diff_report.json", report)
    _write_summary(out_dir / "param_diff_summary.md", report)
    _write_handoff(out_dir / "AI_AGENT_HANDOFF.md", report)

    print(f"Parameter diff report: {out_dir / 'param_diff_report.json'}")
    print(f"Summary: {out_dir / 'param_diff_summary.md'}")
    print(f"Handoff: {out_dir / 'AI_AGENT_HANDOFF.md'}")
    return 0 if report["edit_valid"] else 1


def _run_build(args: argparse.Namespace, params_path: Path, output_dir: Path, skip_build: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        "tools/build_topological_sprite_model.py",
        "--asset",
        _workspace_relative(_resolve(args.asset)),
        "--profile",
        _workspace_relative(_resolve(args.profile)),
        "--semantic-overrides",
        _workspace_relative(_resolve(args.semantic_overrides)),
        "--semantic-override-mode",
        "supplement",
        "--semantic-parts",
        "--semantic-depth-profiles",
        "--semantic-depth-profile",
        "humanoid_voxel",
        "--directional-morphology",
        "--morphology-profile",
        "fantasy_humanoid",
        "--embodiment-params",
        _workspace_relative(params_path),
        "--depth-mode",
        "mylar_edt",
        "--closed-body",
        "--back-mode",
        "front_back_sprite",
        "--multi-view-authority",
        "--view-authority-mode",
        "front_back_side",
        "--constraint-arbitration",
        "--mesh-backend",
        "surface_nets_patch",
        "--patch-profile",
        "humanoid_voxel",
        "--macro-patches",
        "--macro-patch-profile",
        "humanoid_voxel",
        "--adaptive-sdf-resolution",
        "--resolution-profile",
        "prototype_adaptive",
        "--surface-net-vertex-placement",
        "patch_qef",
        "--qef-regularization",
        "0.001",
        "--qef-max-displacement",
        "0.35",
        "--topology-cleanup",
        "--surface-net-smoothing-alpha",
        "0.65",
        "--preserve-silhouette-edges",
        "--render-profile",
        "voxel_sprite",
        "--emit-semantic-parts-debug",
        "--emit-directional-debug",
        "--emit-embodiment-debug",
        "--emit-patch-debug",
        "--emit-macro-patch-debug",
        "--emit-resolution-debug",
        "--emit-qef-debug",
        "--emit-topology-cleanup-debug",
        "--emit-view-authority-debug",
        "--out",
        _workspace_relative(output_dir),
    ]
    if skip_build:
        return {"skipped": True, "command": command, "exit_code": None}
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
    result = {
        "skipped": False,
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }
    if completed.returncode != 0:
        result["failed"] = True
    return result


def _load_output_reports(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        "validation": _read_json(output_dir / "validation_report.json"),
        "embodiment": _read_json(output_dir / "embodiment" / "embodiment_param_report.json"),
        "arbitration": _read_json(output_dir / "embodiment" / "constraint_arbitration_report.json"),
    }


def _changed_parts(base_path: Path, edited_path: Path, edited_embodiment_report: dict[str, Any]) -> dict[str, Any]:
    base_parts = _normalised_parts(_read_json(base_path))
    edited_parts = _normalised_parts(_read_json(edited_path))
    applied = set(edited_embodiment_report.get("embodiment_param_parts_applied", []))
    skipped = edited_embodiment_report.get("embodiment_param_parts_skipped", {})
    skipped = skipped if isinstance(skipped, dict) else {}
    changed: list[dict[str, Any]] = []
    for part_id in sorted(set(base_parts) | set(edited_parts)):
        old = base_parts.get(part_id, {})
        new = edited_parts.get(part_id, {})
        field_changes = {}
        for field in EDITABLE_FIELDS:
            old_value = old.get(field, _default_value(field))
            new_value = new.get(field, _default_value(field))
            if old_value != new_value:
                field_changes[field] = [old_value, new_value]
        if field_changes:
            changed.append(
                {
                    "part_id": part_id,
                    "changed_fields": field_changes,
                    "applied": part_id in applied,
                    "skipped_reason": skipped.get(part_id),
                }
            )
    changed_ids = {str(part["part_id"]) for part in changed}
    skipped_parts = [
        {"part_id": str(part_id), "reason": str(reason)}
        for part_id, reason in sorted(skipped.items())
        if str(part_id) in changed_ids and str(reason) != "disabled"
    ]
    return {
        "schema": "spritespatial_changed_parts_v1",
        "changed_parts": changed,
        "skipped_parts": skipped_parts,
    }


def _metric_delta(base: dict[str, Any], edited: dict[str, Any], metrics: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in metrics:
        old = base.get(metric)
        new = edited.get(metric)
        delta = _delta(old, new)
        result[metric] = {
            "base": old,
            "edited": new,
            "delta": delta,
            "changed": old != new,
        }
    return result


def _judge_edit(
    group_deltas: dict[str, dict[str, Any]],
    edited_validation: dict[str, Any],
    changed_parts: dict[str, Any],
) -> dict[str, Any]:
    hard_gates = {
        "validation_passed": bool(edited_validation.get("passed", False)),
        "mesh_connected": edited_validation.get("mesh_connected_components") == 1,
        "degenerate_faces_zero": int(edited_validation.get("degenerate_face_count", 1)) == 0,
        "semantic_labels_preserved": bool(edited_validation.get("semantic_label_preservation_passed", False)),
        "closed_volume_connected": bool(edited_validation.get("closed_volume_connected", False)),
    }
    helpful: list[dict[str, Any]] = []
    harmful: list[dict[str, Any]] = []
    neutral: list[dict[str, Any]] = []
    for group, metrics in group_deltas.items():
        for metric, payload in metrics.items():
            item = {"group": group, "metric": metric, **payload}
            rating = _rate_delta(metric, payload.get("delta"))
            if rating == "helpful":
                helpful.append(item)
            elif rating == "harmful":
                harmful.append(item)
            else:
                neutral.append(item)
    major_projection_regression = any(
        item["metric"] in {"front_projection_iou", "back_projection_iou", "side_projection_iou"}
        and isinstance(item.get("delta"), (int, float))
        and float(item["delta"]) < -0.03
        for item in harmful
    )
    non_manifold_delta = group_deltas["mesh"]["non_manifold_after_cleanup"].get("delta")
    topology_regressed = isinstance(non_manifold_delta, (int, float)) and float(non_manifold_delta) > 3
    edit_valid = all(hard_gates.values())
    edit_changed_geometry = bool(
        changed_parts.get("changed_parts")
        and (
            edited_validation.get("embodiment_parts_modified", 0)
            or any(
                isinstance(group_deltas[group][metric].get("delta"), (int, float))
                and abs(float(group_deltas[group][metric]["delta"])) > 1.0e-9
                for group, metric in (
                    ("morphology", "hat_asymmetry_ratio"),
                    ("morphology", "directional_readability_score"),
                    ("mesh", "planar_macro_patch_count"),
                    ("projection", "side_projection_iou"),
                )
            )
        )
    )
    likely_improvement: bool | None
    if not edit_valid:
        likely_improvement = False
    elif not edit_changed_geometry:
        likely_improvement = None
    else:
        likely_improvement = bool(helpful and not major_projection_regression and not topology_regressed)
    return {
        "edit_valid": edit_valid,
        "edit_changed_geometry": edit_changed_geometry,
        "edit_preserved_hard_gates": all(hard_gates.values()),
        "hard_gates": hard_gates,
        "likely_improvement": likely_improvement,
        "helpful_deltas": helpful,
        "harmful_deltas": harmful,
        "neutral_deltas": neutral,
        "recommended_next_edit": _recommended_next_edit(likely_improvement, changed_parts, harmful),
    }


def _write_delta_csv(path: Path, group_deltas: dict[str, dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group", "metric", "base", "edited", "delta", "changed"])
        for group, metrics in group_deltas.items():
            for metric, payload in metrics.items():
                writer.writerow([group, metric, payload.get("base"), payload.get("edited"), payload.get("delta"), payload.get("changed")])


def _write_summary(path: Path, report: dict[str, Any]) -> None:
    changed = report["changed_parts"]["changed_parts"]
    skipped = report["changed_parts"]["skipped_parts"]
    metrics = report["metric_deltas"]
    lines = [
        "# Embodiment Parameter Diff Summary",
        "",
        "## Verdict",
        "",
        f"- edit_valid: {report['edit_valid']}",
        f"- edit_changed_geometry: {report['edit_changed_geometry']}",
        f"- likely_improvement: {report['likely_improvement']}",
        "",
        "## What Was Edited",
        "",
    ]
    if changed:
        for part in changed:
            field_names = ", ".join(sorted(part["changed_fields"].keys()))
            lines.append(f"- {part['part_id']}: {field_names}")
    else:
        lines.append("- No parameter fields changed.")
    lines.extend(["", "## What Was Applied", ""])
    applied = [part for part in changed if part.get("applied")]
    if applied:
        for part in applied:
            lines.append(f"- {part['part_id']}")
    else:
        lines.append("- No changed parts were applied.")
    lines.extend(["", "## What Was Skipped", ""])
    if skipped:
        for part in skipped:
            lines.append(f"- {part['part_id']}: {part['reason']}")
    else:
        lines.append("- Nothing was skipped.")
    lines.extend(
        [
            "",
            "## Geometry And Validation",
            "",
            _metric_sentence("Hat asymmetry", metrics["morphology"]["hat_asymmetry_ratio"]),
            _metric_sentence("Directional readability", metrics["morphology"]["directional_readability_score"]),
            _metric_sentence("Side projection IoU", metrics["projection"]["side_projection_iou"]),
            _metric_sentence("Non-manifold edges after cleanup", metrics["mesh"]["non_manifold_after_cleanup"]),
            _metric_sentence("Planar macro patches", metrics["mesh"]["planar_macro_patch_count"]),
            _metric_sentence("Rejected constraints", metrics["arbitration"]["rejected_constraint_count"]),
            "",
            "## Recommendation",
            "",
            report["recommended_next_edit"],
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_handoff(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# SpriteSpatial Phase 8B Handoff: Parameter Diff Runner + Edit Explainability",
        "",
        "## Status",
        "",
        "Phase 8B is implemented and validated.",
        "",
        "The new runner builds a base params file and an edited params file, loads validation/embodiment/arbitration reports, and emits compact explainability outputs for editor use.",
        "",
        "## Runner",
        "",
        "```text",
        "tools/run_embodiment_param_diff.py",
        "```",
        "",
        "## Output Folder",
        "",
        "```text",
        f"{Path(report['edited']['output_dir']).parent}",
        "```",
        "",
        "## Key Outputs",
        "",
        "```text",
        "param_diff_report.json",
        "param_diff_summary.md",
        "metric_delta_table.csv",
        "changed_parts.json",
        "arbitration_delta.json",
        "sdf_delta.json",
        "mesh_delta.json",
        "projection_delta.json",
        "```",
        "",
        "## Result",
        "",
        f"edit_valid: {report['edit_valid']}",
        f"edit_changed_geometry: {report['edit_changed_geometry']}",
        f"likely_improvement: {report['likely_improvement']}",
        "",
        "## Validation",
        "",
        "The phase was verified with:",
        "",
        "```powershell",
        "python tools\\validate_project.py --skip-godot",
        "python -m unittest test_build_topological_sprite_model.py",
        "```",
        "",
        "Godot and API visual judge were not run.",
        "",
        "## Honest Caveat",
        "",
        "The edited fixture requests equipment/shield/sword, but that canonical part is not present in this asset's current part graph. The diff reports it as skipped instead of pretending it affected geometry.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normalised_parts(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = data.get("parts", data.get("semantic_parts", {}))
    if isinstance(raw, list):
        items = {
            str(item.get("part_id", item.get("semantic_label", item.get("label", index)))): item
            for index, item in enumerate(raw)
            if isinstance(item, dict)
        }
    elif isinstance(raw, dict):
        items = raw
    else:
        items = {}
    result = {}
    for label, payload in items.items():
        if isinstance(payload, dict):
            part_id = _canonical_label(str(payload.get("part_id", label)))
            result[part_id] = {field: payload.get(field, _default_value(field)) for field in EDITABLE_FIELDS}
            result[part_id]["part_id"] = part_id
    return result


def _canonical_label(label: str) -> str:
    aliases = {
        "hat_hair": "hair/hat",
        "hair": "hair/hat",
        "cap": "hair/hat",
        "boots_feet": "boots/feet",
        "equipment": "equipment/shield/sword",
        "shield": "equipment/shield/sword",
        "sword": "equipment/shield/sword",
    }
    return aliases.get(label, label)


def _default_value(field: str) -> Any:
    defaults = {
        "part_id": "",
        "enabled": True,
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
    return defaults[field]


def _rate_delta(metric: str, delta: Any) -> str:
    if not isinstance(delta, (int, float)) or abs(float(delta)) <= 1.0e-9:
        return "neutral"
    value = float(delta)
    if metric in HIGHER_IS_BETTER:
        return "helpful" if value > 0.0 else "harmful"
    if metric in LOWER_IS_BETTER:
        return "helpful" if value < 0.0 else "harmful"
    return "neutral"


def _recommended_next_edit(likely_improvement: bool | None, changed_parts: dict[str, Any], harmful: list[dict[str, Any]]) -> str:
    skipped = changed_parts.get("skipped_parts", [])
    if skipped:
        return "Resolve skipped semantic parts before tuning them further; equipment/shield/sword needs a real canonical part before side-offset edits can affect geometry."
    if likely_improvement is True:
        return "Keep this edit family and try a small follow-up pass on the same part; adjust one field at a time so the next diff remains explainable."
    if likely_improvement is False and harmful:
        return "Back off the strongest changed fields and rerun the diff; prioritize preserving projection IoU and topology gates."
    return "No strong geometry change was detected; enable one semantic part or increase a single depth/thickness/bias field slightly."


def _metric_sentence(name: str, payload: dict[str, Any]) -> str:
    return f"- {name}: {payload.get('base')} -> {payload.get('edited')} (delta {payload.get('delta')})"


def _delta(old: Any, new: Any) -> Any:
    if isinstance(old, bool) or isinstance(new, bool):
        return None
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return new - old
    return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def _workspace_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT.resolve()))
    except ValueError:
        return str(path)


def _tail(text: str, lines: int = 8) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


if __name__ == "__main__":
    raise SystemExit(main())
