from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_ROOT = Path(__file__).resolve().parent.parent / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.embodiment_presets import (
    apply_preset,
    list_presets,
    load_preset_profile,
    semantic_part_graph_from_overrides,
    write_preset_params,
)


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ASSETS_ROOT = WORKSPACE_ROOT / "assets" / "samples"
PRESETS_ROOT = WORKSPACE_ROOT / "profiles" / "embodiment_presets"
OUTPUTS_ROOT = WORKSPACE_ROOT / "outputs"
RUNS_ROOT = OUTPUTS_ROOT / "studio_api" / "runs"


def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "spritespatial-studio-api",
        "version": "0.1",
        "local_only": True,
    }


def list_assets() -> list[dict[str, Any]]:
    assets = []
    for directory in sorted(path for path in ASSETS_ROOT.iterdir() if path.is_dir()):
        asset_path = directory / "spriteasset_v1.json"
        if not asset_path.exists():
            continue
        metadata = _read_json(asset_path)
        sprites = metadata.get("source_sprites", {}) if isinstance(metadata.get("source_sprites", {}), dict) else {}
        assets.append(
            {
                "asset_id": directory.name,
                "path": _rel(asset_path),
                "available_sprites": {
                    key: (directory / str(value)).exists()
                    for key, value in sprites.items()
                },
                "source_coverage": metadata.get("source_coverage", {}),
            }
        )
    return assets


def get_asset(asset_id: str) -> dict[str, Any]:
    asset_dir = _asset_dir(asset_id)
    asset_path = asset_dir / "spriteasset_v1.json"
    metadata = _read_json(asset_path)
    semantic_dir = asset_dir / "semantic_overrides"
    return {
        "asset_id": asset_id,
        "path": _rel(asset_path),
        "metadata": metadata,
        "semantic_override_labels": _semantic_override_labels(semantic_dir),
        "available_params_files": [_rel(path) for path in sorted(asset_dir.glob("embodiment_params*.json"))],
    }


def list_preset_profiles() -> list[dict[str, Any]]:
    profiles = []
    for path in sorted(PRESETS_ROOT.glob("*.json")):
        profile = load_preset_profile(path)
        profiles.append(
            {
                "profile_id": str(profile.get("profile_id", path.stem)),
                "path": _rel(path),
                "display_name": profile.get("display_name", path.stem),
                "preset_ids": [preset["preset_id"] for preset in list_presets(profile)],
            }
        )
    return profiles


def get_preset_profile(profile_id: str) -> dict[str, Any]:
    profile = load_preset_profile(_preset_path(profile_id))
    return {
        "profile_id": profile.get("profile_id", profile_id),
        "display_name": profile.get("display_name", profile_id),
        "description": profile.get("description", ""),
        "path": _rel(Path(str(profile.get("path", "")))),
        "presets": list_presets(profile),
        "raw": _strip_runtime_fields(profile),
    }


