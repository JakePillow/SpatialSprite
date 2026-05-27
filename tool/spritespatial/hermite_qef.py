from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


CELL_CORNERS = (
    (0, 0, 0),
    (1, 0, 0),
    (0, 1, 0),
    (1, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (0, 1, 1),
    (1, 1, 1),
)

CELL_EDGES = (
    (0, 1),
    (2, 3),
    (4, 5),
    (6, 7),
    (0, 2),
    (1, 3),
    (4, 6),
    (5, 7),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


def solve_qef_for_cell(
    sdf: np.ndarray,
    semantic: np.ndarray,
    cell: tuple[int, int, int],
    standard_position: np.ndarray,
    iso_level: float = 0.0,
    regularization: float = 0.001,
    max_displacement: float = 0.35,
    placement_mode: str = "qef",
) -> dict[str, Any]:
    y, x, z = cell
    values = np.asarray([sdf[y + dy, x + dx, z + dz] for dy, dx, dz in CELL_CORNERS], dtype=np.float32)
    samples = hermite_samples_for_cell(sdf, semantic, cell, values, iso_level)
    report_base = {
        "source_cell": [int(y), int(x), int(z)],
        "sample_count": len(samples),
        "standard_position": [float(value) for value in standard_position.tolist()],
        "accepted": False,
        "fallback": True,
        "condition_warning": False,
        "displacement": 0.0,
        "reason": "",
    }
    if len(samples) < 3:
        return {**report_base, "position": report_base["standard_position"], "reason": "insufficient_samples", "samples": samples}
    normals = np.asarray([sample["normal"] for sample in samples], dtype=np.float32)
    points = np.asarray([sample["position"] for sample in samples], dtype=np.float32)
    labels = [int(sample.get("semantic_label", 0)) for sample in samples]
    semantic_boundary = len({label for label in labels if label != 0}) > 1
    silhouette = any(bool(sample.get("silhouette", False)) for sample in samples)
    directional = any(bool(sample.get("directional_feature", False)) for sample in samples)
    qef_max = _constrained_max_displacement(
        max_displacement,
        placement_mode,
        silhouette=silhouette,
        semantic_boundary=semantic_boundary,
        directional=directional,
    )
    reg = max(float(regularization), 0.0)
    sqrt_reg = math.sqrt(reg) if reg > 0.0 else 0.0
    if sqrt_reg > 0.0:
        a = np.vstack([normals, np.eye(3, dtype=np.float32) * sqrt_reg])
        b = np.concatenate([np.sum(normals * points, axis=1), standard_position.astype(np.float32) * sqrt_reg])
    else:
        a = normals
        b = np.sum(normals * points, axis=1)
    try:
        ata = a.T @ a
        condition = float(np.linalg.cond(ata))
        solved = np.linalg.lstsq(a, b, rcond=None)[0].astype(np.float32)
    except np.linalg.LinAlgError:
        return {**report_base, "position": report_base["standard_position"], "reason": "linalg_failure", "samples": samples}
    if not bool(np.all(np.isfinite(solved))):
        return {**report_base, "position": report_base["standard_position"], "reason": "nonfinite_solution", "samples": samples}
    solved = _clamp_to_cell(solved, cell, margin=0.12)
    delta = solved - standard_position
    distance = float(np.linalg.norm(delta))
    if distance > qef_max:
        if qef_max <= 1.0e-8:
            solved = standard_position.copy()
        else:
            solved = standard_position + delta / max(distance, 1.0e-8) * qef_max
        distance = float(np.linalg.norm(solved - standard_position))
    condition_warning = condition > 1.0e6
    accepted = not condition_warning and distance > 1.0e-7
    if condition_warning:
        solved = standard_position.copy()
        distance = 0.0
    return {
        **report_base,
        "position": [float(value) for value in solved.tolist()],
        "accepted": bool(accepted),
        "fallback": not bool(accepted),
        "condition_warning": bool(condition_warning),
        "condition_number": condition,
        "displacement": distance,
        "semantic_boundary": semantic_boundary,
        "silhouette": silhouette,
        "directional_feature": directional,
        "max_displacement_used": qef_max,
        "reason": "accepted" if accepted else ("condition_warning" if condition_warning else "zero_or_clamped_displacement"),
        "samples": samples,
    }


def hermite_samples_for_cell(
    sdf: np.ndarray,
    semantic: np.ndarray,
    cell: tuple[int, int, int],
    values: np.ndarray,
    iso_level: float,
) -> list[dict[str, Any]]:
    y, x, z = cell
    corner_positions = [
        np.asarray([float(x + dx), float(y + dy), float(z + dz)], dtype=np.float32)
        for dy, dx, dz in CELL_CORNERS
    ]
    samples = []
    for a, b in CELL_EDGES:
        va = float(values[a] - iso_level)
        vb = float(values[b] - iso_level)
        if (va <= 0.0) == (vb <= 0.0):
            continue
        denom = va - vb
        t = 0.5 if abs(denom) < 1.0e-8 else va / denom
        t = max(0.0, min(1.0, t))
        position = corner_positions[a] + (corner_positions[b] - corner_positions[a]) * t
        normal = _sample_gradient(sdf, position)
        labels = _edge_labels(semantic, cell, a, b)
        label = _majority_nonzero(labels)
        samples.append(
            {
                "position": [float(value) for value in position.tolist()],
                "normal": [float(value) for value in normal.tolist()],
                "semantic_label": int(label),
                "semantic_labels": labels,
                "semantic_boundary": len({value for value in labels if value != 0}) > 1,
                "silhouette": 0 in labels,
                "directional_feature": label == 4,
            }
        )
    return samples


def build_qef_report(cell_reports: list[dict[str, Any]], placement_mode: str, regularization: float, max_displacement: float) -> dict[str, Any]:
    processed = len(cell_reports)
    accepted = sum(1 for item in cell_reports if item.get("accepted", False))
    rejected = processed - accepted
    displacements = [float(item.get("displacement", 0.0)) for item in cell_reports]
    observed_max = float(np.max(displacements)) if displacements else 0.0
    return {
        "surface_net_vertex_placement": placement_mode,
        "qef_enabled": placement_mode in {"qef", "patch_qef"},
        "qef_regularization": float(regularization),
        "qef_max_displacement_limit": float(max_displacement),
        "qef_max_displacement": observed_max,
        "qef_max_displacement_observed": observed_max,
        "qef_cells_processed": processed,
        "qef_cells_accepted": accepted,
        "qef_cells_rejected": rejected,
        "qef_acceptance_ratio": float(accepted) / float(max(processed, 1)),
        "qef_mean_displacement": float(np.mean(displacements)) if displacements else 0.0,
        "qef_fallback_count": sum(1 for item in cell_reports if item.get("fallback", False)),
        "qef_condition_warning_count": sum(1 for item in cell_reports if item.get("condition_warning", False)),
    }


def write_qef_debug(mesh: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    qef = dict(mesh.get("qef", {}))
    reports = list(qef.get("cell_reports", []))
    paths = {
        "hermite_samples": output_dir / "hermite_samples.json",
        "qef_cell_report": output_dir / "qef_cell_report.json",
        "qef_displacement_debug": output_dir / "qef_displacement_debug.png",
        "qef_rejection_debug": output_dir / "qef_rejection_debug.png",
        "qef_normal_debug": output_dir / "qef_normal_debug.png",
        "qef_condition_debug": output_dir / "qef_condition_debug.json",
        "before_after_qef_wireframe": output_dir / "before_after_qef_wireframe.png",
        "before_after_qef_contact_sheet": output_dir / "before_after_qef_contact_sheet.png",
    }
    _write_json(paths["hermite_samples"], {"cells": [{"source_cell": item.get("source_cell"), "samples": item.get("samples", [])} for item in reports]})
    _write_json(paths["qef_cell_report"], {"report": qef.get("report", {}), "cells": reports})
    _write_json(
        paths["qef_condition_debug"],
        {
            "condition_warning_count": qef.get("report", {}).get("qef_condition_warning_count", 0),
            "warnings": [item for item in reports if item.get("condition_warning", False)],
        },
    )
    _write_cell_map(reports, paths["qef_displacement_debug"], "displacement")
    _write_cell_map(reports, paths["qef_rejection_debug"], "rejection")
    _write_cell_map(reports, paths["qef_normal_debug"], "normal")
    before = np.asarray(qef.get("standard_vertices", mesh.get("vertices", [])), dtype=np.float32)
    after = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    _write_pair(_wireframe_image(before, faces), _wireframe_image(after, faces), paths["before_after_qef_wireframe"])
    _write_pair(_projection_image(before), _projection_image(after), paths["before_after_qef_contact_sheet"])
    return paths


def _sample_gradient(sdf: np.ndarray, position: np.ndarray) -> np.ndarray:
    x = int(round(float(position[0])))
    y = int(round(float(position[1])))
    z = int(round(float(position[2])))
    yy = min(max(y, 1), sdf.shape[0] - 2)
    xx = min(max(x, 1), sdf.shape[1] - 2)
    zz = min(max(z, 1), sdf.shape[2] - 2)
    gy = float(sdf[yy + 1, xx, zz] - sdf[yy - 1, xx, zz])
    gx = float(sdf[yy, xx + 1, zz] - sdf[yy, xx - 1, zz])
    gz = float(sdf[yy, xx, zz + 1] - sdf[yy, xx, zz - 1])
    normal = np.asarray([gx, gy, gz], dtype=np.float32)
    length = float(np.linalg.norm(normal))
    if length <= 1.0e-8:
        return np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    return normal / length


def _edge_labels(semantic: np.ndarray, cell: tuple[int, int, int], a: int, b: int) -> list[int]:
    y, x, z = cell
    result = []
    for corner in (a, b):
        dy, dx, dz = CELL_CORNERS[corner]
        yy, xx, zz = y + dy, x + dx, z + dz
        if 0 <= yy < semantic.shape[0] and 0 <= xx < semantic.shape[1] and 0 <= zz < semantic.shape[2]:
            result.append(int(semantic[yy, xx, zz]))
    return result


def _majority_nonzero(labels: list[int]) -> int:
    values = [label for label in labels if label != 0]
    if not values:
        return 0
    return max(set(values), key=values.count)


def _constrained_max_displacement(
    max_displacement: float,
    placement_mode: str,
    *,
    silhouette: bool,
    semantic_boundary: bool,
    directional: bool,
) -> float:
    value = max(0.0, float(max_displacement))
    if placement_mode == "patch_qef":
        if silhouette:
            value *= 0.20
        if semantic_boundary:
            value *= 0.45
        if directional:
            value *= 0.35
    return value


def _clamp_to_cell(position: np.ndarray, cell: tuple[int, int, int], margin: float) -> np.ndarray:
    y, x, z = cell
    low = np.asarray([float(x) - margin, float(y) - margin, float(z) - margin], dtype=np.float32)
    high = np.asarray([float(x) + 1.0 + margin, float(y) + 1.0 + margin, float(z) + 1.0 + margin], dtype=np.float32)
    return np.minimum(np.maximum(position, low), high)


def _write_cell_map(reports: list[dict[str, Any]], path: Path, mode: str) -> None:
    cells = [item.get("source_cell", [0, 0, 0]) for item in reports]
    if not cells:
        Image.new("RGBA", (1, 1), (0, 0, 0, 255)).save(path, format="PNG")
        return
    height = max(int(cell[0]) for cell in cells) + 2
    width = max(int(cell[1]) for cell in cells) + 2
    image = Image.new("RGBA", (width * 5, height * 5), (0, 45, 55, 255))
    draw = ImageDraw.Draw(image)
    max_disp = max((float(item.get("displacement", 0.0)) for item in reports), default=1.0)
    for item in reports:
        y, x, _z = (int(value) for value in item.get("source_cell", [0, 0, 0]))
        if mode == "rejection":
            color = (80, 220, 140, 255) if item.get("accepted", False) else (255, 90, 90, 255)
        elif mode == "normal":
            samples = item.get("samples", [])
            normal = np.asarray(samples[0].get("normal", [0, 0, 1]) if samples else [0, 0, 1], dtype=np.float32)
            axis = int(np.argmax(np.abs(normal)))
            color = [(240, 80, 80, 255), (80, 220, 120, 255), (100, 150, 255, 255)][axis]
        else:
            t = float(item.get("displacement", 0.0)) / max(max_disp, 1.0e-6)
            color = (int(255 * t), int(220 * (1.0 - t)), 70, 255)
        draw.rectangle((x * 5, y * 5, x * 5 + 4, y * 5 + 4), fill=color)
    image.save(path, format="PNG")


def _wireframe_image(vertices: np.ndarray, faces: list[list[int]], scale: int = 5) -> Image.Image:
    if vertices.size == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    width = max(1, int(np.max(vertices[:, 0])) + 3) * scale
    height = max(1, int(np.max(vertices[:, 1])) + 3) * scale
    image = Image.new("RGBA", (width, height), (8, 18, 22, 255))
    draw = ImageDraw.Draw(image)
    for face in faces:
        points = [(float(vertices[index, 0]) * scale, float(vertices[index, 1]) * scale) for index in face if index < len(vertices)]
        if len(points) >= 2:
            draw.line(points + [points[0]], fill=(120, 220, 210, 180), width=1)
    return image


def _projection_image(vertices: np.ndarray, scale: int = 5) -> Image.Image:
    if vertices.size == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    width = max(1, int(np.max(vertices[:, 0])) + 3) * scale
    height = max(1, int(np.max(vertices[:, 1])) + 3) * scale
    image = Image.new("RGBA", (width, height), (8, 18, 22, 255))
    draw = ImageDraw.Draw(image)
    for vertex in vertices:
        x = int(round(float(vertex[0]) * scale))
        y = int(round(float(vertex[1]) * scale))
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(255, 210, 90, 220))
    return image


def _write_pair(left: Image.Image, right: Image.Image, path: Path) -> None:
    width = max(left.width, right.width)
    height = max(left.height, right.height)
    sheet = Image.new("RGBA", (width * 2, height), (0, 0, 0, 255))
    sheet.alpha_composite(left, (0, 0))
    sheet.alpha_composite(right, (width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((2, 2), "average", fill=(255, 255, 255, 255))
    draw.text((width + 2, 2), "qef", fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
