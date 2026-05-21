from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


DEFAULT_BASELINE = WORKSPACE_ROOT / "outputs" / "hero" / "prototype_32"
DEFAULT_ZFIELD = WORKSPACE_ROOT / "outputs" / "hero" / "prototype_32_zfield"
DEFAULT_OUT = WORKSPACE_ROOT / "outputs" / "hero" / "comparisons" / "prototype_32_vs_zfield"
ANGLES = [0, 45, 90, 135, 180]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare SpriteSpatial build outputs.")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--zfield", type=Path, default=DEFAULT_ZFIELD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_dir = _resolve(args.baseline)
    zfield_dir = _resolve(args.zfield)
    out_dir = _resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_model = _load_model_json(baseline_dir)
    zfield_model = _load_model_json(zfield_dir)
    baseline_validation = _load_json(baseline_dir / "validation_report.json")
    zfield_validation = _load_json(zfield_dir / "validation_report.json")
    primitive_assignment = _load_optional_json(zfield_dir / "primitive_assignment.json")
    semantic_warnings = _load_optional_json(zfield_dir / "semantic_warnings.json")

    image_paths = {}
    for angle in ANGLES:
        image = _side_by_side_render(baseline_model, zfield_model, baseline_validation, zfield_validation, angle)
        path = out_dir / f"side_by_side_{angle}.png"
        image.save(path, format="PNG")
        image_paths[str(angle)] = _res_path(path)

    assessment = _build_assessment(baseline_validation, zfield_validation, primitive_assignment, semantic_warnings)
    phase5a_debug_images = _copy_phase5a_debug_images(zfield_dir, out_dir)
    report = {
        "schema": "spritespatial_comparison_v2",
        "baseline_dir": _res_path(baseline_dir),
        "candidate_dir": _res_path(zfield_dir),
        "zfield_dir": _res_path(zfield_dir),
        "comparison_images": image_paths,
        "metrics": _metrics_summary(baseline_validation, zfield_validation),
        "primitive_counts": zfield_validation.get("primitive_count_by_type", {}),
        "semantic_warning_counts": zfield_validation.get("semantic_warning_counts", {}),
        "semantic_override_metrics": _override_metrics(zfield_validation),
        "smoothing_metrics": _smoothing_metrics(zfield_validation),
        "phase5a_metrics": _phase5a_metrics(zfield_validation),
        "phase5a_debug_images": phase5a_debug_images,
        "primitive_assignments": primitive_assignment.get("assignments", []),
        "assessment": assessment,
        "verdict": assessment["overall_verdict"],
    }
    _write_json(out_dir / "comparison_report.json", report)
    (out_dir / "comparison_summary.md").write_text(_summary_markdown(report), encoding="utf-8")
    print(f"Wrote comparison report: {out_dir}")
    print(f"Verdict: {assessment['overall_verdict']}")
    return 0


def _resolve(path: Path) -> Path:
    return (WORKSPACE_ROOT / path if not path.is_absolute() else path).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_model_json(path: Path) -> dict[str, Any]:
    for name in ("mesh.json", "topological_model.json", "depth_volume_model.json"):
        candidate = path / name
        if candidate.exists():
            return _load_json(candidate)
    raise FileNotFoundError(f"No supported mesh/model JSON found in {path}")


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _side_by_side_render(
    baseline_model: dict[str, Any],
    zfield_model: dict[str, Any],
    baseline_validation: dict[str, Any],
    zfield_validation: dict[str, Any],
    angle_degrees: int,
) -> Image.Image:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (245, 245, 242))
    draw = ImageDraw.Draw(image)
    left_box = (40, 80, 620, 650)
    right_box = (660, 80, 1240, 650)
    _draw_panel(draw, left_box, "Phase 1 prototype_32", baseline_validation)
    _draw_panel(draw, right_box, "Phase 2 zfield/primitives", zfield_validation)
    _render_mesh(image, baseline_model, left_box, angle_degrees)
    _render_mesh(image, zfield_model, right_box, angle_degrees)
    draw.text((40, 26), f"SpriteSpatial Phase 2 comparison - {angle_degrees} degrees", fill=(20, 20, 20))
    draw.text((40, 54), "Python fallback orthographic render from mesh JSON; not a Godot material capture.", fill=(80, 80, 80))
    return image


