from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence, cast

import numpy as np
from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.asset_schema import AssetSchema  # noqa: E402
from spritespatial.api_visual_judge import run_api_visual_judge  # noqa: E402
from spritespatial.back_hemisphere import build_back_hemisphere  # noqa: E402
from spritespatial.canonical_silhouette_optimizer import optimize_canonical_silhouette  # noqa: E402
from spritespatial.canonical_views import canonical_view_records, write_canonical_view_records  # noqa: E402
from spritespatial.colour_field import build_colour_field  # noqa: E402
from spritespatial.depthfields.edt import euclidean_distance_transform, normalise_distance  # noqa: E402
from spritespatial.continuity import apply_semantic_continuity  # noqa: E402
from spritespatial.constraint_arbitration import arbitrate_constraints  # noqa: E402
from spritespatial.directional_morphology import load_morphology_profile  # noqa: E402
from spritespatial.embodiment_params import apply_embodiment_params, load_embodiment_params  # noqa: E402
from spritespatial.hermite_qef import write_qef_debug  # noqa: E402
from spritespatial.manifold_validation import build_phase5a_validation  # noqa: E402
from spritespatial.metrics.silhouette_iou import compute_canonical_view_metrics  # noqa: E402
from spritespatial.mesh_surface import MeshBuildConfig, build_surface_mesh  # noqa: E402
from spritespatial.mylar_depth import build_mylar_front_depth  # noqa: E402
from spritespatial.primitives import (  # noqa: E402
    assign_primitives,
    assignments_to_json as primitive_assignments_to_json,
    primitive_count_by_type,
)
from spritespatial.sdf_volume import build_sdf_volume, build_seam_outputs  # noqa: E402
from spritespatial.topology import (  # noqa: E402
    assign_depths,
    assignments_to_json,
    build_part_graph,
    extract_regions,
    graph_to_json,
    load_rgba,
    merge_tiny_regions,
    region_mask_image,
    write_region_debug_images,
)
from spritespatial.semantic import (  # noqa: E402
    build_semantic_parts,
    run_semantic_rule_passes,
    write_semantic_debug_outputs,
)
from spritespatial.semantic_overrides import (  # noqa: E402
    apply_semantic_overrides_to_parts,
    load_semantic_overrides,
)
from spritespatial.semantic_authority import validate_semantic_authority  # noqa: E402
from spritespatial.semantic_depth_profiles import load_profile_set  # noqa: E402
from spritespatial.semantic_macro_patches import load_macro_patch_profile  # noqa: E402
from spritespatial.semantic_patch_nets import (  # noqa: E402
    apply_semantic_patch_nets,
    load_patch_profile,
)
from spritespatial.semantic_parts import consolidate_semantic_parts  # noqa: E402
from spritespatial.semantic_remeshing import (  # noqa: E402
    apply_semantic_remeshing,
    load_remesh_profile,
)
from spritespatial.render_comparison import build_visual_mapping  # noqa: E402
from spritespatial.render_diagnostics import analyze_phase5c_captures  # noqa: E402
from spritespatial.smoothing import SmoothingConfig, smooth_mesh  # noqa: E402
from spritespatial.source_coverage import analyze_source_coverage, emit_view_candidates  # noqa: E402
from spritespatial.surface_cohesion import (  # noqa: E402
    apply_surface_cohesion,
    load_surface_cohesion_profile,
)
from spritespatial.surface_nets import (  # noqa: E402
    emit_surface_nets_input,
    extract_surface_nets,
    load_surface_nets_input,
    write_mesh_json,
    write_surface_nets_debug,
    write_surface_nets_report,
)
from spritespatial.topology_cleanup import apply_topology_cleanup  # noqa: E402
from spritespatial.view_authority import build_view_authority_constraints  # noqa: E402
from spritespatial.voxel_render_profile import apply_voxel_render_profile, load_render_profile  # noqa: E402
from spritespatial.zfield import (  # noqa: E402
    build_semantic_zfield,
    reports_to_json as zfield_reports_to_json,
)


FACE_DELTAS = {
    "back": (0, 0, -1),
    "front": (0, 0, 1),
    "left": (-1, 0, 0),
    "right": (1, 0, 0),
    "up": (0, -1, 0),
    "down": (0, 1, 0),
}


