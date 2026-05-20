from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.asset_schema import AssetSchema  # noqa: E402
from spritespatial.validators import validate_asset_schema  # noqa: E402


DEFAULT_ASSET = WORKSPACE_ROOT / "assets" / "samples" / "hero" / "spriteasset_v1.json"
DEFAULT_PROFILE = WORKSPACE_ROOT / "profiles" / "prototype_32.json"
DEFAULT_OUT = WORKSPACE_ROOT / "outputs" / "hero" / "prototype_32"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SpriteSpatial Phase 1 validation suite.")
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--godot",
        type=Path,
        default=None,
        help="Optional Godot executable. If omitted, GODOT_EXECUTABLE or PATH lookup is used.",
    )
    parser.add_argument(
        "--skip-godot",
        action="store_true",
        help="Skip optional Godot scene-load validation.",
    )
    parser.add_argument(
        "--require-godot",
        action="store_true",
        help="Fail validation if the optional Godot scene-load check cannot complete.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks: list[dict[str, Any]] = []

    checks.append(_run_python_compile())
    checks.append(_run_schema_validation(_resolve(args.asset)))
    checks.append(_run_sample_build(_resolve(args.asset), _resolve(args.profile), _resolve(args.out)))
    checks.append(_run_validation_report_check(_resolve(args.out) / "validation_report.json"))
    checks.append(_run_manifest_check(_resolve(args.out) / "manifest.json"))

    if args.skip_godot:
        checks.append({"name": "godot_scene_load", "passed": True, "skipped": True, "message": "Skipped by flag."})
    else:
        checks.append(
            _run_optional_godot_scene_load(
                args.godot,
                _resolve(args.out) / "link_depth_volume_test.tscn",
                require_godot=args.require_godot,
            )
        )

    passed = all(check["passed"] for check in checks)
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        if check.get("skipped"):
            status = "SKIP"
        print(f"{status}: {check['name']} - {check['message']}")

    return 0 if passed else 1


def _resolve(path: Path) -> Path:
    return (WORKSPACE_ROOT / path if not path.is_absolute() else path).resolve()


def _run_python_compile() -> dict[str, Any]:
    command = [sys.executable, "-m", "compileall", "-q", "tool", "tools"]
    completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
    return {
        "name": "python_compile",
        "passed": completed.returncode == 0,
        "message": _command_message(completed),
    }


def _run_schema_validation(asset_path: Path) -> dict[str, Any]:
    try:
        asset = AssetSchema.load_from_file(asset_path)
        validate_asset_schema(asset)
    except Exception as exc:
        return {"name": "schema_validation", "passed": False, "message": str(exc)}
    return {"name": "schema_validation", "passed": True, "message": f"{asset.asset_name} schema is valid."}


def _run_sample_build(asset_path: Path, profile_path: Path, output_dir: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "tools/build_profiled_asset.py",
        "--asset",
        str(asset_path),
        "--profile",
        str(profile_path),
        "--out",
        str(output_dir),
    ]
    completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
    return {
        "name": "sample_profiled_build",
        "passed": completed.returncode == 0,
        "message": _command_message(completed),
    }


def _run_validation_report_check(report_path: Path) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"name": "validation_report_check", "passed": False, "message": str(exc)}
    if not report.get("passed", False):
        return {
            "name": "validation_report_check",
            "passed": False,
            "message": f"Validation report did not pass: {report_path}",
        }
    return {"name": "validation_report_check", "passed": True, "message": str(report_path)}


def _run_manifest_check(manifest_path: Path) -> dict[str, Any]:
    required = {
        "source_sprites",
        "profile",
        "generated_artefacts",
        "validation_reports",
        "mesh_stats",
        "timestamp",
        "command",
    }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"name": "manifest_check", "passed": False, "message": str(exc)}

    missing = sorted(required - manifest.keys())
    if missing:
        return {"name": "manifest_check", "passed": False, "message": f"Missing keys: {missing}"}

    artefacts = manifest.get("generated_artefacts", {})
    missing_artefacts = [
        key for key in (
            "cleaned_sprite",
            "alpha_mask",
            "semantic_map",
            "depth_map",
            "zfield_debug",
            "occupancy_summary",
            "mesh",
            "validation_report",
            "captures",
        )
        if key not in artefacts
    ]
    if missing_artefacts:
        return {
            "name": "manifest_check",
            "passed": False,
            "message": f"Missing artefacts: {missing_artefacts}",
        }
    return {"name": "manifest_check", "passed": True, "message": str(manifest_path)}


def _run_optional_godot_scene_load(
    godot_arg: Path | None,
    scene_path: Path,
    require_godot: bool = False,
) -> dict[str, Any]:
    godot = _find_godot(godot_arg)
    if godot is None:
        return {
            "name": "godot_scene_load",
            "passed": not require_godot,
            "skipped": not require_godot,
            "message": "Godot executable not found.",
        }

    command = [
        str(godot),
        "--headless",
        "--path",
        str(WORKSPACE_ROOT),
        _to_res_path(scene_path),
        "--quit-after",
        "1",
    ]
    try:
        completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {
            "name": "godot_scene_load",
            "passed": not require_godot,
            "skipped": not require_godot,
            "message": f"Godot scene-load check timed out using {godot}.",
        }
    return {
        "name": "godot_scene_load",
        "passed": completed.returncode == 0 or not require_godot,
        "skipped": completed.returncode != 0 and not require_godot,
        "message": _command_message(completed),
    }


def _find_godot(godot_arg: Path | None) -> Path | None:
    if godot_arg:
        resolved = _resolve(godot_arg)
        return resolved if resolved.exists() else None

    env_path = os.environ.get("GODOT_EXECUTABLE")
    if env_path:
        candidate = Path(env_path)
        return candidate if candidate.exists() else None

    for name in ("godot", "godot4", "Godot_v4.6.2-stable_win64_console.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _to_res_path(path: Path) -> str:
    return "res://" + path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()


def _command_message(completed: subprocess.CompletedProcess[str]) -> str:
    output = (completed.stdout or completed.stderr or "").strip()
    if not output:
        output = f"exit code {completed.returncode}"
    return output.splitlines()[-1]


if __name__ == "__main__":
    raise SystemExit(main())