def _draw_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, validation: dict[str, Any]) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=(90, 90, 90), width=1)
    draw.text((x0 + 12, y0 + 10), title, fill=(15, 15, 15))
    metrics = [
        f"passed: {validation.get('passed')}",
        f"faces: {_face_count(validation)}",
        f"voxels: {_voxel_count(validation)}",
        f"black/fallback: {_fallback_metric(validation):.4f}",
    ]
    if validation.get("primitive_count_by_type"):
        metrics.append(f"primitives: {validation.get('primitive_count_by_type')}")
    if validation.get("mylar_depth_enabled"):
        metrics.append(f"closed SDF: {validation.get('surface_nets_ready')}")
        metrics.append(f"sdf: {validation.get('sdf_volume_shape')}")
    for index, line in enumerate(metrics):
        draw.text((x0 + 12, y0 + 30 + index * 16), line, fill=(55, 55, 55))


def _render_mesh(image: Image.Image, model: dict[str, Any], box: tuple[int, int, int, int], angle_degrees: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    vertices = model.get("vertices", [])
    colors = model.get("colors", [])
    indices = model.get("indices", [])
    if not vertices or not indices:
        return

    angle = math.radians(angle_degrees)
    ca, sa = math.cos(angle), math.sin(angle)
    transformed = []
    for x, y, z in vertices:
        rx = x * ca + z * sa
        rz = -x * sa + z * ca
        transformed.append((rx, y, rz))

    min_x = min(v[0] for v in transformed)
    max_x = max(v[0] for v in transformed)
    min_y = min(v[1] for v in transformed)
    max_y = max(v[1] for v in transformed)
    panel_w = box[2] - box[0]
    panel_h = box[3] - box[1]
    scale = min(panel_w * 0.74 / max(max_x - min_x, 1e-6), panel_h * 0.70 / max(max_y - min_y, 1e-6))
    cx = (box[0] + box[2]) * 0.5
    cy = (box[1] + box[3]) * 0.57

    triangles = []
    for i in range(0, len(indices), 3):
        ids = indices[i:i + 3]
        if len(ids) < 3:
            continue
        pts3 = [transformed[index] for index in ids]
        avg_z = sum(point[2] for point in pts3) / 3.0
        pts2 = [
            (
                cx + (point[0] - (min_x + max_x) * 0.5) * scale,
                cy - (point[1] - (min_y + max_y) * 0.5) * scale,
            )
            for point in pts3
        ]
        color = _triangle_color(colors, ids)
        triangles.append((avg_z, pts2, color))

    for _avg_z, pts2, color in sorted(triangles, key=lambda item: item[0]):
        draw.polygon(pts2, fill=color, outline=(30, 30, 30, 35))


def _triangle_color(colors: list[list[float]], ids: list[int]) -> tuple[int, int, int, int]:
    if not colors:
        return (160, 160, 160, 255)
    samples = [colors[index] for index in ids if index < len(colors)]
    if not samples:
        return (160, 160, 160, 255)
    rgba = [sum(sample[channel] for sample in samples) / len(samples) for channel in range(4)]
    channels = [max(0, min(255, int(value * 255))) for value in rgba]
    return channels[0], channels[1], channels[2], channels[3]


def _build_assessment(
    baseline: dict[str, Any],
    zfield: dict[str, Any],
    primitive_assignment: dict[str, Any],
    semantic_warnings: dict[str, Any],
) -> dict[str, Any]:
    baseline_voxels = _voxel_count(baseline)
    zfield_voxels = _voxel_count(zfield)
    baseline_faces = _face_count(baseline)
    zfield_faces = _face_count(zfield)
    z_bounds = _safe_bounds_size(zfield)
    baseline_bounds = _safe_bounds_size(baseline)
    outline_voxels = zfield.get("outline_shell_voxel_count", 0)
    outline_pixels = _outline_pixels(primitive_assignment)
    primitive_counts = zfield.get("primitive_count_by_type", {})
    phase5a_infrastructure = bool(zfield.get("mylar_depth_enabled") and zfield.get("closed_body_enabled"))

    continuity_score = zfield.get("side_silhouette_continuity_score")
    side_profile_improved = (
        (continuity_score is not None and continuity_score >= 0.75)
        or (zfield.get("primitive_enabled", False) and zfield_voxels <= baseline_voxels and z_bounds[2] > 0)
    )
    volume_coherent = {"ellipsoid", "rounded_cuboid", "tapered_prism"}.issubset(set(primitive_counts))
    outline_controlled = outline_pixels > 0 and outline_voxels <= outline_pixels * 2 and not zfield.get("fail_conditions", {}).get("outline_becomes_full_depth_slab", True)
    smoothing_reported = zfield.get("smoothing_enabled", False) or zfield.get("smoothing_mode") not in (None, "none")
    smoothing_ok = _smoothing_passed(zfield)
    budget_ok = zfield.get("passed", False) and zfield_faces <= 4000 and (not smoothing_reported or smoothing_ok)
    readability_preserved = abs(baseline.get("front_alpha_coverage", baseline.get("alpha_coverage", 0)) - zfield.get("front_projection_coverage", 0)) < 0.01
    worsened_parts = _worsened_parts(zfield, semantic_warnings)

    positives = sum([side_profile_improved, volume_coherent, outline_controlled, budget_ok, readability_preserved])
    if phase5a_infrastructure and zfield.get("surface_nets_ready", False) and zfield_faces == 0:
        verdict = "infrastructure_only"
    elif positives >= 4 and not worsened_parts:
        verdict = "better"
    elif positives >= 4:
        verdict = "better_with_caveats"
    elif positives >= 3:
        verdict = "mixed"
    else:
        verdict = "worse"

    return {
        "side_profile": {
            "improved": side_profile_improved,
            "reason": f"Continuity score is {continuity_score}; occupied voxels changed from {baseline_voxels} to {zfield_voxels}; depth span {z_bounds[2]:.3f} vs baseline {baseline_bounds[2]:.3f}.",
        },
        "head_torso_limb_volume": {
            "improved": volume_coherent,
            "reason": f"Primitive mix is {primitive_counts}; head/torso/limbs are no longer all cuboid/flat.",
        },
        "outline_shell": {
            "controlled": outline_controlled,
            "reason": f"Outline shell voxels {outline_voxels}; outline source pixels {outline_pixels}.",
        },
        "budget": {
            "within_budget": budget_ok,
            "reason": f"Candidate faces {zfield_faces}; baseline faces {baseline_faces}; profile budget treated as 4000.",
        },
        "front_readability": {
            "preserved": readability_preserved,
            "reason": f"Baseline alpha coverage {baseline.get('front_alpha_coverage', baseline.get('alpha_coverage', 0)):.4f}; Candidate front projection {zfield.get('front_projection_coverage', 0):.4f}.",
        },
        "smoothing": {
            "passed": smoothing_ok,
            "reason": _smoothing_reason(zfield),
        },
        "phase5a_closed_sdf": {
            "ready": bool(zfield.get("surface_nets_ready", False)),
            "reason": (
                f"Closed SDF infrastructure present; shape {zfield.get('sdf_volume_shape', [])}; "
                f"dtypes {zfield.get('sdf_dtype')} / {zfield.get('semantic_dtype')}; "
                f"manifold-ready estimate {zfield.get('manifold_ready_estimate')}."
            )
            if phase5a_infrastructure
            else "Candidate is not a Phase 5A closed SDF build.",
        },
        "worsened_parts": worsened_parts,
        "overall_verdict": verdict,
    }


def _worsened_parts(zfield: dict[str, Any], semantic_warnings: dict[str, Any]) -> list[str]:
    worsened = []
    if zfield.get("malformed_region_count", 0):
        worsened.append("malformed semantic regions present")
    if zfield.get("fallback_primitive_count", 0):
        worsened.append("some regions fell back to generic cuboid")
    if zfield.get("override_pixels_applied", 0):
        if zfield.get("torso_head_overlap_count_after_override", 0):
            worsened.append("torso/head overlap remains after override")
        if zfield.get("disconnected_critical_labels_after_override", 0):
            worsened.append("a critical authored label remains disconnected")
        return worsened
    warning_counts = zfield.get("semantic_warning_counts", {})
    if warning_counts.get("disconnected_body_parts", 0):
        worsened.append("semantic labels remain disconnected in source decomposition")
    if warning_counts.get("torso_head_overlap", 0):
        worsened.append("torso/head semantic overlap remains")
    return worsened


def _safe_bounds_size(report: dict[str, Any]) -> list[float]:
    size = None
    if report.get("final_mesh_bounds", {}).get("size"):
        size = report["final_mesh_bounds"]["size"]
    elif report.get("profile_validation", {}).get("mesh_stats", {}).get("bounding_box_dimensions"):
        size = report["profile_validation"]["mesh_stats"]["bounding_box_dimensions"]
    else:
        size = report.get("bounding_box_dimensions")
    return size if isinstance(size, list) and len(size) == 3 else [0.0, 0.0, 0.0]


def _metrics_summary(baseline: dict[str, Any], zfield: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline": {
            "passed": baseline.get("passed"),
            "faces": _face_count(baseline),
            "voxels": _voxel_count(baseline),
            "fallback_or_black_face_percentage": _fallback_metric(baseline),
            "front_coverage": baseline.get("front_alpha_coverage", baseline.get("alpha_coverage", 0.0)),
            "bounds": _safe_bounds_size(baseline),
        },
        "zfield": {
            "passed": zfield.get("passed"),
            "faces": _face_count(zfield),
            "voxels": _voxel_count(zfield),
            "fallback_or_black_face_percentage": _fallback_metric(zfield),
            "front_coverage": zfield.get("front_projection_coverage", 0.0),
            "bounds": _safe_bounds_size(zfield),
            "average_region_depth": zfield.get("average_region_depth"),
            "outline_shell_voxel_count": zfield.get("outline_shell_voxel_count"),
        },
        "candidate": {
            "passed": zfield.get("passed"),
            "faces": _face_count(zfield),
            "voxels": _voxel_count(zfield),
            "fallback_or_black_face_percentage": _fallback_metric(zfield),
            "front_coverage": zfield.get("front_projection_coverage", 0.0),
            "bounds": _safe_bounds_size(zfield),
            "average_region_depth": zfield.get("average_region_depth"),
            "outline_shell_voxel_count": zfield.get("outline_shell_voxel_count"),
            "smoothing": _smoothing_metrics(zfield),
        },
    }


