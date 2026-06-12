from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from io import BytesIO
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
RAW_ROOT = WORKSPACE_ROOT / "assets" / "raw"
PRESETS_ROOT = WORKSPACE_ROOT / "profiles" / "embodiment_presets"
OUTPUTS_ROOT = WORKSPACE_ROOT / "outputs"
RUNS_ROOT = OUTPUTS_ROOT / "studio_api" / "runs"
JOBS_ROOT = OUTPUTS_ROOT / "studio_api" / "jobs"
STUDIO_BUILDS_ROOT = OUTPUTS_ROOT / "studio_builds"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SERVE_EXTENSIONS = IMAGE_EXTENSIONS | {".json"}
FILE_SERVE_ROOTS = (RAW_ROOT, ASSETS_ROOT, OUTPUTS_ROOT)
SEMANTIC_OVERRIDE_LABELS = (
    "outline",
    "head",
    "face",
    "hat_hair",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "boots_feet",
    "equipment",
)
EMBODIMENT_PARAM_PARTS = (
    "hair/hat",
    "head",
    "face",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "boots/feet",
    "equipment/shield/sword",
)


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
        sprite_names = {
            **sprites,
            "side": "side.png",
        }
        assets.append(
            {
                "asset_id": directory.name,
                "path": _rel(asset_path),
                "available_sprites": {
                    key: (directory / str(value)).exists()
                    for key, value in sprite_names.items()
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


def rename_asset_service(asset_id: str, new_asset_id: str) -> dict[str, Any]:
    old_id = _safe_new_asset_id(asset_id)
    new_id = _safe_new_asset_id(new_asset_id)
    if old_id == new_id:
        return {"ok": True, "asset": get_asset(old_id)}
    source_dir = _asset_dir(old_id)
    target_dir = (ASSETS_ROOT / new_id).resolve()
    _ensure_under(target_dir, ASSETS_ROOT)
    if target_dir.exists():
        raise FileExistsError(f"Asset already exists: {new_id}")
    shutil.move(str(source_dir), str(target_dir))
    _rewrite_asset_identity(target_dir, old_id, new_id)
    return {"ok": True, "asset": get_asset(new_id)}


def delete_asset_service(asset_id: str) -> dict[str, Any]:
    safe_id = _safe_new_asset_id(asset_id)
    asset_dir = _asset_dir(safe_id)
    _ensure_under(asset_dir, ASSETS_ROOT)
    shutil.rmtree(asset_dir)
    return {"ok": True, "asset_id": safe_id}


def list_raw_sheets() -> list[dict[str, Any]]:
    sheets = []
    if not RAW_ROOT.exists():
        return sheets
    for path in sorted(path for path in RAW_ROOT.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS):
        sheets.append(_raw_sheet_record(path))
    return sheets


def upload_raw_sheet_service(filename: str, content: bytes) -> dict[str, Any]:
    if not content:
        raise ValueError("Uploaded sheet is empty.")
    safe_name = _safe_upload_filename(filename)
    target = _unique_raw_sheet_path(safe_name)
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        with Image.open(BytesIO(content)) as image:
            image.verify()
    except OSError as exc:
        raise ValueError("Uploaded sheet must be a readable image.") from exc
    target.write_bytes(content)
    return {
        "ok": True,
        "sheet": _raw_sheet_record(target),
    }


def file_response_path(relative_path: str) -> Path:
    path = _safe_existing_file(relative_path, FILE_SERVE_ROOTS)
    if path.suffix.lower() not in SERVE_EXTENSIONS:
        raise ValueError(f"Unsupported file extension for serving: {path.suffix}")
    return path


def extract_view_candidates_service(
    sheet_path: str,
    asset_id: str,
    max_candidates: int = 320,
    ai_rank: bool = False,
) -> dict[str, Any]:
    sheet = _safe_existing_file(sheet_path, (RAW_ROOT,))
    safe_asset_id = _safe_identifier(asset_id, "asset_id")
    asset_schema = _candidate_asset_schema(safe_asset_id)
    run_dir = OUTPUTS_ROOT / safe_asset_id / "view_candidates" / _run_id(safe_asset_id, "sheet_candidates")
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "tools/find_view_candidates.py",
        "--asset",
        _rel(asset_schema),
        "--sheet",
        _rel(sheet),
        "--out",
        _rel(run_dir),
        "--max-candidates",
        str(int(max_candidates)),
    ]
    if ai_rank:
        command.append("--ai-rank")
    completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Candidate extraction failed.")
    report_path = run_dir / "candidate_report.json"
    report = _read_json(report_path)
    candidates = [
        _normalize_candidate_record(record)
        for record in report.get("candidates", [])
        if isinstance(record, dict)
    ]
    contact_sheet = _path_value_to_rel(report.get("candidate_contact_sheet"), run_dir / "candidate_contact_sheet.png")
    normalized_report = dict(report)
    normalized_report["asset"] = _rel(asset_schema)
    normalized_report["sheet"] = _rel(sheet)
    normalized_report["candidate_dir"] = _path_value_to_rel(report.get("candidate_dir"), run_dir / "candidates")
    normalized_report["candidate_contact_sheet"] = contact_sheet
    normalized_report["candidates"] = candidates
    return {
        "ok": True,
        "run_id": run_dir.name,
        "out_dir": _rel(run_dir),
        "asset_schema_used": _rel(asset_schema),
        "candidate_report": normalized_report,
        "candidate_contact_sheet": contact_sheet,
        "candidates": candidates,
        "stdout": completed.stdout.strip(),
    }


def create_asset_from_candidates_service(
    asset_id: str,
    candidate_run_dir: str,
    selection_version: str,
    mode: str,
    selection: dict[str, int | None],
    source_coverage: dict[str, str] | None = None,
) -> dict[str, Any]:
    safe_asset_id = _safe_new_asset_id(asset_id)
    selection_mode = _safe_selection_mode(mode)
    if selection_version != "view_selection_v1":
        raise ValueError("selection_version must be view_selection_v1")
    run_dir = _safe_existing_dir(candidate_run_dir, (OUTPUTS_ROOT,))
    asset_dir = (ASSETS_ROOT / safe_asset_id).resolve()
    _ensure_under(asset_dir, ASSETS_ROOT)
    if asset_dir.exists():
        raise FileExistsError(f"Asset already exists: {safe_asset_id}")

    candidate_records = _candidate_records_by_id(run_dir)
    validation = validate_view_selection_v1(selection, selection_mode, run_dir, candidate_records)
    selected_paths: dict[str, Path] = {}
    for view in ("front", "side", "back", "left", "right"):
        candidate_id = selection.get(view)
        if candidate_id is None:
            continue
        try:
            selected_paths[view] = _candidate_path_for_id(run_dir, candidate_records, int(candidate_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid candidate id for {view}: {candidate_id}") from exc

    asset_dir.mkdir(parents=True)
    created_files: list[str] = []
    try:
        for view, source_path in selected_paths.items():
            target = asset_dir / f"{view}.png"
            shutil.copyfile(source_path, target)
            created_files.append(_rel(target))

        for missing_view in ("side", "back"):
            if missing_view not in selected_paths:
                target = asset_dir / f"{missing_view}.png"
                shutil.copyfile(asset_dir / "front.png", target)
                created_files.append(_rel(target))

        front_size = _image_size(asset_dir / "front.png")
        semantic_dir = asset_dir / "semantic_overrides"
        semantic_dir.mkdir()
        for label in SEMANTIC_OVERRIDE_LABELS:
            path = semantic_dir / f"{label}.png"
            _write_transparent_png(path, front_size)
            created_files.append(_rel(path))

        default_params = _default_embodiment_params(safe_asset_id)
        default_path = asset_dir / "embodiment_params_default.json"
        edited_path = asset_dir / "embodiment_params.json"
        _write_json(default_path, default_params)
        _write_json(edited_path, default_params)
        created_files.extend([_rel(default_path), _rel(edited_path)])

        selected_candidates = _candidate_metadata_for_selection(candidate_records, selected_paths)
        view_selection = _view_selection_v1(
            safe_asset_id,
            run_dir,
            selection_mode,
            selection,
            selected_candidates,
            validation["warnings"],
        )
        view_selection_path = asset_dir / "view_selection_v1.json"
        _write_json(view_selection_path, view_selection)
        created_files.append(_rel(view_selection_path))

        spriteasset = _spriteasset_from_selection(
            safe_asset_id,
            selected_paths,
            selected_candidates,
            view_selection,
            source_coverage or {},
        )
        spriteasset_path = asset_dir / "spriteasset_v1.json"
        _write_json(spriteasset_path, spriteasset)
        created_files.append(_rel(spriteasset_path))
    except Exception:
        shutil.rmtree(asset_dir, ignore_errors=True)
        raise

    return {
        "ok": True,
        "asset_id": safe_asset_id,
        "asset_dir": _rel(asset_dir),
        "spriteasset_path": _rel(spriteasset_path),
        "created_files": created_files,
        "source_coverage": spriteasset["source_coverage"],
        "view_selection_path": _rel(view_selection_path),
        "warnings": validation["warnings"],
    }


def start_build_asset_job_service(asset_id: str) -> dict[str, Any]:
    asset_dir = _asset_dir(asset_id)
    _validate_asset_build_sources(asset_dir)
    job_id = _build_job_id(asset_id)
    output_dir = STUDIO_BUILDS_ROOT / job_id
    now = _now_iso()
    record = {
        "job_id": job_id,
        "asset_id": asset_id,
        "status": "queued",
        "created_at": now,
        "finished_at": None,
        "output_dir": _rel(output_dir),
        "validation_report": None,
        "validation": None,
        "artifacts": {},
        "error": None,
        "command": _build_command(asset_dir / "spriteasset_v1.json", output_dir),
    }
    _write_job_record(record)
    thread = threading.Thread(target=_execute_build_job, args=(job_id,), daemon=True)
    thread.start()
    return {"ok": True, "job_id": job_id, "status": "queued"}


def list_build_jobs() -> list[dict[str, Any]]:
    if not JOBS_ROOT.exists():
        return []
    records = [_hydrate_job_record(_read_json(path)) for path in JOBS_ROOT.glob("*.json")]
    records = [record for record in records if record]
    records.sort(key=lambda record: str(record.get("created_at", "")), reverse=True)
    return [
        {
            "job_id": record.get("job_id"),
            "asset_id": record.get("asset_id"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "finished_at": record.get("finished_at"),
            "output_dir": record.get("output_dir"),
            "validation_report": record.get("validation_report"),
            "validation": record.get("validation"),
            "artifacts": record.get("artifacts", {}),
            "error": record.get("error"),
            "validation_passed": _validation_passed(record),
        }
        for record in records
    ]


def get_build_job(job_id: str) -> dict[str, Any]:
    return _hydrate_job_record(_read_job_record(_safe_job_id(job_id)))


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


def _safe_new_asset_id(asset_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", asset_id):
        raise ValueError("asset_id must use lowercase letters, numbers, and underscore only")
    return asset_id


def _safe_job_id(job_id: str) -> str:
    if not re.fullmatch(r"build_[A-Za-z0-9_-]+", job_id):
        raise ValueError("Invalid job_id")
    return job_id


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


def _safe_existing_dir(value: str, roots: tuple[Path, ...]) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError("Absolute paths are not accepted by API v0.1")
    if ".." in path.parts:
        raise ValueError("Parent directory traversal is not accepted")
    resolved = (WORKSPACE_ROOT / path).resolve()
    if not any(_is_under(resolved, root) for root in roots):
        raise ValueError(f"Path is outside allowed roots: {value}")
    if not resolved.is_dir():
        raise FileNotFoundError(value)
    return resolved


def _safe_existing_file(value: str, roots: tuple[Path, ...]) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError("Absolute paths are not accepted by API v0.1")
    if ".." in path.parts:
        raise ValueError("Parent directory traversal is not accepted")
    resolved = (WORKSPACE_ROOT / path).resolve()
    if not any(_is_under(resolved, root) for root in roots):
        raise ValueError(f"Path is outside allowed roots: {value}")
    if not resolved.is_file():
        raise FileNotFoundError(value)
    return resolved


def _safe_identifier(value: str, label: str) -> str:
    if not value:
        raise ValueError(f"Invalid {label}")
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"Invalid {label}")
    safe = "".join(ch for ch in value if ch.isalnum() or ch in {"_", "-"})
    if safe != value:
        raise ValueError(f"Invalid {label}")
    return safe


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        raise ValueError("Uploaded sheet filename is required.")
    suffix = Path(name).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError("Uploaded sheet must be a PNG, JPG, JPEG, WEBP, or GIF image.")
    stem = Path(name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_. -]+", "_", stem).strip(" ._")
    if not safe_stem:
        safe_stem = "sheet"
    return f"{safe_stem}{suffix}"


def _unique_raw_sheet_path(filename: str) -> Path:
    target = (RAW_ROOT / filename).resolve()
    _ensure_under(target, RAW_ROOT)
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 1000):
        candidate = (RAW_ROOT / f"{stem}_{index}{suffix}").resolve()
        _ensure_under(candidate, RAW_ROOT)
        if not candidate.exists():
            return candidate
    raise ValueError("Unable to choose a unique filename for uploaded sheet.")


def _raw_sheet_record(path: Path) -> dict[str, Any]:
    width = 0
    height = 0
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        pass
    return {
        "sheet_id": path.name,
        "filename": path.name,
        "path": _rel(path),
        "width": width,
        "height": height,
        "size_bytes": path.stat().st_size,
    }


def _candidate_asset_schema(asset_id: str) -> Path:
    candidate = ASSETS_ROOT / asset_id / "spriteasset_v1.json"
    if candidate.exists():
        return candidate.resolve()
    fallback = ASSETS_ROOT / "hero_side_fixture" / "spriteasset_v1.json"
    if not fallback.exists():
        fallback = ASSETS_ROOT / "hero" / "spriteasset_v1.json"
    if not fallback.exists():
        raise FileNotFoundError("No sample spriteasset_v1.json is available for candidate extraction")
    return fallback.resolve()


def _candidate_records_by_id(run_dir: Path) -> dict[int, dict[str, Any]]:
    report = _read_json(run_dir / "candidate_report.json")
    records: dict[int, dict[str, Any]] = {}
    for record in report.get("candidates", []):
        if not isinstance(record, dict):
            continue
        try:
            records[int(record["candidate_id"])] = record
        except (KeyError, TypeError, ValueError):
            continue
    return records


def validate_view_selection_v1(
    selection: dict[str, int | None],
    mode: str,
    run_dir: Path,
    records: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    if selection.get("front") is None:
        raise ValueError("Front view is required.")
    if mode == "strict":
        if selection.get("side") is None:
            raise ValueError("Side view is required in strict mode.")
        if selection.get("back") is None:
            raise ValueError("Back view is required in strict mode.")
    else:
        if selection.get("side") is None:
            warnings.append("Side will be inferred. Fidelity will be limited.")
        if selection.get("back") is None:
            warnings.append("Back will be inferred. Fidelity will be limited.")

    selected_ids = [int(value) for view, value in selection.items() if view in {"front", "side", "back"} and value is not None]
    if len(selected_ids) != len(set(selected_ids)):
        warnings.append("Same candidate used for multiple views.")

    for view in ("front", "side", "back", "left", "right"):
        value = selection.get(view)
        if value is None:
            continue
        try:
            candidate_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid candidate id for {view}: {value}") from exc
        path = _candidate_path_for_id(run_dir, records, candidate_id)
        width, height = _image_size(path)
        if width < 12 or height < 12:
            warnings.append("Candidate may be too small.")
        if width > 256 or height > 256 or width / max(1, height) > 3.0 or height / max(1, width) > 3.0:
            warnings.append("Candidate may not be a clean sprite crop.")

    if selection.get("front") is not None and selection.get("side") is not None:
        front_record = records.get(int(selection["front"]))
        side_record = records.get(int(selection["side"]))
        if front_record and side_record and front_record.get("size") == side_record.get("size"):
            warnings.append("Side may be front-like. Confirm manually.")

    return {"ok": True, "warnings": sorted(set(warnings))}


def _candidate_path_for_id(run_dir: Path, records: dict[int, dict[str, Any]], candidate_id: int) -> Path:
    record = records.get(candidate_id)
    if not record:
        raise ValueError(f"Unknown candidate id: {candidate_id}")
    if not isinstance(record.get("path"), str):
        raise ValueError(f"Candidate record is missing image path: {candidate_id}")
    path = Path(str(record["path"]))
    if not path.is_absolute():
        path = (WORKSPACE_ROOT / path).resolve()
    candidate_root = (run_dir / "candidates").resolve()
    _ensure_under(path, candidate_root)
    if path.suffix.lower() != ".png":
        raise ValueError(f"Candidate file must be a PNG: {candidate_id}")
    if not path.exists():
        raise FileNotFoundError(f"Candidate file not found: {candidate_id}")
    return path


def _candidate_metadata_for_selection(records: dict[int, dict[str, Any]], selected_paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    path_to_view = {path.resolve(): view for view, path in selected_paths.items()}
    for candidate_id, record in records.items():
        path_value = record.get("path")
        if not isinstance(path_value, str):
            continue
        path = Path(path_value)
        if not path.is_absolute():
            path = (WORKSPACE_ROOT / path).resolve()
        view = path_to_view.get(path.resolve())
        if not view:
            continue
        metadata[view] = {
            "candidate_id": candidate_id,
            "image_path": _rel(path),
            "bbox": record.get("bbox"),
            "size": record.get("size"),
            "deterministic_pose_hint": record.get("deterministic_pose_hint"),
        }
    return metadata


def _safe_selection_mode(mode: str) -> str:
    if mode not in {"strict", "prototype"}:
        raise ValueError("mode must be strict or prototype")
    return mode


def _view_selection_v1(
    asset_id: str,
    run_dir: Path,
    mode: str,
    selection: dict[str, int | None],
    selected_candidates: dict[str, dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    views: dict[str, dict[str, Any]] = {}
    for view in ("front", "side", "back", "left", "right"):
        candidate = selected_candidates.get(view)
        required = view in {"front", "side", "back"} and (mode == "strict" or view == "front")
        if candidate:
            views[view] = {
                "candidate_id": candidate["candidate_id"],
                "authority": "user_selected",
                "required": required,
                "image_path": candidate["image_path"],
                "bbox": candidate.get("bbox"),
                "size": candidate.get("size"),
            }
        elif view in {"front", "side", "back"}:
            views[view] = {
                "candidate_id": None,
                "authority": "inferred_required_later",
                "required": required,
            }
    return {
        "selection_version": "view_selection_v1",
        "asset_id": asset_id,
        "candidate_run_id": run_dir.name,
        "candidate_run_dir": _rel(run_dir),
        "mode": mode,
        "views": views,
        "warnings": warnings,
    }


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _write_transparent_png(path: Path, size: tuple[int, int]) -> None:
    from PIL import Image

    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.save(path, format="PNG")


def _default_embodiment_params(asset_id: str) -> dict[str, Any]:
    parts = {}
    for part_id in EMBODIMENT_PARAM_PARTS:
        parts[part_id] = {
            "part_id": part_id,
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
            "notes": "Default disabled baseline generated by Studio asset creation.",
        }
    return {
        "schema": "spritespatial_embodiment_params_v1",
        "name": f"{asset_id}_default_embodiment_params",
        "description": "Default editor-safe embodiment parameter file generated from candidate view assignment.",
        "parts": parts,
    }


def _spriteasset_from_selection(
    asset_id: str,
    selected_paths: dict[str, Path],
    selected_candidates: dict[str, dict[str, Any]],
    view_selection: dict[str, Any],
    requested_coverage: dict[str, str],
) -> dict[str, Any]:
    source_sprites = {
        "front": "front.png",
        "back": "back.png",
        "left": "side.png",
        "right": "side.png",
    }
    source_coverage = {
        "front": "authored",
        "back": requested_coverage.get("back", "authored" if "back" in selected_paths else "missing"),
        "left": requested_coverage.get("left", "authored_side" if "side" in selected_paths else "missing"),
        "right": requested_coverage.get("right", "authored_side" if "side" in selected_paths else "missing"),
        "candidate_selection_method": "studio_manual",
    }
    source_coverage["front"] = "authored"
    if "back" not in selected_paths:
        source_coverage["back"] = "missing"
    if "side" not in selected_paths:
        source_coverage["left"] = "missing"
        source_coverage["right"] = "missing"
    return {
        "schema_version": "spriteasset_v1",
        "asset_name": asset_id,
        "asset_type": "character",
        "source_sprites": source_sprites,
        "render_mode": "directional_sprite_3d",
        "pixel_scale": 0.06,
        "upscaling": {
            "method": "nearest_integer",
            "scale_factor": 2,
            "generates_new_art_content": False,
            "deterministic": True,
            "output_format": "png",
        },
        "collision": {
            "type": "capsule",
            "height": 1.6,
            "radius": 0.35,
        },
        "source_coverage": source_coverage,
        "candidate_selection": selected_candidates,
        "view_selection": {
            "version": "view_selection_v1",
            "front": view_selection["views"].get("front"),
            "side": view_selection["views"].get("side"),
            "back": view_selection["views"].get("back"),
            "mode": view_selection["mode"],
            "warnings": view_selection.get("warnings", []),
        },
    }


def _validate_asset_build_sources(asset_dir: Path) -> None:
    spriteasset_path = asset_dir / "spriteasset_v1.json"
    metadata = _read_json(spriteasset_path)
    sprites = metadata.get("source_sprites") if isinstance(metadata, dict) else None
    if not isinstance(sprites, dict):
        raise ValueError("spriteasset_v1.json must define source_sprites before Studio build.")
    front = sprites.get("front")
    if not isinstance(front, str) or not front:
        raise ValueError("spriteasset_v1.json must define a front source sprite before Studio build.")
    front_path = Path(front)
    if front_path.is_absolute() or ".." in front_path.parts:
        raise ValueError("Front sprite must be a local asset crop, not an absolute or parent-relative path.")
    resolved = (asset_dir / front_path).resolve()
    _ensure_under(resolved, asset_dir)
    if not resolved.is_file():
        raise FileNotFoundError(f"Front sprite not found: {front}")
    width, height = _image_size(resolved)
    if width > 256 or height > 256:
        raise ValueError("Front sprite appears to be a full sheet or invalid crop.")


def _build_job_id(asset_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"build_{stamp}_{asset_id}"


def _build_command(asset_path: Path, output_dir: Path) -> list[str]:
    asset_dir = asset_path.parent
    command = [
        sys.executable,
        "tools/build_topological_sprite_model.py",
        "--asset",
        _rel(asset_path),
        "--profile",
        "profiles/prototype_32.json",
        "--out",
        _rel(output_dir),
    ]
    semantic_overrides = asset_dir / "semantic_overrides"
    if semantic_overrides.exists():
        command.extend(["--semantic-overrides", _rel(semantic_overrides)])
    if (asset_dir / "front.png").exists() and (asset_dir / "side.png").exists() and (asset_dir / "back.png").exists():
        command.extend(["--multi-view-authority", "--view-authority-mode", "front_back_side", "--back-mode", "front_back_sprite"])
    return command


def _execute_build_job(job_id: str) -> None:
    try:
        record = _read_job_record(job_id)
    except (FileNotFoundError, ValueError):
        return
    output_dir = (WORKSPACE_ROOT / str(record["output_dir"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    record["status"] = "running"
    record["started_at"] = _now_iso()
    _write_job_record(record)
    try:
        completed = subprocess.run(
            record["command"],
            cwd=WORKSPACE_ROOT,
            text=True,
            capture_output=True,
        )
        if completed.returncode == 0:
            _write_studio_preview_mesh(str(record.get("asset_id", "")), output_dir)
        artifacts = _discover_build_artifacts(output_dir)
        validation = _read_json(output_dir / "validation_report.json")
        record["artifacts"] = artifacts
        record["validation_report"] = validation or None
        record["validation"] = validation or None
        record["stdout_tail"] = completed.stdout[-4000:]
        record["stderr_tail"] = completed.stderr[-4000:]
        record["finished_at"] = _now_iso()
        if completed.returncode == 0:
            if _has_renderable_mesh_artifact(artifacts):
                record["status"] = "completed"
                record["error"] = None
            else:
                record["status"] = "failed"
                record["error"] = "Builder completed without a renderable mesh artifact."
        else:
            record["status"] = "failed"
            record["error"] = completed.stderr.strip() or completed.stdout.strip() or f"Builder exited {completed.returncode}"
    except Exception as exc:  # pragma: no cover - defensive for background worker
        record["status"] = "failed"
        record["finished_at"] = _now_iso()
        record["error"] = str(exc)
        record["artifacts"] = _discover_build_artifacts(output_dir)
        record["validation_report"] = _read_json(output_dir / "validation_report.json") or None
        record["validation"] = record["validation_report"]
    _write_job_record(record)


def _discover_build_artifacts(output_dir: Path) -> dict[str, str]:
    names = {
        "validation_report": "validation_report.json",
        "topological_model": "topological_model.json",
        "mesh": "mesh.json",
        "mesh_topology_cleaned": "mesh_topology_cleaned.json",
        "manifest": "manifest.json",
    }
    artifacts = {}
    for key, name in names.items():
        path = output_dir / name
        if path.exists() and (key not in {"topological_model", "mesh", "mesh_topology_cleaned"} or _is_renderable_mesh_json(path)):
            artifacts[key] = _rel(path)
    return artifacts


def _hydrate_job_record(record: dict[str, Any]) -> dict[str, Any]:
    output_dir_value = record.get("output_dir")
    if not output_dir_value:
        return record
    output_dir = (WORKSPACE_ROOT / str(output_dir_value)).resolve()
    if not _is_under(output_dir, STUDIO_BUILDS_ROOT) or not output_dir.exists():
        return record
    artifacts = _discover_build_artifacts(output_dir)
    if record.get("status") == "completed" and "mesh" not in artifacts:
        _write_studio_preview_mesh(str(record.get("asset_id", "")), output_dir)
        artifacts = _discover_build_artifacts(output_dir)
    record = {**record, "artifacts": artifacts}
    if record.get("status") == "completed" and not _has_renderable_mesh_artifact(artifacts):
        record["status"] = "failed"
        record["error"] = record.get("error") or "Build has no renderable mesh artifact."
    if not record.get("validation_report"):
        validation_path = output_dir / "validation_report.json"
        validation = _read_json(validation_path)
        if validation:
            record["validation_report"] = validation
            record["validation"] = validation
    return record


def _has_renderable_mesh_artifact(artifacts: dict[str, str]) -> bool:
    return any(key in artifacts for key in ("mesh_topology_cleaned", "mesh", "topological_model"))


def _is_renderable_mesh_json(path: Path) -> bool:
    data = _read_json(path)
    if not isinstance(data, dict) or not data:
        return False
    body = data.get("mesh") if isinstance(data.get("mesh"), dict) else data
    vertices = body.get("vertices") or body.get("verts")
    faces = body.get("faces") or body.get("triangles") or body.get("indices")
    return isinstance(vertices, list) and len(vertices) > 0 and isinstance(faces, list) and len(faces) > 0


def _write_studio_preview_mesh(asset_id: str, output_dir: Path) -> None:
    if not asset_id:
        return
    asset_dir = _asset_dir(asset_id)
    front_path = asset_dir / "front.png"
    if not front_path.exists():
        return
    mesh_path = output_dir / "mesh.json"
    if mesh_path.exists() and _is_renderable_mesh_json(mesh_path):
        return

    from PIL import Image

    with Image.open(front_path) as source:
        image = source.convert("RGBA")
        width, height = image.size
        pixels: Any = image.load()
        if pixels is None:
            return
        opaque = {
            (x, y)
            for y in range(height)
            for x in range(width)
            if pixels[x, y][3] > 16
        }
        if not opaque:
            return

        min_x = min(x for x, _y in opaque)
        max_x = max(x for x, _y in opaque) + 1
        min_y = min(y for _x, y in opaque)
        max_y = max(y for _x, y in opaque) + 1
        span = max(max_x - min_x, max_y - min_y, 1)
        scale = 1.6 / span
        depth = max(scale * 2.0, 0.08)
        z_front = depth / 2.0
        z_back = -depth / 2.0

        vertices: list[list[float]] = []
        indices: list[int] = []
        colors: list[list[float]] = []

        def point(px: int, py: int, z: float) -> list[float]:
            return [
                (px - (min_x + max_x) / 2.0) * scale,
                ((min_y + max_y) / 2.0 - py) * scale,
                z,
            ]

        def rgba_at(x: int, y: int, shade: float = 1.0) -> list[float]:
            r, g, b, a = pixels[x, y]
            return [
                min(1.0, max(0.0, (r / 255.0) * shade)),
                min(1.0, max(0.0, (g / 255.0) * shade)),
                min(1.0, max(0.0, (b / 255.0) * shade)),
                a / 255.0,
            ]

        def add_quad(points: list[list[float]], colour: list[float]) -> None:
            start = len(vertices)
            vertices.extend(points)
            colors.extend([colour, colour, colour, colour])
            indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])

        for x, y in sorted(opaque):
            add_quad(
                [point(x, y, z_front), point(x + 1, y, z_front), point(x + 1, y + 1, z_front), point(x, y + 1, z_front)],
                rgba_at(x, y),
            )
            add_quad(
                [point(x + 1, y, z_back), point(x, y, z_back), point(x, y + 1, z_back), point(x + 1, y + 1, z_back)],
                rgba_at(x, y, 0.72),
            )
            for dx, dy, corners in (
                (-1, 0, [(x, y), (x, y + 1)]),
                (1, 0, [(x + 1, y + 1), (x + 1, y)]),
                (0, -1, [(x + 1, y), (x, y)]),
                (0, 1, [(x, y + 1), (x + 1, y + 1)]),
            ):
                if (x + dx, y + dy) in opaque:
                    continue
                a, b = corners
                add_quad(
                    [point(a[0], a[1], z_front), point(b[0], b[1], z_front), point(b[0], b[1], z_back), point(a[0], a[1], z_back)],
                    rgba_at(x, y, 0.62),
                )

    _write_json(
        mesh_path,
        {
            "schema": "spritespatial_studio_preview_mesh_v1",
            "asset_id": asset_id,
            "source": _rel(front_path),
            "mesh_kind": "authoritative_front_sprite_slab",
            "vertices": vertices,
            "indices": indices,
            "colors": colors,
        },
    )


def _job_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{_safe_job_id(job_id)}.json"


def _read_job_record(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return _read_json(path)


def _write_job_record(record: dict[str, Any]) -> None:
    _write_json(_job_path(str(record["job_id"])), record)


def _validation_passed(record: dict[str, Any]) -> bool | None:
    validation = record.get("validation_report") or record.get("validation")
    if isinstance(validation, dict) and isinstance(validation.get("passed"), bool):
        return bool(validation["passed"])
    return None


def _ensure_under(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes allowed root: {path}") from exc


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _normalize_candidate_record(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    if "path" in result:
        result["path"] = _path_value_to_rel(result["path"], None)
    return result


def _path_value_to_rel(value: object, fallback: Path | None) -> str:
    path = fallback
    if isinstance(value, str) and value:
        path = Path(value)
    if path is None:
        return ""
    if not path.is_absolute():
        path = (WORKSPACE_ROOT / path).resolve()
    return _rel(path)


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _rewrite_asset_identity(asset_dir: Path, old_id: str, new_id: str) -> None:
    replacements = {
        "spriteasset_v1.json": ("asset_name",),
        "view_selection_v1.json": ("asset_id",),
    }
    for filename, keys in replacements.items():
        path = asset_dir / filename
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        for key in keys:
            if data.get(key) == old_id:
                data[key] = new_id
        _write_json(path, data)

    for path in (asset_dir / "embodiment_params.json", asset_dir / "embodiment_params_default.json"):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if isinstance(name, str) and old_id in name:
            data["name"] = name.replace(old_id, new_id)
        _write_json(path, data)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