def apply_preset_service(
    asset_id: str,
    base_params: str,
    preset_profile: str,
    preset_id: str,
    intensity: float,
    run_diff: bool,
    fast_smoke: bool = False,
) -> dict[str, Any]:
    asset = get_asset(asset_id)
    run_id = _run_id(asset_id, f"{preset_id}_{int(round(float(intensity) * 100)):03d}")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    out_params = run_dir / "edited_params.json"
    base_path = _safe_existing_relative(base_params, ASSETS_ROOT)
    profile_path = _preset_path(preset_profile)
    profile = load_preset_profile(profile_path)
    semantic_overrides = _asset_dir(asset_id) / "semantic_overrides"
    semantic_graph = semantic_part_graph_from_overrides(semantic_overrides)
    applied = apply_preset(
        _read_json(base_path),
        preset_id,
        intensity,
        preset_profile=profile,
        valid_parts={str(part.get("part_id")) for part in semantic_graph.get("parts", []) if isinstance(part, dict)},
    )
    write_preset_params(out_params, applied["params"], applied["report"])
    application_report = {
        **applied["report"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset_id": asset_id,
        "asset": asset,
        "base_params": _rel(base_path),
        "out_params": _rel(out_params),
        "preset_profile": _rel(profile_path),
        "available_parts": [part.get("part_id") for part in semantic_graph.get("parts", [])],
    }
    _write_json(run_dir / "preset_application_report.json", application_report)
    diff_report: dict[str, Any] | None = None
    if run_diff:
        diff_result = run_diff_service(
            asset_id,
            _rel(base_path),
            _rel(out_params),
            "base",
            preset_id,
            out_dir=run_dir,
            fast_smoke=fast_smoke,
        )
        diff_report = diff_result.get("param_diff_report", {})
    return {
        "ok": True,
        "run_id": run_id,
        "out_dir": _rel(run_dir),
        "edited_params_path": _rel(out_params),
        "preset_application_report": application_report,
        "param_diff_report": diff_report,
        "summary_md": _read_text(run_dir / "param_diff_summary.md"),
        "paths": _run_paths(run_dir),
    }


def run_diff_service(
    asset_id: str,
    base_params: str,
    edited_params: str,
    label_base: str = "default",
    label_edited: str = "edited",
    out_dir: Path | None = None,
    fast_smoke: bool = False,
) -> dict[str, Any]:
    asset_dir = _asset_dir(asset_id)
    run_dir = out_dir or (RUNS_ROOT / _run_id(asset_id, f"diff_{label_edited}"))
    run_dir.mkdir(parents=True, exist_ok=True)
    base_path = _safe_existing_relative(base_params, WORKSPACE_ROOT)
    edited_path = _safe_existing_relative(edited_params, WORKSPACE_ROOT)
    if fast_smoke:
        report = _fast_smoke_diff_report(asset_id, base_path, edited_path, label_base, label_edited)
        _write_json(run_dir / "param_diff_report.json", report)
        (run_dir / "param_diff_summary.md").write_text("# Fast Smoke Parameter Diff\n\nMock diff completed for API smoke testing.\n", encoding="utf-8")
        _write_json(run_dir / "changed_parts.json", report.get("changed_parts", {}))
    else:
        command = [
            sys.executable,
            "tools/run_embodiment_param_diff.py",
            "--asset",
            _rel(asset_dir / "spriteasset_v1.json"),
            "--profile",
            "profiles/prototype_32.json",
            "--semantic-overrides",
            _rel(asset_dir / "semantic_overrides"),
            "--base-params",
            _rel(base_path),
            "--edited-params",
            _rel(edited_path),
            "--label-base",
            label_base,
            "--label-edited",
            label_edited,
            "--out",
            _rel(run_dir),
        ]
        completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
        if completed.returncode != 0:
            return {
                "ok": False,
                "out_dir": _rel(run_dir),
                "error": completed.stderr.strip() or completed.stdout.strip(),
                "paths": _run_paths(run_dir),
            }
    return {
        "ok": True,
        "run_id": run_dir.name,
        "out_dir": _rel(run_dir),
        "param_diff_report": _read_json(run_dir / "param_diff_report.json"),
        "summary_md": _read_text(run_dir / "param_diff_summary.md"),
        "paths": _run_paths(run_dir),
    }


def list_runs() -> list[dict[str, Any]]:
    if not RUNS_ROOT.exists():
        return []
    runs = []
    for directory in sorted((path for path in RUNS_ROOT.iterdir() if path.is_dir()), reverse=True):
        runs.append(
            {
                "run_id": directory.name,
                "out_dir": _rel(directory),
                "has_preset_report": (directory / "preset_application_report.json").exists(),
                "has_param_diff_report": (directory / "param_diff_report.json").exists(),
                "created_at": datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc).isoformat(),
            }
        )
    return runs