def _face_count(report: dict[str, Any]) -> int:
    return int(report.get("total_faces") or report.get("profile_validation", {}).get("mesh_stats", {}).get("triangle_count") or report.get("exposed_face_count") or 0)


def _voxel_count(report: dict[str, Any]) -> int:
    return int(report.get("occupied_voxels") or report.get("occupied_voxel_count") or 0)


def _fallback_metric(report: dict[str, Any]) -> float:
    return float(report.get("fallback_face_percentage", report.get("percentage_of_black_side_faces", 0.0)))


def _outline_pixels(primitive_assignment: dict[str, Any]) -> int:
    for assignment in primitive_assignment.get("assignments", []):
        if assignment.get("name") == "outline":
            return int(assignment.get("pixel_count", 0))
    return 0


def _override_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": report.get("semantic_override_mode"),
        "override_pixels_applied": report.get("override_pixels_applied", 0),
        "override_overlap_count": report.get("override_overlap_count", 0),
        "unlabelled_opaque_pixel_ratio": report.get("unlabelled_opaque_pixel_ratio", 0.0),
        "critical_label_coverage": report.get("critical_label_coverage", {}),
        "torso_head_overlap_count_after_override": report.get("torso_head_overlap_count_after_override"),
        "disconnected_critical_labels_after_override": report.get("disconnected_critical_labels_after_override"),
    }


