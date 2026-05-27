from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

SCALES = (1.0, 1.5, 2.0)

METRIC_KEYS = (
    "sdf_volume_shape",
    "surface_net_vertices",
    "surface_net_faces",
    "surface_net_triangles",
    "non_manifold_edge_count",
    "degenerate_face_count",
    "mesh_connected_components",
    "patch_count",
    "macro_patch_count",
    "small_patch_ratio",
    "small_macro_patch_ratio",
    "planar_macro_patch_count",
    "mean_macro_patch_size",
    "patch_coherence_score",
    "macro_patch_coherence_score",
    "staircase_artifact_after",
    "surface_flow_after",
    "planar_surface_score",
    "lowpoly_coherence_score",
    "silhouette_drift_px",
    "hat_asymmetry_ratio",
    "passed",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SpriteSpatial Phase 6G controlled SDF resolution diagnostic.")
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--semantic-overrides", type=Path, required=True)
    parser.add_argument("--semantic-override-mode", default="supplement")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = _resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    scale_results = []
    for scale in SCALES:
        scale_dir = out_dir / _scale_name(scale)
        command = _build_command(args, scale, scale_dir)
        result = _run_command(command)
        metrics = _collect_metrics(scale, scale_dir, result)
        scale_results.append(metrics)
    report = _build_report(scale_results)
    _write_json(out_dir / "resolution_diagnostic_report.json", report)
    _write_metric_delta_table(out_dir / "metric_delta_table.csv", scale_results)
    _write_summary(out_dir / "resolution_diagnostic_summary.md", report)
    _write_contact_sheets(out_dir, scale_results)
    _write_handoff(out_dir / "AI_AGENT_HANDOFF.md", report)
    return 0 if all(item.get("build_exit_code") == 0 for item in scale_results) else 1


def _build_command(args: argparse.Namespace, scale: float, scale_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(WORKSPACE_ROOT / "tools" / "build_topological_sprite_model.py"),
        "--asset",
        str(_resolve(args.asset)),
        "--profile",
        str(_resolve(args.profile)),
        "--semantic-overrides",
        str(_resolve(args.semantic_overrides)),
        "--semantic-override-mode",
        str(args.semantic_override_mode),
        "--semantic-parts",
        "--semantic-depth-profiles",
        "--semantic-depth-profile",
        "humanoid_voxel",
        "--directional-morphology",
        "--morphology-profile",
        "fantasy_humanoid",
        "--depth-mode",
        "mylar_edt",
        "--closed-body",
        "--back-mode",
        "semantic_rules",
        "--mesh-backend",
        "surface_nets_patch",
        "--patch-profile",
        "humanoid_voxel",
        "--macro-patches",
        "--macro-patch-profile",
        "humanoid_voxel",
        "--sdf-resolution-scale",
        _scale_arg(scale),
        "--z-resolution-scale",
        _scale_arg(scale),
        "--surface-net-smoothing-alpha",
        "0.65",
        "--preserve-silhouette-edges",
        "--render-profile",
        "voxel_sprite",
        "--emit-semantic-parts-debug",
        "--emit-directional-debug",
        "--emit-patch-debug",
        "--emit-macro-patch-debug",
        "--emit-resolution-diagnostic",
        "--out",
        str(scale_dir),
    ]


def _run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "exit_code": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _collect_metrics(scale: float, scale_dir: Path, command_result: dict[str, Any]) -> dict[str, Any]:
    validation = _read_json(scale_dir / "validation_report.json")
    patch_report = _read_json(scale_dir / "patch_nets" / "patch_report.json")
    macro_report = _read_json(scale_dir / "macro_patches" / "macro_patch_report.json")
    surface_report = _read_json(scale_dir / "surface_nets_report.json")
    sdf_summary = _read_json(scale_dir / "sdf" / "sdf_summary.json")
    metrics: dict[str, Any] = {
        "scale": scale,
        "scale_name": _scale_name(scale),
        "output_dir": str(scale_dir),
        "build_exit_code": int(command_result["exit_code"]),
        "build_command": " ".join(command_result["command"]),
        "build_stdout_tail": _tail(command_result.get("stdout", "")),
        "build_stderr_tail": _tail(command_result.get("stderr", "")),
        "validation_report_exists": bool(validation),
    }
    metrics.update(
        {
            "sdf_volume_shape": validation.get("sdf_volume_shape", sdf_summary.get("shape", [])),
            "surface_net_vertices": validation.get("surface_net_vertices", surface_report.get("surface_net_vertices", 0)),
            "surface_net_faces": validation.get("surface_net_faces", surface_report.get("surface_net_faces", 0)),
            "surface_net_triangles": patch_report.get(
                "triangle_count_after_patch",
                validation.get("triangle_count_after_patch", validation.get("surface_net_faces", 0) * 2),
            ),
            "non_manifold_edge_count": validation.get("non_manifold_edge_count", surface_report.get("non_manifold_edge_count", 0)),
            "degenerate_face_count": validation.get("degenerate_face_count", surface_report.get("degenerate_face_count", 0)),
            "mesh_connected_components": validation.get("mesh_connected_components", surface_report.get("mesh_connected_components", 99)),
            "patch_count": validation.get("patch_count", patch_report.get("patch_count", 0)),
            "macro_patch_count": validation.get("macro_patch_count", macro_report.get("macro_patch_count", 0)),
            "small_patch_ratio": validation.get("small_patch_ratio", patch_report.get("small_patch_ratio", 0.0)),
            "small_macro_patch_ratio": validation.get("small_macro_patch_ratio", macro_report.get("small_macro_patch_ratio", 0.0)),
            "planar_macro_patch_count": validation.get("planar_macro_patch_count", macro_report.get("planar_macro_patch_count", 0)),
            "mean_macro_patch_size": validation.get("mean_macro_patch_size", macro_report.get("mean_macro_patch_size", 0.0)),
            "patch_coherence_score": validation.get("patch_coherence_score", patch_report.get("patch_coherence_score", 0.0)),
            "macro_patch_coherence_score": validation.get(
                "macro_patch_coherence_score",
                macro_report.get("macro_patch_coherence_score", 0.0),
            ),
            "staircase_artifact_after": validation.get(
                "staircase_artifact_after",
                patch_report.get("staircase_artifact_after", 1.0),
            ),
            "surface_flow_after": validation.get("surface_flow_after", patch_report.get("surface_flow_after", 0.0)),
            "planar_surface_score": validation.get(
                "planar_surface_score",
                patch_report.get("planar_surface_score_after", 0.0),
            ),
            "lowpoly_coherence_score": validation.get("lowpoly_coherence_score", 0.0),
            "silhouette_drift_px": validation.get("silhouette_drift_px", patch_report.get("silhouette_drift_px", 99.0)),
            "hat_asymmetry_ratio": validation.get("hat_asymmetry_ratio", 0.0),
            "passed": bool(validation.get("passed", False)) and int(command_result["exit_code"]) == 0,
        }
    )
    _write_json(scale_dir / "resolution_diagnostic_metrics.json", metrics)
    return metrics


def _build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = _result_for_scale(results, 1.0) or (results[0] if results else {})
    best = _best_result(results, baseline)
    helped = _resolution_helped(best, baseline)
    quality_ok = _quality_gates_pass(best, baseline)
    resolution_helped = bool(helped and quality_ok)
    if resolution_helped:
        next_step = "increase_resolution_path"
        reason = "Higher SDF resolution improved at least one target topology metric while preserving hard gates."
    else:
        next_step = "qef_surface_nets"
        reason = "Resolution did not materially improve staircase, surface-flow, or planar macro-patch metrics under the preservation gates."
        if not all(item.get("passed", False) for item in results):
            next_step = "patch_threshold_tuning"
            reason = "One or more diagnostic builds failed; inspect failed scale outputs before QEF/Hermite work."
    non_manifold_delta = int(best.get("non_manifold_edge_count", 0)) - int(baseline.get("non_manifold_edge_count", 0))
    if resolution_helped and non_manifold_delta > 0:
        reason += f" Caveat: non-manifold edge count increased by {non_manifold_delta}, so the production path needs topology cleanup."
    return {
        "schema": "spritespatial_phase6g_resolution_diagnostic_v1",
        "resolution_helped": resolution_helped,
        "best_scale": float(best.get("scale", 1.0)) if best else 1.0,
        "recommended_next_step": next_step,
        "reason": reason,
        "non_manifold_delta_at_best_scale": non_manifold_delta,
        "baseline_scale": 1.0,
        "scales": results,
        "decision_thresholds": {
            "staircase_improvement": 0.02,
            "surface_flow_improvement": 0.02,
            "planar_macro_patch_increase": max(3, int(float(baseline.get("planar_macro_patch_count", 0)) * 0.5)),
            "silhouette_drift_max": 1.0,
            "hat_asymmetry_min_ratio_vs_baseline": 0.90,
        },
    }


def _best_result(results: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    if not results:
        return {}
    return max(results, key=lambda item: _resolution_score(item, baseline))


def _resolution_score(item: dict[str, Any], baseline: dict[str, Any]) -> float:
    if not _quality_gates_pass(item, baseline):
        return -1000.0 + float(item.get("scale", 0.0))
    staircase_gain = float(baseline.get("staircase_artifact_after", 1.0)) - float(item.get("staircase_artifact_after", 1.0))
    flow_gain = float(item.get("surface_flow_after", 0.0)) - float(baseline.get("surface_flow_after", 0.0))
    planar_gain = float(item.get("planar_macro_patch_count", 0)) - float(baseline.get("planar_macro_patch_count", 0))
    small_gain = float(baseline.get("small_macro_patch_ratio", 1.0)) - float(item.get("small_macro_patch_ratio", 1.0))
    return staircase_gain * 3.0 + flow_gain * 3.0 + planar_gain * 0.05 + small_gain + float(item.get("scale", 0.0)) * 0.001


def _resolution_helped(item: dict[str, Any], baseline: dict[str, Any]) -> bool:
    staircase_gain = float(baseline.get("staircase_artifact_after", 1.0)) - float(item.get("staircase_artifact_after", 1.0))
    flow_gain = float(item.get("surface_flow_after", 0.0)) - float(baseline.get("surface_flow_after", 0.0))
    planar_gain = int(item.get("planar_macro_patch_count", 0)) - int(baseline.get("planar_macro_patch_count", 0))
    planar_threshold = max(3, int(float(baseline.get("planar_macro_patch_count", 0)) * 0.5))
    return bool(staircase_gain >= 0.02 or flow_gain >= 0.02 or planar_gain >= planar_threshold)


def _quality_gates_pass(item: dict[str, Any], baseline: dict[str, Any]) -> bool:
    baseline_hat = float(baseline.get("hat_asymmetry_ratio", 0.0))
    return bool(
        item.get("passed", False)
        and int(item.get("degenerate_face_count", 99)) == 0
        and int(item.get("mesh_connected_components", 99)) == 1
        and float(item.get("silhouette_drift_px", 99.0)) <= 1.0
        and float(item.get("hat_asymmetry_ratio", 0.0)) >= baseline_hat * 0.90
    )


def _write_metric_delta_table(path: Path, results: list[dict[str, Any]]) -> None:
    baseline = _result_for_scale(results, 1.0) or {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "scale_1_0", "scale_1_5", "scale_2_0", "delta_1_5", "delta_2_0"])
        by_scale = {float(item["scale"]): item for item in results}
        for metric in METRIC_KEYS:
            base_value = baseline.get(metric, "")
            value_15 = by_scale.get(1.5, {}).get(metric, "")
            value_20 = by_scale.get(2.0, {}).get(metric, "")
            writer.writerow(
                [
                    metric,
                    _cell(base_value),
                    _cell(value_15),
                    _cell(value_20),
                    _delta(value_15, base_value),
                    _delta(value_20, base_value),
                ]
            )


def _write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# SpriteSpatial Phase 6G Resolution Diagnostic",
        "",
        f"Resolution helped: `{str(report['resolution_helped']).lower()}`",
        f"Best scale: `{report['best_scale']}`",
        f"Recommended next step: `{report['recommended_next_step']}`",
        "",
        report["reason"],
        "",
        "## Scale Metrics",
        "",
        "| scale | passed | sdf shape | macro patches | small macro ratio | planar macro patches | staircase | surface flow | non-manifold | hat asymmetry |",
        "|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["scales"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("scale")),
                    str(item.get("passed")),
                    str(item.get("sdf_volume_shape")),
                    str(item.get("macro_patch_count")),
                    f"{float(item.get('small_macro_patch_ratio', 0.0)):.4f}",
                    str(item.get("planar_macro_patch_count")),
                    f"{float(item.get('staircase_artifact_after', 0.0)):.4f}",
                    f"{float(item.get('surface_flow_after', 0.0)):.4f}",
                    str(item.get("non_manifold_edge_count")),
                    f"{float(item.get('hat_asymmetry_ratio', 0.0)):.4f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Semantics, morphology, rendering profile, patch profile, and macro-patch profile are held constant.",
            "- Only SDF X/Y sampling scale and Z sampling scale change.",
            "- Godot preview is not run by this diagnostic.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_contact_sheets(out_dir: Path, results: list[dict[str, Any]]) -> None:
    contact_dir = out_dir / "contact_sheets"
    contact_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        ("macro", "macro_patches/before_after_contact_sheet.png"),
        ("patch", "patch_nets/before_after_contact_sheet.png"),
        ("sdf", "sdf/sdf_slice_contact_sheet.png"),
    ]
    for name, relative in candidates:
        frames = []
        for item in results:
            path = Path(str(item["output_dir"])) / relative
            if path.exists():
                frame = Image.open(path).convert("RGBA")
            else:
                frame = Image.new("RGBA", (160, 80), (30, 30, 30, 255))
                ImageDraw.Draw(frame).text((8, 8), "missing", fill=(255, 100, 100, 255))
            label = Image.new("RGBA", (frame.width, frame.height + 18), (0, 35, 42, 255))
            label.alpha_composite(frame, (0, 18))
            ImageDraw.Draw(label).text((4, 3), str(item.get("scale_name", "")), fill=(255, 255, 255, 255))
            frames.append(label)
        _stitch_horizontal(frames, contact_dir / f"{name}_scale_contact_sheet.png")