def get_run(run_id: str) -> dict[str, Any]:
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError("Invalid run_id")
    run_dir = (RUNS_ROOT / run_id).resolve()
    _ensure_under(run_dir, RUNS_ROOT)
    if not run_dir.exists():
        raise FileNotFoundError(run_id)
    return {
        "run_id": run_id,
        "out_dir": _rel(run_dir),
        "preset_application_report": _read_json(run_dir / "preset_application_report.json"),
        "param_diff_report": _read_json(run_dir / "param_diff_report.json"),
        "summary_md": _read_text(run_dir / "param_diff_summary.md"),
        "paths": _run_paths(run_dir),
    }


def _asset_dir(asset_id: str) -> Path:
    if "/" in asset_id or "\\" in asset_id or ".." in asset_id:
        raise ValueError("Invalid asset_id")
    path = (ASSETS_ROOT / asset_id).resolve()
    _ensure_under(path, ASSETS_ROOT)
    if not (path / "spriteasset_v1.json").exists():
        raise FileNotFoundError(asset_id)
    return path


def _preset_path(profile_id: str) -> Path:
    if "/" in profile_id or "\\" in profile_id or ".." in profile_id:
        raise ValueError("Invalid preset_profile")
    name = profile_id if profile_id.endswith(".json") else f"{profile_id}.json"
    path = (PRESETS_ROOT / name).resolve()
    _ensure_under(path, PRESETS_ROOT)
    if not path.exists():
        raise FileNotFoundError(profile_id)
    return path


def _safe_existing_relative(value: str, root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError("Absolute paths are not accepted by API v0.1")
    resolved = (WORKSPACE_ROOT / path).resolve()
    _ensure_under(resolved, root.resolve())
    if not resolved.exists():
        raise FileNotFoundError(value)
    return resolved


def _ensure_under(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes allowed root: {path}") from exc


def _semantic_override_labels(root: Path) -> list[dict[str, Any]]:
    labels = []
    if not root.exists():
        return labels
    for path in sorted(root.glob("*.png")):
        labels.append({"label": path.stem, "path": _rel(path), "nonempty": _alpha_nonempty(path)})
    return labels


def _alpha_nonempty(path: Path) -> bool:
    try:
        from PIL import Image

        image = Image.open(path).convert("RGBA")
        alpha = image.getchannel("A")
        data = alpha.get_flattened_data() if hasattr(alpha, "get_flattened_data") else alpha.getdata()
        return any(int(value) > 16 for value in data)
    except OSError:
        return False


def _fast_smoke_diff_report(asset_id: str, base_path: Path, edited_path: Path, label_base: str, label_edited: str) -> dict[str, Any]:
    return {
        "schema": "spritespatial_embodiment_param_diff_v1",
        "fast_smoke": True,
        "asset_id": asset_id,
        "base": {"label": label_base, "params": _rel(base_path)},
        "edited": {"label": label_edited, "params": _rel(edited_path)},
        "changed_parts": {"schema": "spritespatial_changed_parts_v1", "changed_parts": [], "skipped_parts": []},
        "edit_valid": True,
        "edit_changed_geometry": False,
        "edit_preserved_hard_gates": True,
        "likely_improvement": None,
        "helpful_deltas": [],
        "harmful_deltas": [],
        "neutral_deltas": [],
        "recommended_next_edit": "Fast smoke mode did not run reconstruction.",
    }


def _run_id(asset_id: str, label: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in label)
    return f"{stamp}_{asset_id}_{safe_label}"


def _run_paths(run_dir: Path) -> dict[str, str]:
    names = (
        "edited_params.json",
        "preset_application_report.json",
        "param_diff_report.json",
        "param_diff_summary.md",
        "changed_parts.json",
        "metric_delta_table.csv",
    )
    return {name: _rel(run_dir / name) for name in names if (run_dir / name).exists()}


def _strip_runtime_fields(profile: dict[str, Any]) -> dict[str, Any]:
    result = dict(profile)
    result.pop("preset_by_id", None)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT.resolve()))
    except ValueError:
        return str(path)