def _smoothing_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": report.get("smoothing_enabled", False),
        "mode": report.get("smoothing_mode", "none"),
        "silhouette_drift_px": report.get("silhouette_drift_px", 0.0),
        "outline_preservation_score": report.get("outline_preservation_score", 1.0),
        "semantic_boundary_violation_count": report.get("semantic_boundary_violation_count", 0),
        "face_count_before_smoothing": report.get("face_count_before_smoothing", 0),
        "face_count_after_smoothing": report.get("face_count_after_smoothing", 0),
        "degenerate_faces_removed": report.get("degenerate_faces_removed", 0),
        "smoothing_passed": report.get("smoothing_passed", True),
    }


def _smoothing_passed(report: dict[str, Any]) -> bool:
    if not report.get("smoothing_enabled", False) and report.get("smoothing_mode") in (None, "none"):
        return True
    return (
        bool(report.get("smoothing_passed", False))
        and float(report.get("silhouette_drift_px", 999.0)) <= 1.0
        and float(report.get("outline_preservation_score", 0.0)) >= 0.98
        and int(report.get("semantic_boundary_violation_count", 999)) == 0
        and int(report.get("face_count_after_smoothing", 0)) > 0
    )


def _smoothing_reason(report: dict[str, Any]) -> str:
    metrics = _smoothing_metrics(report)
    if not metrics["enabled"] and metrics["mode"] in (None, "none"):
        return "Smoothing was not enabled for the candidate."
    return (
        f"Mode {metrics['mode']}; drift {float(metrics['silhouette_drift_px']):.2f}px; "
        f"outline preservation {float(metrics['outline_preservation_score']):.3f}; "
        f"semantic boundary violations {metrics['semantic_boundary_violation_count']}; "
        f"faces {metrics['face_count_before_smoothing']} -> {metrics['face_count_after_smoothing']}."
    )


