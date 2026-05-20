from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.asset_schema import AssetSchema, SOURCE_DIRECTIONS  # noqa: E402
from spritespatial.validators import validate_asset_schema  # noqa: E402

from build_front_back_depth_volume import build_depth_volume  # noqa: E402


GOLDEN_PIPELINE = "link_depth_volume"
REQUIRED_PROFILE_KEYS = {
    "depth_slices",
    "voxel_size",
    "model_depth_units",
    "semantic_mode",
    "primitive_mode",
    "smoothing_mode",
    "outline_policy",
    "target_face_budget",
    "capture_angles",
    "validation_thresholds",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a SpriteSpatial asset through a canonical profile pipeline."
    )
    parser.add_argument("--asset", type=Path, required=True, help="Path to spriteasset_v1.json.")
    parser.add_argument("--profile", type=Path, required=True, help="Path to a profile JSON file.")
    parser.add_argument(
        "--out",
        type=Path,
        help="Output directory. Defaults to outputs/<asset>/<profile>.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = build_profiled_asset(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Built profiled SpriteSpatial asset")
    print(f"  Pipeline: {result['pipeline']}")
    print(f"  Output: {result['output_dir']}")
    print(f"  Manifest: {result['manifest']}")
    print(f"  Validation: {result['validation_report']}")
    return 0


def build_profiled_asset(args: argparse.Namespace) -> dict[str, Any]:
    asset_path = _resolve_input(args.asset)
    profile_path = _resolve_input(args.profile)
    profile = _load_profile(profile_path)

    asset = AssetSchema.load_from_file(asset_path)
    validate_asset_schema(asset)

    output_dir = args.out
    if output_dir is None:
        output_dir = WORKSPACE_ROOT / "outputs" / asset.asset_name / profile["name"]
    elif not output_dir.is_absolute():
        output_dir = WORKSPACE_ROOT / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if profile.get("pipeline", GOLDEN_PIPELINE) != GOLDEN_PIPELINE:
        raise ValueError(f"Phase 1 only supports the {GOLDEN_PIPELINE!r} pipeline.")
    if profile["primitive_mode"] != "depth_volume":
        raise ValueError("Phase 1 profiles must use primitive_mode='depth_volume'.")

    builder_args = argparse.Namespace(
        front=asset.sprite_path("front"),
        back=asset.sprite_path("back"),
        output_dir=output_dir,
        front_depth=None,
        back_depth=None,
        regions=None,
        total_depth_slices=int(profile["depth_slices"]),
        front_relief_ratio=float(profile.get("front_relief_ratio", 0.30)),
        core_ratio=float(profile.get("core_ratio", 0.40)),
        back_relief_ratio=float(profile.get("back_relief_ratio", 0.30)),
        voxel_size=float(profile["voxel_size"]),
        model_depth_units=float(profile["model_depth_units"]),
        simplify_mesh=profile["smoothing_mode"] != "raw_debug",
        side_colour_mode=_side_colour_mode(profile),
        cleanup_mode=profile["smoothing_mode"],
        debug_show_zones=profile["semantic_mode"] != "none",
        alpha_threshold=int(profile.get("alpha_threshold", 16)),
        scene_path=output_dir / "link_depth_volume_test.tscn",
    )
    build_result = build_depth_volume(builder_args)

    canonical = _write_canonical_stage_outputs(output_dir)
    validation_report = _apply_profile_validation(
        output_dir / "validation_report.json",
        profile,
        build_result["mesh_report"],
    )
    manifest = _write_manifest(
        asset=asset,
        asset_path=asset_path,
        profile=profile,
        profile_path=profile_path,
        output_dir=output_dir,
        artefacts=canonical,
        validation_report=validation_report,
        mesh_report=build_result["mesh_report"],
    )

    return {
        "pipeline": GOLDEN_PIPELINE,
        "output_dir": output_dir,
        "manifest": manifest,
        "validation_report": output_dir / "validation_report.json",
    }


def _resolve_input(path: Path) -> Path:
    return (WORKSPACE_ROOT / path if not path.is_absolute() else path).resolve()


def _load_profile(profile_path: Path) -> dict[str, Any]:
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_PROFILE_KEYS - profile.keys())
    if missing:
        raise ValueError(f"Profile missing required keys: {missing}")
    if "name" not in profile:
        profile["name"] = profile_path.stem
    if not isinstance(profile["capture_angles"], list) or not profile["capture_angles"]:
        raise ValueError("Profile capture_angles must be a non-empty array.")
    return profile


def _side_colour_mode(profile: dict[str, Any]) -> str:
    if profile["outline_policy"] == "nearest_valid_body_colour":
        return "nearest_valid_edge"
    return "blend_front_back"