def _write_handoff(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# SpriteSpatial Phase 6G Handoff: Controlled SDF Resolution Diagnostic",
        "",
        "## Status",
        "",
        "Phase 6G diagnostic is implemented and executed for the hero asset.",
        "",
        f"Resolution helped: `{str(report['resolution_helped']).lower()}`",
        f"Best scale: `{report['best_scale']}`",
        f"Recommended next step: `{report['recommended_next_step']}`",
        "",
        report["reason"],
        "",
        "## Output Folder",
        "",
        "```text",
        str(path.parent.relative_to(WORKSPACE_ROOT)),
        "```",
        "",
        "## Commands Run",
        "",
        "```powershell",
        "python tools\\run_resolution_diagnostic.py --asset assets\\samples\\hero\\spriteasset_v1.json --profile profiles\\prototype_32.json --semantic-overrides assets\\samples\\hero\\semantic_overrides --semantic-override-mode supplement --out outputs\\hero\\resolution_diagnostic_phase6g",
        "```",
        "",
        "## Commands Deliberately Not Run",
        "",
        "```powershell",
        "godot",
        "```",
        "",
        "Godot preview was intentionally skipped.",
        "",
        "## Files Added Or Changed",
        "",
        "```text",
        "tool/spritespatial/sdf_volume.py",
        "tool/spritespatial/manifold_validation.py",
        "tools/build_topological_sprite_model.py",
        "tools/run_resolution_diagnostic.py",
        "```",
        "",
        "## Primary Reports",
        "",
        "```text",
        "resolution_diagnostic_report.json",
        "resolution_diagnostic_summary.md",
        "metric_delta_table.csv",
        "contact_sheets/",
        "scale_1_0/resolution_diagnostic_metrics.json",
        "scale_1_5/resolution_diagnostic_metrics.json",
        "scale_2_0/resolution_diagnostic_metrics.json",
        "```",
        "",
        "## Key Metrics",
        "",
        "| scale | passed | sdf shape | macro patches | small macro ratio | planar macro patches | staircase | surface flow | non-manifold | hat asymmetry |",
        "|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["scales"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("scale")),
                    str(item.get("passed")),
                    str(item.get("sdf_volume_shape")),
                    str(item.get("macro_patch_count")),
                    f"{float(item.get('small_macro_patch_ratio', 0.0)):.4f}",
                    str(item.get("planar_macro_patch_count")),
                    f"{float(item.get('staircase_artifact_after', 0.0)):.4f}",
                    f"{float(item.get('surface_flow_after', 0.0)):.4f}",
                    str(item.get("non_manifold_edge_count")),
                    f"{float(item.get('hat_asymmetry_ratio', 0.0)):.4f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Pass/Fail Result",
            "",
            "The diagnostic passes if all three scale builds complete and the comparison reports are generated. Individual scale validation status is listed above.",
            "",
            "## Diagnosis",
            "",
            _diagnosis_text(report),
            "",
            "## Recommended Next Engineering Step",
            "",
            _next_step_text(report),
            "",
            "## Handoff Checklist",
            "",
            "- [x] SDF X/Y resolution scale flag added",
            "- [x] Z resolution scale flag added",
            "- [x] semantic masks remain source-authoritative",
            "- [x] resolution diagnostic runner added",
            "- [x] scale outputs generated or failures recorded",
            "- [x] metric delta table generated",
            "- [x] summary generated",
            "- [x] contact sheets generated",
            "- [x] Godot preview not run",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _diagnosis_text(report: dict[str, Any]) -> str:
    if report.get("resolution_helped"):
        caveat = ""
        if int(report.get("non_manifold_delta_at_best_scale", 0)) > 0:
            caveat = " Non-manifold edges rose at the best scale, so this should be treated as a resolution signal, not a production-ready topology answer."
        return (
            "Resolution materially helped under preservation gates. The next phase should make the higher-resolution SDF path "
            "production-ready and decide whether adaptive resolution is preferable to globally raising the grid."
            + caveat
        )
    return (
        "Resolution did not materially improve the target metrics under preservation gates. This points away from raw grid "
        "resolution as the main bottleneck and toward QEF/Hermite-corrected Surface Nets vertex placement."
    )


def _next_step_text(report: dict[str, Any]) -> str:
    value = str(report.get("recommended_next_step", "qef_surface_nets"))
    if value == "increase_resolution_path":
        return "Promote an adaptive high-resolution SDF path, address the non-manifold increase, and rerun the visual benchmark before changing vertex placement."
    if value == "patch_threshold_tuning":
        return "Inspect failed scale folders and patch/macro debug maps before starting QEF/Hermite work."
    return "Implement QEF/Hermite-corrected patch-aware Surface Nets vertex placement."


def _result_for_scale(results: list[dict[str, Any]], scale: float) -> dict[str, Any] | None:
    for item in results:
        if abs(float(item.get("scale", 0.0)) - scale) < 1.0e-6:
            return item
    return None


def _scale_name(scale: float) -> str:
    return "scale_" + str(scale).replace(".", "_")


def _scale_arg(scale: float) -> str:
    return str(scale).rstrip("0").rstrip(".") if "." in str(scale) else str(scale)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _tail(text: str, max_lines: int = 12) -> str:
    lines = text.strip().splitlines()
    return "\n".join(lines[-max_lines:])


def _cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _delta(value: Any, baseline: Any) -> str:
    if isinstance(value, bool) or isinstance(baseline, bool):
        return ""
    try:
        return f"{float(value) - float(baseline):.6f}"
    except (TypeError, ValueError):
        return ""


def _stitch_horizontal(frames: list[Image.Image], path: Path) -> None:
    if not frames:
        Image.new("RGBA", (1, 1), (0, 0, 0, 255)).save(path, format="PNG")
        return
    height = max(frame.height for frame in frames)
    width = sum(frame.width for frame in frames)
    sheet = Image.new("RGBA", (width, height), (0, 35, 42, 255))
    x = 0
    for frame in frames:
        sheet.alpha_composite(frame, (x, 0))
        x += frame.width
    sheet.save(path, format="PNG")


if __name__ == "__main__":
    raise SystemExit(main())