def _phase5a_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "mylar_depth_enabled": report.get("mylar_depth_enabled", False),
        "closed_body_enabled": report.get("closed_body_enabled", False),
        "back_mode": report.get("back_mode"),
        "sdf_volume_shape": report.get("sdf_volume_shape", []),
        "sdf_dtype": report.get("sdf_dtype"),
        "semantic_dtype": report.get("semantic_dtype"),
        "surface_nets_ready": report.get("surface_nets_ready", False),
        "manifold_ready_estimate": report.get("manifold_ready_estimate", False),
    }


def _copy_phase5a_debug_images(candidate_dir: Path, out_dir: Path) -> dict[str, str]:
    sources = {
        "z_front": candidate_dir / "mylar" / "z_front.png",
        "z_back": candidate_dir / "back" / "z_back.png",
        "seam_debug": candidate_dir / "back" / "seam_debug.png",
        "sdf_slice_contact_sheet": candidate_dir / "sdf" / "sdf_slice_contact_sheet.png",
    }
    copied = {}
    for name, source in sources.items():
        if not source.exists():
            continue
        target = out_dir / f"{name}.png"
        shutil.copyfile(source, target)
        copied[name] = _res_path(target)
    return copied


def _summary_markdown(report: dict[str, Any]) -> str:
    assessment = report["assessment"]
    metrics = report["metrics"]
    return "\n".join(
        [
            "# SpriteSpatial Profile Comparison",
            "",
            f"Verdict: **{report['verdict']}**",
            "",
            "## Metrics",
            "",
            f"- Baseline faces: {metrics['baseline']['faces']}",
            f"- Candidate faces: {metrics['zfield']['faces']}",
            f"- Baseline voxels: {metrics['baseline']['voxels']}",
            f"- Candidate voxels: {metrics['zfield']['voxels']}",
            f"- Candidate primitives: {report['primitive_counts']}",
            f"- Candidate semantic warnings: {report['semantic_warning_counts']}",
            f"- Candidate override metrics: {report['semantic_override_metrics']}",
            f"- Candidate smoothing: {report['smoothing_metrics']}",
            f"- Candidate Phase 5A: {report['phase5a_metrics']}",
            "",
            "## Questions",
            "",
            f"1. Side profile improved: **{assessment['side_profile']['improved']}**. {assessment['side_profile']['reason']}",
            f"2. Head/torso/limb volume coherent: **{assessment['head_torso_limb_volume']['improved']}**. {assessment['head_torso_limb_volume']['reason']}",
            f"3. Outline shell controlled: **{assessment['outline_shell']['controlled']}**. {assessment['outline_shell']['reason']}",
            f"4. Face/voxel budget ok: **{assessment['budget']['within_budget']}**. {assessment['budget']['reason']}",
            f"5. Front readability preserved: **{assessment['front_readability']['preserved']}**. {assessment['front_readability']['reason']}",
            f"6. Worsened semantic parts: {assessment['worsened_parts'] or 'none detected by validation, though source semantic warnings remain.'}",
            f"7. Smoothing passed: **{assessment['smoothing']['passed']}**. {assessment['smoothing']['reason']}",
            f"8. Closed SDF infrastructure ready: **{assessment['phase5a_closed_sdf']['ready']}**. {assessment['phase5a_closed_sdf']['reason']}",
            "",
            "## Render Note",
            "",
            "Side-by-side images are Python fallback orthographic renders from mesh JSON, not Godot captures.",
            "",
        ]
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _res_path(path: Path) -> str:
    try:
        return "res://" + path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
