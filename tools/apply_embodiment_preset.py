from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.embodiment_presets import (  # noqa: E402
    apply_preset,
    list_presets,
    load_preset_profile,
    semantic_part_graph_from_overrides,
    write_preset_params,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a named SpriteSpatial embodiment preset.")
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=Path("profiles/prototype_32.json"))
    parser.add_argument("--semantic-overrides", type=Path, required=True)
    parser.add_argument("--base-params", type=Path, required=True)
    parser.add_argument("--preset-profile", type=Path, required=True)
    parser.add_argument("--preset-id", required=True)
    parser.add_argument("--intensity", type=float, default=1.0)
    parser.add_argument("--out-params", type=Path, required=True)
    parser.add_argument("--run-diff", action="store_true")
    parser.add_argument("--diff-out", type=Path)
    parser.add_argument("--list-presets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = load_preset_profile(_resolve(args.preset_profile))
    if args.list_presets:
        print(json.dumps(list_presets(profile), indent=2))
        return 0
    base_params = _read_json(_resolve(args.base_params))
    semantic_graph = semantic_part_graph_from_overrides(_resolve(args.semantic_overrides))
    applied = apply_preset(
        base_params,
        args.preset_id,
        args.intensity,
        preset_profile=profile,
        valid_parts={str(part.get("part_id")) for part in semantic_graph.get("parts", []) if isinstance(part, dict)},
    )
    out_params = _resolve(args.out_params)
    write_preset_params(out_params, applied["params"], applied["report"])
    report_dir = _resolve(args.diff_out) if args.diff_out else out_params.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "preset_application_report.json"
    _write_json(report_path, _application_report(args, profile, semantic_graph, applied, out_params))

    diff_result: dict[str, Any] = {"run": False}
    if args.run_diff:
        diff_result = _run_diff(args, out_params, report_dir)
        if diff_result.get("exit_code", 1) != 0:
            _write_handoff(report_dir / "AI_AGENT_HANDOFF.md", applied["report"], diff_result, failed=True)
            return int(diff_result.get("exit_code", 1) or 1)

    _write_handoff(report_dir / "AI_AGENT_HANDOFF.md", applied["report"], diff_result, failed=False)
    print(f"Edited params: {out_params}")
    print(f"Preset application report: {report_path}")
    if args.run_diff:
        print(f"Diff report: {report_dir / 'param_diff_report.json'}")
    return 0


def _application_report(
    args: argparse.Namespace,
    profile: dict[str, Any],
    semantic_graph: dict[str, Any],
    applied: dict[str, Any],
    out_params: Path,
) -> dict[str, Any]:
    return {
        **applied["report"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": str(_resolve(args.asset)),
        "semantic_overrides": str(_resolve(args.semantic_overrides)),
        "base_params": str(_resolve(args.base_params)),
        "out_params": str(out_params),
        "preset_profile": str(_resolve(args.preset_profile)),
        "preset_profile_id": profile.get("profile_id", ""),
        "available_parts": [part.get("part_id") for part in semantic_graph.get("parts", [])],
    }


def _run_diff(args: argparse.Namespace, out_params: Path, report_dir: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "tools/run_embodiment_param_diff.py",
        "--asset",
        _workspace_relative(_resolve(args.asset)),
        "--profile",
        _workspace_relative(_resolve(args.profile)),
        "--semantic-overrides",
        _workspace_relative(_resolve(args.semantic_overrides)),
        "--base-params",
        _workspace_relative(_resolve(args.base_params)),
        "--edited-params",
        _workspace_relative(out_params),
        "--label-base",
        "base",
        "--label-edited",
        str(args.preset_id),
        "--out",
        _workspace_relative(report_dir),
    ]
    completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
    return {
        "run": True,
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _write_handoff(path: Path, preset_report: dict[str, Any], diff_result: dict[str, Any], failed: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    param_diff = _read_json(path.parent / "param_diff_report.json")
    lines = [
        "# SpriteSpatial Phase 8C Handoff: Embodiment Presets + Preset Diff Runner",
        "",
        "## Status",
        "",
        "Phase 8C preset application completed." if not failed else "Phase 8C preset application failed during diff execution.",
        "",
        "## Preset",
        "",
        f"preset_id: {preset_report.get('preset_id')}",
        f"intensity: {preset_report.get('intensity')}",
        f"target_parts: {preset_report.get('target_parts')}",
        f"applied_parts: {preset_report.get('applied_parts')}",
        f"skipped_parts: {preset_report.get('skipped_parts')}",
        "",
        "## Outputs",
        "",
        "```text",
        "edited_params.json",
        "preset_application_report.json",
        "param_diff_report.json",
        "param_diff_summary.md",
        "changed_parts.json",
        "metric_delta_table.csv",
        "AI_AGENT_HANDOFF.md",
        "```",
        "",
        "## Diff Result",
        "",
        f"run_diff: {diff_result.get('run', False)}",
        f"diff_exit_code: {diff_result.get('exit_code')}",
        f"edit_valid: {param_diff.get('edit_valid')}",
        f"edit_changed_geometry: {param_diff.get('edit_changed_geometry')}",
        f"likely_improvement: {param_diff.get('likely_improvement')}",
        "",
        "## Verification",
        "",
        "Run after this phase:",
        "",
        "```powershell",
        "python tools\\validate_project.py --skip-godot",
        "python -m unittest test_build_topological_sprite_model.py",
        "```",
        "",
        "Godot and API visual judge were not run by this preset runner.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def _workspace_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT.resolve()))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _tail(text: str, lines: int = 8) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


if __name__ == "__main__":
    raise SystemExit(main())