def _write_canonical_stage_outputs(output_dir: Path) -> dict[str, str]:
    captures_dir = output_dir / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)

    canonical_files = {
        "cleaned_sprite": output_dir / "cleaned_sprite.png",
        "alpha_mask": output_dir / "alpha_mask.png",
        "semantic_map": output_dir / "semantic_map.png",
        "depth_map": output_dir / "depth_map.png",
        "zfield_debug": output_dir / "zfield_debug.png",
        "occupancy_summary": output_dir / "occupancy_summary.json",
        "mesh": output_dir / "mesh.json",
        "validation_report": output_dir / "validation_report.json",
        "captures": captures_dir,
    }

    front_aligned = output_dir / "front_aligned.png"
    front_depth = output_dir / "front_depth.png"
    zfield = output_dir / "depth_debug_overlay.png"
    model = output_dir / "depth_volume_model.json"
    validation = output_dir / "validation_report.json"

    _copy_required(front_aligned, canonical_files["cleaned_sprite"])
    _copy_required(front_depth, canonical_files["depth_map"])
    _copy_required(zfield, canonical_files["zfield_debug"])
    _copy_required(model, canonical_files["mesh"])

    front = Image.open(front_aligned).convert("RGBA")
    alpha = front.getchannel("A")
    alpha.save(canonical_files["alpha_mask"], format="PNG")
    _write_semantic_placeholder(front, canonical_files["semantic_map"])

    validation_data = json.loads(validation.read_text(encoding="utf-8"))
    mesh_data = json.loads(model.read_text(encoding="utf-8"))
    occupancy = {
        "schema": "spritespatial_occupancy_summary_v1",
        "occupied_voxel_count": validation_data.get("occupied_voxel_count"),
        "exposed_face_count": validation_data.get("exposed_face_count"),
        "internal_faces_removed": validation_data.get("internal_faces_removed"),
        "hollow_gap_ratio": validation_data.get("hollow_gap_ratio"),
        "canvas_size": mesh_data.get("canvas_size"),
        "config": mesh_data.get("config", {}),
    }
    _write_json(canonical_files["occupancy_summary"], occupancy)

    return {key: _res_or_relative(path) for key, path in canonical_files.items()}


def _copy_required(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Expected build artefact missing: {source}")
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)


def _write_semantic_placeholder(front: Image.Image, path: Path) -> None:
    alpha = front.getchannel("A")
    semantic = Image.new("RGBA", front.size, (0, 0, 0, 0))
    pixels = semantic.load()
    alpha_pixels = alpha.load()
    for y in range(front.height):
        for x in range(front.width):
            if alpha_pixels[x, y] > 0:
                pixels[x, y] = (255, 255, 255, alpha_pixels[x, y])
    semantic.save(path, format="PNG")


def _apply_profile_validation(
    validation_path: Path,
    profile: dict[str, Any],
    mesh_report: dict[str, Any],
) -> dict[str, Any]:
    report = json.loads(validation_path.read_text(encoding="utf-8"))
    thresholds = profile["validation_thresholds"]
    profile_failures: list[str] = []

    black_side = report.get("percentage_of_black_side_faces", 0.0)
    if black_side > thresholds.get("max_black_side_face_percentage", 1.0):
        profile_failures.append(f"black side face percentage {black_side:.4f} exceeds profile threshold")

    hollow_gap = report.get("hollow_gap_ratio", 0.0)
    if hollow_gap > thresholds.get("max_hollow_gap_ratio", 1.0):
        profile_failures.append(f"hollow gap ratio {hollow_gap:.4f} exceeds profile threshold")

    fallback_count = report.get("number_of_side_faces_using_fallback_colour", 0)
    if fallback_count > thresholds.get("max_fallback_colour_count", fallback_count):
        profile_failures.append(f"fallback colour count {fallback_count} exceeds profile threshold")

    if thresholds.get("require_nonzero_faces", False) and mesh_report.get("exposed_face_count", 0) <= 0:
        profile_failures.append("mesh has zero exposed faces")

    if mesh_report.get("triangle_count", 0) > int(profile["target_face_budget"]):
        profile_failures.append(
            f"triangle count {mesh_report['triangle_count']} exceeds target_face_budget {profile['target_face_budget']}"
        )

    report["profile"] = profile["name"]
    report["profile_validation"] = {
        "thresholds": thresholds,
        "target_face_budget": profile["target_face_budget"],
        "mesh_stats": mesh_report,
        "failures": profile_failures,
        "passed": not profile_failures,
    }
    report["passed"] = bool(report.get("passed", False)) and not profile_failures
    _write_json(validation_path, report)
    return report


def _write_manifest(
    asset: AssetSchema,
    asset_path: Path,
    profile: dict[str, Any],
    profile_path: Path,
    output_dir: Path,
    artefacts: dict[str, str],
    validation_report: dict[str, Any],
    mesh_report: dict[str, Any],
) -> Path:
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema": "spritespatial_build_manifest_v1",
        "asset_name": asset.asset_name,
        "asset_schema": _res_or_relative(asset_path),
        "pipeline": GOLDEN_PIPELINE,
        "source_sprites": {
            direction: _res_or_relative(asset.sprite_path(direction).resolve())
            for direction in SOURCE_DIRECTIONS
        },
        "profile_path": _res_or_relative(profile_path),
        "profile": profile,
        "generated_artefacts": artefacts,
        "validation_reports": {
            "main": artefacts["validation_report"],
            "depth_report": _res_or_relative(output_dir / "depth_report.json"),
        },
        "mesh_stats": mesh_report,
        "validation_passed": validation_report.get("passed", False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": "python " + " ".join(sys.argv),
    }
    _write_json(manifest_path, manifest)
    return manifest_path


def _res_or_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return "res://" + resolved.relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
