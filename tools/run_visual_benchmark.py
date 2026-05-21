from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

ANGLE_CAPTURE = {
    "0": "front.png",
    "45": "oblique.png",
    "90": "side.png",
    "135": "side_135.png",
    "180": "back.png",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SpriteSpatial visual regression benchmark phases.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--update-reference",
        action="store_true",
        help="Replace the stored reference metrics with this benchmark run.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Read existing phase outputs instead of executing build commands.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = _resolve(args.config)
    output_dir = _resolve(args.out)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    contact_dir = output_dir / "contact_sheets"
    contact_dir.mkdir(parents=True, exist_ok=True)

    phase_results: list[dict[str, Any]] = []
    for asset in config.get("assets", []):
        for phase in config.get("phases", []):
            phase_results.append(_run_or_read_phase(asset, phase, args.skip_build))

    metrics = _collect_all_metrics(phase_results, config.get("metrics", []))
    deltas = _metric_deltas(metrics, config.get("metrics", []))
    failures, reference_status = _regression_failures(config, metrics, args.update_reference)

    contact_paths = _write_contact_sheets(config, metrics, contact_dir)
    csv_path = output_dir / "metric_delta_table.csv"
    _write_delta_csv(deltas, csv_path)
    failures_path = output_dir / "failures.json"
    failures_payload = {
        "schema": "spritespatial_visual_benchmark_failures_v1",
        "failed": bool(failures),
        "reference_status": reference_status,
        "failures": failures,
    }
    failures_path.write_text(json.dumps(failures_payload, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema": "spritespatial_visual_benchmark_report_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "reference_status": reference_status,
        "assets": config.get("assets", []),
        "phase_results": phase_results,
        "metrics": metrics,
        "metric_deltas": deltas,
        "contact_sheets": {key: str(path) for key, path in contact_paths.items()},
        "failures": failures,
        "passed": not failures,
    }
    report_path = output_dir / "benchmark_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_summary(config, report, output_dir / "benchmark_summary.md")

    print(f"Visual benchmark report: {report_path}")
    print(f"Metric deltas: {csv_path}")
    print(f"Failures: {failures_path}")
    return 0 if not failures else 1


def _run_or_read_phase(asset: dict[str, Any], phase: dict[str, Any], skip_build: bool) -> dict[str, Any]:
    output_dir = _resolve(Path(str(phase["out"])))
    command = _phase_command(asset, phase, output_dir)
    completed: subprocess.CompletedProcess[str] | None = None
    attempts: list[dict[str, Any]] = []
    if not skip_build:
        output_dir.mkdir(parents=True, exist_ok=True)
        retries = max(0, int(phase.get("retries", 1)))
        for attempt in range(retries + 1):
            completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "exit_code": completed.returncode,
                    "stdout_tail": _tail(completed.stdout, 4),
                    "stderr_tail": _tail(completed.stderr, 4),
                }
            )
            if completed.returncode == 0 or not _retryable_build_failure(completed):
                break
            time.sleep(1.5)
    validation_path = output_dir / "validation_report.json"
    visual_path = output_dir / "visual_mapping_report.json"
    validation = _read_json(validation_path)
    visual = _read_json(visual_path)
    return {
        "asset": asset.get("name", "asset"),
        "phase": phase.get("name", output_dir.name),
        "output_dir": str(output_dir),
        "command": command,
        "build_exit_code": completed.returncode if completed else None,
        "build_stdout_tail": _tail(completed.stdout) if completed else "",
        "build_stderr_tail": _tail(completed.stderr) if completed else "",
        "build_attempts": attempts,
        "validation_report": str(validation_path),
        "visual_mapping_report": str(visual_path),
        "validation_loaded": bool(validation),
        "visual_mapping_loaded": bool(visual),
        "validation_passed": bool(validation.get("passed", False)),
    }


def _phase_command(asset: dict[str, Any], phase: dict[str, Any], output_dir: Path) -> list[str]:
    context = {
        "asset": str(asset["asset"]),
        "profile": str(asset["profile"]),
        "semantic_overrides": str(asset.get("semantic_overrides", "")),
        "out": _workspace_relative(output_dir),
    }
    args = [_substitute(str(item), context) for item in phase.get("args", [])]
    return [sys.executable, "tools/build_topological_sprite_model.py", *args]