DEPTH_MULTIPLIERS = {
    "head": 0.8,
    "hair": 0.85,
    "torso": 0.55,
    "left_arm": 0.7,
    "right_arm": 0.7,
    "legs": 0.65,
    "feet": 1.1,
    "boots": 1.1,  # Assuming "boots" label maps to "feet"
    "outline": 0.1,  # Give outlines a very thin depth
    "equipment": 0.3,  # Default for equipment
    "unknown": 0.4,  # Default for unknown parts
    "face": 0.8,  # Face is part of head, but can have its own depth
    "clothing": 0.5,  # Default for clothing
    "shield": 0.4,
    "sword": 0.2,
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Track C3 topological sprite decomposition model.")
    parser.add_argument("--asset", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--front", type=Path)
    parser.add_argument("--back", type=Path)
    parser.add_argument("--depth", type=Path)
    parser.add_argument("--regions", type=Path)
    parser.add_argument("--out", "--output-dir", dest="output_dir", type=Path, default=WORKSPACE_ROOT / "outputs" / "link_topological")
    parser.add_argument("--alpha-threshold", type=int, default=16)
    parser.add_argument("--colour-bucket", type=int, default=24)
    parser.add_argument("--min-region-pixels", type=int, default=3)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--model-depth-units", type=float, default=0.65)
    parser.add_argument("--total-depth-slices", type=int, default=14)
    parser.add_argument("--scene-path", type=Path, default=WORKSPACE_ROOT / "scenes" / "link_topological_test.tscn")
    parser.add_argument("--front-ink-shell", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--silhouette-core", action=argparse.BooleanOptionalAction, default=False) # Changed default to False for cuboid_parts
    parser.add_argument("--representation-style", choices=("relief_cutout", "paper_cutout", "part_depth", "cuboid_parts"), default="relief_cutout")
    parser.add_argument("--paper-depth-units", type=float, default=0.18)
    parser.add_argument("--paper-depth-slices", type=int, default=4)
    parser.add_argument("--relief-depth-units", type=float, default=0.34)
    parser.add_argument("--relief-depth-slices", type=int, default=9)
    parser.add_argument("--use-zfield", action="store_true")
    parser.add_argument("--use-primitives", action="store_true")
    parser.add_argument("--use-continuity", action="store_true")
    parser.add_argument("--emit-zfield-debug", action="store_true")
    parser.add_argument("--depth-mode", choices=("primitive", "mylar_edt"), default="primitive")
    parser.add_argument("--closed-body", action="store_true")
    parser.add_argument("--back-mode", choices=("symmetric", "semantic_rules", "front_back_sprite"), default="semantic_rules")
    parser.add_argument("--multi-view-authority", action="store_true")
    parser.add_argument("--view-authority-mode", choices=("front_back_sprite", "front_back_side", "auto"), default="auto")
    parser.add_argument("--allow-mirrored-side-fallback", action="store_true")
    parser.add_argument("--emit-view-authority-debug", action="store_true")
    parser.add_argument("--constraint-arbitration", action="store_true")
    parser.add_argument("--emit-sdf-debug", action="store_true")
    parser.add_argument("--emit-closure-debug", action="store_true")
    parser.add_argument("--mesh-backend", choices=("greedy", "surface_nets", "surface_nets_patch", "voxel_depth"), default="greedy")
    parser.add_argument("--surface-net-smoothing-alpha", type=float, default=0.65)
    parser.add_argument("--surface-net-vertex-placement", choices=("average", "qef", "patch_qef"), default="average")
    parser.add_argument("--qef-regularization", type=float, default=0.001)
    parser.add_argument("--qef-max-displacement", type=float, default=0.35)
    parser.add_argument("--emit-qef-debug", action="store_true")
    parser.add_argument("--emit-surface-net-debug", action="store_true")
    parser.add_argument("--patch-profile", default="humanoid_voxel")
    parser.add_argument("--emit-patch-debug", action="store_true")
    parser.add_argument("--macro-patches", action="store_true")
    parser.add_argument("--macro-patch-profile", default="humanoid_voxel")
    parser.add_argument("--emit-macro-patch-debug", action="store_true")
    parser.add_argument("--sdf-resolution-scale", type=float, default=1.0)
    parser.add_argument("--z-resolution-scale", type=float, default=1.0)
    parser.add_argument("--emit-resolution-diagnostic", action="store_true")
    parser.add_argument("--adaptive-sdf-resolution", action="store_true")
    parser.add_argument("--resolution-profile", default="prototype_adaptive")
    parser.add_argument("--emit-resolution-debug", action="store_true")
    parser.add_argument("--topology-cleanup", action="store_true")
    parser.add_argument("--emit-topology-cleanup-debug", action="store_true")
    parser.add_argument("--surface-cohesion", action="store_true")
    parser.add_argument("--surface-cohesion-profile", default="humanoid_voxel")
    parser.add_argument("--surface-cohesion-strength", type=float, default=0.35)
    parser.add_argument("--surface-cohesion-iterations", type=int, default=2)
    parser.add_argument("--emit-surface-cohesion-debug", action="store_true")
    parser.add_argument("--semantic-remesh", action="store_true")
    parser.add_argument("--remesh-profile", default="humanoid_lowpoly")
    parser.add_argument("--remesh-iterations", type=int, default=1)
    parser.add_argument("--remesh-strength", type=float, default=0.35)
    parser.add_argument("--preserve-silhouette-edges", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--emit-remesh-debug", action="store_true")
    parser.add_argument("--godot-preview", action="store_true")
    parser.add_argument("--godot-executable", type=Path)
    parser.add_argument("--emit-render-diagnostics", action="store_true")
    parser.add_argument("--emit-canonical-view-metrics", action="store_true")
    parser.add_argument("--emit-visual-mapping", action="store_true")
    parser.add_argument("--api-visual-judge", action="store_true")
    parser.add_argument("--canonical-silhouette-correct", action="store_true")
    parser.add_argument("--silhouette-correction-iterations", type=int, default=1)
    parser.add_argument("--max-silhouette-displacement", type=float, default=0.15)
    parser.add_argument("--emit-silhouette-correction-debug", action="store_true")
    parser.add_argument("--semantic-depth-profiles", action="store_true")
    parser.add_argument("--semantic-depth-profile", default="humanoid_voxel")
    parser.add_argument("--emit-semantic-depth-debug", action="store_true")
    parser.add_argument("--directional-morphology", action="store_true")
    parser.add_argument("--morphology-profile", default="fantasy_humanoid")
    parser.add_argument("--emit-directional-debug", action="store_true")
    parser.add_argument("--embodiment-params", type=Path)
    parser.add_argument("--emit-embodiment-param-debug", "--emit-embodiment-debug", dest="emit_embodiment_param_debug", action="store_true")
    parser.add_argument("--surface-flow", action="store_true")
    parser.add_argument("--surface-flow-strength", type=float, default=0.45)
    parser.add_argument("--surface-flow-iterations", type=int, default=2)
    parser.add_argument("--emit-surface-flow-debug", action="store_true")
    parser.add_argument("--rfd", action="store_true")
    parser.add_argument("--emit-rfd-debug", action="store_true")
    parser.add_argument("--render-profile")
    parser.add_argument("--find-view-candidates", action="store_true")
    parser.add_argument("--semantic-overrides", type=Path)
    parser.add_argument("--semantic-override-mode", choices=("none", "supplement", "replace", "strict"), default=None)
    parser.add_argument("--semantic-parts", action="store_true")
    parser.add_argument("--emit-semantic-parts-debug", action="store_true")
    parser.add_argument("--smooth", action="store_true")
    parser.add_argument(
        "--smoothing-mode",
        choices=("none", "semantic_laplacian", "bevel_edges", "voxel_soften", "primitive_rounding", "hybrid_lowpoly"),
        default=None,
    )
    parser.add_argument("--emit-smoothing-debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_topological_model(args)
    print("Built Track C3 topological sprite model")
    print(f"  Regions: {result['region_count']}")
    print(f"  Model: {result['model']}")
    print(f"  Part graph: {result['part_graph']}")
    print(f"  Validation: {result['validation_report']}")
    if result.get("scene"):
        print(f"  Scene: {result['scene']}")
    return 0


def _load_profile(profile_path: Path | None) -> dict:
    if not profile_path:
        return {}
    path = profile_path if profile_path.is_absolute() else WORKSPACE_ROOT / profile_path
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _load_resolution_profile(profile_ref: str | Path | None) -> dict[str, Any]:
    name = str(profile_ref or "prototype_adaptive")
    path = Path(name)
    if not path.suffix:
        path = WORKSPACE_ROOT / "profiles" / "resolution_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = WORKSPACE_ROOT / path
    data = json.loads(path.resolve().read_text(encoding="utf-8"))
    data["name"] = data.get("name", path.stem)
    data["path"] = str(path.resolve())
    return data


def _adaptive_resolution_settings(
    args: argparse.Namespace,
    base_z_samples: int,
    source_size: tuple[int, int],
) -> dict[str, Any]:
    if not getattr(args, "adaptive_sdf_resolution", False):
        xy_scale = max(1.0, float(getattr(args, "sdf_resolution_scale", 1.0)))
        z_scale = max(1.0, float(getattr(args, "z_resolution_scale", 1.0)))
        return {
            "enabled": False,
            "profile": None,
            "xy_scale": xy_scale,
            "z_scale": z_scale,
            "z_samples": int(round(float(base_z_samples - 1) * z_scale)) + 1,
            "strategy": "uniform",
        }
    profile = _load_resolution_profile(getattr(args, "resolution_profile", "prototype_adaptive"))
    requested_xy = max(
        float(profile.get("base_xy_scale", 1.0)),
        float(profile.get("high_detail_xy_scale", 1.0)),
        float(profile.get("silhouette_band_extra_scale", 1.0)),
        float(profile.get("semantic_boundary_extra_scale", 1.0)),
    )
    requested_z = max(float(profile.get("base_z_scale", 1.0)), float(profile.get("high_detail_z_scale", 1.0)))
    width, height = source_size
    requested_voxels = (height * requested_xy) * (width * requested_xy) * (base_z_samples * requested_z)
    base_voxels = max(1.0, float(height * width * base_z_samples))
    requested_multiplier = requested_voxels / base_voxels
    budget = max(1.0, float(profile.get("max_voxel_budget_multiplier", requested_multiplier)))
    clamp = min(1.0, (budget / max(requested_multiplier, 1.0e-6)) ** (1.0 / 3.0))
    xy_scale = max(float(profile.get("base_xy_scale", 1.0)), requested_xy * clamp)
    z_scale = max(float(profile.get("base_z_scale", 1.0)), requested_z * clamp)
    z_samples = int(round(float(base_z_samples - 1) * z_scale)) + 1
    base_voxel_count = max(1, width * height * base_z_samples)
    for _ in range(12):
        scaled_width = max(width, int(round(width * xy_scale)))
        scaled_height = max(height, int(round(height * xy_scale)))
        multiplier = (scaled_width * scaled_height * z_samples) / float(base_voxel_count)
        if multiplier <= budget + 1.0e-6:
            break
        xy_scale = max(float(profile.get("base_xy_scale", 1.0)), xy_scale * 0.985)
        z_scale = max(float(profile.get("base_z_scale", 1.0)), z_scale * 0.985)
        z_samples = int(round(float(base_z_samples - 1) * z_scale)) + 1
    return {
        "enabled": True,
        "profile": profile,
        "xy_scale": xy_scale,
        "z_scale": z_scale,
        "z_samples": z_samples,
        "strategy": "highres_internal_downsampled" if clamp < 0.999 else "adaptive",
        "requested_xy_scale": requested_xy,
        "requested_z_scale": requested_z,
        "budget_clamp": clamp,
    }


def _resolve_optional_path(path: Path | None) -> Path | None:
    if not path:
        return None
    return (path if path.is_absolute() else WORKSPACE_ROOT / path).resolve()


def _apply_profile_defaults(args: argparse.Namespace, profile: dict) -> None:
    if not profile:
        return
    if "voxel_size" in profile:
        args.voxel_size = float(profile["voxel_size"])
    if "model_depth_units" in profile:
        args.model_depth_units = float(profile["model_depth_units"])
    if "depth_slices" in profile:
        args.total_depth_slices = int(profile["depth_slices"])
    if "max_depth_slices" in profile:
        args.total_depth_slices = min(args.total_depth_slices, int(profile["max_depth_slices"]))
    if profile.get("use_zfield", False):
        args.use_zfield = True
    if profile.get("use_primitives", False):
        args.use_primitives = True
    if profile.get("use_continuity", False):
        args.use_continuity = True
    if profile.get("emit_all_debug", False):
        args.emit_zfield_debug = True
    if profile.get("semantic_override_mode") and args.semantic_override_mode is None:
        args.semantic_override_mode = profile["semantic_override_mode"]
    if profile.get("semantic_override_dir") and not args.semantic_overrides:
        args.semantic_overrides = Path(profile["semantic_override_dir"])
    if args.semantic_override_mode is None:
        args.semantic_override_mode = "supplement"
    if profile.get("smoothing_enabled", False):
        args.smooth = True
    if profile.get("smoothing_mode") and args.smoothing_mode is None:
        args.smoothing_mode = profile["smoothing_mode"]
    if profile.get("semantic_depth_profiles", False):
        args.semantic_depth_profiles = True
    if profile.get("semantic_depth_profile") and not getattr(args, "semantic_depth_profile", None):
        args.semantic_depth_profile = profile["semantic_depth_profile"]
    if profile.get("directional_morphology", False):
        args.directional_morphology = True
    if profile.get("morphology_profile") and not getattr(args, "morphology_profile", None):
        args.morphology_profile = profile["morphology_profile"]
    if profile.get("surface_flow", False):
        args.surface_flow = True
    if "surface_flow_strength" in profile:
        args.surface_flow_strength = float(profile["surface_flow_strength"])
    if "surface_flow_iterations" in profile:
        args.surface_flow_iterations = int(profile["surface_flow_iterations"])
    if profile.get("rfd", False):
        args.rfd = True
    if profile.get("semantic_parts", False):
        args.semantic_parts = True
    if profile.get("surface_cohesion", False):
        args.surface_cohesion = True
    if "patch_profile" in profile:
        args.patch_profile = str(profile["patch_profile"])
    if profile.get("macro_patches", False):
        args.macro_patches = True
    if "macro_patch_profile" in profile:
        args.macro_patch_profile = str(profile["macro_patch_profile"])
    if profile.get("semantic_remesh", False):
        args.semantic_remesh = True
    if "remesh_profile" in profile:
        args.remesh_profile = str(profile["remesh_profile"])
    if "remesh_iterations" in profile:
        args.remesh_iterations = int(profile["remesh_iterations"])
    if "remesh_strength" in profile:
        args.remesh_strength = float(profile["remesh_strength"])
    if args.smoothing_mode is None:
        args.smoothing_mode = "none"
    if args.use_zfield or args.use_primitives or args.use_continuity:
        args.representation_style = "semantic_zfield"


def _smoothing_config(args: argparse.Namespace, profile: dict) -> SmoothingConfig:
    mode = getattr(args, "smoothing_mode", None) or "none"
    return SmoothingConfig(
        enabled=bool(getattr(args, "smooth", False)) and mode != "none",
        mode=mode,
        iterations=int(profile.get("smoothing_iterations", 1)),
        bevel_strength=float(profile.get("bevel_strength", 0.15)),
        silhouette_preservation_weight=float(profile.get("silhouette_preservation_weight", 1.0)),
        semantic_boundary_weight=float(profile.get("semantic_boundary_weight", 0.85)),
        outline_preservation_weight=float(profile.get("outline_preservation_weight", 1.0)),
        max_silhouette_drift_px=float(profile.get("max_silhouette_drift_px", 1.0)),
        voxel_size=float(getattr(args, "voxel_size", 0.05)),
    )


def build_topological_model(args: argparse.Namespace) -> dict:
    profile = _load_profile(getattr(args, "profile", None))
    _apply_profile_defaults(args, profile)
    if getattr(args, "semantic_override_mode", None) is None:
        args.semantic_override_mode = "supplement"
    if getattr(args, "smoothing_mode", None) is None:
        args.smoothing_mode = "none"
    if getattr(args, "asset", None):
        asset = AssetSchema.load_from_file(args.asset.resolve())
        args._asset_schema = asset
        args.front = asset.sprite_path("front")
        if not getattr(args, "back", None):
            args.back = asset.sprite_path("back")
        args.left = asset.sprite_path("left")
        args.right = asset.sprite_path("right")
    if not getattr(args, "front", None):
        raise ValueError("Either --asset or --front is required.")
    front = load_rgba(args.front.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    default_scene = (WORKSPACE_ROOT / "scenes" / "link_topological_test.tscn").resolve()
    if (getattr(args, "asset", None) or getattr(args, "profile", None)) and args.scene_path.resolve() == default_scene:
        args.scene_path = output_dir / "topological_sprite_test.tscn"
    part_debug_dir = output_dir / "per_part_mesh_debug"
    part_debug_dir.mkdir(parents=True, exist_ok=True)

    front_path = output_dir / "front.png"
    front.save(front_path, format="PNG")
    cleaned_path = output_dir / "stage_1_cleaned_sprite.png"
    front.save(cleaned_path, format="PNG")

    regions, region_map = extract_regions(front, args.alpha_threshold, args.colour_bucket)
    regions, region_map = merge_tiny_regions(front, regions, region_map, args.min_region_pixels)
    graph = build_part_graph(front, regions, region_map)
    assignments = assign_depths(graph)
    assignment_by_id = {item.region_id: item for item in assignments}
    semantic_regions, semantic_report, semantic_warnings = run_semantic_rule_passes(front, regions, graph)
    heuristic_parts = build_semantic_parts(front, regions, semantic_regions)
    override_dir = _resolve_optional_path(getattr(args, "semantic_overrides", None))
    asset_schema = getattr(args, "_asset_schema", None)
    source_coverage = analyze_source_coverage(
        asset_schema,
        profile,
        getattr(args, "back_mode", "semantic_rules"),
    )
    args._source_coverage = source_coverage
    view_candidate_paths: dict[str, Path] = {}
    if getattr(args, "find_view_candidates", False) and asset_schema is not None:
        view_candidate_result = emit_view_candidates(
            asset_schema,
            output_dir.parent / "view_candidates",
            WORKSPACE_ROOT / "assets" / "raw",
        )
        view_candidate_paths = view_candidate_result.get("paths", {})
    override_load = load_semantic_overrides(
        override_dir,
        front.size,
        getattr(args, "semantic_override_mode", "supplement"),
    )
    override_parts, override_apply_report, override_debug_paths = apply_semantic_overrides_to_parts(
        front,
        heuristic_parts,
        override_load["masks"],
        getattr(args, "semantic_override_mode", "supplement"),
        output_dir / "semantic_overrides"
        if override_load["masks"] or getattr(args, "semantic_override_mode", "supplement") != "none"
        else None,
    )
    semantic_override_report = {**override_load["report"], **override_apply_report}
    args._semantic_override_parts = override_parts
    args._semantic_override_report = semantic_override_report
    args._semantic_override_debug_paths = override_debug_paths

    region_id_map, region_overlay = write_region_debug_images(front, regions, output_dir)
    depth_debug = _write_depth_debug(front, regions, assignment_by_id, output_dir / "depth_debug.png")
    semantic_paths = write_semantic_debug_outputs(front, regions, semantic_regions, output_dir)
    for region_id, region in enumerate(regions):
        mask = region_mask_image(front.size, region)
        mask.save(part_debug_dir / f"part_{region_id:03d}_mask.png", format="PNG")

    if getattr(args, "closed_body", False) or getattr(args, "depth_mode", "primitive") == "mylar_edt":
        return _build_phase5a_closed_body(
            args,
            front,
            output_dir,
            cleaned_path,
            graph,
            assignments,
            semantic_report,
            semantic_warnings,
            semantic_override_report,
            override_parts,
            override_load["masks"],
            regions,
            region_id_map,
            region_overlay,
            depth_debug,
            semantic_paths,
            override_debug_paths,
            source_coverage,
            view_candidate_paths,
        )

    mesh: dict[str, Any]
    part_reports: list[dict[str, Any]]
    mesh, part_reports = _build_part_mesh(front, regions, graph, assignment_by_id, args, semantic_regions)
    smoothing_report: dict[str, Any] = {}
    smoothing_debug_paths: dict[str, Path] = {}
    if getattr(args, "smooth", False) or getattr(args, "smoothing_mode", "none") != "none":
        smoothed_mesh, smoothing_report = smooth_mesh(
            cast(dict[str, list[Any]], mesh),
            part_reports,
            _smoothing_config(args, profile),
            output_dir / "smoothing",
        )
        mesh = cast(dict[str, Any], smoothed_mesh)
        smoothing_debug_paths = {
            "smoothing_before": output_dir / "smoothing" / "smoothing_before.png",
            "smoothing_after": output_dir / "smoothing" / "smoothing_after.png",
            "silhouette_drift": output_dir / "smoothing" / "silhouette_drift.png",
            "boundary_preservation": output_dir / "smoothing" / "boundary_preservation.png",
            "smoothing_report": output_dir / "smoothing" / "smoothing_report.json",
        }
    mesh["smoothing_report"] = smoothing_report
    mesh["smoothing_debug_paths"] = {
        key: _res_path(path)
        for key, path in smoothing_debug_paths.items()
        if path.exists()
    }
    validation_report = _validation_report(front, regions, mesh, part_reports, args, semantic_warnings)
    validation_path = output_dir / "validation_report.json"
    _write_json(validation_path, validation_report)
    model_path = output_dir / "topological_model.json"
    model = {
        "schema": "spritespatial_topological_model_v1",
        "pipeline_stages": {
            "stage_0_source_sprite": _res_path(args.front.resolve()),
            "stage_1_cleaned_transparent_sprite": _res_path(cleaned_path),
            "stage_2_region_depth_debug": {
                "region_id_map": _res_path(region_id_map),
                "region_overlay": _res_path(region_overlay),
                "depth_debug": _res_path(depth_debug),
                "semantic_region_overlay": _res_path(semantic_paths["semantic_region_overlay"]),
                "semantic_id_map": _res_path(semantic_paths["semantic_id_map"]),
                "semantic_bbox_overlay": _res_path(semantic_paths["semantic_bbox_overlay"]),
                "semantic_depth_overlay": _res_path(semantic_paths["semantic_depth_overlay"]),
            },
            "stage_3_generated_part_volumes": _res_path(part_debug_dir),
            "stage_4_final_combined_model": _res_path(model_path),
        },
        "front_texture": _res_path(cleaned_path),
        "region_overlay": _res_path(region_overlay),
        "region_id_map": _res_path(region_id_map),
        "depth_debug": _res_path(depth_debug),
        "semantic_region_overlay": _res_path(semantic_paths["semantic_region_overlay"]),
        "semantic_id_map": _res_path(semantic_paths["semantic_id_map"]),
        "semantic_bbox_overlay": _res_path(semantic_paths["semantic_bbox_overlay"]),
        "semantic_depth_overlay": _res_path(semantic_paths["semantic_depth_overlay"]),
        "semantic_outline_only": _res_path(semantic_paths["semantic_outline_only"]),
        "semantic_unknown_regions": _res_path(semantic_paths["semantic_unknown_regions"]),
        "semantic_occupancy": _res_path(semantic_paths["semantic_occupancy"]),
        "semantic_report": _res_path(output_dir / "semantic_report.json"),
        "semantic_warnings": _res_path(output_dir / "semantic_warnings.json"),
        "canvas_size": [front.width, front.height],
        "config": {
            "voxel_size": args.voxel_size,
            "model_depth_units": args.model_depth_units,
            "total_depth_slices": args.total_depth_slices,
            "colour_bucket": args.colour_bucket,
            "min_region_pixels": args.min_region_pixels,
            "front_ink_shell": args.front_ink_shell,
            "silhouette_core": args.silhouette_core,
            "representation_style": args.representation_style,
            "paper_depth_units": args.paper_depth_units,
            "paper_depth_slices": args.paper_depth_slices,
            "relief_depth_units": args.relief_depth_units,
            "relief_depth_slices": args.relief_depth_slices,
            "use_zfield": getattr(args, "use_zfield", False),
            "use_primitives": getattr(args, "use_primitives", False),
            "use_continuity": getattr(args, "use_continuity", False),
            "emit_zfield_debug": getattr(args, "emit_zfield_debug", False),
            "profile": _res_path(args.profile.resolve()) if getattr(args, "profile", None) else "",
            "semantic_overrides": _res_path(override_dir) if override_dir else "",
            "semantic_override_mode": getattr(args, "semantic_override_mode", "supplement"),
            "smoothing_enabled": bool(smoothing_report.get("smoothing_enabled", False)),
            "smoothing_mode": smoothing_report.get("smoothing_mode", getattr(args, "smoothing_mode", "none")),
            "source_coverage": source_coverage,
        },
        # For cuboid_parts, these will be actual cuboid dimensions
        # For other modes, these are voxel-based
        "vertices": mesh["vertices"],
        "normals": mesh["normals"],
        "colors": mesh["colors"],
        "indices": mesh["indices"],
        "part_ids": mesh["part_ids"],
        "parts": part_reports,
        "semantic_regions": semantic_report["regions"],
        "primitive_assignments": mesh.get("primitive_assignments", []),
        "zfield_reports": mesh.get("zfield_reports", []),
        "zfield_heatmap": mesh.get("zfield_debug_paths", {}).get("zfield_heatmap", ""),
        "zfield_debug": mesh.get("zfield_debug_paths", {}).get("zfield_debug", ""),
        "primitive_assignment": mesh.get("zfield_debug_paths", {}).get("primitive_assignment", ""),
        "occupancy_slices": mesh.get("zfield_debug_paths", {}).get("occupancy_slices_sheet", ""),
        "occupancy_slices_dir": mesh.get("zfield_debug_paths", {}).get("occupancy_slices", ""),
        "outline_shell": mesh.get("zfield_debug_paths", {}).get("outline_shell", ""),
        "continuity_overlay": mesh.get("continuity_debug_paths", {}).get("continuity_overlay", ""),
        "bridge_debug": mesh.get("continuity_debug_paths", {}).get("bridge_debug", ""),
        "continuity_graph": mesh.get("continuity_debug_paths", {}).get("continuity_graph", ""),
        "side_silhouette_debug": mesh.get("continuity_debug_paths", {}).get("side_silhouette_debug", ""),
        "shell_overlap_debug": mesh.get("continuity_debug_paths", {}).get("shell_overlap_debug", ""),
        "semantic_override_overlay": {
            key: _res_path(path)
            for key, path in override_debug_paths.items()
        },
        "smoothing_before": mesh.get("smoothing_debug_paths", {}).get("smoothing_before", ""),
        "smoothing_after": mesh.get("smoothing_debug_paths", {}).get("smoothing_after", ""),
        "silhouette_drift": mesh.get("smoothing_debug_paths", {}).get("silhouette_drift", ""),
        "boundary_preservation": mesh.get("smoothing_debug_paths", {}).get("boundary_preservation", ""),
        "smoothing_report": mesh.get("smoothing_debug_paths", {}).get("smoothing_report", ""),
        "view_candidates": {key: _res_path(path) for key, path in view_candidate_paths.items()},
        "generated_sprite_model": {
            "mesh_instance": "GeneratedSpriteModel",
            "materials": ["vertex_color_unshaded"],
            "metadata": {
                "regions_generated": len(regions),
                "source": _res_path(args.front.resolve()),
                "normal_scene_renders": ["source_reference", "final_combined_model"],
            },
            "validation_report": validation_report,
        },
    }
    _write_json(model_path, model)
    _write_json(output_dir / "part_graph.json", {"regions": graph_to_json(graph)})
    _write_json(output_dir / "depth_assignment.json", {"assignments": assignments_to_json(assignments)})
    _write_json(output_dir / "semantic_report.json", semantic_report)
    _write_json(output_dir / "semantic_warnings.json", semantic_warnings)
    _write_json(output_dir / "semantic_override_report.json", semantic_override_report)
    if mesh.get("primitive_assignments"):
        _write_json(output_dir / "primitive_assignment.json", {"assignments": mesh["primitive_assignments"]})
    if mesh.get("zfield_reports"):
        _write_json(output_dir / "zfield_region_report.json", {"regions": mesh["zfield_reports"]})
    if mesh.get("continuity_graph"):
        _write_json(output_dir / "continuity_graph.json", mesh["continuity_graph"])
    if mesh.get("bridge_reports"):
        _write_json(output_dir / "bridge_report.json", {"bridges": mesh["bridge_reports"]})
    if mesh.get("smoothing_report"):
        _write_json(output_dir / "smoothing_report.json", mesh["smoothing_report"])

    _write_scene(args.scene_path.resolve(), model_path)
    return {
        "region_count": len(regions),
        "model": model_path,
        "part_graph": output_dir / "part_graph.json",
        "validation_report": validation_path,
        "scene": args.scene_path.resolve(),
    }


def _build_part_mesh(front: Image.Image, regions, graph, assignments, args, semantic_regions=None) -> tuple[dict, list[dict]]:
    if getattr(args, "use_zfield", False) or getattr(args, "use_primitives", False):
        return _build_semantic_zfield_mesh(front, regions, graph, args, semantic_regions)
    if args.representation_style == "relief_cutout":
        return _build_relief_cutout_mesh(front, regions, graph, assignments, args)
    if args.representation_style == "paper_cutout":
        return _build_paper_cutout_mesh(front, regions, graph, args)
    if args.representation_style == "cuboid_parts":
        return _build_cuboid_parts_mesh(front, regions, graph, assignments, args, semantic_regions)

    source_rgba = front.convert("RGBA")
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.model_depth_units * 0.5
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    part_reports: list[dict] = []
    total_voxels = 0
    global_occupied: set[tuple[int, int, int]] = set()
    region_lookup: dict[tuple[int, int], int] = {}
    region_colour_lookup: dict[int, list[int]] = {}

    for region_info, region in zip(graph, regions):
        region_colour_lookup[region_info.region_id] = region_info.dominant_colour
        for x, y in region:
            if not (0 <= x < width and 0 <= y < height):
                continue
            if _source_rgba_at(source_rgba, x, y)[3] <= args.alpha_threshold:
                continue
            region_lookup[(x, y)] = region_info.region_id

    for region_info, region in zip(graph, regions):
        assignment = assignments[region_info.region_id]
        occupied = _part_occupancy(region, width, height, args.total_depth_slices, assignment)
        global_occupied.update(occupied)
        total_voxels += len(occupied)
        exposed_faces = 0
        for z in range(args.total_depth_slices):
            z0 = z_start + z * voxel_z
            z1 = z0 + voxel_z
            for y in range(height):
                y0 = total_height - (y + 1) * voxel_y
                y1 = total_height - y * voxel_y
                for x in range(width):
                    if (x, y, z) not in occupied:
                        continue
                    x0 = x * voxel_x - total_width * 0.5
                    x1 = x0 + voxel_x
                    for face, delta in FACE_DELTAS.items():
                        nx, ny, nz = x + delta[0], y + delta[1], z + delta[2]
                        if (nx, ny, nz) in occupied:
                            continue
                        exposed_faces += 1
                        colour, used_fallback = _part_face_colour(_source_rgba_at(source_rgba, x, y), region_info.dominant_colour, assignment.label, face)
                        _add_face(vertices, normals, colors, indices, part_ids, region_info.region_id, face, x0, x1, y0, y1, z0, z1, colour)
        part_reports.append(
            {
                "region_id": region_info.region_id,
                "label": assignment.label,
                "pixel_count": region_info.pixel_count,
                "voxel_count": len(occupied),
                "exposed_faces": exposed_faces,
                "z_offset": assignment.z_offset,
                "local_depth": assignment.local_depth,
                "merge_policy": assignment.merge_policy,
            }
        )
    if args.silhouette_core:
        core_report = _add_silhouette_core(
            front,
            regions,
            global_occupied,
            region_lookup,
            region_colour_lookup,
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            args,
        )
        total_voxels += core_report["voxel_count"]
        part_reports.append(core_report)
    if args.front_ink_shell:
        shell_report = _add_front_ink_shell(
            front,
            regions,
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            args,
        )
        part_reports.append(shell_report)
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": total_voxels,
    }, part_reports


def _build_semantic_zfield_mesh(front: Image.Image, regions, graph, args, semantic_regions=None) -> tuple[dict, list[dict]]:
    parts = getattr(args, "_semantic_override_parts", None) or segmentSpriteParts(front, regions, graph, semantic_regions)
    primitive_assignments = assign_primitives(parts, _load_profile(getattr(args, "profile", None)))
    output_dir = args.output_dir.resolve()
    zfield_dir = output_dir / "zfield"
    zfield_result = build_semantic_zfield(
        front.size,
        parts,
        primitive_assignments,
        args.total_depth_slices,
        zfield_dir if getattr(args, "emit_zfield_debug", False) else output_dir,
    )
    occupied = zfield_result["occupancy"]
    owner_by_voxel = zfield_result["owner_by_voxel"]
    reports_by_id = {report.part_id: report for report in zfield_result["reports"]}
    assignment_by_id = {item.part_id: item for item in primitive_assignments}
    part_by_id = {part_id: part for part_id, part in enumerate(parts)}
    continuity_result = {}
    if getattr(args, "use_continuity", False):
        continuity_result = apply_semantic_continuity(
            parts,
            primitive_assignments,
            occupied,
            owner_by_voxel,
            args.total_depth_slices,
            output_dir / "continuity",
            front.size,
        )

    source_rgba = front.convert("RGBA")
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.model_depth_units * 0.5
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    face_counts: dict[int, int] = {}

    for x, y, z in sorted(occupied):
        part_id = owner_by_voxel[(x, y, z)]
        assignment = assignment_by_id[part_id]
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        source_pixel = _source_rgba_at(source_rgba, x, y)
        if source_pixel[3] <= args.alpha_threshold:
            part = part_by_id.get(part_id, {})
            source_pixel = tuple(part.get("dominant_colour", (160, 160, 160, 255)))
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            colour = _zfield_face_colour(source_pixel, assignment.name, assignment.primitive_type, face)
            _add_face(vertices, normals, colors, indices, part_ids, part_id, face, x0, x1, y0, y1, z0, z1, colour)
            face_counts[part_id] = face_counts.get(part_id, 0) + 1

    part_reports: list[dict] = []
    for assignment in primitive_assignments:
        z_report = reports_by_id[assignment.part_id]
        part = part_by_id.get(assignment.part_id, {})
        part_reports.append(
            {
                "region_id": assignment.part_id,
                "name": assignment.name,
                "label": assignment.name,
                "semantic_label": assignment.semantic_label,
                "primitive_type": assignment.primitive_type,
                "zfield_profile": assignment.zfield_profile,
                "pixel_count": assignment.pixel_count,
                "voxel_count": z_report.occupied_voxels,
                "exposed_faces": face_counts.get(assignment.part_id, 0),
                "z_offset": assignment.z_offset,
                "local_depth": assignment.local_depth,
                "average_depth": z_report.average_depth,
                "min_depth": z_report.min_depth,
                "max_depth": z_report.max_depth,
                "smoothing_policy": assignment.smoothing_policy,
                "boundary_policy": assignment.boundary_policy,
                "fallback_primitive": assignment.fallback,
                "malformed": z_report.malformed,
                "bbox": part.get("bbox", assignment.bbox),
                "merge_policy": "semantic_zfield_primitive",
            }
        )

    mesh = {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
        "zfield_reports": zfield_reports_to_json(zfield_result["reports"]),
        "primitive_assignments": primitive_assignments_to_json(primitive_assignments),
        "primitive_count_by_type": primitive_count_by_type(primitive_assignments),
        "zfield_debug_paths": {
            key: _res_path(path)
            for key, path in zfield_result.get("debug_paths", {}).items()
        },
        "continuity_enabled": bool(getattr(args, "use_continuity", False)),
        "continuity_graph": continuity_result.get("graph", {}),
        "bridge_reports": continuity_result.get("bridge_reports", []),
        "continuity_metrics": continuity_result.get("metrics", {}),
        "continuity_debug_paths": {
            key: _res_path(path)
            for key, path in continuity_result.get("debug_paths", {}).items()
        },
    }
    return mesh, part_reports


def _zfield_face_colour(source_pixel, label: str, primitive_type: str, face: str) -> tuple[int, int, int, int]:
    red, green, blue, alpha = source_pixel
    if face == "front":
        return red, green, blue, alpha
    if primitive_type == "shell" or label == "outline":
        factor = 0.35
    elif face == "back":
        factor = 0.72
    else:
        factor = 0.82
    return int(red * factor), int(green * factor), int(blue * factor), alpha


def _build_paper_cutout_mesh(front: Image.Image, regions, graph, args) -> tuple[dict, list[dict]]:
    source_rgba = front.convert("RGBA")
    width, height = front.size
    depth_slices = max(1, args.paper_depth_slices)
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.paper_depth_units / depth_slices
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.paper_depth_units * 0.5

    occupied: set[tuple[int, int, int]] = set()
    region_by_pixel: dict[tuple[int, int], int] = {}
    label_by_region: dict[int, str] = {}
    for region_info, region in zip(graph, regions):
        label_by_region[region_info.region_id] = region_info.likely_label
        for x, y in region:
            region_by_pixel[(x, y)] = region_info.region_id
            for z in range(depth_slices):
                occupied.add((x, y, z))

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    exposed_faces = 0
    for x, y, z in sorted(occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        region_id = region_by_pixel.get((x, y), -1)
        label = label_by_region.get(region_id, "unknown")
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            exposed_faces += 1
            colour = _paper_face_colour(_source_rgba_at(source_rgba, x, y), label, face)
            _add_face(vertices, normals, colors, indices, part_ids, region_id, face, x0, x1, y0, y1, z0, z1, colour)

    reports = [
        {
            "region_id": -300,
            "label": "paper_cutout_silhouette",
            "pixel_count": len({(x, y) for x, y, _z in occupied}),
            "voxel_count": len(occupied),
            "exposed_faces": exposed_faces,
            "z_offset": 0.0,
            "local_depth": args.paper_depth_units,
            "merge_policy": "single_coherent_cutout",
        }
    ]
    reports.extend(
        {
            "region_id": region.region_id,
            "label": region.likely_label,
            "pixel_count": region.pixel_count,
            "voxel_count": region.pixel_count * depth_slices,
            "exposed_faces": 0,
            "z_offset": 0.0,
            "local_depth": args.paper_depth_units,
            "merge_policy": "metadata_region",
        }
        for region in graph
    )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
    }, reports


def _paper_face_colour(source_pixel, label: str, face: str) -> tuple[int, int, int, int]:
    red, green, blue, alpha = source_pixel
    if face == "front":
        return (red, green, blue, alpha)
    if label == "outline" or max(red, green, blue) <= 72:
        return (24, 24, 24, alpha)
    factor = 0.72 if face not in {"front", "back"} else 0.82
    return (int(red * factor), int(green * factor), int(blue * factor), alpha)


def segmentSpriteParts(front: Image.Image, regions, graph, semantic_regions=None) -> list[dict]:
    if semantic_regions is None:
        semantic_regions, _semantic_report, _semantic_warnings = run_semantic_rule_passes(front, regions, graph)
    return build_semantic_parts(front, regions, semantic_regions)


def getPartBoundingBoxes(parts: list[dict]) -> list[dict]:
    return [
        {
            "name": part["name"],
            "pixels": part["pixels"],
            "bbox": part["bbox"],
            "pixel_count": len(part["pixels"]),
            "dominant_colour": part["dominant_colour"],
            "semantic_label": part.get("semantic_label", part["name"]),
        }
        for part in parts
    ]


def _build_cuboid_parts_mesh(front: Image.Image, regions, graph, assignments, args, semantic_regions=None) -> tuple[dict, list[dict]]:
    parts = segmentSpriteParts(front, regions, graph, semantic_regions)
    part_boxes = getPartBoundingBoxes(parts)
    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    reports: list[dict] = []
    occupied, voxel_owner, part_depths = _build_global_unit_cube_lattice(front, part_boxes, args.alpha_threshold)
    face_counts = _emit_global_unit_cube_surface(
        front,
        occupied,
        voxel_owner,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        args.voxel_size,
        front.height * args.voxel_size,
    )
    for part_index, part in enumerate(part_boxes):
        x0_px, y0_px, x1_px, y1_px = part["bbox"]
        width_px = x1_px - x0_px
        height_px = y1_px - y0_px
        depth_cells = part_depths.get(part_index, 1)
        reports.append(
            {
                "region_id": part_index,
                "name": part["name"],
                "label": part["name"],
                "semantic_label": part.get("semantic_label", part["name"]),
                "pixel_count": len(part["pixels"]),
                "voxel_count": len(part["pixels"]) * depth_cells,
                "exposed_faces": face_counts.get(part_index, 0),
                "width": width_px * args.voxel_size,
                "height": height_px * args.voxel_size,
                "depth": depth_cells * args.voxel_size,
                "width_pixels": width_px,
                "height_pixels": height_px,
                "depth_pixels": depth_cells,
                "centerX": (x0_px + x1_px) * 0.5,
                "centerY": (y0_px + y1_px) * 0.5,
                "merge_policy": "global_shared_unit_cube_lattice",
                "unit_cube_size": args.voxel_size,
                "merged_cuboids": 0,
            }
        )

    print("SpriteSpatial cuboid parts:")
    for report in reports:
        if "depth" not in report or report["depth"] == 0:
            continue
        print(
            "  {name}: width={width:.3f}, height={height:.3f}, depth={depth:.3f}, centerX={centerX:.2f}, centerY={centerY:.2f}".format(
                **report
            )
        )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
    }, reports


def _build_global_unit_cube_lattice(front: Image.Image, part_boxes: list[dict], alpha_threshold: int) -> tuple[set[tuple[int, int, int]], dict[tuple[int, int, int], dict], dict[int, int]]:
    source_rgba = front.convert("RGBA")
    occupied: set[tuple[int, int, int]] = set()
    voxel_owner: dict[tuple[int, int, int], dict] = {}
    part_depths: dict[int, int] = {}
    for part_index, part in enumerate(part_boxes):
        depth_cells = _part_depth_cells(part)
        part_depths[part_index] = depth_cells
        for x, y in sorted(part["pixels"]):
            if not (0 <= x < front.width and 0 <= y < front.height):
                continue
            if _source_rgba_at(source_rgba, x, y)[3] <= alpha_threshold:
                continue
            # z=0 is the authoritative front plane for every part. Extra
            # depth grows backward only, so the side view is one coherent
            # cubic lattice instead of many locally-centered slabs.
            for depth_index in range(depth_cells):
                z = -depth_index
                key = (x, y, z)
                occupied.add(key)
                voxel_owner[key] = {
                    "part_id": part_index,
                    "part_name": part["name"],
                    "source_xy": (x, y),
                }
    return occupied, voxel_owner, part_depths


def _part_depth_cells(part: dict) -> int:
    x0_px, _y0_px, x1_px, _y1_px = part["bbox"]
    width_px = x1_px - x0_px
    name = part["name"]
    if name == "outline":
        return 1
    semantic_depth = int(round(width_px * _depth_multiplier_for_part(name)))
    minimum_depths = {
        "head": 4,
        "face": 4,
        "hair": 4,
        "torso": 4,
        "left_arm": 3,
        "right_arm": 3,
        "left_leg": 3,
        "right_leg": 3,
        "left_foot": 4,
        "right_foot": 4,
        "equipment": 3,
        "unknown": 3,
    }
    return max(minimum_depths.get(name, 3), semantic_depth)


def _emit_global_unit_cube_surface( # type: ignore[no-untyped-def]
    front: Image.Image,
    occupied: set[tuple[int, int, int]],
    voxel_owner: dict[tuple[int, int, int], dict],
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    pixel_size: float,
    total_height: float,
) -> dict[int, int]:
    source_rgba = front.convert("RGBA")
    total_width = front.width * pixel_size
    face_counts: dict[int, int] = {}
    for x, y, z in sorted(occupied):
        owner = voxel_owner[(x, y, z)]
        part_id = owner["part_id"]
        sx, sy = owner["source_xy"]
        source_pixel = _source_rgba_at(source_rgba, sx, sy)
        if source_pixel[3] == 0:
            continue
        x0 = x * pixel_size - total_width * 0.5
        x1 = x0 + pixel_size
        y0 = total_height - (y + 1) * pixel_size
        y1 = total_height - y * pixel_size
        z0 = (z - 0.5) * pixel_size
        z1 = z0 + pixel_size
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            is_front_face = face == "front" and z == 0
            colour = _rgba_float(source_pixel) if is_front_face else _vibrant_side_colour(source_pixel)
            _add_cuboid_face(
                vertices,
                normals,
                colors,
                indices,
                part_ids,
                part_id,
                face,
                x0,
                x1,
                y0,
                y1,
                z0,
                z1,
                colour,
            )
            face_counts[part_id] = face_counts.get(part_id, 0) + 1
    return face_counts


def createCuboidForPart(front: Image.Image, part: dict, part_id: int, vertices: list[list[float]], normals: list[list[float]], colors: list[list[float]], indices: list[int], part_ids: list[int], pixel_size: float, total_height: float) -> dict:
    x0_px, y0_px, x1_px, y1_px = part["bbox"]
    width_px = x1_px - x0_px
    height_px = y1_px - y0_px
    center_x = (x0_px + x1_px) * 0.5
    center_y = (y0_px + y1_px) * 0.5
    depth_multiplier = _depth_multiplier_for_part(part["name"])
    if part["name"] == "outline":
        depth_px = 1.0
    else:
        depth_px = max(1.0, width_px * depth_multiplier)
    depth_cells = max(1, int(round(depth_px)))
    occupied = _part_unit_cube_occupancy(part["pixels"], depth_cells)
    face_count = _emit_unit_cube_surface(
        front,
        occupied,
        part_id,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        pixel_size,
        total_height,
    )
    return {
        "region_id": part_id,
        "name": part["name"],
        "label": part["name"],
        "semantic_label": part.get("semantic_label", part["name"]),
        "pixel_count": len(part["pixels"]),
        "voxel_count": len(occupied),
        "exposed_faces": face_count,
        "width": width_px * pixel_size,
        "height": height_px * pixel_size,
        "depth": depth_cells * pixel_size,
        "width_pixels": width_px,
        "height_pixels": height_px,
        "depth_pixels": depth_cells,
        "centerX": center_x,
        "centerY": center_y,
        "merge_policy": "semantic_unit_cube_lattice",
        "unit_cube_size": pixel_size,
        "merged_cuboids": 0,
    }


def createCuboidRectForPart( # type: ignore[no-untyped-def]
    front: Image.Image,
    rectangle: dict,
    depth_px: float,
    part_id: int,
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    part_ids: list[int],
    pixel_size: float,
    total_height: float,
) -> int:
    x0_px, y0_px, x1_px, y1_px = rectangle["bbox"]
    pixel = rectangle["colour"]
    x0 = x0_px * pixel_size - front.width * pixel_size * 0.5
    x1 = x1_px * pixel_size - front.width * pixel_size * 0.5
    y0 = total_height - y1_px * pixel_size
    y1 = total_height - y0_px * pixel_size
    z0 = -depth_px * pixel_size * 0.5
    z1 = depth_px * pixel_size * 0.5
    front_colour = _rgba_float(pixel)
    side_colour = _vibrant_side_colour(pixel)
    for face in ("back", "front", "left", "right", "up", "down"):
        _add_cuboid_face(
            vertices,
            normals,
            colors,
            indices,
            part_ids,
            part_id,
            face,
            x0,
            x1,
            y0,
            y1,
            z0,
            z1,
            front_colour if face == "front" else side_colour,
        )
    return 6


def _part_unit_cube_occupancy(pixel_coords: set[tuple[int, int]], depth_cells: int) -> set[tuple[int, int, int]]:
    return {
        (x, y, z_index)
        for x, y in pixel_coords
        for z_index in range(depth_cells)
    }


def _emit_unit_cube_surface(
    front: Image.Image,
    occupied: set[tuple[int, int, int]],
    part_id: int,
    vertices,
    normals,
    colors,
    indices,
    part_ids,
    pixel_size: float,
    total_height: float,
) -> int:
    source_rgba = front.convert("RGBA")
    total_width = front.width * pixel_size
    face_count = 0
    if not occupied:
        return face_count
    min_z = min(z for _x, _y, z in occupied)
    max_z = max(z for _x, _y, z in occupied)
    depth_cells = max_z - min_z + 1
    max_z_by_pixel: dict[tuple[int, int], int] = {}
    for x, y, z in occupied:
        max_z_by_pixel[(x, y)] = max(z, max_z_by_pixel.get((x, y), z))
    for x, y, z in sorted(occupied):
        x0 = x * pixel_size - total_width * 0.5
        x1 = x0 + pixel_size
        y0 = total_height - (y + 1) * pixel_size
        y1 = total_height - y * pixel_size
        z0 = (z - min_z - depth_cells * 0.5) * pixel_size
        z1 = z0 + pixel_size
        source_pixel = _source_rgba_at(source_rgba, x, y)
        if source_pixel[3] == 0:
            continue
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            is_front_face = face == "front" and z == max_z_by_pixel[(x, y)]
            colour = _rgba_float(source_pixel) if is_front_face else _vibrant_side_colour(source_pixel)
            _add_cuboid_face(
                vertices,
                normals,
                colors,
                indices,
                part_ids,
                part_id,
                face,
                x0,
                x1,
                y0,
                y1,
                z0,
                z1,
                colour,
            )
            face_count += 1
    return face_count


def createPixelCubeForPart( # type: ignore[no-untyped-def]
    front: Image.Image,
    x: int,
    y: int,
    depth_px: float,
    part_id: int,
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    part_ids: list[int],
    pixel_size: float,
    total_height: float,
    pixel,
) -> int:
    return createCuboidRectForPart(
        front,
        {"bbox": [x, y, x + 1, y + 1], "colour": pixel},
        depth_px,
        part_id,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        pixel_size,
        total_height,
    )


def _greedy_rectangles_for_part(front: Image.Image, part: dict) -> list[dict]:
    source_rgba = front.convert("RGBA")
    remaining = set(part["pixels"])
    rectangles: list[dict] = []
    while remaining:
        start_x, start_y = min(remaining, key=lambda pixel: (pixel[1], pixel[0]))
        colour = _source_rgba_at(source_rgba, start_x, start_y)
        width = 1
        while (start_x + width, start_y) in remaining and _source_rgba_at(source_rgba, start_x + width, start_y) == colour:
            width += 1

        height = 1
        while True:
            next_y = start_y + height
            row_pixels = {(x, next_y) for x in range(start_x, start_x + width)}
            if not row_pixels.issubset(remaining):
                break
            if any(_source_rgba_at(source_rgba, x, next_y) != colour for x in range(start_x, start_x + width)):
                break
            height += 1

        for y in range(start_y, start_y + height):
            for x in range(start_x, start_x + width):
                remaining.remove((x, y))
        rectangles.append(
            {
                "bbox": [start_x, start_y, start_x + width, start_y + height],
                "colour": colour,
                "pixel_count": width * height,
            }
        )
    return rectangles


def buildCharacterRoot(parts: list[dict]) -> dict:
    return {"name": "GeneratedSpriteModel", "parts": parts}


def enableDepthDebugMode(model: dict, enabled: bool = True) -> dict:
    model["debug_depth_mode_enabled"] = enabled
    return model


def _semantic_part_label(region_info, pixels, mid_x: float, sprite_height: int) -> str:
    red, green, blue, _alpha = region_info.dominant_colour
    bbox = region_info.bbox
    cx, cy = region_info.centroid
    lower = cy > sprite_height * 0.58
    upper = cy < sprite_height * 0.36
    middle = not upper and not lower
    is_skin = red > 180 and green > 110 and blue < 150
    is_hair_or_shoe = red > 70 and red < 170 and green < 120 and blue < 90
    is_shirt = blue > 130 and green > 110 and red < 120
    is_pants = blue > 120 and red < 100 and green < 130

    if upper and is_hair_or_shoe:
        return "hair"
    if upper and is_skin:
        return "head"
    if middle and is_shirt:
        return "torso"
    if middle and is_skin:
        return "left_arm" if cx < mid_x else "right_arm"
    if lower and is_pants:
        return "split_legs"
    if lower and is_hair_or_shoe:
        return "split_feet"
    if region_info.likely_label in {"left_arm", "right_arm", "torso", "head", "face"}:
        return "head" if region_info.likely_label == "face" else region_info.likely_label
    if lower:
        return "split_feet" if (bbox[2] - bbox[0]) > 2 else "split_legs"
    return "torso"


def _depth_multiplier_for_part(name: str) -> float:
    mapping = {
        "outline": 0.95,
        "head": 0.8,
        "face": 0.72,
        "hair": 0.85,
        "torso": 0.55,
        "left_arm": 0.7,
        "right_arm": 0.7,
        "left_leg": 0.65,
        "right_leg": 0.65,
        "left_foot": 1.1,
        "right_foot": 1.1,
        "equipment": 0.4,
        "unknown": 0.45,
    }
    return mapping.get(name, 0.55)


def _pixel_bbox(pixels_set: set[tuple[int, int]]) -> list[int]:
    xs = [x for x, _y in pixels_set]
    ys = [y for _x, y in pixels_set]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def _source_rgba_at(source_rgba: Image.Image, x: int, y: int) -> tuple[int, int, int, int]:
    if source_rgba.mode != "RGBA":
        source_rgba = source_rgba.convert("RGBA")
    pixel = source_rgba.getpixel((x, y))
    if not isinstance(pixel, tuple) or len(pixel) < 4:
        raise ValueError("Expected RGBA pixel data.")
    red, green, blue, alpha = pixel[:4]
    return int(red), int(green), int(blue), int(alpha)


def _dominant_colour(front: Image.Image, pixels_set: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    source_rgba = front.convert("RGBA")
    colours = [
        _source_rgba_at(source_rgba, x, y)
        for x, y in pixels_set
        if _source_rgba_at(source_rgba, x, y)[3] > 0
    ]
    if not colours:
        return (255, 0, 255, 255)
    return max(set(colours), key=colours.count)


def _rgba_float(colour: tuple[int, int, int, int]) -> list[float]:
    return [colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, colour[3] / 255.0]


def _vibrant_side_colour(colour: tuple[int, int, int, int]) -> list[float]:
    red, green, blue, alpha = colour
    if max(red, green, blue) <= 72:
        factor = 0.9
    else:
        factor = 0.75
    return [red / 255.0 * factor, green / 255.0 * factor, blue / 255.0 * factor, alpha / 255.0]


def _apply_surface_net_vertex_colours(mesh: dict[str, Any], front: Image.Image) -> None:
    source_rgba = front.convert("RGBA")
    width, height = source_rgba.size
    pixels = source_rgba.load()
    source_scale = max(1.0, float(mesh.get("config", {}).get("sdf_resolution_scale", 1.0)))
    vertices = mesh.get("vertices", [])
    metadata = mesh.get("vertex_metadata", [])
    colours: list[list[float]] = []

    for index, vertex in enumerate(vertices):
        item = metadata[index] if index < len(metadata) and isinstance(metadata[index], dict) else {}
        source_cell = item.get("source_cell")
        if isinstance(source_cell, list) and len(source_cell) >= 2:
            sample_x = int(round(float(source_cell[1]) / source_scale))
            sample_y = int(round(float(source_cell[0]) / source_scale))
        elif isinstance(vertex, list) and len(vertex) >= 2:
            sample_x = int(round(float(vertex[0]) / source_scale))
            sample_y = int(round(float(vertex[1]) / source_scale))
        else:
            sample_x = 0
            sample_y = 0
        colours.append(_sample_surface_vertex_colour(pixels, width, height, sample_x, sample_y))

    if colours:
        mesh["colors"] = colours
        mesh["color_source"] = "front_sprite_projected_from_surface_net_source_cells"
        mesh["color_stats"] = {
            "vertex_color_count": len(colours),
            "vertex_count": len(vertices),
            "source_scale": source_scale,
            "unique_vertex_colours": len({tuple(round(channel, 4) for channel in colour[:3]) for colour in colours}),
        }


def _sample_surface_vertex_colour(pixels: Any, width: int, height: int, sample_x: int, sample_y: int) -> list[float]:
    clamped_x = min(max(sample_x, 0), max(width - 1, 0))
    clamped_y = min(max(sample_y, 0), max(height - 1, 0))
    direct = pixels[clamped_x, clamped_y]
    if direct[3] > 16:
        return _rgba_float((int(direct[0]), int(direct[1]), int(direct[2]), int(direct[3])))
    for radius in range(1, 5):
        best: tuple[int, int, int, int] | None = None
        best_distance = radius * radius * 4 + 1
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x = clamped_x + dx
                y = clamped_y + dy
                if x < 0 or y < 0 or x >= width or y >= height:
                    continue
                pixel = pixels[x, y]
                if pixel[3] <= 16:
                    continue
                distance = dx * dx + dy * dy
                if distance < best_distance:
                    best = (int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3]))
                    best_distance = distance
        if best is not None:
            return _rgba_float(best)
    return [0.55, 0.57, 0.62, 1.0]


def _build_voxel_depth_mesh(
    front: Image.Image,
    back_path: Path | None,
    side_path: Path | None,
    occupancy: np.ndarray,
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    side = _voxel_depth_side_image(side_path, front)
    relief_occupancy, relief_report = _build_front_led_voxel_occupancy(
        front,
        occupancy,
        alpha_threshold=int(getattr(args, "alpha_threshold", 16)),
        side=side,
    )
    volume = _volume_from_occupancy(relief_occupancy)
    back = _voxel_depth_back_image(back_path, front)
    colour_field, colour_report = build_colour_field(
        front,
        back,
        volume,
        mode="nearest_valid_edge",
        alpha_threshold=int(getattr(args, "alpha_threshold", 16)),
    )
    mesh, mesh_report = build_surface_mesh(
        volume,
        colour_field,
        MeshBuildConfig(
            voxel_size=float(getattr(args, "voxel_size", 0.05)),
            model_depth_units=float(getattr(args, "model_depth_units", 0.60)),
            simplify_mesh=False,
            cleanup_mode="exposed_voxel_faces",
        ),
    )
    mesh.update(
        {
            "schema": "spritespatial_voxel_depth_mesh_v1",
            "mesh_backend": "voxel_depth",
            "color_source": "nearest_front_or_back_sprite_per_exposed_voxel_face",
            "config": {
                "mesh_backend": "voxel_depth",
                "voxel_size": float(getattr(args, "voxel_size", 0.05)),
                "model_depth_units": float(getattr(args, "model_depth_units", 0.60)),
                "depth_slices": len(volume),
                "colour_mode": "nearest_valid_edge",
                "face_vertex_policy": "unique_vertices_per_face",
                "pixel_art_interpolation": False,
                "front_axis": "+z",
                "y_axis": "image_top_maps_to_positive_y",
                "geometry_authority": "front_sprite_relief",
                "back_view_role": "colour_only",
                "side_view_role": "bounded_depth_cap" if side is not None else "reference_only",
            },
        }
    )
    actual_dimensions = _mesh_bounding_box_dimensions(mesh.get("vertices", []))
    report = {
        "schema": "spritespatial_voxel_depth_report_v1",
        "mesh_backend": "voxel_depth",
        "passed": bool(mesh_report.get("vertex_count", 0) > 0 and mesh_report.get("triangle_count", 0) > 0),
        "voxel_depth_vertices": int(mesh_report.get("vertex_count", 0)),
        "voxel_depth_triangles": int(mesh_report.get("triangle_count", 0)),
        "voxel_depth_exposed_faces": int(mesh_report.get("exposed_face_count", 0)),
        "voxel_depth_internal_faces_removed": int(mesh_report.get("internal_faces_removed", 0)),
        "voxel_depth_material_colour_count": int(mesh_report.get("material_colour_count", 0)),
        "voxel_depth_black_side_face_percentage": float(mesh_report.get("black_side_face_percentage", 0.0)),
        "voxel_depth_occupied_voxels": int(np.count_nonzero(relief_occupancy)),
        "voxel_depth_shape": list(relief_occupancy.shape),
        "colour_fallback_count": int(colour_report.get("fallback_colour_count", 0)),
        "bounding_box_dimensions": actual_dimensions,
        "voxel_grid_dimensions": mesh_report.get("bounding_box_dimensions", []),
        **relief_report,
        "back_view_colour_used": bool(back_path and back_path.exists()),
    }
    mesh_path = output_dir / "mesh.json"
    report_path = output_dir / "voxel_depth_report.json"
    write_mesh_json(mesh, mesh_path)
    _write_json(report_path, report)
    return {"mesh": mesh, "report": report, "paths": {"mesh": mesh_path, "voxel_depth_report": report_path}}


def _build_front_led_voxel_occupancy(
    front: Image.Image,
    source_occupancy: np.ndarray,
    alpha_threshold: int = 16,
    side: Image.Image | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    if source_occupancy.ndim != 3:
        raise ValueError(f"Expected 3D occupancy volume, got shape {source_occupancy.shape}")
    height, width, depth = source_occupancy.shape
    rgba = np.asarray(
        front.convert("RGBA").resize((width, height), Image.Resampling.NEAREST),
        dtype=np.uint8,
    )
    alpha = rgba[:, :, 3] > int(alpha_threshold)
    if not bool(np.any(alpha)) or depth <= 0:
        return source_occupancy.copy(), {
            "geometry_authority": "closed_sdf_fallback",
            "front_relief_fallback": True,
            "side_view_geometry_used": False,
            "back_view_geometry_used": False,
        }

    coverage_by_slice = source_occupancy.sum(axis=(0, 1))
    peak_coverage = int(coverage_by_slice.max()) if coverage_by_slice.size else 0
    centre_candidates = np.flatnonzero(coverage_by_slice == peak_coverage)
    centre_index = int(round(float(centre_candidates.mean()))) if centre_candidates.size else depth // 2

    body_relief = normalise_distance(euclidean_distance_transform(alpha), alpha)
    detail_relief, component_count = _connected_colour_relief(rgba, alpha)
    visible_columns = int(np.count_nonzero(alpha.any(axis=0)))
    target_span = min(depth, max(7, int(round(float(visible_columns) * 1.15))))
    front_max_radius = max(4, int(round(float(target_span - 1) * 0.58)))
    back_max_radius = max(2, target_span - 1 - front_max_radius)
    front_max_radius = min(front_max_radius, max(0, depth - 1 - centre_index))
    back_max_radius = min(back_max_radius, max(0, centre_index))
    front_base = min(2, max(1, front_max_radius - 1))
    back_base = min(2, max(1, back_max_radius - 1))
    detail_budget = min(3, max(1, front_max_radius - front_base - 1))
    body_front_budget = max(0, front_max_radius - front_base - detail_budget)
    body_back_budget = max(0, back_max_radius - back_base)
    side_caps, side_cap_report = _side_depth_caps(
        side,
        alpha,
        target_span,
        int(alpha_threshold),
    )

    occupancy = np.zeros_like(source_occupancy, dtype=bool)
    thicknesses: list[int] = []
    front_radii: list[int] = []
    back_radii: list[int] = []
    for y, x in np.argwhere(alpha):
        body = float(body_relief[int(y), int(x)])
        detail = float(detail_relief[int(y), int(x)])
        front_radius = min(
            front_max_radius,
            front_base + int(round(body * body_front_budget + detail * detail_budget)),
        )
        back_radius = min(back_max_radius, back_base + int(round(body * body_back_budget)))
        side_cap = side_caps.get(int(y))
        if side_cap is not None:
            capped_front = max(1, int(round(float(side_cap - 1) * 0.58)))
            capped_back = max(1, side_cap - 1 - capped_front)
            front_radius = min(front_radius, capped_front)
            back_radius = min(back_radius, capped_back)
        z_start = max(0, centre_index - back_radius)
        z_end = min(depth - 1, centre_index + front_radius)
        occupancy[int(y), int(x), z_start : z_end + 1] = True
        thicknesses.append(z_end - z_start + 1)
        front_radii.append(z_end - centre_index)
        back_radii.append(centre_index - z_start)

    occupied_slices = np.flatnonzero(occupancy.any(axis=(0, 1)))
    return occupancy, {
        "geometry_authority": "front_alpha_local_colour_relief",
        "front_relief_fallback": False,
        "front_relief_center_slice": centre_index,
        "front_relief_colour_component_count": component_count,
        "front_relief_target_depth_slices": target_span,
        "front_relief_occupied_depth_slices": int(len(occupied_slices)),
        "front_relief_peak_slices": max(front_radii, default=0),
        "back_relief_peak_slices": max(back_radii, default=0),
        "front_relief_min_column_slices": min(thicknesses, default=0),
        "front_relief_max_column_slices": max(thicknesses, default=0),
        "front_relief_mean_column_slices": float(np.mean(thicknesses)) if thicknesses else 0.0,
        "side_view_geometry_used": bool(side_cap_report.get("side_view_depth_cap_used", False)),
        **side_cap_report,
        "back_view_geometry_used": False,
    }


def _side_depth_caps(
    side: Image.Image | None,
    front_alpha: np.ndarray,
    target_span: int,
    alpha_threshold: int,
) -> tuple[dict[int, int], dict[str, Any]]:
    disabled = {
        "side_view_depth_cap_used": False,
        "side_view_voxels_added": False,
        "side_view_depth_cap_rows": 0,
        "side_view_depth_cap_reason": "side_missing",
    }
    if side is None:
        return {}, disabled

    height, width = front_alpha.shape
    side_rgba = np.asarray(
        side.convert("RGBA").resize((width, height), Image.Resampling.NEAREST),
        dtype=np.uint8,
    )
    side_alpha = side_rgba[:, :, 3] > int(alpha_threshold)
    front_rows = np.flatnonzero(front_alpha.any(axis=1))
    side_rows = np.flatnonzero(side_alpha.any(axis=1))
    if front_rows.size == 0 or side_rows.size == 0:
        return {}, {**disabled, "side_view_depth_cap_reason": "empty_silhouette"}

    front_height = int(front_rows[-1] - front_rows[0] + 1)
    side_height = int(side_rows[-1] - side_rows[0] + 1)
    height_ratio = float(side_height / max(front_height, 1))
    area_ratio = float(np.count_nonzero(side_alpha) / max(np.count_nonzero(front_alpha), 1))
    if not (0.75 <= height_ratio <= 1.25 and 0.45 <= area_ratio <= 1.80):
        return {}, {
            **disabled,
            "side_view_depth_cap_reason": "silhouette_mismatch",
            "side_view_height_ratio": height_ratio,
            "side_view_area_ratio": area_ratio,
        }

    side_spans: dict[int, int] = {}
    for side_y in side_rows:
        xs = np.flatnonzero(side_alpha[int(side_y)])
        if xs.size:
            side_spans[int(side_y)] = int(xs[-1] - xs[0] + 1)
    max_side_span = max(side_spans.values(), default=0)
    if max_side_span < 2:
        return {}, {**disabled, "side_view_depth_cap_reason": "side_too_thin"}

    caps: dict[int, int] = {}
    for front_y in front_rows:
        progress = float(int(front_y) - int(front_rows[0])) / float(max(front_height - 1, 1))
        side_y = int(round(float(side_rows[0]) + progress * float(side_height - 1)))
        span = side_spans.get(side_y)
        if span is None:
            nearest = min(side_spans, key=lambda candidate: abs(candidate - side_y))
            span = side_spans[nearest]
        caps[int(front_y)] = max(3, min(target_span, int(round(float(target_span) * span / max_side_span))))

    return caps, {
        "side_view_depth_cap_used": True,
        "side_view_voxels_added": False,
        "side_view_depth_cap_rows": len(caps),
        "side_view_depth_cap_reason": "trusted_silhouette_envelope",
        "side_view_height_ratio": height_ratio,
        "side_view_area_ratio": area_ratio,
        "side_view_max_source_span": max_side_span,
        "side_view_min_depth_cap_slices": min(caps.values(), default=0),
        "side_view_max_depth_cap_slices": max(caps.values(), default=0),
    }


def _connected_colour_relief(rgba: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = alpha.shape
    visited = np.zeros(alpha.shape, dtype=bool)
    relief = np.zeros(alpha.shape, dtype=np.float32)
    component_count = 0
    for start_y, start_x in np.argwhere(alpha):
        y = int(start_y)
        x = int(start_x)
        if visited[y, x]:
            continue
        component_count += 1
        colour = tuple(int(channel) for channel in rgba[y, x, :3])
        stack = [(y, x)]
        visited[y, x] = True
        component: list[tuple[int, int]] = []
        while stack:
            current_y, current_x = stack.pop()
            component.append((current_y, current_x))
            for next_y, next_x in (
                (current_y - 1, current_x),
                (current_y + 1, current_x),
                (current_y, current_x - 1),
                (current_y, current_x + 1),
            ):
                if next_y < 0 or next_x < 0 or next_y >= height or next_x >= width:
                    continue
                if visited[next_y, next_x] or not alpha[next_y, next_x]:
                    continue
                if tuple(int(channel) for channel in rgba[next_y, next_x, :3]) != colour:
                    continue
                visited[next_y, next_x] = True
                stack.append((next_y, next_x))

        ys, xs = zip(*component)
        min_y, max_y = min(ys), max(ys)
        min_x, max_x = min(xs), max(xs)
        component_mask = np.zeros((max_y - min_y + 3, max_x - min_x + 3), dtype=bool)
        local_ys = np.asarray(ys) - min_y + 1
        local_xs = np.asarray(xs) - min_x + 1
        component_mask[local_ys, local_xs] = True
        component_relief = normalise_distance(
            euclidean_distance_transform(component_mask),
            component_mask,
        )
        area_weight = min(1.0, float(len(component)) ** 0.5 / 3.0)
        if max(colour) <= 72:
            area_weight *= 0.15
        relief[np.asarray(ys), np.asarray(xs)] = np.maximum(
            relief[np.asarray(ys), np.asarray(xs)],
            component_relief[local_ys, local_xs] * area_weight,
        )
    return relief, component_count


def _mesh_bounding_box_dimensions(vertices: list[list[float]]) -> list[float]:
    if not vertices:
        return [0.0, 0.0, 0.0]
    array = np.asarray(vertices, dtype=np.float64)
    return [float(value) for value in (array.max(axis=0) - array.min(axis=0))]


def _volume_from_occupancy(occupancy: np.ndarray) -> list[list[list[bool]]]:
    if occupancy.ndim != 3:
        raise ValueError(f"Expected 3D occupancy volume, got shape {occupancy.shape}")
    height, width, depth = occupancy.shape
    return [
        [
            [bool(occupancy[y, x, z]) for x in range(width)]
            for y in range(height)
        ]
        for z in range(depth)
    ]


def _voxel_depth_back_image(back_path: Path | None, front: Image.Image) -> Image.Image:
    if back_path and back_path.exists():
        back = Image.open(back_path).convert("RGBA")
        if back.size != front.size:
            back = back.resize(front.size, Image.Resampling.NEAREST)
        return back
    return front.convert("RGBA")


def _voxel_depth_side_image(side_path: Path | None, front: Image.Image) -> Image.Image | None:
    if not side_path or not side_path.exists():
        return None
    side = Image.open(side_path).convert("RGBA")
    if side.size != front.size:
        side = side.resize(front.size, Image.Resampling.NEAREST)
    return side


def _add_cuboid_front_sprite_shell(front: Image.Image, regions, vertices, normals, colors, indices, part_ids, args, z_front: float) -> int:
    source_rgba = front.convert("RGBA")
    width, height = front.size
    pixel_size = args.voxel_size
    total_width = width * pixel_size
    total_height = height * pixel_size
    shell_z = pixel_size * 0.025
    shell_id = -501
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = _source_rgba_at(source_rgba, x, y)
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * pixel_size - total_width * 0.5
            x1 = x0 + pixel_size
            y0 = total_height - (y + 1) * pixel_size
            y1 = total_height - y * pixel_size
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z_front - shell_z, z_front, pixel)
            face_count += 1
    return face_count


def _max_z(vertices: list[list[float]]) -> float:
    if not vertices:
        return 0.0
    return max(vertex[2] for vertex in vertices)


def _build_relief_cutout_mesh(front: Image.Image, regions, graph, assignments, args) -> tuple[dict, list[dict]]:
    source_rgba = front.convert("RGBA")
    width, height = front.size
    depth_slices = max(5, args.relief_depth_slices)
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.relief_depth_units / depth_slices
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.relief_depth_units * 0.5

    region_by_pixel: dict[tuple[int, int], int] = {}
    label_by_region: dict[int, str] = {}
    for region_info, region in zip(graph, regions):
        label_by_region[region_info.region_id] = region_info.likely_label
        for x, y in region:
            region_by_pixel[(x, y)] = region_info.region_id

    occupied: set[tuple[int, int, int]] = set()
    pixel_z_ranges: dict[tuple[int, int], tuple[int, int]] = {}
    for region_info, region in zip(graph, regions):
        label = region_info.likely_label
        z_min, z_max = _relief_z_range(label, depth_slices)
        for x, y in region:
            pixel_z_ranges[(x, y)] = (z_min, z_max)
            for z in range(z_min, z_max + 1):
                occupied.add((x, y, z))

    vertices: list[list[float]] = []
    normals: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    part_ids: list[int] = []
    exposed_faces = 0

    for x, y, z in sorted(occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        region_id = region_by_pixel.get((x, y), -1)
        label = label_by_region.get(region_id, "unknown")
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in occupied:
                continue
            exposed_faces += 1
            colour = _relief_face_colour(_source_rgba_at(source_rgba, x, y), label, face)
            _add_face(vertices, normals, colors, indices, part_ids, region_id, face, x0, x1, y0, y1, z0, z1, colour)

    shell_faces = _add_relief_front_sprite_shell(
        front,
        regions,
        vertices,
        normals,
        colors,
        indices,
        part_ids,
        args,
        args.relief_depth_units * 0.5 + voxel_z * 0.08,
    )
    reports = [
        {
            "region_id": -400,
            "label": "relief_cutout_body",
            "pixel_count": len(pixel_z_ranges),
            "voxel_count": len(occupied),
            "exposed_faces": exposed_faces,
            "z_offset": 0.0,
            "local_depth": args.relief_depth_units,
            "merge_policy": "coherent_relief_cutout",
        },
        {
            "region_id": -401,
            "label": "authoritative_front_sprite_shell",
            "pixel_count": shell_faces,
            "voxel_count": 0,
            "exposed_faces": shell_faces,
            "z_offset": 0.5,
            "local_depth": 0.0,
            "merge_policy": "preserve_source_pixels",
        },
    ]
    reports.extend(
        {
            "region_id": region.region_id,
            "label": region.likely_label,
            "pixel_count": region.pixel_count,
            "voxel_count": sum((pixel_z_ranges[pixel][1] - pixel_z_ranges[pixel][0] + 1) for pixel in regions[region.region_id]),
            "exposed_faces": 0,
            "z_offset": 0.0,
            "local_depth": args.relief_depth_units,
            "merge_policy": "relief_metadata_region",
        }
        for region in graph
    )
    return {
        "vertices": vertices,
        "normals": normals,
        "colors": colors,
        "indices": indices,
        "part_ids": part_ids,
        "occupied_voxels": len(occupied),
    }, reports


def _relief_z_range(label: str, depth_slices: int) -> tuple[int, int]:
    back = 0
    front = depth_slices - 1
    if label == "outline":
        return max(0, front - 2), front
    if label in {"face", "head"}:
        return max(0, front - 5), front
    if label in {"hat", "hair"}:
        return max(0, front - 4), front
    if label in {"left_arm", "right_arm", "equipment"}:
        return max(0, front - 4), front
    if label == "torso":
        return max(0, front - 6), front - 1
    if label in {"legs", "boots"}:
        return back + 1, max(back + 4, front - 2)
    return max(0, front - 4), front - 1


def _relief_face_colour(source_pixel: tuple[int, int, int, int], label: str, face: str) -> tuple[int, int, int, int]:
    if face == "front":
        return source_pixel
    if label == "outline" or max(source_pixel[0], source_pixel[1], source_pixel[2]) <= 72:
        return (24, 24, 24, source_pixel[3])
    if face == "back":
        factor = 0.9
    else:
        factor = 0.88
    return (int(source_pixel[0] * factor), int(source_pixel[1] * factor), int(source_pixel[2] * factor), source_pixel[3])


def _add_relief_front_sprite_shell(front: Image.Image, regions, vertices: list[list[float]], normals: list[list[float]], colors: list[list[float]], indices: list[int], part_ids: list[int], args, z_front: float) -> int:
    source_rgba = front.convert("RGBA")
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    shell_z = args.relief_depth_units / max(args.relief_depth_slices, 1) * 0.03
    total_width = width * voxel_x
    total_height = height * voxel_y
    shell_id = -401
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = _source_rgba_at(source_rgba, x, y)
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * voxel_x - total_width * 0.5
            x1 = x0 + voxel_x
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z_front - shell_z, z_front, pixel)
            face_count += 1
    return face_count


def _part_occupancy(region: list[tuple[int, int]], width: int, height: int, total_depth_slices: int, assignment) -> set[tuple[int, int, int]]:
    depth_slices = max(1, int(round(total_depth_slices * assignment.local_depth)))
    center = (total_depth_slices - 1) * (0.5 + assignment.z_offset * 0.45)
    z_min = max(0, int(round(center - depth_slices * 0.5)))
    z_max = min(total_depth_slices - 1, int(round(center + depth_slices * 0.5)))
    if assignment.label == "outline":
        # Rim pixels become a bevel shell, not a full-depth wall.
        z_mid = total_depth_slices - 2
        z_min = max(0, z_mid - 1)
        z_max = total_depth_slices - 1
    occupied: set[tuple[int, int, int]] = set()
    for x, y in region:
        for z in range(z_min, z_max + 1):
            occupied.add((x, y, z))
    return occupied


def _part_face_colour(source_pixel: tuple[int, int, int, int], dominant_colour: tuple[int, int, int, int], label: str, face: str) -> tuple[tuple[int, int, int, int], bool]:
    if face == "front":
        return (source_pixel[0], source_pixel[1], source_pixel[2], source_pixel[3]), False
    red, green, blue, alpha = dominant_colour
    used_fallback = False
    if alpha == 0:
        red, green, blue, alpha = source_pixel[0], source_pixel[1], source_pixel[2], source_pixel[3]
        used_fallback = alpha == 0
    if label == "outline" and face not in {"front", "back"}:
        red = min(red, 36)
        green = min(green, 36)
        blue = min(blue, 36)
    elif face not in {"front", "back"}:
        red = int(red * 0.86)
        green = int(green * 0.86)
        blue = int(blue * 0.86)
    return (red, green, blue, alpha), used_fallback


def _add_silhouette_core( # type: ignore[no-untyped-def]
    front: Image.Image,
    regions,
    existing_occupied: set[tuple[int, int, int]],
    region_lookup: dict[tuple[int, int], int],
    region_colour_lookup: dict[int, list[int]],
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    part_ids: list[int],
    args,
) -> dict:
    width, height = front.size
    source_rgba = front.convert("RGBA")
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z_start = -args.model_depth_units * 0.5
    core_id = -100
    z_min = max(0, args.total_depth_slices // 2 - 2)
    z_max = min(args.total_depth_slices - 3, args.total_depth_slices // 2 + 2)
    core_occupied: set[tuple[int, int, int]] = set()
    for region in regions:
        for x, y in region:
            for z in range(z_min, z_max + 1):
                key = (x, y, z)
                if key not in existing_occupied:
                    core_occupied.add(key)
    exposed_faces = 0
    for x, y, z in sorted(core_occupied):
        x0 = x * voxel_x - total_width * 0.5
        x1 = x0 + voxel_x
        y0 = total_height - (y + 1) * voxel_y
        y1 = total_height - y * voxel_y
        z0 = z_start + z * voxel_z
        z1 = z0 + voxel_z
        for face, delta in FACE_DELTAS.items():
            neighbour = (x + delta[0], y + delta[1], z + delta[2])
            if neighbour in existing_occupied or neighbour in core_occupied:
                continue
            exposed_faces += 1
            region_id = region_lookup.get((x, y), -1)
            fallback_pixel = _source_rgba_at(source_rgba, x, y)
            dominant = region_colour_lookup.get(region_id, [fallback_pixel[0], fallback_pixel[1], fallback_pixel[2], fallback_pixel[3]])
            colour = _core_colour(dominant, face)
            _add_face(vertices, normals, colors, indices, part_ids, core_id, face, x0, x1, y0, y1, z0, z1, colour)
    existing_occupied.update(core_occupied)
    return {
        "region_id": core_id,
        "label": "silhouette_core",
        "pixel_count": sum(len(region) for region in regions),
        "voxel_count": len(core_occupied),
        "exposed_faces": exposed_faces,
        "z_offset": 0.0,
        "local_depth": (z_max - z_min + 1) / max(args.total_depth_slices, 1),
        "merge_policy": "coherence_anchor",
    }


def _add_front_ink_shell( # type: ignore[no-untyped-def]
    front: Image.Image,
    regions,
    vertices: list[list[float]],
    normals: list[list[float]],
    colors: list[list[float]],
    indices: list[int],
    part_ids: list[int],
    args,
) -> dict:
    source_rgba = front.convert("RGBA")
    width, height = front.size
    voxel_x = args.voxel_size
    voxel_y = args.voxel_size
    voxel_z = args.model_depth_units / max(args.total_depth_slices, 1)
    total_width = width * voxel_x
    total_height = height * voxel_y
    z1 = args.model_depth_units * 0.5 + voxel_z * 0.06
    z0 = z1 - voxel_z * 0.08
    shell_id = -200
    face_count = 0
    for region in regions:
        for x, y in region:
            pixel = _source_rgba_at(source_rgba, x, y)
            if pixel[3] <= args.alpha_threshold:
                continue
            x0 = x * voxel_x - total_width * 0.5
            x1 = x0 + voxel_x
            y0 = total_height - (y + 1) * voxel_y
            y1 = total_height - y * voxel_y
            _add_face(vertices, normals, colors, indices, part_ids, shell_id, "front", x0, x1, y0, y1, z0, z1, pixel)
            face_count += 1
    return {
        "region_id": shell_id,
        "label": "front_ink_shell",
        "pixel_count": face_count,
        "voxel_count": 0,
        "exposed_faces": face_count,
        "z_offset": 0.5,
        "local_depth": 0.0,
        "merge_policy": "authoritative_front_projection",
    }


def _core_colour(dominant_colour: list[int], face: str) -> tuple[int, int, int, int]:
    red, green, blue, alpha = dominant_colour
    if max(red, green, blue) <= 72:
        return (24, 24, 24, alpha)
    factor = 0.78 if face not in {"front", "back"} else 0.9
    return (int(red * factor), int(green * factor), int(blue * factor), alpha)


def _cuboid_side_color(dominant_colour: tuple[int, int, int, int]) -> list[float]:
    red, green, blue, alpha = dominant_colour
    factor = 0.7
    return [red / 255.0 * factor, green / 255.0 * factor, blue / 255.0 * factor, alpha / 255.0]


def _write_depth_debug(front: Image.Image, regions, assignments: dict[int, Any], path: Path) -> Path:
    debug = Image.new("RGBA", front.size, (0, 0, 0, 0))
    pixels = debug.load()
    if pixels is None:
        raise ValueError("Could not load depth debug pixel buffer.")
    for region_id, region in enumerate(regions):
        assignment = assignments[region_id]
        value = int(max(0.0, min(1.0, assignment.local_depth + assignment.z_offset * 0.35)) * 255)
        for x, y in region:
            pixels[x, y] = (value, value, value, 255)
    debug.save(path, format="PNG")
    return path


def _validation_report(front: Image.Image, regions, mesh: dict, part_reports: list[dict], args, semantic_warnings=None) -> dict:
    total_faces = len(mesh["indices"]) // 6
    fallback_faces = 0
    colours = {
        tuple(int(channel * 255) for channel in colour)
        for colour in mesh["colors"]
    }
    alpha = front.getchannel("A")
    opaque_pixels = sum(1 for value in alpha.tobytes() if value > args.alpha_threshold)
    transparent_pixels = front.width * front.height - opaque_pixels
    bounds = _mesh_bounds(mesh["vertices"])
    fallback_percent = fallback_faces / total_faces if total_faces else 1.0
    zfield_enabled = bool(getattr(args, "use_zfield", False))
    primitive_enabled = bool(getattr(args, "use_primitives", False))
    primitive_counts = mesh.get("primitive_count_by_type", {})
    depth_reports = [
        report for report in part_reports
        if report.get("pixel_count", 0) > 0 and report.get("region_id", 0) >= 0
    ]
    average_region_depth = (
        sum(float(report.get("average_depth", report.get("local_depth", 0.0))) for report in depth_reports)
        / max(len(depth_reports), 1)
    )
    depth_by_region = {
        str(report.get("region_id")): {
            "min": report.get("min_depth", report.get("local_depth", 0.0)),
            "max": report.get("max_depth", report.get("local_depth", 0.0)),
        }
        for report in depth_reports
    }
    outline_shell_voxel_count = sum(
        int(report.get("voxel_count", 0))
        for report in depth_reports
        if report.get("primitive_type") == "shell" or report.get("label") == "outline"
    )
    malformed_region_count = sum(1 for report in depth_reports if report.get("malformed", False))
    fallback_primitive_count = sum(1 for report in depth_reports if report.get("fallback_primitive", False))
    opaque_zero_depth = [
        report.get("region_id")
        for report in depth_reports
        if float(report.get("max_depth", report.get("local_depth", 0.0))) <= 0.0
    ]
    outline_full_depth = any(
        (report.get("primitive_type") == "shell" or report.get("label") == "outline")
        and int(report.get("voxel_count", 0)) > int(report.get("pixel_count", 0)) * 2
        for report in depth_reports
    )
    fallback_ratio = fallback_primitive_count / max(len(depth_reports), 1)
    continuity_enabled = bool(mesh.get("continuity_enabled", False))
    continuity_metrics = mesh.get("continuity_metrics", {})
    phase2_score = _phase2_continuity_score()
    side_worsened = (
        continuity_enabled
        and phase2_score is not None
        and continuity_metrics.get("side_silhouette_continuity_score", 0.0) + 0.001 < phase2_score
    )
    override_report = getattr(args, "_semantic_override_report", {})
    critical = override_report.get("critical_label_coverage", {})
    missing_critical = [
        label for label in ("head", "torso", "left_leg", "right_leg")
        if int(critical.get(label, 0)) <= 0
    ]
    strict_mode = getattr(args, "semantic_override_mode", "supplement") == "strict"
    smoothing_report = mesh.get("smoothing_report", {})
    smoothing_enabled = bool(smoothing_report.get("smoothing_enabled", False))
    smoothing_passed = bool(smoothing_report.get("smoothing_passed", not smoothing_enabled))
    source_coverage = getattr(args, "_source_coverage", {})
    fail_conditions = {
        "fallback_faces_above_1_percent": fallback_percent > 0.01,
        "generated_mesh_has_zero_faces": total_faces == 0,
        "no_regions_generated": len(regions) == 0 and args.representation_style != "cuboid_parts", # Allow 0 regions for cuboid_parts if no parts are found
        "opaque_regions_receive_zero_depth": bool(opaque_zero_depth),
        "outline_becomes_full_depth_slab": outline_full_depth,
        "fallback_primitives_above_10_percent": primitive_enabled and fallback_ratio > 0.10,
        "critical_body_regions_float_disconnected": continuity_enabled
        and continuity_metrics.get("side_silhouette_continuity_score", 0.0) < 0.75,
        "shell_occupies_too_much_side_area": continuity_enabled and continuity_metrics.get("shell_dominance_ratio", 0.0) > 0.24,
        "side_continuity_worsened_vs_phase2": side_worsened,
        "semantic_override_dimensions_mismatch": bool(override_report.get("dimension_mismatches")),
        "semantic_override_overlap_in_strict_mode": strict_mode and override_report.get("override_overlap_count", 0) > 0,
        "torso_head_overlap_after_override": override_report.get("torso_head_overlap_count_after_override", 0) > 0,
        "critical_labels_missing_after_override": bool(missing_critical),
        "smoothing_silhouette_drift_above_max": smoothing_enabled
        and smoothing_report.get("silhouette_drift_px", 0.0)
        > smoothing_report.get("config", {}).get("max_silhouette_drift_px", 1.0),
        "smoothing_outline_preservation_below_threshold": smoothing_enabled
        and smoothing_report.get("outline_preservation_score", 1.0) < 0.98,
        "smoothing_semantic_boundary_violations": smoothing_enabled
        and smoothing_report.get("semantic_boundary_violation_count", 0) > 0,
        "smoothing_face_count_zero": smoothing_enabled
        and smoothing_report.get("face_count_after_smoothing", total_faces) == 0,
        "front_readability_worsened_after_smoothing": smoothing_enabled
        and abs(smoothing_report.get("front_readability_delta", 0.0)) > 0.01,
        "source_coverage_policy_failed": bool(source_coverage.get("fail_conditions"))
        and any(source_coverage.get("fail_conditions", {}).values()),
    }


def _build_phase5a_closed_body(
    args: argparse.Namespace,
    front: Image.Image,
    output_dir: Path,
    cleaned_path: Path,
    graph,
    assignments,
    semantic_report: dict[str, Any],
    semantic_warnings: dict[str, Any],
    semantic_override_report: dict[str, Any],
    parts: list[dict[str, Any]],
    override_masks: dict[str, set[tuple[int, int]]],
    raw_regions: list[set[tuple[int, int]]],
    region_id_map: Path,
    region_overlay: Path,
    depth_debug: Path,
    semantic_paths: dict[str, Path],
    override_debug_paths: dict[str, Path],
    source_coverage: dict[str, Any],
    view_candidate_paths: dict[str, Path],
) -> dict[str, Any]:
    semantic_parts_result: dict[str, Any] = {}
    semantic_parts_paths: dict[str, Path] = {}
    view_authority_result: dict[str, Any] = {}
    view_authority_paths: dict[str, Path] = {}
    if getattr(args, "semantic_parts", False):
        semantic_parts_result = consolidate_semantic_parts(
            front,
            parts,
            raw_regions,
            graph,
            override_masks,
            {},
            output_dir / "semantic_parts",
            emit_debug=bool(getattr(args, "emit_semantic_parts_debug", False)),
        )
        parts = semantic_parts_result["parts"]
        semantic_parts_paths = {
            key: path
            for key, path in semantic_parts_result.get("paths", {}).items()
            if isinstance(path, Path)
        }
    mylar = build_mylar_front_depth(front.size, parts, output_dir / "mylar", max_total_depth=float(args.model_depth_units))
    back = build_back_hemisphere(
        mylar["z_front"],
        mylar["seam_mask"],
        mylar["label_by_pixel"],
        output_dir / "back",
        mode=getattr(args, "back_mode", "semantic_rules"),
        back_sprite_path=getattr(args, "back", None),
        front_alpha_mask=mylar["alpha_mask"],
    )
    seam = build_seam_outputs(
        mylar["alpha_mask"],
        mylar["seam_mask"],
        mylar["z_front"],
        back["z_back"],
        output_dir / "seam",
    )
    semantic_depth_profile: dict[str, Any] | None = None
    semantic_depth_paths: dict[str, Path] = {}
    directional_morphology: dict[str, Any] | None = None
    directional_paths: dict[str, Path] = {}
    embodiment_param_result: dict[str, Any] = {}
    embodiment_param_paths: dict[str, Path] = {}
    embodiment_params_data: dict[str, Any] | None = None
    constraint_arbitration_result: dict[str, Any] = {}
    constraint_arbitration_paths: dict[str, Path] = {}
    semantic_authority_result: dict[str, Any] = {}
    semantic_authority_paths: dict[str, Path] = {}
    surface_flow_paths: dict[str, Path] = {}
    rfd_paths: dict[str, Path] = {}
    if getattr(args, "semantic_depth_profiles", False):
        semantic_depth_profile = load_profile_set(getattr(args, "semantic_depth_profile", "humanoid_voxel"), WORKSPACE_ROOT)
    if getattr(args, "directional_morphology", False):
        directional_morphology = load_morphology_profile(getattr(args, "morphology_profile", "fantasy_humanoid"), WORKSPACE_ROOT)
        if semantic_depth_profile is None:
            args.semantic_depth_profiles = True
            semantic_depth_profile = load_profile_set(getattr(args, "semantic_depth_profile", "humanoid_voxel"), WORKSPACE_ROOT)
    semantic_authority_result = validate_semantic_authority(
        front,
        parts,
        load_semantic_overrides(
            _resolve_optional_path(getattr(args, "semantic_overrides", None)),
            front.size,
            getattr(args, "semantic_override_mode", "supplement"),
        )["masks"],
        semantic_override_report,
        directional_morphology,
        _load_profile(getattr(args, "profile", None)),
        source_coverage,
        back["report"],
        getattr(args, "back", None),
        getattr(args, "back_mode", "semantic_rules"),
        output_dir / "semantic_authority",
    )
    semantic_authority_paths = {
        key: path
        for key, path in semantic_authority_result.get("paths", {}).items()
        if isinstance(path, Path)
    }
    directional_morphology = semantic_authority_result.get("morphology_profile", directional_morphology)
    should_load_embodiment_params = bool(
        getattr(args, "embodiment_params", None)
        or getattr(args, "constraint_arbitration", False)
        or getattr(args, "emit_embodiment_param_debug", False)
    )
    if should_load_embodiment_params:
        embodiment_params_data = load_embodiment_params(getattr(args, "embodiment_params", None), WORKSPACE_ROOT)
    if getattr(args, "multi_view_authority", False):
        view_authority_result = build_view_authority_constraints(
            front,
            parts,
            source_coverage,
            getattr(args, "back", None),
            getattr(args, "left", None),
            getattr(args, "right", None),
            output_dir / "view_authority",
            mode=getattr(args, "view_authority_mode", "auto"),
            emit_debug=bool(getattr(args, "emit_view_authority_debug", False)),
            semantic_overrides_dir=_resolve_optional_path(getattr(args, "semantic_overrides", None)),
            allow_mirrored_side_fallback=bool(getattr(args, "allow_mirrored_side_fallback", False)),
        )
        view_authority_paths = {
            key: path
            for key, path in view_authority_result.get("paths", {}).items()
            if isinstance(path, Path)
        }
    if getattr(args, "constraint_arbitration", False) and view_authority_result:
        constraint_arbitration_result = arbitrate_constraints(
            view_authority_result.get("constraints", {}),
            embodiment_params_data,
            output_dir / "embodiment",
            emit_debug=bool(getattr(args, "emit_embodiment_param_debug", False)),
        )
        view_authority_result["constraints"] = constraint_arbitration_result.get(
            "constraints", view_authority_result.get("constraints", {})
        )
        arbitration_report_fields = {
            key: value
            for key, value in constraint_arbitration_result.get("report", {}).items()
            if key != "schema"
        }
        view_authority_result["report"] = {
            **dict(view_authority_result.get("report", {})),
            **arbitration_report_fields,
            "constraint_arbitration_report": constraint_arbitration_result.get("report", {}),
        }
        constraint_arbitration_paths = {
            key: path
            for key, path in constraint_arbitration_result.get("paths", {}).items()
            if isinstance(path, Path)
        }
    if should_load_embodiment_params and embodiment_params_data is not None:
        if semantic_depth_profile is None:
            args.semantic_depth_profiles = True
            semantic_depth_profile = load_profile_set(getattr(args, "semantic_depth_profile", "humanoid_voxel"), WORKSPACE_ROOT)
        if directional_morphology is None:
            args.directional_morphology = True
            directional_morphology = load_morphology_profile(getattr(args, "morphology_profile", "fantasy_humanoid"), WORKSPACE_ROOT)
        embodiment_param_result = apply_embodiment_params(
            semantic_depth_profile,
            directional_morphology,
            embodiment_params_data,
            parts,
            output_dir / "embodiment",
            emit_debug=bool(getattr(args, "emit_embodiment_param_debug", False)),
        )
        semantic_depth_profile = embodiment_param_result.get("semantic_depth_profile", semantic_depth_profile)
        directional_morphology = embodiment_param_result.get("directional_morphology", directional_morphology)
        embodiment_param_paths = {
            key: path
            for key, path in embodiment_param_result.get("paths", {}).items()
            if isinstance(path, Path)
        }
    base_z_samples = max(17, int(args.total_depth_slices) * 2 + 1)
    resolution_settings = _adaptive_resolution_settings(args, base_z_samples, front.size)
    z_samples = int(resolution_settings["z_samples"])
    resolution_profile = resolution_settings.get("profile")
    sdf = build_sdf_volume(
        mylar["z_front"],
        back["z_back"],
        mylar["alpha_mask"],
        mylar["label_by_pixel"],
        output_dir / "sdf",
        z_samples=z_samples,
        semantic_depth_profile=semantic_depth_profile,
        semantic_depth_output_dir=output_dir / "depth_profiles" if semantic_depth_profile else None,
        emit_semantic_depth_debug=bool(getattr(args, "emit_semantic_depth_debug", False)),
        directional_morphology=directional_morphology,
        directional_output_dir=output_dir / "directional_debug" if directional_morphology else None,
        emit_directional_debug=bool(getattr(args, "emit_directional_debug", False)),
        surface_flow_enabled=bool(getattr(args, "surface_flow", False)),
        surface_flow_strength=float(getattr(args, "surface_flow_strength", 0.45)),
        surface_flow_iterations=int(getattr(args, "surface_flow_iterations", 2)),
        surface_flow_output_dir=output_dir / "surface_flow" if getattr(args, "surface_flow", False) else None,
        emit_surface_flow_debug=bool(getattr(args, "emit_surface_flow_debug", False)),
        rfd_enabled=bool(getattr(args, "rfd", False)),
        rfd_output_dir=output_dir / "rfd" if getattr(args, "rfd", False) else None,
        emit_rfd_debug=bool(getattr(args, "emit_rfd_debug", False)),
        sdf_resolution_scale=float(resolution_settings["xy_scale"]),
        base_z_samples=base_z_samples,
        adaptive_resolution_profile=resolution_profile if isinstance(resolution_profile, dict) else None,
        resolution_output_dir=output_dir / "resolution"
        if getattr(args, "adaptive_sdf_resolution", False) or getattr(args, "emit_resolution_debug", False)
        else None,
        emit_resolution_debug=bool(getattr(args, "emit_resolution_debug", False)),
        view_authority=view_authority_result.get("constraints") if view_authority_result else None,
        view_authority_output_dir=output_dir / "view_authority" if view_authority_result else None,
        emit_view_authority_debug=bool(getattr(args, "emit_view_authority_debug", False)),
    )
    if sdf.get("semantic_depth_profile"):
        semantic_depth_paths = {
            key: path
            for key, path in sdf["semantic_depth_profile"].get("paths", {}).items()
            if isinstance(path, Path)
        }
    if sdf.get("rfd"):
        rfd_paths = {
            key: path
            for key, path in sdf["rfd"].get("paths", {}).items()
            if isinstance(path, Path)
        }
    if sdf.get("surface_flow"):
        surface_flow_paths = {
            key: path
            for key, path in sdf["surface_flow"].get("paths", {}).items()
            if isinstance(path, Path)
        }
    if sdf.get("directional_morphology"):
        directional_paths = {
            key: path
            for key, path in sdf["directional_morphology"].get("paths", {}).items()
            if isinstance(path, Path)
        }
    meshing = emit_surface_nets_input(sdf["sdf"], sdf["semantic_volume"], output_dir / "meshing")
    mesh_backend = getattr(args, "mesh_backend", "greedy")
    surface_net_mesh: dict[str, Any] | None = None
    output_mesh: dict[str, Any] | None = None
    mesh_path: Path | None = None
    raw_mesh_path: Path | None = None
    surface_net_report: dict[str, Any] = {}
    surface_net_paths: dict[str, Path] = {}
    surface_net_debug_paths: dict[str, Path] = {}
    voxel_depth_result: dict[str, Any] = {}
    voxel_depth_paths: dict[str, Path] = {}
    qef_debug_paths: dict[str, Path] = {}
    semantic_patch_result: dict[str, Any] = {}
    semantic_patch_paths: dict[str, Path] = {}
    macro_patch_paths: dict[str, Path] = {}
    topology_cleanup_result: dict[str, Any] = {}
    topology_cleanup_paths: dict[str, Path] = {}
    surface_cohesion_result: dict[str, Any] = {}
    surface_cohesion_paths: dict[str, Path] = {}
    semantic_remesh_result: dict[str, Any] = {}
    semantic_remesh_paths: dict[str, Path] = {}
    voxel_render_result: dict[str, Any] = {}
    material_debug_paths: dict[str, Path] = {}
    if mesh_backend in {"surface_nets", "surface_nets_patch"}:
        surface_net_input = meshing["paths"]["surface_nets_input"]
        surface_sdf, surface_semantic = load_surface_nets_input(surface_net_input)
        surface_net_mesh = extract_surface_nets(
            surface_sdf,
            surface_semantic,
            iso_level=0.0,
            smoothing_alpha=float(getattr(args, "surface_net_smoothing_alpha", 0.65)),
            vertex_placement=getattr(args, "surface_net_vertex_placement", "average"),
            qef_regularization=float(getattr(args, "qef_regularization", 0.001)),
            qef_max_displacement=float(getattr(args, "qef_max_displacement", 0.35)),
        )
        surface_net_mesh["config"] = {
            **dict(surface_net_mesh.get("config", {})),
            "sdf_resolution_scale": float(resolution_settings["xy_scale"]),
            "z_resolution_scale": float(resolution_settings["z_scale"]),
            "adaptive_sdf_resolution": bool(getattr(args, "adaptive_sdf_resolution", False)),
            "resolution_profile": getattr(args, "resolution_profile", "prototype_adaptive"),
        }
        _apply_surface_net_vertex_colours(surface_net_mesh, front)
        raw_mesh_path = write_mesh_json(surface_net_mesh, output_dir / "mesh.json")
        mesh_path = raw_mesh_path
        if getattr(args, "emit_qef_debug", False):
            qef_debug_paths = write_qef_debug(surface_net_mesh, output_dir / "qef")
        if mesh_backend == "surface_nets_patch":
            patch_profile = load_patch_profile(getattr(args, "patch_profile", "humanoid_voxel"), WORKSPACE_ROOT)
            macro_patch_profile = (
                load_macro_patch_profile(getattr(args, "macro_patch_profile", "humanoid_voxel"), WORKSPACE_ROOT)
                if getattr(args, "macro_patches", False)
                else None
            )
            semantic_patch_result = apply_semantic_patch_nets(
                surface_net_mesh,
                surface_sdf,
                surface_semantic,
                semantic_parts_result.get("report", {}),
                sdf.get("directional_morphology", {}).get("report", {}) if isinstance(sdf.get("directional_morphology"), dict) else {},
                patch_profile,
                output_dir / "patch_nets",
                emit_debug=bool(getattr(args, "emit_patch_debug", False)),
                macro_patch_profile=macro_patch_profile,
                macro_output_dir=output_dir / "macro_patches" if getattr(args, "macro_patches", False) else None,
                emit_macro_debug=bool(getattr(args, "emit_macro_patch_debug", False)),
            )
            surface_net_mesh = semantic_patch_result["mesh"]
            semantic_patch_paths = {
                key: path
                for key, path in semantic_patch_result.get("paths", {}).items()
                if isinstance(path, Path)
            }
            macro_patch_paths = {
                key.removeprefix("macro_"): path
                for key, path in semantic_patch_paths.items()
                if key.startswith("macro_")
            }
            mesh_path = semantic_patch_paths.get("mesh_patch", output_dir / "mesh_patch.json")
        if getattr(args, "topology_cleanup", False):
            topology_cleanup_result = apply_topology_cleanup(
                surface_net_mesh,
                output_dir / "topology_cleanup",
                emit_debug=bool(getattr(args, "emit_topology_cleanup_debug", False)),
                preserve_silhouette_edges=bool(getattr(args, "preserve_silhouette_edges", True)),
                preserve_semantic_boundaries=True,
            )
            surface_net_mesh = topology_cleanup_result["mesh"]
            topology_cleanup_paths = {
                key: path
                for key, path in topology_cleanup_result.get("paths", {}).items()
                if isinstance(path, Path)
            }
            mesh_path = topology_cleanup_paths.get("mesh_topology_cleaned", output_dir / "topology_cleanup" / "mesh_topology_cleaned.json")
        if getattr(args, "render_profile", None):
            render_profile = load_render_profile(getattr(args, "render_profile"), WORKSPACE_ROOT)
            voxel_render_result = apply_voxel_render_profile(
                surface_net_mesh,
                front,
                output_dir / "material_debug",
                render_profile,
            )
            surface_net_mesh = voxel_render_result["mesh"]
            material_debug_paths = {
                key: path
                for key, path in voxel_render_result.get("paths", {}).items()
                if isinstance(path, Path)
            }
        if getattr(args, "surface_cohesion", False):
            cohesion_profile = load_surface_cohesion_profile(
                getattr(args, "surface_cohesion_profile", "humanoid_voxel"),
                WORKSPACE_ROOT,
            )
            surface_cohesion_result = apply_surface_cohesion(
                surface_net_mesh,
                semantic_parts_result.get("report", {}),
                cohesion_profile,
                output_dir / "surface_cohesion",
                strength=float(getattr(args, "surface_cohesion_strength", 0.35)),
                iterations=int(getattr(args, "surface_cohesion_iterations", 2)),
                emit_debug=bool(getattr(args, "emit_surface_cohesion_debug", False)),
            )
            surface_net_mesh = surface_cohesion_result["mesh"]
            surface_cohesion_paths = {
                key: path
                for key, path in surface_cohesion_result.get("paths", {}).items()
                if isinstance(path, Path)
            }
            mesh_path = surface_cohesion_paths.get("mesh_cohesive", output_dir / "mesh_cohesive.json")
        else:
            mesh_path = write_mesh_json(surface_net_mesh, mesh_path)
        if getattr(args, "semantic_remesh", False):
            if not raw_mesh_path.exists():
                raw_mesh_path = write_mesh_json(surface_net_mesh, output_dir / "mesh.json")
            remesh_profile = load_remesh_profile(
                getattr(args, "remesh_profile", "humanoid_lowpoly"),
                WORKSPACE_ROOT,
            )
            semantic_remesh_result = apply_semantic_remeshing(
                surface_net_mesh,
                semantic_parts_result.get("report", {}),
                remesh_profile,
                output_dir / "remeshing",
                iterations=int(getattr(args, "remesh_iterations", 1)),
                strength=float(getattr(args, "remesh_strength", 0.35)),
                preserve_silhouette_edges=bool(getattr(args, "preserve_silhouette_edges", True)),
                emit_debug=bool(getattr(args, "emit_remesh_debug", False)),
            )
            surface_net_mesh = semantic_remesh_result["mesh"]
            semantic_remesh_paths = {
                key: path
                for key, path in semantic_remesh_result.get("paths", {}).items()
                if isinstance(path, Path)
            }
            mesh_path = semantic_remesh_paths.get("mesh_remeshed", output_dir / "mesh_remeshed.json")
        surface_net_report = write_surface_nets_report(surface_net_mesh, output_dir, surface_net_input)
        boundary_path = output_dir / "semantic_boundary_debug.json"
        _write_json(
            boundary_path,
            {
                "semantic_boundary_edges": surface_net_mesh.get("semantic_boundary_edges", []),
                "material_groups": surface_net_mesh.get("stats", {}).get("material_groups", {}),
            },
        )
        surface_net_paths = {
            "mesh": mesh_path,
            "raw_mesh": raw_mesh_path,
            "surface_nets_report": output_dir / "surface_nets_report.json",
            "semantic_boundary_debug": boundary_path,
        }
        if getattr(args, "emit_surface_net_debug", False):
            surface_net_debug_paths = write_surface_nets_debug(
                surface_net_mesh,
                surface_sdf,
                surface_semantic,
                output_dir / "debug",
            )
        output_mesh = surface_net_mesh
    elif mesh_backend == "voxel_depth":
        side_path = getattr(args, "left", None) or getattr(args, "right", None)
        voxel_depth_result = _build_voxel_depth_mesh(
            front,
            getattr(args, "back", None),
            side_path,
            sdf["occupancy"],
            args,
            output_dir,
        )
        output_mesh = voxel_depth_result["mesh"]
        mesh_path = voxel_depth_result["paths"]["mesh"]
        raw_mesh_path = mesh_path
        voxel_depth_paths = {
            key: path
            for key, path in voxel_depth_result.get("paths", {}).items()
            if isinstance(path, Path)
        }
    validation_report = build_phase5a_validation(
        mylar,
        back,
        seam,
        sdf,
        meshing,
        parts,
        getattr(args, "back_mode", "semantic_rules"),
        source_coverage,
        semantic_authority_result.get("report", {}),
        semantic_parts_result.get("report", {}),
    )
    if mesh_backend in {"surface_nets", "surface_nets_patch"}:
        validation_report = _extend_phase5b_validation(
            validation_report,
            surface_net_report,
            meshing,
            float(getattr(args, "surface_net_smoothing_alpha", 0.65)),
            mesh_backend,
        )
    if mesh_backend == "voxel_depth":
        validation_report = _extend_voxel_depth_validation(validation_report, voxel_depth_result.get("report", {}))
    if semantic_patch_result:
        validation_report = _extend_semantic_patch_validation(validation_report, semantic_patch_result)
    if topology_cleanup_result or getattr(args, "adaptive_sdf_resolution", False):
        validation_report = _extend_resolution_and_topology_validation(
            validation_report,
            sdf.get("summary", {}),
            topology_cleanup_result,
            resolution_profile if isinstance(resolution_profile, dict) else {},
        )
    if surface_cohesion_result:
        validation_report = _extend_surface_cohesion_validation(validation_report, surface_cohesion_result)
    if semantic_remesh_result:
        validation_report = _extend_semantic_remesh_validation(validation_report, semantic_remesh_result)
    if voxel_render_result:
        validation_report = _extend_phase5f_validation(validation_report, voxel_render_result)
    if mesh_backend in {"surface_nets", "surface_nets_patch"} and getattr(args, "godot_preview", False):
        render_result = _run_phase5c_godot_preview(args, output_dir, surface_net_paths.get("mesh"))
        validation_report = _extend_phase5c_validation(validation_report, render_result)
        if voxel_render_result:
            contact_sheet = _write_before_after_render_contact_sheet(output_dir)
            validation_report["before_after_render_contact_sheet"] = str(contact_sheet)
    if getattr(args, "emit_render_diagnostics", False) or getattr(args, "emit_canonical_view_metrics", False):
        phase5d_result = _run_phase5d_diagnostics(args, output_dir, source_coverage)
        validation_report = _extend_phase5d_validation(validation_report, phase5d_result)
    if getattr(args, "emit_visual_mapping", False) or getattr(args, "api_visual_judge", False) or getattr(args, "canonical_silhouette_correct", False):
        visual_mapping_result = _run_phase5d_visual_mapping(args, output_dir, source_coverage)
        validation_report = _extend_visual_mapping_validation(
            validation_report,
            visual_mapping_result,
            getattr(args, "api_visual_judge", False),
        )
    silhouette_correction_result: dict[str, Any] = {}
    if getattr(args, "canonical_silhouette_correct", False):
        silhouette_correction_result = _run_phase6a_canonical_silhouette_correction(
            args,
            output_dir,
            source_coverage,
            surface_net_paths.get("mesh"),
        )
        validation_report = _extend_phase6a_validation(validation_report, silhouette_correction_result)
    validation_path = output_dir / "validation_report.json"
    model_path = output_dir / "topological_model.json"
    _write_json(validation_path, validation_report)
    model = {
        "schema": "spritespatial_phase5a_closed_sdf_v1",
        "pipeline": "phase5a_closed_sdf",
        "versions": {
            "pipeline_version": mylar["report"].get("pipeline_version", "0.4.0"),
            "semantic_version": mylar["report"].get("semantic_version", "0.2.1"),
            "depth_version": mylar["report"].get("depth_version", "0.3.0"),
            "mesher_version": "0.1.0",
            "profile_pack": mylar["report"].get("profile_pack", "humanoid_default_v2"),
        },
        "front_texture": _res_path(cleaned_path),
        "region_overlay": _res_path(region_overlay),
        "region_id_map": _res_path(region_id_map),
        "depth_debug": _res_path(depth_debug),
        "semantic_region_overlay": _res_path(semantic_paths["semantic_region_overlay"]),
        "semantic_override_overlay": {key: _res_path(path) for key, path in override_debug_paths.items()},
        "mylar": {key: _res_path(path) for key, path in mylar["paths"].items()},
        "back": {key: _res_path(path) for key, path in back["paths"].items()},
        "seam": {key: _res_path(path) for key, path in seam["paths"].items()},
        "sdf": {key: _res_path(path) for key, path in sdf["paths"].items()},
        "semantic_depth_profiles": {key: _res_path(path) for key, path in semantic_depth_paths.items()},
        "directional_morphology": {key: _res_path(path) for key, path in directional_paths.items()},
        "embodiment_params": {key: _res_path(path) for key, path in embodiment_param_paths.items()},
        "constraint_arbitration": {key: _res_path(path) for key, path in constraint_arbitration_paths.items()},
        "semantic_authority": {key: _res_path(path) for key, path in semantic_authority_paths.items()},
        "view_authority": {key: _res_path(path) for key, path in view_authority_paths.items()},
        "semantic_parts": {key: _res_path(path) for key, path in semantic_parts_paths.items()},
        "surface_flow": {key: _res_path(path) for key, path in surface_flow_paths.items()},
        "rfd": {key: _res_path(path) for key, path in rfd_paths.items()},
        "meshing": {key: _res_path(path) for key, path in meshing["paths"].items()},
        "surface_nets": {key: _res_path(path) for key, path in surface_net_paths.items()},
        "voxel_depth": {key: _res_path(path) for key, path in voxel_depth_paths.items()},
        "surface_net_debug": {key: _res_path(path) for key, path in surface_net_debug_paths.items()},
        "qef": {key: _res_path(path) for key, path in qef_debug_paths.items()},
        "semantic_patch_nets": {key: _res_path(path) for key, path in semantic_patch_paths.items()},
        "macro_patches": {key: _res_path(path) for key, path in macro_patch_paths.items()},
        "topology_cleanup": {key: _res_path(path) for key, path in topology_cleanup_paths.items()},
        "surface_cohesion": {key: _res_path(path) for key, path in surface_cohesion_paths.items()},
        "semantic_remeshing": {key: _res_path(path) for key, path in semantic_remesh_paths.items()},
        "material_debug": {key: _res_path(path) for key, path in material_debug_paths.items()},
        "voxel_render_report": _res_path(output_dir / "voxel_render_report.json") if voxel_render_result else "",
        "silhouette_correction": {
            "mesh_corrected": _res_path(Path(silhouette_correction_result["mesh_corrected"]))
            if silhouette_correction_result.get("mesh_corrected")
            else "",
            "correction_report": _res_path(output_dir / "correction_report.json")
            if silhouette_correction_result
            else "",
            "corrected_visual_mapping": _res_path(output_dir / "corrected_visual_mapping")
            if silhouette_correction_result.get("corrected_visual_mapping_report")
            else "",
        },
        "source_coverage": source_coverage,
        "view_candidates": {key: _res_path(path) for key, path in view_candidate_paths.items()},
        "canvas_size": [front.width, front.height],
        "config": {
            "depth_mode": getattr(args, "depth_mode", "mylar_edt"),
            "closed_body": True,
            "back_mode": getattr(args, "back_mode", "semantic_rules"),
            "multi_view_authority": getattr(args, "multi_view_authority", False),
            "view_authority_mode": getattr(args, "view_authority_mode", "auto"),
            "allow_mirrored_side_fallback": getattr(args, "allow_mirrored_side_fallback", False),
            "emit_view_authority_debug": getattr(args, "emit_view_authority_debug", False),
            "constraint_arbitration": getattr(args, "constraint_arbitration", False),
            "emit_sdf_debug": getattr(args, "emit_sdf_debug", False),
            "emit_closure_debug": getattr(args, "emit_closure_debug", False),
            "mesh_backend": mesh_backend,
            "surface_net_smoothing_alpha": float(getattr(args, "surface_net_smoothing_alpha", 0.65)),
            "surface_net_vertex_placement": getattr(args, "surface_net_vertex_placement", "average"),
            "qef_regularization": float(getattr(args, "qef_regularization", 0.001)),
            "qef_max_displacement": float(getattr(args, "qef_max_displacement", 0.35)),
            "emit_qef_debug": getattr(args, "emit_qef_debug", False),
            "emit_surface_net_debug": getattr(args, "emit_surface_net_debug", False),
            "patch_profile": getattr(args, "patch_profile", "humanoid_voxel"),
            "emit_patch_debug": getattr(args, "emit_patch_debug", False),
            "macro_patches": getattr(args, "macro_patches", False),
            "macro_patch_profile": getattr(args, "macro_patch_profile", "humanoid_voxel"),
            "emit_macro_patch_debug": getattr(args, "emit_macro_patch_debug", False),
            "sdf_resolution_scale": float(resolution_settings["xy_scale"]),
            "z_resolution_scale": float(resolution_settings["z_scale"]),
            "emit_resolution_diagnostic": getattr(args, "emit_resolution_diagnostic", False),
            "adaptive_sdf_resolution": getattr(args, "adaptive_sdf_resolution", False),
            "resolution_profile": getattr(args, "resolution_profile", "prototype_adaptive"),
            "emit_resolution_debug": getattr(args, "emit_resolution_debug", False),
            "topology_cleanup": getattr(args, "topology_cleanup", False),
            "emit_topology_cleanup_debug": getattr(args, "emit_topology_cleanup_debug", False),
            "surface_cohesion": getattr(args, "surface_cohesion", False),
            "surface_cohesion_profile": getattr(args, "surface_cohesion_profile", "humanoid_voxel"),
            "surface_cohesion_strength": float(getattr(args, "surface_cohesion_strength", 0.35)),
            "surface_cohesion_iterations": int(getattr(args, "surface_cohesion_iterations", 2)),
            "emit_surface_cohesion_debug": getattr(args, "emit_surface_cohesion_debug", False),
            "semantic_remesh": getattr(args, "semantic_remesh", False),
            "remesh_profile": getattr(args, "remesh_profile", "humanoid_lowpoly"),
            "remesh_iterations": int(getattr(args, "remesh_iterations", 1)),
            "remesh_strength": float(getattr(args, "remesh_strength", 0.35)),
            "preserve_silhouette_edges": getattr(args, "preserve_silhouette_edges", True),
            "emit_remesh_debug": getattr(args, "emit_remesh_debug", False),
            "semantic_depth_profiles": getattr(args, "semantic_depth_profiles", False),
            "semantic_depth_profile": getattr(args, "semantic_depth_profile", "humanoid_voxel"),
            "emit_semantic_depth_debug": getattr(args, "emit_semantic_depth_debug", False),
            "directional_morphology": getattr(args, "directional_morphology", False),
            "morphology_profile": getattr(args, "morphology_profile", "fantasy_humanoid"),
            "emit_directional_debug": getattr(args, "emit_directional_debug", False),
            "embodiment_params": str(getattr(args, "embodiment_params", "") or ""),
            "emit_embodiment_param_debug": getattr(args, "emit_embodiment_param_debug", False),
            "emit_embodiment_debug": getattr(args, "emit_embodiment_param_debug", False),
            "surface_flow": getattr(args, "surface_flow", False),
            "surface_flow_strength": float(getattr(args, "surface_flow_strength", 0.45)),
            "surface_flow_iterations": int(getattr(args, "surface_flow_iterations", 2)),
            "emit_surface_flow_debug": getattr(args, "emit_surface_flow_debug", False),
            "rfd": getattr(args, "rfd", False),
            "emit_rfd_debug": getattr(args, "emit_rfd_debug", False),
            "render_profile": getattr(args, "render_profile", ""),
            "canonical_silhouette_correct": getattr(args, "canonical_silhouette_correct", False),
            "silhouette_correction_iterations": int(getattr(args, "silhouette_correction_iterations", 1)),
            "max_silhouette_displacement": float(getattr(args, "max_silhouette_displacement", 0.15)),
            "semantic_override_mode": getattr(args, "semantic_override_mode", "supplement"),
            "semantic_parts": getattr(args, "semantic_parts", False),
            "emit_semantic_parts_debug": getattr(args, "emit_semantic_parts_debug", False),
            "model_depth_units": args.model_depth_units,
            "total_depth_slices": args.total_depth_slices,
        },
        "vertices": output_mesh.get("vertices", []) if output_mesh else [],
        "normals": output_mesh.get("normals", []) if output_mesh else [],
        "colors": output_mesh.get("colors", []) if output_mesh else [],
        "indices": output_mesh.get("indices", []) if output_mesh else [],
        "faces": output_mesh.get("faces", []) if output_mesh else [],
        "vertex_metadata": output_mesh.get("vertex_metadata", []) if output_mesh else [],
        "face_metadata": output_mesh.get("face_metadata", []) if output_mesh else [],
        "part_ids": [
            int(item.get("semantic_label", 0))
            for item in output_mesh.get("face_metadata", [])
        ] if output_mesh else [],
        "parts": _parts_json_summary(parts),
        "semantic_regions": semantic_report["regions"],
        "validation_report": validation_report,
    }
    _write_json(model_path, model)
    _write_json(output_dir / "part_graph.json", {"regions": graph_to_json(graph)})
    _write_json(output_dir / "depth_assignment.json", {"assignments": assignments_to_json(assignments)})
    _write_json(output_dir / "semantic_report.json", semantic_report)
    _write_json(output_dir / "semantic_warnings.json", semantic_warnings)
    _write_json(output_dir / "semantic_override_report.json", semantic_override_report)
    if not validation_report.get("passed", False):
        failures = [
            key for key, failed in validation_report.get("fail_conditions", {}).items()
            if failed
        ]
        if getattr(args, "multi_view_authority", False):
            phase_name = "Phase 7A"
        elif mesh_backend == "surface_nets_patch" and getattr(args, "macro_patches", False):
            phase_name = "Phase 6F"
        elif mesh_backend == "surface_nets_patch":
            phase_name = "Phase 6E"
        elif getattr(args, "semantic_remesh", False):
            phase_name = "Phase 6D"
        elif getattr(args, "rfd", False):
            phase_name = "Phase 6D"
        elif getattr(args, "canonical_silhouette_correct", False):
            phase_name = "Phase 6A"
        elif getattr(args, "surface_flow", False):
            phase_name = "Phase 6B"
        elif getattr(args, "surface_cohesion", False):
            phase_name = "Phase 6C"
        else:
            phase_name = "Phase 5B" if mesh_backend == "surface_nets" else "Phase 5A"
        raise ValueError(f"{phase_name} validation failed: {failures}")
    for warning in source_coverage.get("warnings", []):
        print(f"WARNING: {warning}")
    return {
        "region_count": len(graph),
        "model": model_path,
        "part_graph": output_dir / "part_graph.json",
        "validation_report": validation_path,
        "scene": "",
    }


def _extend_phase5b_validation(
    validation_report: dict[str, Any],
    surface_net_report: dict[str, Any],
    meshing: dict[str, Any],
    smoothing_alpha: float,
    mesh_backend: str = "surface_nets",
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    faces = int(surface_net_report.get("surface_net_faces", 0))
    vertices = int(surface_net_report.get("surface_net_vertices", 0))
    degenerate = int(surface_net_report.get("degenerate_face_count", 0))
    labels_mesh = set(int(value) for value in surface_net_report.get("semantic_labels_in_mesh", []))
    labels_volume = set(int(value) for value in surface_net_report.get("semantic_labels_in_volume", []))
    missing_labels = sorted(labels_volume - labels_mesh)
    input_report = meshing.get("report", {})
    qef_enabled = bool(surface_net_report.get("qef_enabled", False))
    qef_limit = float(surface_net_report.get("qef_max_displacement_limit", surface_net_report.get("qef_max_displacement", 0.0)))
    qef_observed = float(surface_net_report.get("qef_max_displacement", surface_net_report.get("qef_max_displacement_observed", 0.0)))
    fail_conditions.update(
        {
            "surface_net_zero_vertices": vertices <= 0,
            "surface_net_zero_faces": faces <= 0,
            "surface_net_degenerate_faces": degenerate > max(1, int(faces * 0.01)),
            "surface_net_semantic_labels_lost": bool(missing_labels),
            "surface_nets_input_not_loadable": not bool(input_report.get("surface_nets_input_loadable", False)),
            "surface_nets_input_shape_invalid": not bool(input_report.get("surface_nets_input_shape_valid", False)),
            "qef_no_cells_accepted": qef_enabled and int(surface_net_report.get("qef_cells_accepted", 0)) <= 0,
            "qef_max_displacement_exceeded": qef_enabled and qef_observed > qef_limit + 1.0e-6,
        }
    )
    report.update(
        {
            "mesh_backend": mesh_backend,
            "surface_net_vertices": vertices,
            "surface_net_faces": faces,
            "active_cell_count": int(surface_net_report.get("active_cell_count", 0)),
            "semantic_boundary_edge_count": int(surface_net_report.get("semantic_boundary_edge_count", 0)),
            "silhouette_vertex_count": int(surface_net_report.get("silhouette_vertex_count", 0)),
            "degenerate_face_count": degenerate,
            "non_manifold_edge_count": int(surface_net_report.get("non_manifold_edge_count", 0)),
            "mesh_connected_components": int(surface_net_report.get("mesh_connected_components", 0)),
            "semantic_labels_in_mesh": sorted(labels_mesh),
            "semantic_labels_in_volume": sorted(labels_volume),
            "semantic_labels_missing_from_mesh": missing_labels,
            "semantic_label_preservation_passed": not missing_labels,
            "surface_net_smoothing_alpha": float(smoothing_alpha),
            "surface_net_vertex_placement": surface_net_report.get("surface_net_vertex_placement", "average"),
            "qef_enabled": qef_enabled,
            "qef_cells_processed": int(surface_net_report.get("qef_cells_processed", 0)),
            "qef_cells_accepted": int(surface_net_report.get("qef_cells_accepted", 0)),
            "qef_cells_rejected": int(surface_net_report.get("qef_cells_rejected", 0)),
            "qef_acceptance_ratio": float(surface_net_report.get("qef_acceptance_ratio", 0.0)),
            "qef_mean_displacement": float(surface_net_report.get("qef_mean_displacement", 0.0)),
            "qef_max_displacement": qef_observed,
            "qef_max_displacement_limit": qef_limit,
            "qef_fallback_count": int(surface_net_report.get("qef_fallback_count", 0)),
            "qef_condition_warning_count": int(surface_net_report.get("qef_condition_warning_count", 0)),
            "staircase_artifact_before_qef": float(surface_net_report.get("staircase_artifact_before_qef", 0.0)),
            "staircase_artifact_after_qef": float(surface_net_report.get("staircase_artifact_after_qef", 0.0)),
            "surface_flow_before_qef": float(surface_net_report.get("surface_flow_before_qef", 0.0)),
            "surface_flow_after_qef": float(surface_net_report.get("surface_flow_after_qef", 0.0)),
            "planar_surface_score_before_qef": float(surface_net_report.get("planar_surface_score_before_qef", 0.0)),
            "planar_surface_score_after_qef": float(surface_net_report.get("planar_surface_score_after_qef", 0.0)),
            "qef_quality_metric_improved": bool(surface_net_report.get("qef_quality_metric_improved", False)),
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _extend_voxel_depth_validation(
    validation_report: dict[str, Any],
    voxel_report: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    vertices = int(voxel_report.get("voxel_depth_vertices", 0))
    triangles = int(voxel_report.get("voxel_depth_triangles", 0))
    material_count = int(voxel_report.get("voxel_depth_material_colour_count", 0))
    fail_conditions.update(
        {
            "voxel_depth_zero_vertices": vertices <= 0,
            "voxel_depth_zero_triangles": triangles <= 0,
            "voxel_depth_missing_material_colours": material_count <= 0,
        }
    )
    report.update(
        {
            "mesh_backend": "voxel_depth",
            "voxel_depth_vertices": vertices,
            "voxel_depth_triangles": triangles,
            "voxel_depth_exposed_faces": int(voxel_report.get("voxel_depth_exposed_faces", 0)),
            "voxel_depth_internal_faces_removed": int(voxel_report.get("voxel_depth_internal_faces_removed", 0)),
            "voxel_depth_material_colour_count": material_count,
            "voxel_depth_black_side_face_percentage": float(voxel_report.get("voxel_depth_black_side_face_percentage", 0.0)),
            "voxel_depth_occupied_voxels": int(voxel_report.get("voxel_depth_occupied_voxels", 0)),
            "voxel_depth_shape": voxel_report.get("voxel_depth_shape", []),
            "voxel_depth_report": voxel_report,
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _extend_surface_cohesion_validation(
    validation_report: dict[str, Any],
    surface_cohesion_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    cohesion_report = dict(surface_cohesion_result.get("report", {}))
    fail_conditions = dict(report.get("fail_conditions", {}))
    for key, value in cohesion_report.get("fail_conditions", {}).items():
        fail_conditions[f"surface_cohesion_{key}"] = bool(value)
    report.update(
        {
            "surface_cohesion_enabled": bool(cohesion_report.get("surface_cohesion_enabled", False)),
            "surface_cohesion_profile": cohesion_report.get("surface_cohesion_profile", ""),
            "cohesion_vertices_adjusted": int(cohesion_report.get("cohesion_vertices_adjusted", 0)),
            "mean_vertex_displacement": float(cohesion_report.get("mean_vertex_displacement", 0.0)),
            "max_vertex_displacement": float(cohesion_report.get("max_vertex_displacement", 0.0)),
            "semantic_boundary_preservation_score": float(
                cohesion_report.get("semantic_boundary_preservation_score", 0.0)
            ),
            "normal_discontinuity_before": float(cohesion_report.get("normal_discontinuity_before", 0.0)),
            "normal_discontinuity_after": float(cohesion_report.get("normal_discontinuity_after", 0.0)),
            "surface_fragmentation_before": float(cohesion_report.get("surface_fragmentation_before", 0.0)),
            "surface_fragmentation_after": float(cohesion_report.get("surface_fragmentation_after", 0.0)),
            "silhouette_drift_px": float(cohesion_report.get("silhouette_drift_px", 0.0)),
            "hat_tip_preserved": bool(cohesion_report.get("hat_tip_preserved", True)),
            "outline_preserved": bool(cohesion_report.get("outline_preserved", True)),
            "surface_cohesion_report": cohesion_report,
            "fail_conditions": fail_conditions,
        }
    )
    report["passed"] = not any(fail_conditions.values())
    return report


def _extend_semantic_patch_validation(
    validation_report: dict[str, Any],
    semantic_patch_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    patch_report = dict(semantic_patch_result.get("report", {}))
    fail_conditions = dict(report.get("fail_conditions", {}))
    for key, value in patch_report.get("fail_conditions", {}).items():
        fail_conditions[f"semantic_patch_nets_{key}"] = bool(value)
    report.update(
        {
            "semantic_patch_nets_enabled": bool(patch_report.get("semantic_patch_nets_enabled", False)),
            "patch_profile": patch_report.get("patch_profile", ""),
            "patch_count": int(patch_report.get("patch_count", 0)),
            "mean_patch_size": float(patch_report.get("mean_patch_size", 0.0)),
            "small_patch_ratio": float(patch_report.get("small_patch_ratio", 0.0)),
            "planar_patch_count": int(patch_report.get("planar_patch_count", 0)),
            "curved_patch_count": int(patch_report.get("curved_patch_count", 0)),
            "silhouette_patch_count": int(patch_report.get("silhouette_patch_count", 0)),
            "semantic_boundary_patch_count": int(patch_report.get("semantic_boundary_patch_count", 0)),
            "macro_patches_enabled": bool(patch_report.get("macro_patches_enabled", False)),
            "micro_patch_count": int(patch_report.get("micro_patch_count", patch_report.get("patch_count", 0))),
            "macro_patch_count": int(patch_report.get("macro_patch_count", 0)),
            "macro_patch_reduction_ratio": float(patch_report.get("macro_patch_reduction_ratio", 0.0)),
            "mean_macro_patch_size": float(patch_report.get("mean_macro_patch_size", 0.0)),
            "small_macro_patch_ratio": float(patch_report.get("small_macro_patch_ratio", 0.0)),
            "planar_macro_patch_count": int(patch_report.get("planar_macro_patch_count", 0)),
            "curved_macro_patch_count": int(patch_report.get("curved_macro_patch_count", 0)),
            "directional_feature_macro_patch_count": int(
                patch_report.get("directional_feature_macro_patch_count", 0)
            ),
            "noise_fragments_absorbed": int(patch_report.get("noise_fragments_absorbed", 0)),
            "macro_patch_coherence_score": float(patch_report.get("macro_patch_coherence_score", 0.0)),
            "triangle_count_before_patch": int(patch_report.get("triangle_count_before_patch", 0)),
            "triangle_count_after_patch": int(patch_report.get("triangle_count_after_patch", 0)),
            "staircase_artifact_before": float(patch_report.get("staircase_artifact_before", 0.0)),
            "staircase_artifact_after": float(patch_report.get("staircase_artifact_after", 0.0)),
            "surface_flow_before": float(patch_report.get("surface_flow_before", 0.0)),
            "surface_flow_after": float(patch_report.get("surface_flow_after", 0.0)),
            "patch_coherence_score": float(patch_report.get("patch_coherence_score", 0.0)),
            "semantic_boundary_preservation_score": float(
                patch_report.get("semantic_boundary_preservation_score", 0.0)
            ),
            "silhouette_edge_preservation_score": float(
                patch_report.get("silhouette_edge_preservation_score", 0.0)
            ),
            "directional_feature_preservation_score": float(
                patch_report.get("directional_feature_preservation_score", 0.0)
            ),
            "surface_net_vertex_placement": patch_report.get(
                "surface_net_vertex_placement",
                report.get("surface_net_vertex_placement", "average"),
            ),
            "qef_enabled": bool(patch_report.get("qef_enabled", report.get("qef_enabled", False))),
            "qef_cells_processed": int(patch_report.get("qef_cells_processed", report.get("qef_cells_processed", 0))),
            "qef_cells_accepted": int(patch_report.get("qef_cells_accepted", report.get("qef_cells_accepted", 0))),
            "qef_cells_rejected": int(patch_report.get("qef_cells_rejected", report.get("qef_cells_rejected", 0))),
            "qef_acceptance_ratio": float(patch_report.get("qef_acceptance_ratio", report.get("qef_acceptance_ratio", 0.0))),
            "qef_mean_displacement": float(patch_report.get("qef_mean_displacement", report.get("qef_mean_displacement", 0.0))),
            "qef_max_displacement": float(patch_report.get("qef_max_displacement", report.get("qef_max_displacement", 0.0))),
            "qef_max_displacement_limit": float(
                patch_report.get("qef_max_displacement_limit", report.get("qef_max_displacement_limit", 0.0))
            ),
            "qef_fallback_count": int(patch_report.get("qef_fallback_count", report.get("qef_fallback_count", 0))),
            "qef_condition_warning_count": int(
                patch_report.get("qef_condition_warning_count", report.get("qef_condition_warning_count", 0))
            ),
            "staircase_artifact_before_qef": float(
                patch_report.get("staircase_artifact_before_qef", report.get("staircase_artifact_before_qef", 0.0))
            ),
            "staircase_artifact_after_qef": float(
                patch_report.get("staircase_artifact_after_qef", report.get("staircase_artifact_after_qef", 0.0))
            ),
            "surface_flow_before_qef": float(
                patch_report.get("surface_flow_before_qef", report.get("surface_flow_before_qef", 0.0))
            ),
            "surface_flow_after_qef": float(
                patch_report.get("surface_flow_after_qef", report.get("surface_flow_after_qef", 0.0))
            ),
            "planar_surface_score_before_qef": float(
                patch_report.get("planar_surface_score_before_qef", report.get("planar_surface_score_before_qef", 0.0))
            ),
            "planar_surface_score_after_qef": float(
                patch_report.get("planar_surface_score_after_qef", report.get("planar_surface_score_after_qef", 0.0))
            ),
            "qef_quality_metric_improved": bool(
                patch_report.get("qef_quality_metric_improved", report.get("qef_quality_metric_improved", False))
            ),
            "semantic_patch_nets_report": patch_report,
            "fail_conditions": fail_conditions,
        }
    )
    report["passed"] = not any(fail_conditions.values())
    return report


def _extend_resolution_and_topology_validation(
    validation_report: dict[str, Any],
    sdf_summary: dict[str, Any],
    topology_cleanup_result: dict[str, Any],
    resolution_profile: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    cleanup_report = dict(topology_cleanup_result.get("report", {})) if topology_cleanup_result else {}
    fail_conditions = dict(report.get("fail_conditions", {}))
    adaptive_enabled = bool(sdf_summary.get("adaptive_sdf_resolution_enabled", False))
    max_non_manifold_increase = int(resolution_profile.get("max_non_manifold_edge_increase", 15))
    baseline_non_manifold = int(resolution_profile.get("baseline_non_manifold_edge_count", 11))
    max_voxel_multiplier = float(resolution_profile.get("max_voxel_budget_multiplier", 999.0))
    non_manifold_after = int(
        cleanup_report.get("non_manifold_after_cleanup", report.get("non_manifold_edge_count", 0))
    )
    effective_budget = float(sdf_summary.get("effective_voxel_budget_multiplier", 1.0))
    degenerate_after = int(cleanup_report.get("degenerate_face_count", report.get("degenerate_face_count", 0)))
    components_after = int(cleanup_report.get("mesh_connected_components", report.get("mesh_connected_components", 1)))
    semantic_missing = list(cleanup_report.get("semantic_labels_missing_from_mesh", report.get("semantic_labels_missing_from_mesh", [])))
    hat_ratio = float(report.get("hat_asymmetry_ratio", sdf_summary.get("hat_asymmetry_ratio", 0.0)))
    fail_conditions.update(
        {
            "adaptive_sdf_voxel_budget_exceeded": adaptive_enabled and effective_budget > max_voxel_multiplier + 1.0e-6,
            "topology_cleanup_mesh_disconnected": bool(cleanup_report) and components_after != 1,
            "topology_cleanup_semantic_labels_disappeared": bool(semantic_missing),
            "topology_cleanup_degenerate_faces": bool(cleanup_report) and degenerate_after > 0,
            "topology_cleanup_non_manifold_above_target": bool(cleanup_report)
            and non_manifold_after > baseline_non_manifold + max_non_manifold_increase,
            "adaptive_sdf_hat_asymmetry_regressed": adaptive_enabled and hat_ratio < 2.0,
        }
    )
    report.update(
        {
            "adaptive_sdf_resolution_enabled": adaptive_enabled,
            "resolution_profile": sdf_summary.get("resolution_profile", resolution_profile.get("name", "")),
            "effective_voxel_budget_multiplier": effective_budget,
            "adaptive_high_detail_region_count": int(sdf_summary.get("adaptive_high_detail_region_count", 0)),
            "silhouette_band_high_res_enabled": bool(sdf_summary.get("silhouette_band_high_res_enabled", False)),
            "semantic_boundary_high_res_enabled": bool(sdf_summary.get("semantic_boundary_high_res_enabled", False)),
            "sdf_resolution_strategy": sdf_summary.get("sdf_resolution_strategy", "uniform"),
            "topology_cleanup_applied": bool(cleanup_report.get("topology_cleanup_applied", False)),
            "non_manifold_before_cleanup": int(cleanup_report.get("non_manifold_before_cleanup", report.get("non_manifold_edge_count", 0))),
            "non_manifold_after_cleanup": non_manifold_after,
            "duplicate_faces_removed": int(cleanup_report.get("duplicate_faces_removed", 0)),
            "duplicate_vertices_merged": int(cleanup_report.get("duplicate_vertices_merged", 0)),
            "sliver_faces_removed": int(cleanup_report.get("sliver_faces_removed", 0)),
            "topology_cleanup_report": cleanup_report,
            "fail_conditions": fail_conditions,
        }
    )
    if cleanup_report:
        report["non_manifold_edge_count"] = non_manifold_after
        report["degenerate_face_count"] = degenerate_after
        report["mesh_connected_components"] = components_after
        report["semantic_labels_missing_from_mesh"] = semantic_missing
        report["semantic_label_preservation_passed"] = not semantic_missing
    report["passed"] = not any(fail_conditions.values())
    return report


def _extend_semantic_remesh_validation(
    validation_report: dict[str, Any],
    semantic_remesh_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    remesh_report = dict(semantic_remesh_result.get("report", {}))
    fail_conditions = dict(report.get("fail_conditions", {}))
    for key, value in remesh_report.get("fail_conditions", {}).items():
        fail_conditions[f"semantic_remesh_{key}"] = bool(value)
    report.update(
        {
            "semantic_remesh_enabled": bool(remesh_report.get("semantic_remesh_enabled", False)),
            "remesh_profile": remesh_report.get("remesh_profile", ""),
            "triangle_count_before": int(remesh_report.get("triangle_count_before", 0)),
            "triangle_count_after": int(remesh_report.get("triangle_count_after", 0)),
            "triangle_reduction_ratio": float(remesh_report.get("triangle_reduction_ratio", 0.0)),
            "coplanar_merge_count": int(remesh_report.get("coplanar_merge_count", 0)),
            "staircase_artifact_before": float(remesh_report.get("staircase_artifact_before", 0.0)),
            "staircase_artifact_after": float(remesh_report.get("staircase_artifact_after", 0.0)),
            "surface_flow_before": float(remesh_report.get("surface_flow_before", 0.0)),
            "surface_flow_after": float(remesh_report.get("surface_flow_after", 0.0)),
            "silhouette_edge_preservation_score": float(
                remesh_report.get("silhouette_edge_preservation_score", 0.0)
            ),
            "semantic_boundary_preservation_score": float(
                remesh_report.get("semantic_boundary_preservation_score", 0.0)
            ),
            "directional_feature_preservation_score": float(
                remesh_report.get("directional_feature_preservation_score", 0.0)
            ),
            "planar_surface_score": float(remesh_report.get("planar_surface_score", 0.0)),
            "oblique_readability_score": float(remesh_report.get("oblique_readability_score", 0.0)),
            "lowpoly_coherence_score": float(remesh_report.get("lowpoly_coherence_score", 0.0)),
            "semantic_remesh_report": remesh_report,
            "fail_conditions": fail_conditions,
        }
    )
    report["passed"] = not any(fail_conditions.values())
    return report


def _run_phase5c_godot_preview(
    args: argparse.Namespace,
    output_dir: Path,
    mesh_path: Path | None,
) -> dict[str, Any]:
    return _run_godot_preview_for_mesh(args, output_dir, mesh_path)


def _run_godot_preview_for_mesh(
    args: argparse.Namespace,
    render_dir: Path,
    mesh_path: Path | None,
) -> dict[str, Any]:
    captures_dir = render_dir / "captures"
    render_dir.mkdir(parents=True, exist_ok=True)
    captures_dir.mkdir(parents=True, exist_ok=True)
    if mesh_path is None or not mesh_path.exists():
        result = {
            "godot_preview_requested": True,
            "godot_preview_ran": False,
            "godot_preview_exit_code": -1,
            "error": "mesh.json is missing; cannot run Godot preview.",
        }
        _write_json(render_dir / "render_report.json", result)
        _write_json(render_dir / "semantic_material_report.json", {"semantic_materials_assigned": False})
        return result
    godot = _find_godot_executable(getattr(args, "godot_executable", None))
    if godot is None:
        result = {
            "godot_preview_requested": True,
            "godot_preview_ran": False,
            "godot_preview_exit_code": -1,
            "error": "Godot executable not found.",
        }
        _write_json(render_dir / "render_report.json", result)
        _write_json(render_dir / "semantic_material_report.json", {"semantic_materials_assigned": False})
        return result
    scene_path = WORKSPACE_ROOT / "scenes" / "surface_nets_preview.tscn"
    command = [
        str(godot),
        "--path",
        str(WORKSPACE_ROOT),
        _res_path(scene_path),
        "--",
        "--capture-surface-nets-preview",
        "--surface-nets-mesh",
        _res_path(mesh_path),
        "--surface-nets-output",
        _res_path(render_dir),
    ]
    render_report_path = render_dir / "render_report.json"
    material_report_path = render_dir / "semantic_material_report.json"
    completed: subprocess.CompletedProcess[str] | None = None
    render_report: dict[str, Any] = {}
    material_report: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    outputs_valid = False
    for attempt in range(3):
        completed = subprocess.run(command, cwd=WORKSPACE_ROOT, text=True, capture_output=True, timeout=90)
        render_report = _read_json_if_exists(render_report_path)
        material_report = _read_json_if_exists(material_report_path)
        captures = render_report.get("captures", []) if isinstance(render_report, dict) else []
        capture_names = {str(item.get("name", "")) for item in captures if isinstance(item, dict)}
        outputs_valid = bool(
            render_report.get("passed", False)
            and render_report.get("mesh_loads_in_godot", False)
            and {"front", "oblique", "side", "back", "wireframe"}.issubset(capture_names)
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "exit_code": completed.returncode,
                "outputs_valid": outputs_valid,
                "stderr_tail": "\n".join((completed.stderr or "").splitlines()[-4:]),
            }
        )
        if completed.returncode == 0 or outputs_valid:
            break
        time.sleep(1.5)
    for name in ("front", "oblique", "side", "side_135", "back", "wireframe"):
        source = captures_dir / f"{name}.png"
        if source.exists():
            shutil.copyfile(source, render_dir / f"{name}.png")
    result = {
        "godot_preview_requested": True,
        "godot_preview_ran": bool((completed and completed.returncode == 0) or outputs_valid),
        "godot_preview_exit_code": completed.returncode if completed else -1,
        "godot_stdout_tail": "\n".join(((completed.stdout if completed else "") or "").splitlines()[-8:]),
        "godot_stderr_tail": "\n".join(((completed.stderr if completed else "") or "").splitlines()[-8:]),
        "godot_preview_attempts": attempts,
        "render_report": render_report,
        "semantic_material_report": material_report,
        "captures_dir": str(captures_dir),
        "scene": str(scene_path),
    }
    if not render_report:
        _write_json(render_report_path, result)
    return result


def _extend_phase5c_validation(
    validation_report: dict[str, Any],
    render_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    render_report = render_result.get("render_report", {}) if isinstance(render_result.get("render_report", {}), dict) else {}
    material_report = (
        render_result.get("semantic_material_report", {})
        if isinstance(render_result.get("semantic_material_report", {}), dict)
        else {}
    )
    captures = render_report.get("captures", []) if isinstance(render_report, dict) else []
    required_capture_names = {"front", "oblique", "side", "back", "wireframe"}
    capture_names = {str(item.get("name", "")) for item in captures if isinstance(item, dict)}
    fail_conditions.update(
        {
            "godot_preview_failed": not render_result.get("godot_preview_ran", False),
            "godot_mesh_load_failed": not render_report.get("mesh_loads_in_godot", False),
            "godot_missing_surfaces": not render_report.get("no_missing_surfaces", False),
            "godot_semantic_materials_missing": not material_report.get("semantic_materials_assigned", False),
            "godot_outline_pass_missing": not render_report.get("outline_pass_renders", False),
            "godot_missing_required_captures": not required_capture_names.issubset(capture_names),
            "godot_mesh_not_visible_all_angles": not render_report.get("mesh_visible_from_all_orbit_angles", False),
            "godot_catastrophic_shading_artifacts": bool(render_report.get("catastrophic_shading_artifacts", True)),
        }
    )
    report.update(
        {
            "phase5c_render_enabled": True,
            "godot_preview_ran": render_result.get("godot_preview_ran", False),
            "godot_preview_exit_code": render_result.get("godot_preview_exit_code", -1),
            "render_report": render_report,
            "semantic_material_report": material_report,
            "captures_generated": sorted(capture_names),
            "mesh_loads_in_godot": render_report.get("mesh_loads_in_godot", False),
            "semantic_materials_assigned": material_report.get("semantic_materials_assigned", False),
            "outline_pass_renders": render_report.get("outline_pass_renders", False),
            "mesh_visible_from_all_orbit_angles": render_report.get("mesh_visible_from_all_orbit_angles", False),
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _extend_phase5f_validation(
    validation_report: dict[str, Any],
    voxel_render_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    voxel_report = voxel_render_result.get("report", {})
    fail_conditions.update(
        {
            "voxel_render_internal_black_faces_excessive": float(voxel_report.get("internal_black_face_ratio", 1.0)) > 0.18,
            "voxel_render_outline_preservation_low": float(voxel_report.get("outer_outline_preservation_score", 0.0)) < 0.45,
            "voxel_render_source_colour_match_low": float(voxel_report.get("source_colour_match_score", 0.0)) < 0.45,
            "voxel_render_side_shading_low": float(voxel_report.get("side_face_shading_score", 0.0)) < 0.65,
            "voxel_render_readability_low": float(voxel_report.get("voxel_face_readability_score", 0.0)) < 0.55,
        }
    )
    report.update(
        {
            "render_profile": voxel_report.get("render_profile", ""),
            "voxel_render_profile_enabled": True,
            "internal_black_face_ratio": voxel_report.get("internal_black_face_ratio", 0.0),
            "outer_outline_preservation_score": voxel_report.get("outer_outline_preservation_score", 0.0),
            "source_colour_match_score": voxel_report.get("source_colour_match_score", 0.0),
            "side_face_shading_score": voxel_report.get("side_face_shading_score", 0.0),
            "voxel_face_readability_score": voxel_report.get("voxel_face_readability_score", 0.0),
            "voxel_render_report": voxel_report,
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _write_before_after_render_contact_sheet(output_dir: Path) -> Path:
    previous_dir = output_dir.parent / output_dir.name.replace("phase5f_voxel_render", "phase5e_semantic_depth")
    views = ("front", "oblique", "side", "side_135", "back")
    panel_size = (160, 132)
    sheet = Image.new("RGBA", (panel_size[0] * 2, panel_size[1] * len(views)), (28, 28, 28, 255))
    for row, view in enumerate(views):
        before = _render_contact_panel(previous_dir / "captures" / f"{view}.png", f"before {view}", panel_size)
        after = _render_contact_panel(output_dir / "captures" / f"{view}.png", f"after {view}", panel_size)
        y = row * panel_size[1]
        sheet.alpha_composite(before, (0, y))
        sheet.alpha_composite(after, (panel_size[0], y))
    path = output_dir / "before_after_render_contact_sheet.png"
    sheet.save(path, format="PNG")
    return path


def _render_contact_panel(path: Path, title: str, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (20, 20, 20, 255))
    draw = ImageDraw.Draw(panel)
    draw.text((5, 5), title[:28], fill=(245, 245, 245, 255))
    if path.exists():
        image = Image.open(path).convert("RGBA")
    else:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).text((5, 24), "missing", fill=(255, 80, 80, 255))
    image.thumbnail((size[0] - 12, size[1] - 28), Image.Resampling.NEAREST)
    panel.alpha_composite(image, ((size[0] - image.width) // 2, 24 + (size[1] - 28 - image.height) // 2))
    return panel


def _run_phase5d_diagnostics(
    args: argparse.Namespace,
    output_dir: Path,
    source_coverage: dict[str, Any],
) -> dict[str, Any]:
    captures_dir = output_dir / "captures"
    diagnostics_report: dict[str, Any] = {}
    canonical_report: dict[str, Any] = {}
    records = canonical_view_records(source_coverage)
    write_canonical_view_records(records, output_dir / "canonical_views.json")
    if getattr(args, "emit_render_diagnostics", False):
        diagnostics_report = analyze_phase5c_captures(captures_dir, output_dir)
    if getattr(args, "emit_canonical_view_metrics", False):
        asset_schema = getattr(args, "_asset_schema", None)
        front_path = asset_schema.sprite_path("front") if asset_schema else args.front
        back_path = asset_schema.sprite_path("back") if asset_schema else getattr(args, "back", None)
        side_path = None
        if asset_schema:
            left_path = asset_schema.sprite_path("left")
            right_path = asset_schema.sprite_path("right")
            side_path = left_path if left_path.exists() else right_path
        canonical_report = compute_canonical_view_metrics(
            captures_dir,
            output_dir,
            front_path,
            back_path,
            side_path,
            source_coverage,
            diagnostics_report,
        )
    _write_phase5d_summary(output_dir, diagnostics_report, canonical_report)
    return {
        "render_diagnostics": diagnostics_report,
        "canonical_view_metrics": canonical_report,
        "canonical_views": records,
    }


def _extend_phase5d_validation(
    validation_report: dict[str, Any],
    phase5d_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    metrics = phase5d_result.get("canonical_view_metrics", {})
    diagnostics = phase5d_result.get("render_diagnostics", {})
    report.update(
        {
            "render_diagnostics_enabled": bool(diagnostics),
            "canonical_view_metrics_enabled": bool(metrics),
            "canonical_view_metrics": {
                "front_iou": metrics.get("front_iou", 0.0),
                "oblique_iou": metrics.get("oblique_iou", 0.0),
                "side_iou": metrics.get("side_iou", 0.0),
                "back_iou": metrics.get("back_iou", 0.0),
                "worst_view": metrics.get("worst_view", ""),
                "front_back_similarity_warning": metrics.get("front_back_similarity_warning", False),
                "side_profile_authority": metrics.get("side_profile_authority", ""),
                "back_view_authority": metrics.get("back_view_authority", ""),
            },
            "front_back_similarity_warning": diagnostics.get("front_back_visual_similarity_warning", False),
            "side_front_similarity_warning": diagnostics.get("side_front_visual_similarity_warning", False),
            "passed": not any(report.get("fail_conditions", {}).values()),
        }
    )
    return report


def _write_phase5d_summary(
    output_dir: Path,
    diagnostics: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    lines = [
        "# Phase 5D Diagnostics",
        "",
        f"- front/back similarity warning: {diagnostics.get('front_back_visual_similarity_warning', False)}",
        f"- side/front similarity warning: {diagnostics.get('side_front_visual_similarity_warning', False)}",
        f"- front IoU: {metrics.get('front_iou', 0.0)}",
        f"- side IoU: {metrics.get('side_iou', 0.0)}",
        f"- back IoU: {metrics.get('back_iou', 0.0)}",
        f"- worst view: {metrics.get('worst_view', '')}",
        "",
        "Interpretation: these metrics diagnose canonical-view silhouette failure; they do not apply correction.",
    ]
    (output_dir / "phase5d_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_phase5d_visual_mapping(
    args: argparse.Namespace,
    output_dir: Path,
    source_coverage: dict[str, Any],
) -> dict[str, Any]:
    asset_schema = getattr(args, "_asset_schema", None)
    front_path = asset_schema.sprite_path("front") if asset_schema else args.front
    back_path = asset_schema.sprite_path("back") if asset_schema else getattr(args, "back", None)
    side_path = None
    if asset_schema:
        left_path = asset_schema.sprite_path("left")
        right_path = asset_schema.sprite_path("right")
        side_path = left_path if left_path.exists() else right_path
    semantic_override_dir = _resolve_optional_path(getattr(args, "semantic_overrides", None))
    canonical_metrics = _read_json_if_exists(output_dir / "canonical_view_metrics.json")
    visual_report: dict[str, Any] = {}
    api_result: dict[str, Any] = {}
    try:
        visual_report = build_visual_mapping(
            output_dir / "captures",
            output_dir,
            front_path,
            back_path,
            side_path,
            semantic_override_dir,
            source_coverage,
            canonical_metrics,
        )
    except Exception as exc:
        error_payload = {
            "schema": "spritespatial_visual_mapping_error_v1",
            "ok": False,
            "error": str(exc),
        }
        _write_json(output_dir / "visual_mapping_error.json", error_payload)
        return {
            "visual_mapping_report": {},
            "visual_mapping_error": error_payload,
            "api_visual_judge_result": {},
        }
    if getattr(args, "api_visual_judge", False):
        api_result = run_api_visual_judge(output_dir)
    return {
        "visual_mapping_report": visual_report,
        "visual_mapping_report_path": output_dir / "visual_mapping_report.json",
        "comparison_contact_sheet": output_dir / "comparison_contact_sheet.png",
        "compare_images": [output_dir / f"compare_{angle}.png" for angle in (0, 45, 90, 135, 180)],
        "api_visual_judge_result": api_result,
    }


def _extend_visual_mapping_validation(
    validation_report: dict[str, Any],
    visual_result: dict[str, Any],
    api_requested: bool,
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    visual_report = visual_result.get("visual_mapping_report", {})
    compare_images = list(visual_result.get("compare_images", []))
    report_path_raw = visual_result.get("visual_mapping_report_path")
    contact_sheet_raw = visual_result.get("comparison_contact_sheet")
    report_path = Path(report_path_raw) if report_path_raw else None
    contact_sheet = Path(contact_sheet_raw) if contact_sheet_raw else None
    outputs_exist = bool(visual_report) and bool(report_path and report_path.exists()) and all(Path(path).exists() for path in compare_images)
    api_result = visual_result.get("api_visual_judge_result", {})
    api_judgement_path = Path(str(api_result.get("path", ""))) if api_result.get("path") else None
    api_ok = bool(api_result.get("ok", False)) if api_result else False
    api_error_exists = bool(api_requested and api_judgement_path and api_judgement_path.exists() and not api_ok)
    fail_conditions.update(
        {
            "visual_mapping_outputs_missing": not outputs_exist,
            "visual_mapping_contact_sheet_missing": not bool(contact_sheet and contact_sheet.exists()),
            "visual_mapping_report_invalid": not bool(visual_report.get("schema") == "spritespatial_visual_mapping_report_v1"),
        }
    )
    report.update(
        {
            "visual_mapping_enabled": True,
            "api_visual_judge_enabled": bool(api_requested),
            "visual_mapping_outputs_exist": outputs_exist,
            "comparison_contact_sheet_exists": bool(contact_sheet and contact_sheet.exists()),
            "api_visual_judgement_exists": bool(api_ok and api_judgement_path and api_judgement_path.exists()),
            "api_visual_judgement_error_exists": api_error_exists,
            "front_visual_mapping_iou": visual_report.get("front_visual_mapping_iou", 0.0),
            "worst_visual_mapping_view": visual_report.get("worst_visual_mapping_view", ""),
            "worst_visual_mapping_score": visual_report.get("worst_visual_mapping_score", 0.0),
            "visual_mapping_report_path": str(report_path) if report_path else "",
            "comparison_contact_sheet": str(contact_sheet) if contact_sheet else "",
            "api_visual_judge_result_path": str(api_judgement_path) if api_judgement_path else "",
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _run_phase6a_canonical_silhouette_correction(
    args: argparse.Namespace,
    output_dir: Path,
    source_coverage: dict[str, Any],
    mesh_path: Path | None,
) -> dict[str, Any]:
    if mesh_path is None or not mesh_path.exists():
        error = {
            "schema": "spritespatial_phase6a_correction_error_v1",
            "ok": False,
            "error": "Surface-nets mesh is required before canonical silhouette correction.",
        }
        _write_json(output_dir / "correction_report.json", error)
        return error
    asset_schema = getattr(args, "_asset_schema", None)
    front_path = asset_schema.sprite_path("front") if asset_schema else args.front
    back_path = asset_schema.sprite_path("back") if asset_schema else getattr(args, "back", None)
    side_path = None
    if asset_schema:
        left_path = asset_schema.sprite_path("left")
        right_path = asset_schema.sprite_path("right")
        side_path = left_path if left_path.exists() else right_path
    correction_report = optimize_canonical_silhouette(
        mesh_path,
        output_dir,
        front_path,
        back_path,
        side_path,
        source_coverage,
        iterations=int(getattr(args, "silhouette_correction_iterations", 1)),
        max_displacement=float(getattr(args, "max_silhouette_displacement", 0.15)),
        emit_debug=bool(getattr(args, "emit_silhouette_correction_debug", False)),
    )
    corrected_mesh_path = Path(correction_report["mesh_corrected"])
    render_result: dict[str, Any] = {}
    corrected_visual_result: dict[str, Any] = {}
    if getattr(args, "godot_preview", False):
        corrected_render_dir = output_dir / "corrected_captures"
        render_result = _run_godot_preview_for_mesh(args, corrected_render_dir, corrected_mesh_path)
        semantic_override_dir = _resolve_optional_path(getattr(args, "semantic_overrides", None))
        corrected_visual_dir = output_dir / "corrected_visual_mapping"
        canonical_metrics = _read_json_if_exists(output_dir / "canonical_view_metrics.json")
        try:
            corrected_visual_report = build_visual_mapping(
                corrected_render_dir / "captures",
                corrected_visual_dir,
                front_path,
                back_path,
                side_path,
                semantic_override_dir,
                source_coverage,
                canonical_metrics,
            )
            corrected_visual_result = {
                "visual_mapping_report": corrected_visual_report,
                "visual_mapping_report_path": corrected_visual_dir / "visual_mapping_report.json",
                "comparison_contact_sheet": corrected_visual_dir / "comparison_contact_sheet.png",
                "compare_images": [corrected_visual_dir / f"compare_{angle}.png" for angle in (0, 45, 90, 135, 180)],
            }
        except Exception as exc:
            error_payload = {
                "schema": "spritespatial_corrected_visual_mapping_error_v1",
                "ok": False,
                "error": str(exc),
            }
            _write_json(output_dir / "corrected_visual_mapping_error.json", error_payload)
            corrected_visual_result = {"visual_mapping_report": {}, "visual_mapping_error": error_payload}
    correction_report.update(
        {
            "corrected_render_result": render_result,
            "corrected_visual_mapping_report": corrected_visual_result.get("visual_mapping_report", {}),
            "corrected_visual_mapping_report_path": str(corrected_visual_result.get("visual_mapping_report_path", "")),
            "corrected_visual_mapping_contact_sheet": str(corrected_visual_result.get("comparison_contact_sheet", "")),
        }
    )
    _write_json(output_dir / "correction_report.json", correction_report)
    return correction_report


def _extend_phase6a_validation(
    validation_report: dict[str, Any],
    correction_result: dict[str, Any],
) -> dict[str, Any]:
    report = dict(validation_report)
    fail_conditions = dict(report.get("fail_conditions", {}))
    corrected_visual = correction_result.get("corrected_visual_mapping_report", {})
    corrected_report_path = Path(str(correction_result.get("corrected_visual_mapping_report_path", "")))
    visual_outputs_exist = bool(corrected_visual) and corrected_report_path.exists()
    original_non_manifold = int(report.get("non_manifold_edge_count", 0))
    corrected_non_manifold = int(correction_result.get("non_manifold_edge_count", original_non_manifold))
    fail_conditions.update(
        {
            "silhouette_correction_failed": not bool(correction_result.get("passed", False)),
            "silhouette_correction_front_iou_regressed": not bool(correction_result.get("front_iou_not_worse", False)),
            "silhouette_correction_worst_view_not_improved": not bool(correction_result.get("worst_view_iou_improved", False)),
            "silhouette_correction_semantic_labels_lost": bool(correction_result.get("semantic_labels_lost", [])),
            "silhouette_correction_semantic_boundary_violations": int(correction_result.get("semantic_boundary_violations", 0)) > 0,
            "silhouette_correction_degenerate_faces": int(correction_result.get("degenerate_face_count", 0)) > 0,
            "silhouette_correction_disconnected_mesh": int(correction_result.get("mesh_connected_components", 99)) > 1,
            "silhouette_correction_non_manifold_increase": corrected_non_manifold > original_non_manifold + max(2, int(original_non_manifold * 0.1)),
            "corrected_visual_mapping_outputs_missing": not visual_outputs_exist,
        }
    )
    report.update(
        {
            "canonical_silhouette_correction_enabled": True,
            "silhouette_correction_iterations": correction_result.get("iterations", 0),
            "max_silhouette_displacement": correction_result.get("max_silhouette_displacement", 0.0),
            "max_vertex_displacement": correction_result.get("max_vertex_displacement", 0.0),
            "front_iou_before_correction": correction_result.get("front_iou_before", 0.0),
            "front_iou_after_correction": correction_result.get("front_iou_after", 0.0),
            "front_iou_not_worse": correction_result.get("front_iou_not_worse", False),
            "worst_view_before_correction": correction_result.get("worst_view_before", ""),
            "worst_view_after_correction": correction_result.get("worst_view_after", ""),
            "worst_view_iou_before_correction": correction_result.get("worst_view_iou_before", 0.0),
            "worst_view_iou_after_correction": correction_result.get("worst_view_iou_after", 0.0),
            "worst_view_iou_improved": correction_result.get("worst_view_iou_improved", False),
            "semantic_boundary_violations": correction_result.get("semantic_boundary_violations", 0),
            "corrected_visual_mapping_enabled": bool(corrected_visual),
            "corrected_visual_mapping_outputs_exist": visual_outputs_exist,
            "corrected_visual_mapping_report_path": str(corrected_report_path) if str(corrected_report_path) else "",
            "corrected_front_visual_mapping_iou": corrected_visual.get("front_visual_mapping_iou", 0.0),
            "corrected_worst_visual_mapping_view": corrected_visual.get("worst_visual_mapping_view", ""),
            "corrected_worst_visual_mapping_score": corrected_visual.get("worst_visual_mapping_score", 0.0),
            "fail_conditions": fail_conditions,
            "passed": not any(fail_conditions.values()),
        }
    )
    return report


def _find_godot_executable(godot_arg: Path | None) -> Path | None:
    candidates: list[Path] = []
    if godot_arg:
        candidates.append(godot_arg if godot_arg.is_absolute() else WORKSPACE_ROOT / godot_arg)
    env_path = os.environ.get("GODOT_EXECUTABLE")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path("C:/Users/jakep/Downloads/Godot_v4.6.2-stable_win64.exe/Godot_v4.6.2-stable_win64_console.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Godot" / "godot.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for name in ("godot", "godot4", "Godot_v4.6.2-stable_win64_console.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _parts_json_summary(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for index, part in enumerate(parts):
        pixels = part.get("pixels", set())
        summary.append(
            {
                "index": index,
                "name": part.get("name", "unknown"),
                "semantic_label": part.get("semantic_label", part.get("name", "unknown")),
                "pixel_count": len(pixels),
                "bbox": part.get("bbox", [0, 0, 0, 0]),
                "dominant_colour": list(part.get("dominant_colour", (255, 0, 255, 255))),
            }
        )
    return summary
    semantic_warnings = semantic_warnings or {}
    warning_counts = {key: len(value) for key, value in semantic_warnings.items()}
    return {
        "total_faces": total_faces,
        "faces_with_fallback_material": fallback_faces,
        "fallback_face_percentage": fallback_percent,
        "number_of_materials": len(colours),
        "occupied_voxels": mesh.get("occupied_voxels", 0),
        "transparent_pixels_ignored": transparent_pixels,
        "alpha_coverage": opaque_pixels / max(front.width * front.height, 1),
        "regions_generated": len(regions),
        "final_mesh_bounds": bounds,
        "front_projection_coverage": opaque_pixels / max(front.width * front.height, 1),
        "part_count": len(part_reports),
        "zfield_enabled": zfield_enabled,
        "primitive_enabled": primitive_enabled,
        "primitive_count_by_type": primitive_counts,
        "average_region_depth": average_region_depth,
        "min_max_depth_by_region": depth_by_region,
        "outline_shell_voxel_count": outline_shell_voxel_count,
        "malformed_region_count": malformed_region_count,
        "fallback_primitive_count": fallback_primitive_count,
        "continuity_enabled": continuity_enabled,
        "disconnected_mass_count": continuity_metrics.get("disconnected_mass_count", 0),
        "floating_fragment_count": continuity_metrics.get("floating_fragment_count", 0),
        "side_silhouette_continuity_score": continuity_metrics.get("side_silhouette_continuity_score", 0.0),
        "semantic_bridge_count": continuity_metrics.get("semantic_bridge_count", 0),
        "shell_dominance_ratio": continuity_metrics.get("shell_dominance_ratio", 0.0),
        "phase2_side_silhouette_continuity_score": phase2_score,
        "semantic_override_mode": getattr(args, "semantic_override_mode", "supplement"),
        "override_pixels_applied": override_report.get("override_pixels_applied", 0),
        "override_overlap_count": override_report.get("override_overlap_count", 0),
        "unlabelled_opaque_pixel_ratio": override_report.get("unlabelled_opaque_pixel_ratio", 0.0),
        "critical_label_coverage": critical,
        "torso_head_overlap_count_after_override": override_report.get("torso_head_overlap_count_after_override", 0),
        "disconnected_critical_labels_after_override": override_report.get("disconnected_critical_labels_after_override", 0),
        "missing_critical_labels_after_override": missing_critical,
        "smoothing_enabled": smoothing_enabled,
        "smoothing_mode": smoothing_report.get("smoothing_mode", getattr(args, "smoothing_mode", "none")),
        "silhouette_drift_px": smoothing_report.get("silhouette_drift_px", 0.0),
        "outline_preservation_score": smoothing_report.get("outline_preservation_score", 1.0),
        "semantic_boundary_violation_count": smoothing_report.get("semantic_boundary_violation_count", 0),
        "face_count_before_smoothing": smoothing_report.get("face_count_before_smoothing", total_faces),
        "face_count_after_smoothing": smoothing_report.get("face_count_after_smoothing", total_faces),
        "degenerate_faces_removed": smoothing_report.get("degenerate_faces_removed", 0),
        "smoothing_passed": smoothing_passed,
        "source_coverage": source_coverage,
        "build_warnings": list(source_coverage.get("warnings", [])),
        "semantic_warning_counts": warning_counts,
        "fail_conditions": fail_conditions,
        "passed": not any(fail_conditions.values()),
    }


def _mesh_bounds(vertices: list[list[float]]) -> dict:
    if not vertices:
        return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
    mins = [min(vertex[i] for vertex in vertices) for i in range(3)]
    maxs = [max(vertex[i] for vertex in vertices) for i in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)],
    }


def _phase2_continuity_score() -> float | None:
    path = WORKSPACE_ROOT / "outputs" / "hero" / "prototype_32_zfield" / "validation_report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("side_silhouette_continuity_score")
    return float(value) if value is not None else None


def _add_face(vertices: list[list[float]], normals: list[list[float]], colors: list[list[float]], indices: list[int], part_ids: list[int], part_id: int, face: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, colour: tuple[int, int, int, int]) -> None:
    if face == "back":
        verts = ([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0])
        normal = [0.0, 0.0, -1.0]
    elif face == "front":
        verts = ([x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1])
        normal = [0.0, 0.0, 1.0]
    elif face == "left":
        verts = ([x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0])
        normal = [-1.0, 0.0, 0.0]
    elif face == "right":
        verts = ([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
        normal = [1.0, 0.0, 0.0]
    elif face == "up":
        verts = ([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1])
        normal = [0.0, 1.0, 0.0]
    else:
        verts = ([x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0])
        normal = [0.0, -1.0, 0.0]
    start = len(vertices)
    rgba = [colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, colour[3] / 255.0]
    vertices.extend([list(vertex) for vertex in verts])
    normals.extend([normal, normal, normal, normal])
    colors.extend([rgba, rgba, rgba, rgba])
    part_ids.extend([part_id, part_id, part_id, part_id])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])


def _add_cuboid_face(vertices: list[list[float]], normals: list[list[float]], colors: list[list[float]], indices: list[int], part_ids: list[int], part_id: int, face: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, colour_rgba_float: list[float]) -> None:
    if face == "back":
        verts = ([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0])
        normal = [0.0, 0.0, -1.0]
    elif face == "front":
        verts = ([x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1])
        normal = [0.0, 0.0, 1.0]
    elif face == "left":
        verts = ([x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0])
        normal = [-1.0, 0.0, 0.0]
    elif face == "right":
        verts = ([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1])
        normal = [1.0, 0.0, 0.0]
    elif face == "up":
        verts = ([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1])
        normal = [0.0, 1.0, 0.0]
    else: # down
        verts = ([x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0])
        normal = [0.0, -1.0, 0.0]
    start = len(vertices)
    _append_face_data(vertices, normals, colors, indices, part_ids, part_id, verts, normal, colour_rgba_float)


def _append_face_data(vertices: list[list[float]], normals: list[list[float]], colors: list[list[float]], indices: list[int], part_ids: list[int], part_id: int, verts: Sequence[Sequence[float]], normal: Sequence[float], colour_rgba_float: list[float]) -> None:
    start = len(vertices)
    vertices.extend([list(vertex) for vertex in verts])
    normal_list = list(normal)
    normals.extend([normal_list, normal_list, normal_list, normal_list])
    colors.extend([colour_rgba_float, colour_rgba_float, colour_rgba_float, colour_rgba_float])
    part_ids.extend([part_id, part_id, part_id, part_id])
    indices.extend([start, start + 1, start + 2, start, start + 2, start + 3])


def _write_scene(scene_path: Path, model_json: Path) -> None:
    text = f"""[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://scripts/topological_sprite_viewer.gd" id="1_viewer"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_floor"]
albedo_color = Color(0.33, 0.34, 0.33, 1)
roughness = 1.0

[sub_resource type="PlaneMesh" id="PlaneMesh_floor"]
size = Vector2(5.5, 4.5)

[node name="TopologicalSpriteTest" type="Node3D"]
script = ExtResource("1_viewer")
model_data_path = "{_res_path(model_json)}"

[node name="Floor" type="MeshInstance3D" parent="."]
mesh = SubResource("PlaneMesh_floor")
surface_material_override/0 = SubResource("StandardMaterial3D_floor")

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.966235, -0.257663, 0, 0.257663, 0.966235, 0, 1.65, 4.6)
current = true
fov = 40.0

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.707107, -0.353553, 0.612372, 0, 0.866025, 0.5, -0.707107, -0.353553, 0.612372, 0, 5, 3)
light_energy = 1.2
"""
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _res_path(path: Path) -> str:
    return "res://" + path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
