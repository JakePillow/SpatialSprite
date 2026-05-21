from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

SMOOTHING_MODES = {
    "none",
    "semantic_laplacian",
    "bevel_edges",
    "voxel_soften",
    "primitive_rounding",
    "hybrid_lowpoly",
}


@dataclass(frozen=True)
class SmoothingConfig:
    enabled: bool = False
    mode: str = "hybrid_lowpoly"
    iterations: int = 1
    bevel_strength: float = 0.15
    silhouette_preservation_weight: float = 1.0
    semantic_boundary_weight: float = 0.85
    outline_preservation_weight: float = 1.0
    max_silhouette_drift_px: float = 1.0
    voxel_size: float = 0.05


def smooth_mesh(
    mesh: dict[str, list],
    part_reports: list[dict[str, Any]],
    config: SmoothingConfig,
    output_dir: Path | None = None,
) -> tuple[dict[str, list], dict[str, Any]]:
    if config.mode not in SMOOTHING_MODES:
        raise ValueError(f"Unsupported smoothing mode: {config.mode}")

    before_mesh = _clone_mesh(mesh)
    if not config.enabled or config.mode == "none":
        report = _report(before_mesh, before_mesh, part_reports, config, 0)
        if output_dir:
            write_smoothing_debug_outputs(before_mesh, before_mesh, report, output_dir)
        return before_mesh, report

    after_mesh = _clone_mesh(mesh)
    part_by_id = {int(part.get("region_id", -9999)): part for part in part_reports}
    bounds_by_part = _part_bounds(after_mesh)

    for _iteration in range(max(1, config.iterations)):
        for index, vertex in enumerate(after_mesh.get("vertices", [])):
            part_id = int(after_mesh.get("part_ids", [])[index]) if index < len(after_mesh.get("part_ids", [])) else -9999
            part = part_by_id.get(part_id, {})
            primitive = part.get("primitive_type", "")
            label = part.get("label", part.get("name", ""))
            if primitive == "shell" or label == "outline":
                continue
            bounds = bounds_by_part.get(part_id)
            if not bounds:
                continue
            vertex[2] = _smoothed_z(vertex, bounds, primitive, config)

    degenerate_removed = _remove_degenerate_faces(after_mesh)
    report = _report(before_mesh, after_mesh, part_reports, config, degenerate_removed)
    if output_dir:
        write_smoothing_debug_outputs(before_mesh, after_mesh, report, output_dir)
    return after_mesh, report


def write_smoothing_debug_outputs(
    before_mesh: dict[str, list],
    after_mesh: dict[str, list],
    report: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    before_path = output_dir / "smoothing_before.png"
    after_path = output_dir / "smoothing_after.png"
    drift_path = output_dir / "silhouette_drift.png"
    boundary_path = output_dir / "boundary_preservation.png"
    report_path = output_dir / "smoothing_report.json"

    _render_projection(before_mesh).save(before_path, format="PNG")
    _render_projection(after_mesh).save(after_path, format="PNG")
    _render_drift(before_mesh, after_mesh).save(drift_path, format="PNG")
    _render_boundary_preservation(after_mesh).save(boundary_path, format="PNG")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "smoothing_before": before_path,
        "smoothing_after": after_path,
        "silhouette_drift": drift_path,
        "boundary_preservation": boundary_path,
        "smoothing_report": report_path,
    }


def _smoothed_z(vertex: list[float], bounds: dict[str, list[float]], primitive: str, config: SmoothingConfig) -> float:
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_z = (min_z + max_z) * 0.5
    half_z = max((max_z - min_z) * 0.5, 1e-6)
    depth_norm = abs(vertex[2] - center_z) / half_z
    strength = config.bevel_strength
    if config.mode == "semantic_laplacian":
        strength *= 0.55
    elif config.mode == "bevel_edges":
        strength *= 0.75
    elif config.mode == "voxel_soften":
        strength *= 0.85
    elif config.mode == "primitive_rounding":
        strength *= 1.1
    elif config.mode == "hybrid_lowpoly":
        strength *= 1.0

    if primitive in {"ellipsoid", "rounded_cuboid"}:
        strength *= 1.12
    elif primitive == "tapered_prism":
        strength *= 0.78
    elif primitive == "rigid_slab":
        strength *= 0.25

    # Preserve low-poly character: move only in depth, and only enough to
    # soften slab faces and voxel teeth without changing the authored outline.
    rounded_depth = center_z + (vertex[2] - center_z) * (1.0 - min(strength, 0.45) * (0.35 + 0.65 * depth_norm))
    return rounded_depth


def _part_bounds(mesh: dict[str, list]) -> dict[int, dict[str, list[float]]]:
    bounds: dict[int, dict[str, list[float]]] = {}
    vertices = mesh.get("vertices", [])
    part_ids = mesh.get("part_ids", [])
    for index, vertex in enumerate(vertices):
        if index >= len(part_ids):
            continue
        part_id = int(part_ids[index])
        if part_id not in bounds:
            bounds[part_id] = {"min": list(vertex), "max": list(vertex)}
            continue
        for axis in range(3):
            bounds[part_id]["min"][axis] = min(bounds[part_id]["min"][axis], vertex[axis])
            bounds[part_id]["max"][axis] = max(bounds[part_id]["max"][axis], vertex[axis])
    return bounds