def _collect_all_metrics(phase_results: list[dict[str, Any]], metric_names: list[str]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for result in phase_results:
        output_dir = Path(str(result["output_dir"]))
        validation = _read_json(output_dir / "validation_report.json")
        visual = _read_json(output_dir / "visual_mapping_report.json")
        key = f"{result['asset']}::{result['phase']}"
        results[key] = {
            "asset": result["asset"],
            "phase": result["phase"],
            "output_dir": str(output_dir),
            "metrics": _phase_metrics(validation, visual, metric_names),
            "validation_passed": bool(validation.get("passed", False)),
        }
    return results


def _phase_metrics(validation: dict[str, Any], visual: dict[str, Any], metric_names: list[str]) -> dict[str, Any]:
    views = visual.get("views", {}) if isinstance(visual.get("views", {}), dict) else {}
    extracted = {
        "front_iou": _view_metric(views, "front", "silhouette_iou", validation.get("front_visual_mapping_iou")),
        "side_iou": _view_metric(views, "side", "silhouette_iou"),
        "back_iou": _view_metric(views, "back", "silhouette_iou"),
        "worst_view_iou": visual.get("worst_visual_mapping_score", validation.get("worst_visual_mapping_score")),
        "semantic_match_ratio": _mean_view_metric(views, "semantic_match_ratio"),
        "source_colour_match_score": validation.get("source_colour_match_score"),
        "voxel_face_readability_score": validation.get("voxel_face_readability_score"),
        "side_profile_readability_score": validation.get("side_profile_readability_score"),
        "directional_readability_score": validation.get("directional_readability_score"),
        "oblique_surface_readability": validation.get("oblique_surface_readability"),
        "staircase_artifact_score": validation.get("staircase_artifact_score"),
        "surface_fragmentation_score": validation.get("surface_fragmentation_score"),
        "internal_black_face_ratio": validation.get("internal_black_face_ratio"),
        "non_manifold_edge_count": validation.get("non_manifold_edge_count"),
        "degenerate_face_count": validation.get("degenerate_face_count"),
        "validation_passed": bool(validation.get("passed", False)),
    }
    return {name: extracted.get(name) for name in metric_names + ["validation_passed"]}


def _metric_deltas(metrics: dict[str, Any], metric_names: list[str]) -> list[dict[str, Any]]:
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for value in metrics.values():
        by_asset.setdefault(str(value["asset"]), []).append(value)
    deltas: list[dict[str, Any]] = []
    for asset, phases in by_asset.items():
        for index in range(1, len(phases)):
            previous = phases[index - 1]
            current = phases[index]
            for metric in metric_names:
                old = _number(previous["metrics"].get(metric))
                new = _number(current["metrics"].get(metric))
                delta = None if old is None or new is None else new - old
                deltas.append(
                    {
                        "asset": asset,
                        "from_phase": previous["phase"],
                        "to_phase": current["phase"],
                        "metric": metric,
                        "from_value": old,
                        "to_value": new,
                        "delta": delta,
                    }
                )
    return deltas


def _regression_failures(
    config: dict[str, Any],
    metrics: dict[str, Any],
    update_reference: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for key, payload in metrics.items():
        phase_metrics = payload["metrics"]
        if phase_metrics.get("validation_passed") is not True:
            failures.append({"phase": key, "gate": "validation_report_passed", "value": phase_metrics.get("validation_passed")})
        degenerate = _number(phase_metrics.get("degenerate_face_count"))
        if degenerate is not None and degenerate > 0:
            failures.append({"phase": key, "gate": "degenerate_face_count", "value": degenerate})

    reference_path = _resolve(Path(str(config.get("reference_metrics_path", "benchmarks/reference_visual_benchmark.json"))))
    reference_phase = str(config.get("reference_phase", "phase6b_surface_flow"))
    reference_payload = {
        "schema": "spritespatial_visual_benchmark_reference_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reference_phase": reference_phase,
        "metrics": metrics,
    }
    if update_reference or not reference_path.exists():
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_text(json.dumps(reference_payload, indent=2) + "\n", encoding="utf-8")
        return failures, {
            "reference_path": str(reference_path),
            "reference_phase": reference_phase,
            "established": True,
            "updated": bool(update_reference),
            "regression_checks_run": False,
        }

    reference = _read_json(reference_path)
    reference_metrics = reference.get("metrics", {}) if isinstance(reference.get("metrics", {}), dict) else {}
    if not _reference_has_passing_phase(reference_metrics, reference_phase):
        reference_path.write_text(json.dumps(reference_payload, indent=2) + "\n", encoding="utf-8")
        return failures, {
            "reference_path": str(reference_path),
            "reference_phase": reference_phase,
            "established": True,
            "updated": False,
            "regression_checks_run": False,
            "reason": "previous reference did not contain a passing reference phase",
        }
    thresholds = config.get("regression_thresholds", {})
    for key, payload in metrics.items():
        if not key.endswith(f"::{reference_phase}"):
            continue
        previous = reference_metrics.get(key, {}).get("metrics", {})
        current = payload.get("metrics", {})
        failures.extend(_compare_against_reference(key, previous, current, thresholds))
    return failures, {
        "reference_path": str(reference_path),
        "reference_phase": reference_phase,
        "established": False,
        "updated": False,
        "regression_checks_run": True,
    }


def _reference_has_passing_phase(reference_metrics: dict[str, Any], reference_phase: str) -> bool:
    for key, payload in reference_metrics.items():
        if key.endswith(f"::{reference_phase}") and payload.get("metrics", {}).get("validation_passed") is True:
            return True
    return False


def _compare_against_reference(
    phase_key: str,
    previous: dict[str, Any],
    current: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    drop_thresholds = {
        "front_iou": float(thresholds.get("max_front_iou_drop", 0.05)),
        "side_iou": float(thresholds.get("max_side_iou_drop", 0.05)),
        "worst_view_iou": float(thresholds.get("max_worst_view_iou_drop", 0.05)),
        "semantic_match_ratio": float(thresholds.get("max_semantic_match_ratio_drop", 0.05)),
    }
    for metric, threshold in drop_thresholds.items():
        old = _number(previous.get(metric))
        new = _number(current.get(metric))
        if old is not None and new is not None and old - new > threshold:
            failures.append({"phase": phase_key, "gate": f"{metric}_drop", "reference": old, "current": new, "threshold": threshold})
    increases = {
        "surface_fragmentation_score": float(thresholds.get("max_surface_fragmentation_increase", 0.0)),
        "staircase_artifact_score": float(thresholds.get("max_staircase_artifact_increase", 0.10)),
        "non_manifold_edge_count": float(thresholds.get("max_non_manifold_edge_increase", 0.0)),
    }
    for metric, threshold in increases.items():
        old = _number(previous.get(metric))
        new = _number(current.get(metric))
        if old is not None and new is not None and new - old > threshold:
            failures.append({"phase": phase_key, "gate": f"{metric}_increase", "reference": old, "current": new, "threshold": threshold})
    return failures


def _write_contact_sheets(config: dict[str, Any], metrics: dict[str, Any], contact_dir: Path) -> dict[str, Path]:
    phases = [str(phase["name"]) for phase in config.get("phases", [])]
    assets = [str(asset["name"]) for asset in config.get("assets", [])]
    paths: dict[str, Path] = {}
    for asset in assets:
        phase_outputs = {
            item["phase"]: Path(str(item["output_dir"]))
            for item in metrics.values()
            if item["asset"] == asset
        }
        pairs = [
            ("baseline_vs_5e", "baseline_smoothed", "phase5e_semantic_depth"),
            ("5e_vs_5g", "phase5e_semantic_depth", "phase5g_directional_morphology"),
            ("5g_vs_6b", "phase5g_directional_morphology", "phase6b_surface_flow"),
        ]
        for name, left, right in pairs:
            if left in phase_outputs and right in phase_outputs:
                path = contact_dir / f"{asset}_{name}.png"
                _write_phase_sheet([(left, phase_outputs[left]), (right, phase_outputs[right])], path)
                paths[f"{asset}_{name}"] = path
        full = [(phase, phase_outputs[phase]) for phase in phases if phase in phase_outputs]
        if full:
            path = contact_dir / f"{asset}_full_progression.png"
            _write_phase_sheet(full, path)
            paths[f"{asset}_full_progression"] = path
    return paths


def _write_phase_sheet(phases: list[tuple[str, Path]], path: Path) -> None:
    cell = (160, 132)
    header = 24
    angles = ["0", "45", "90", "135", "180"]
    sheet = Image.new("RGBA", (cell[0] * len(phases) + 56, header + cell[1] * len(angles)), (28, 28, 28, 255))
    draw = ImageDraw.Draw(sheet)
    for column, (phase, _) in enumerate(phases):
        draw.text((56 + column * cell[0] + 6, 6), phase[:26], fill=(245, 245, 245, 255))
    for row, angle in enumerate(angles):
        y = header + row * cell[1]
        draw.text((8, y + 8), f"{angle} deg", fill=(245, 245, 245, 255))
        for column, (_, out_dir) in enumerate(phases):
            panel = _capture_panel(out_dir, angle, cell)
            sheet.alpha_composite(panel, (56 + column * cell[0], y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, format="PNG")


def _capture_panel(out_dir: Path, angle: str, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (18, 18, 18, 255))
    candidates = [
        out_dir / "captures" / ANGLE_CAPTURE[angle],
        out_dir / ANGLE_CAPTURE[angle],
        out_dir / f"compare_{angle}.png",
    ]
    image = None
    for candidate in candidates:
        if candidate.exists():
            image = Image.open(candidate).convert("RGBA")
            break
    if image is None:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).text((4, 24), "missing", fill=(255, 90, 90, 255))
    image.thumbnail((size[0] - 10, size[1] - 10), Image.Resampling.NEAREST)
    panel.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return panel


def _write_delta_csv(deltas: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asset", "from_phase", "to_phase", "metric", "from_value", "to_value", "delta"])
        writer.writeheader()
        writer.writerows(deltas)


def _write_summary(config: dict[str, Any], report: dict[str, Any], path: Path) -> None:
    lines = [
        "# SpriteSpatial Visual Benchmark",
        "",
        f"Generated: {report['generated_at']}",
        f"Passed: {report['passed']}",
        f"Reference phase: {config.get('reference_phase', 'phase6b_surface_flow')}",
        f"Reference status: {report['reference_status']}",
        "",
        "## Phase Metrics",
        "",
    ]
    for key, payload in report["metrics"].items():
        metrics = payload["metrics"]
        lines.append(f"### {key}")
        for metric in config.get("metrics", []):
            lines.append(f"- {metric}: {metrics.get(metric)}")
        lines.append("")
    lines.extend(["## Failures", ""])
    if report["failures"]:
        for failure in report["failures"]:
            lines.append(f"- {failure}")
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve(path: Path) -> Path:
    return (path if path.is_absolute() else WORKSPACE_ROOT / path).resolve()


def _workspace_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _substitute(value: str, context: dict[str, str]) -> str:
    result = value
    for key, replacement in context.items():
        result = result.replace("{" + key + "}", replacement)
    return result


def _tail(text: str | None, lines: int = 8) -> str:
    return "\n".join((text or "").splitlines()[-lines:])


def _retryable_build_failure(completed: subprocess.CompletedProcess[str]) -> bool:
    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    retry_markers = (
        "godot_preview_failed",
        "godot_mesh_load_failed",
        "visual_mapping_outputs_missing",
        "Godot",
        "C++ BACKTRACE",
    )
    return any(marker in text for marker in retry_markers)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _view_metric(views: dict[str, Any], view: str, metric: str, fallback: Any = None) -> Any:
    payload = views.get(view, {}) if isinstance(views.get(view, {}), dict) else {}
    return payload.get(metric, fallback)


def _mean_view_metric(views: dict[str, Any], metric: str) -> float | None:
    values = [
        float(payload[metric])
        for payload in views.values()
        if isinstance(payload, dict) and isinstance(payload.get(metric), (int, float))
    ]
    return float(sum(values) / len(values)) if values else None


if __name__ == "__main__":
    raise SystemExit(main())