def _report(
    before_mesh: dict[str, list],
    after_mesh: dict[str, list],
    part_reports: list[dict[str, Any]],
    config: SmoothingConfig,
    degenerate_removed: int,
) -> dict[str, Any]:
    before_faces = len(before_mesh.get("indices", [])) // 3
    after_faces = len(after_mesh.get("indices", [])) // 3
    drift = _silhouette_drift_px(before_mesh, after_mesh, config.voxel_size)
    outline_score = _outline_preservation_score(before_mesh, after_mesh, part_reports)
    violations = _semantic_boundary_violation_count(before_mesh, after_mesh, part_reports, config.voxel_size)
    return {
        "schema": "spritespatial_smoothing_report_v1",
        "config": asdict(config),
        "smoothing_enabled": config.enabled,
        "smoothing_mode": config.mode,
        "silhouette_drift_px": drift,
        "outline_preservation_score": outline_score,
        "semantic_boundary_violation_count": violations,
        "face_count_before_smoothing": before_faces,
        "face_count_after_smoothing": after_faces,
        "degenerate_faces_removed": degenerate_removed,
        "front_readability_delta": 0.0,
        "smoothing_passed": (
            drift <= config.max_silhouette_drift_px
            and outline_score >= 0.98
            and violations <= 0
            and after_faces > 0
        ),
    }


def _silhouette_drift_px(before_mesh: dict[str, list], after_mesh: dict[str, list], voxel_size: float) -> float:
    before_xy = {(round(v[0], 6), round(v[1], 6)) for v in before_mesh.get("vertices", [])}
    after_xy = {(round(v[0], 6), round(v[1], 6)) for v in after_mesh.get("vertices", [])}
    if before_xy == after_xy:
        return 0.0
    return 999.0


def _outline_preservation_score(before_mesh: dict[str, list], after_mesh: dict[str, list], part_reports: list[dict[str, Any]]) -> float:
    outline_ids = {
        int(part.get("region_id", -9999))
        for part in part_reports
        if part.get("primitive_type") == "shell" or part.get("label") == "outline"
    }
    if not outline_ids:
        return 1.0
    before = before_mesh.get("vertices", [])
    after = after_mesh.get("vertices", [])
    part_ids = before_mesh.get("part_ids", [])
    changed = 0
    total = 0
    for index, part_id in enumerate(part_ids):
        if int(part_id) not in outline_ids:
            continue
        total += 1
        if index >= len(after) or before[index] != after[index]:
            changed += 1
    return 1.0 - changed / max(total, 1)


def _semantic_boundary_violation_count(
    before_mesh: dict[str, list],
    after_mesh: dict[str, list],
    part_reports: list[dict[str, Any]],
    voxel_size: float,
) -> int:
    before = before_mesh.get("vertices", [])
    after = after_mesh.get("vertices", [])
    part_ids = before_mesh.get("part_ids", [])
    protected = {
        int(part.get("region_id", -9999))
        for part in part_reports
        if part.get("primitive_type") in {"shell", "rigid_slab"} or part.get("label") in {"outline", "equipment"}
    }
    violations = 0
    for index, part_id in enumerate(part_ids):
        if int(part_id) not in protected:
            continue
        if index < len(after) and abs(after[index][2] - before[index][2]) > voxel_size * 0.01:
            violations += 1
    return violations


def _remove_degenerate_faces(mesh: dict[str, list]) -> int:
    vertices = mesh.get("vertices", [])
    indices = mesh.get("indices", [])
    kept: list[int] = []
    removed = 0
    for i in range(0, len(indices), 3):
        tri = indices[i:i + 3]
        if len(tri) < 3:
            continue
        a, b, c = [vertices[index] for index in tri]
        if _triangle_area(a, b, c) <= 1e-10:
            removed += 1
            continue
        kept.extend(tri)
    mesh["indices"] = kept
    return removed


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5 * 0.5


def _clone_mesh(mesh: dict[str, list]) -> dict[str, list]:
    return {
        key: [list(item) if isinstance(item, list) else item for item in value]
        if isinstance(value, list)
        else value
        for key, value in mesh.items()
    }


def _render_projection(mesh: dict[str, list], size: tuple[int, int] = (256, 256)) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    vertices = mesh.get("vertices", [])
    if not vertices:
        return image
    min_x = min(v[0] for v in vertices)
    max_x = max(v[0] for v in vertices)
    min_y = min(v[1] for v in vertices)
    max_y = max(v[1] for v in vertices)
    scale = min((size[0] - 24) / max(max_x - min_x, 1e-6), (size[1] - 24) / max(max_y - min_y, 1e-6))
    for x, y, z in vertices:
        px = 12 + int((x - min_x) * scale)
        py = size[1] - 12 - int((y - min_y) * scale)
        shade = 120 + int(100 * (z - min(v[2] for v in vertices)) / max(max(v[2] for v in vertices) - min(v[2] for v in vertices), 1e-6))
        draw.point((px, py), fill=(shade, shade, shade, 220))
    return image


def _render_drift(before_mesh: dict[str, list], after_mesh: dict[str, list]) -> Image.Image:
    before = _render_projection(before_mesh)
    after = _render_projection(after_mesh)
    image = Image.new("RGBA", before.size, (0, 0, 0, 0))
    image.alpha_composite(before)
    image.alpha_composite(after)
    return image


def _render_boundary_preservation(mesh: dict[str, list]) -> Image.Image:
    return _render_projection(mesh)
