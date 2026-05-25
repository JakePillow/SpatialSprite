from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

Pixel = tuple[int, int]


SEMANTIC_LABEL_IDS = {
    "outline": 1,
    "head": 2,
    "face": 3,
    "hair/hat": 4,
    "hat_hair": 4,
    "torso": 5,
    "left_arm": 6,
    "right_arm": 7,
    "left_leg": 8,
    "right_leg": 9,
    "boots/feet": 10,
    "boots_feet": 10,
    "equipment/shield/sword": 11,
    "equipment": 11,
    "shield": 11,
    "sword": 11,
    "unknown": 12,
}

LABEL_ALIASES = {
    "hat_hair": "hair/hat",
    "hair": "hair/hat",
    "cap": "hair/hat",
    "boots_feet": "boots/feet",
    "feet": "boots/feet",
    "boots": "boots/feet",
    "equipment": "equipment/shield/sword",
    "shield": "equipment/shield/sword",
    "sword": "equipment/shield/sword",
}

PRIMITIVE_CANDIDATES = {
    "head": ["ellipsoid", "rounded_cuboid"],
    "face": ["rounded_front", "rigid_slab"],
    "hair/hat": ["tapered_prism", "shell", "capsule_chain"],
    "torso": ["rounded_cuboid", "ellipsoid"],
    "left_arm": ["capsule_chain", "tapered_prism"],
    "right_arm": ["capsule_chain", "tapered_prism"],
    "left_leg": ["tapered_capsule_chain", "capsule_chain"],
    "right_leg": ["tapered_capsule_chain", "capsule_chain"],
    "boots/feet": ["flattened_rounded_box", "rounded_cuboid"],
    "equipment/shield/sword": ["rigid_slab", "shell", "tapered_prism"],
    "outline": ["shell"],
    "unknown": ["rounded_cuboid"],
}


@dataclass(frozen=True)
class RegionFieldDescriptor:
    region_id: int
    semantic_class: str
    centerline: list[list[float]]
    tangent_vectors: list[list[float]]
    local_frame_basis: dict[str, list[float]]
    thickness_function: dict[str, Any]
    depth_bias: float
    anisotropy: dict[str, float]
    curvature_profile: list[float]
    primitive_candidates: list[str]
    silhouette_constraint_mask: dict[str, Any]
    directional_profile: str
    adjacency_links: list[dict[str, Any]]
    attachment_anchors: list[dict[str, Any]]


def build_region_field_descriptors(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    z_front: np.ndarray,
    z_back: np.ndarray,
    z_axis: np.ndarray,
    output_dir: Path | None = None,
    emit_debug: bool = False,
) -> dict[str, Any]:
    labels = _label_grid(alpha_mask, label_by_pixel)
    seam = _silhouette_seam(alpha_mask)
    components = _semantic_components(labels, alpha_mask)
    region_grid = np.full(alpha_mask.shape, -1, dtype=np.int32)
    raw: list[dict[str, Any]] = []
    masks: dict[int, np.ndarray] = {}
    field_map = np.zeros(alpha_mask.shape, dtype=np.float32)
    anisotropy_map = np.zeros(alpha_mask.shape, dtype=np.float32)
    curvature_map = np.zeros(alpha_mask.shape, dtype=np.float32)

    for region_id, component in enumerate(components):
        semantic = str(component["semantic_class"])
        mask = component["mask"]
        region_grid[mask] = region_id
        masks[region_id] = mask
        edt = _edt(mask)
        centerline = _extract_centerline(mask, edt, semantic)
        thickness_samples = _thickness_samples(centerline, edt, semantic)
        tangents = _tangent_vectors(centerline)
        frame = _local_frame(tangents)
        depth_bias = _depth_bias(mask, z_front, z_back)
        anisotropy = _anisotropy(mask, semantic)
        curvature = _curvature_profile(tangents)
        silhouette_points = [[int(x), int(y)] for y, x in np.argwhere(mask & seam)]
        descriptor = {
            "region_id": region_id,
            "semantic_class": semantic,
            "centerline": centerline,
            "tangent_vectors": tangents,
            "local_frame_basis": frame,
            "thickness_function": {
                "type": _thickness_kind(semantic),
                "samples": [
                    {"s": float(index / max(len(thickness_samples) - 1, 1)), "value": float(value)}
                    for index, value in enumerate(thickness_samples)
                ],
            },
            "depth_bias": depth_bias,
            "anisotropy": anisotropy,
            "curvature_profile": curvature,
            "primitive_candidates": PRIMITIVE_CANDIDATES.get(semantic, PRIMITIVE_CANDIDATES["unknown"]),
            "silhouette_constraint_mask": {
                "pixel_count": len(silhouette_points),
                "pixels": silhouette_points,
            },
            "directional_profile": _directional_profile(semantic),
            "adjacency_links": [],
            "attachment_anchors": [],
            "pixel_count": int(np.count_nonzero(mask)),
        }
        raw.append(descriptor)
        _write_field_maps(mask, centerline, thickness_samples, anisotropy, curvature, field_map, anisotropy_map, curvature_map)

    _attach_adjacency(raw, masks, region_grid)
    descriptors = [RegionFieldDescriptor(**{key: value for key, value in item.items() if key != "pixel_count"}) for item in raw]
    refined, refined_semantic, silhouette_score = apply_rfd_fields(
        occupancy,
        semantic_volume,
        alpha_mask,
        seam,
        labels,
        descriptors,
        masks,
        z_front,
        z_back,
        z_axis,
    )
    report = _rfd_report(descriptors, raw, refined, alpha_mask, field_map, silhouette_score)
    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = write_rfd_debug(
            output_dir,
            descriptors,
            labels,
            alpha_mask,
            field_map,
            anisotropy_map,
            curvature_map,
            report,
            emit_debug,
        )
    return {
        "descriptors": descriptors,
        "descriptor_json": [_descriptor_json(descriptor) for descriptor in descriptors],
        "region_masks": masks,
        "region_grid": region_grid,
        "labels": labels,
        "occupancy": refined,
        "semantic_volume": refined_semantic,
        "report": report,
        "paths": paths,
    }


def apply_rfd_fields(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    alpha_mask: np.ndarray,
    seam: np.ndarray,
    labels: np.ndarray,
    descriptors: list[RegionFieldDescriptor],
    masks: dict[int, np.ndarray],
    z_front: np.ndarray,
    z_back: np.ndarray,
    z_axis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    refined = occupancy.copy()
    refined_semantic = semantic_volume.copy()
    dz = abs(float(np.min(np.diff(z_axis)))) if len(z_axis) > 1 else 1.0
    center_index = int(np.argmin(np.abs(z_axis))) if z_axis.size else occupancy.shape[2] // 2
    for descriptor in descriptors:
        semantic = descriptor.semantic_class
        if semantic == "outline":
            continue
        mask = masks.get(descriptor.region_id)
        if mask is None or not bool(np.any(mask)):
            continue
        centerline = np.asarray(descriptor.centerline, dtype=np.float32)
        thickness_samples = [float(item["value"]) for item in descriptor.thickness_function.get("samples", [])]
        for y, x in np.argwhere(mask):
            y_i = int(y)
            x_i = int(x)
            if seam[y_i, x_i]:
                continue
            distance, s, thickness = _field_sample(centerline, thickness_samples, float(x_i), float(y_i))
            current = refined[y_i, x_i, :]
            occupied = np.where(current)[0]
            if occupied.size:
                centre_z = float(np.mean(z_axis[occupied]))
                half = max(dz * 0.55, float(z_axis[int(occupied.max())] - z_axis[int(occupied.min())]) * 0.5 + dz * 0.5)
            else:
                centre_z = float(z_back[y_i, x_i] + z_front[y_i, x_i]) * 0.5
                half = max(dz * 0.55, float(z_front[y_i, x_i] - z_back[y_i, x_i]) * 0.28)
            radial = distance / max(thickness, 0.55)
            field_weight = max(0.42, min(1.18, 1.12 - 0.38 * (radial ** 1.35)))
            thickness_weight = _thickness_profile_weight(descriptor.thickness_function.get("type", "constant"), s)
            anisotropy_weight = 0.82 + 0.22 * float(descriptor.anisotropy.get("depth", 1.0))
            half = max(dz * 0.55, half * field_weight * thickness_weight * anisotropy_weight)
            centre_z += descriptor.depth_bias * (float(z_axis.max()) - float(z_axis.min())) * 0.09
            inside = np.abs(z_axis - centre_z) <= half
            if not bool(np.any(inside)):
                inside[int(np.argmin(np.abs(z_axis - centre_z)))] = True
            # RFDs add field-defined continuity without cutting away the validated body core.
            inside = inside | current
            refined[y_i, x_i, :] = inside
            label_id = SEMANTIC_LABEL_IDS.get(str(labels[y_i, x_i]), SEMANTIC_LABEL_IDS["unknown"])
            refined_semantic[y_i, x_i, :] = 0
            refined_semantic[y_i, x_i, inside] = label_id
    refined[~alpha_mask, :] = False
    refined[seam, :] = False
    refined[seam, center_index] = True
    for y, x in np.argwhere(seam):
        label_id = SEMANTIC_LABEL_IDS.get(str(labels[int(y), int(x)]), SEMANTIC_LABEL_IDS["unknown"])
        refined_semantic[int(y), int(x), :] = 0
        refined_semantic[int(y), int(x), center_index] = label_id
    preserved = bool(np.all(refined[seam, :].sum(axis=1) == 1)) if bool(np.any(seam)) else True
    return refined, refined_semantic, 1.0 if preserved else 0.0


def write_rfd_debug(
    output_dir: Path,
    descriptors: list[RegionFieldDescriptor],
    labels: np.ndarray,
    alpha_mask: np.ndarray,
    field_map: np.ndarray,
    anisotropy_map: np.ndarray,
    curvature_map: np.ndarray,
    report: dict[str, Any],
    emit_debug: bool,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "centerlines": output_dir / "centerlines.png",
        "centerline_splines": output_dir / "centerline_splines.json",
        "local_frames": output_dir / "local_frames.json",
        "thickness_functions": output_dir / "thickness_functions.json",
        "field_heatmaps": output_dir / "field_heatmaps.png",
        "anisotropy_debug": output_dir / "anisotropy_debug.png",
        "curvature_debug": output_dir / "curvature_debug.png",
        "attachment_anchor_debug": output_dir / "attachment_anchor_debug.png",
        "primitive_candidate_overlay": output_dir / "primitive_candidate_overlay.png",
        "rfd_report": output_dir / "rfd_report.json",
    }
    _write_centerlines(labels, alpha_mask, descriptors, paths["centerlines"])
    paths["centerline_splines"].write_text(
        json.dumps({"regions": [_centerline_json(item) for item in descriptors]}, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["local_frames"].write_text(
        json.dumps({"regions": [{"region_id": item.region_id, "frame": item.local_frame_basis, "tangents": item.tangent_vectors} for item in descriptors]}, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["thickness_functions"].write_text(
        json.dumps({"regions": [{"region_id": item.region_id, "semantic_class": item.semantic_class, "thickness_function": item.thickness_function} for item in descriptors]}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_heatmap(field_map, paths["field_heatmaps"], (70, 225, 255))
    _write_heatmap(anisotropy_map, paths["anisotropy_debug"], (255, 165, 80))
    _write_heatmap(curvature_map, paths["curvature_debug"], (255, 90, 210))
    _write_anchors(alpha_mask, descriptors, paths["attachment_anchor_debug"])
    _write_primitives(alpha_mask, descriptors, paths["primitive_candidate_overlay"])
    paths["rfd_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if emit_debug:
        paths["region_descriptors"] = output_dir / "region_descriptors.json"
        paths["region_descriptors"].write_text(
            json.dumps({"regions": [_descriptor_json(item) for item in descriptors]}, indent=2) + "\n",
            encoding="utf-8",
        )
    return paths


def descriptor_alignment(descriptors: list[RegionFieldDescriptor], semantic_a: str, semantic_b: str) -> float:
    candidates_a = [item for item in descriptors if item.semantic_class == _canonical_label(semantic_a)]
    candidates_b = [item for item in descriptors if item.semantic_class == _canonical_label(semantic_b)]
    values: list[float] = []
    for left in candidates_a:
        for link in left.adjacency_links:
            if str(link.get("semantic_class")) != _canonical_label(semantic_b):
                continue
            values.append(float(link.get("field_alignment", 0.0)))
        for right in candidates_b:
            values.append(_frame_alignment(left.local_frame_basis, right.local_frame_basis))
    return float(sum(values) / len(values)) if values else 0.0


def _semantic_components(labels: np.ndarray, alpha_mask: np.ndarray) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    visited = np.zeros(alpha_mask.shape, dtype=bool)
    height, width = alpha_mask.shape
    for y, x in np.argwhere(alpha_mask):
        y_i = int(y)
        x_i = int(x)
        if visited[y_i, x_i]:
            continue
        semantic = str(labels[y_i, x_i])
        mask = np.zeros(alpha_mask.shape, dtype=bool)
        queue = deque([(x_i, y_i)])
        visited[y_i, x_i] = True
        while queue:
            cx, cy = queue.popleft()
            mask[cy, cx] = True
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] and alpha_mask[ny, nx] and str(labels[ny, nx]) == semantic:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        components.append({"semantic_class": semantic, "mask": mask})
    return components


def _extract_centerline(mask: np.ndarray, edt: np.ndarray, semantic: str) -> list[list[float]]:
    points_yx = np.argwhere(mask)
    if points_yx.size == 0:
        return [[0.0, 0.0]]
    points = np.stack([points_yx[:, 1], points_yx[:, 0]], axis=1).astype(np.float32)
    centre = np.mean(points, axis=0)
    if len(points) == 1:
        return [[float(points[0, 0]), float(points[0, 1])]]
    covariance = np.cov((points - centre).T)
    eigvals, eigvecs = np.linalg.eigh(covariance)
    axis = eigvecs[:, int(np.argmax(eigvals))]
    if semantic == "torso":
        axis = np.array([0.0, 1.0], dtype=np.float32)
    elif semantic == "hair/hat" and abs(float(axis[0])) < 0.35:
        axis = np.array([-0.65, 0.35], dtype=np.float32)
    projections = (points - centre) @ axis
    bin_count = max(2, min(9, int(round(math.sqrt(len(points)) * 0.62))))
    edges = np.linspace(float(projections.min()), float(projections.max()), bin_count + 1)
    samples: list[list[float]] = []
    for index in range(bin_count):
        in_bin = (projections >= edges[index]) & (projections <= edges[index + 1] if index == bin_count - 1 else projections < edges[index + 1])
        candidates = points[in_bin]
        if candidates.size == 0:
            continue
        candidate_scores = [float(edt[int(point[1]), int(point[0])]) for point in candidates]
        selected = candidates[int(np.argmax(candidate_scores))]
        sample = [float(selected[0]), float(selected[1])]
        if not samples or _distance(samples[-1], sample) >= 0.65:
            samples.append(sample)
    if not samples:
        samples = [[float(centre[0]), float(centre[1])]]
    return _simplify_polyline(samples)


def _simplify_polyline(points: list[list[float]]) -> list[list[float]]:
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    for index in range(1, len(points) - 1):
        a = np.asarray(simplified[-1], dtype=np.float32)
        b = np.asarray(points[index], dtype=np.float32)
        c = np.asarray(points[index + 1], dtype=np.float32)
        ab = b - a
        bc = c - b
        denom = max(float(np.linalg.norm(ab) * np.linalg.norm(bc)), 1e-6)
        alignment = abs(float(np.dot(ab, bc)) / denom)
        if alignment < 0.995 or float(np.linalg.norm(ab)) > 2.0:
            simplified.append(points[index])
    simplified.append(points[-1])
    return simplified


def _thickness_samples(centerline: list[list[float]], edt: np.ndarray, semantic: str) -> list[float]:
    if not centerline:
        return [1.0]
    raw = [max(0.75, float(edt[int(round(point[1])), int(round(point[0]))])) for point in centerline]
    length = max(len(raw) - 1, 1)
    adjusted: list[float] = []
    for index, value in enumerate(raw):
        s = index / length
        adjusted.append(float(value * _thickness_profile_weight(_thickness_kind(semantic), s)))
    return adjusted


def _thickness_kind(semantic: str) -> str:
    if semantic in {"left_arm", "right_arm", "left_leg", "right_leg"}:
        return "asymmetric_taper"
    if semantic == "hair/hat":
        return "taper"
    if semantic == "torso":
        return "bell"
    if semantic == "equipment/shield/sword":
        return "segmented"
    return "constant"


def _thickness_profile_weight(kind: str, s: float) -> float:
    s = max(0.0, min(1.0, float(s)))
    if kind == "taper":
        return 1.14 - 0.72 * s
    if kind == "bell":
        return 0.72 + 0.38 * math.sin(math.pi * s)
    if kind == "asymmetric_taper":
        return 1.08 - 0.38 * s + 0.08 * math.sin(math.pi * s)
    if kind == "segmented":
        return 0.78 + 0.22 * (1.0 - abs(round(s * 3.0) / 3.0 - s) * 3.0)
    return 1.0


def _tangent_vectors(points: list[list[float]]) -> list[list[float]]:
    if len(points) <= 1:
        return [[0.0, 1.0, 0.0]]
    tangents: list[list[float]] = []
    for index, point in enumerate(points):
        prev_point = np.asarray(points[max(0, index - 1)], dtype=np.float32)
        next_point = np.asarray(points[min(len(points) - 1, index + 1)], dtype=np.float32)
        vector = next_point - prev_point
        norm = max(float(np.linalg.norm(vector)), 1e-6)
        tangents.append([float(vector[0] / norm), float(vector[1] / norm), 0.0])
    return tangents


def _local_frame(tangents: list[list[float]]) -> dict[str, list[float]]:
    tangent = np.mean(np.asarray(tangents, dtype=np.float32), axis=0)
    tangent_norm = max(float(np.linalg.norm(tangent[:2])), 1e-6)
    tangent_xy = np.array([float(tangent[0] / tangent_norm), float(tangent[1] / tangent_norm), 0.0], dtype=np.float32)
    normal = np.array([-tangent_xy[1], tangent_xy[0], 0.0], dtype=np.float32)
    return {
        "tangent": [float(value) for value in tangent_xy],
        "normal": [float(value) for value in normal],
        "forward": [0.0, 0.0, 1.0],
        "backward": [0.0, 0.0, -1.0],
        "up": [0.0, -1.0, 0.0],
        "down": [0.0, 1.0, 0.0],
    }


def _depth_bias(mask: np.ndarray, z_front: np.ndarray, z_back: np.ndarray) -> float:
    if not bool(np.any(mask)):
        return 0.0
    front = float(np.mean(z_front[mask]))
    back = float(np.mean(np.abs(z_back[mask])))
    return max(-1.0, min(1.0, (front - back) / max(front + back, 1e-6)))


def _anisotropy(mask: np.ndarray, semantic: str) -> dict[str, float]:
    ys, xs = np.where(mask)
    width = max(1.0, float(xs.max() - xs.min() + 1)) if xs.size else 1.0
    height = max(1.0, float(ys.max() - ys.min() + 1)) if ys.size else 1.0
    chain = max(width, height) / max(min(width, height), 1.0)
    depth = 1.0
    if semantic in {"left_arm", "right_arm", "left_leg", "right_leg", "hair/hat"}:
        depth = min(1.45, 0.88 + chain * 0.12)
    if semantic in {"face", "outline"}:
        depth = 0.72
    return {
        "chain": max(0.0, min(2.0, chain / 2.0)),
        "lateral": max(0.45, min(1.65, width / height)),
        "vertical": max(0.45, min(1.65, height / width)),
        "depth": depth,
    }


def _curvature_profile(tangents: list[list[float]]) -> list[float]:
    if len(tangents) <= 1:
        return [0.0]
    values = [0.0]
    for left, right in zip(tangents, tangents[1:]):
        a = np.asarray(left[:2], dtype=np.float32)
        b = np.asarray(right[:2], dtype=np.float32)
        angle = 1.0 - max(-1.0, min(1.0, float(np.dot(a, b))))
        values.append(max(0.0, min(1.0, angle * 0.5)))
    return values


def _directional_profile(semantic: str) -> str:
    if semantic == "hair/hat":
        return "HAT_POINTED_BACK"
    if semantic == "face":
        return "NOSE_FORWARD"
    if semantic == "equipment/shield/sword":
        return "RIGID_ATTACHMENT"
    if semantic in {"left_arm", "right_arm", "left_leg", "right_leg"}:
        return "LIMB_CHAIN"
    return "NEUTRAL"


def _attach_adjacency(raw: list[dict[str, Any]], masks: dict[int, np.ndarray], region_grid: np.ndarray) -> None:
    contacts: dict[tuple[int, int], list[list[int]]] = {}
    height, width = region_grid.shape
    for y in range(height):
        for x in range(width):
            region_id = int(region_grid[y, x])
            if region_id < 0:
                continue
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx >= width or ny >= height:
                    continue
                other = int(region_grid[ny, nx])
                if other < 0 or other == region_id:
                    continue
                key = tuple(sorted((region_id, other)))
                contacts.setdefault(key, []).extend([[x, y], [nx, ny]])
    by_id = {int(item["region_id"]): item for item in raw}
    for (left_id, right_id), points in contacts.items():
        anchor = np.mean(np.asarray(points, dtype=np.float32), axis=0)
        left = by_id[left_id]
        right = by_id[right_id]
        alignment = _frame_alignment(left["local_frame_basis"], right["local_frame_basis"])
        for item, other in ((left, right), (right, left)):
            item["adjacency_links"].append(
                {
                    "region_id": int(other["region_id"]),
                    "semantic_class": str(other["semantic_class"]),
                    "contact_length": int(len(points) // 2),
                    "field_alignment": alignment,
                }
            )
            item["attachment_anchors"].append(
                {
                    "region_id": int(other["region_id"]),
                    "semantic_class": str(other["semantic_class"]),
                    "point": [float(anchor[0]), float(anchor[1]), 0.0],
                    "contact_length": int(len(points) // 2),
                }
            )


def _field_sample(centerline: np.ndarray, thickness_samples: list[float], x: float, y: float) -> tuple[float, float, float]:
    if centerline.size == 0:
        return 0.0, 0.0, 1.0
    point = np.array([x, y], dtype=np.float32)
    if len(centerline) == 1:
        return float(np.linalg.norm(point - centerline[0])), 0.0, thickness_samples[0] if thickness_samples else 1.0
    distances = np.linalg.norm(centerline - point, axis=1)
    index = int(np.argmin(distances))
    s = index / max(len(centerline) - 1, 1)
    thickness = thickness_samples[min(index, len(thickness_samples) - 1)] if thickness_samples else 1.0
    return float(distances[index]), float(s), float(thickness)


def _write_field_maps(
    mask: np.ndarray,
    centerline: list[list[float]],
    thickness: list[float],
    anisotropy: dict[str, float],
    curvature: list[float],
    field_map: np.ndarray,
    anisotropy_map: np.ndarray,
    curvature_map: np.ndarray,
) -> None:
    center = np.asarray(centerline, dtype=np.float32)
    for y, x in np.argwhere(mask):
        distance, _, local_thickness = _field_sample(center, thickness, float(x), float(y))
        field_map[int(y), int(x)] = max(0.0, 1.0 - distance / max(local_thickness, 0.55))
        anisotropy_map[int(y), int(x)] = float(anisotropy.get("depth", 1.0))
    if centerline:
        for index, point in enumerate(centerline):
            x = int(round(point[0]))
            y = int(round(point[1]))
            if 0 <= y < curvature_map.shape[0] and 0 <= x < curvature_map.shape[1]:
                curvature_map[y, x] = float(curvature[min(index, len(curvature) - 1)]) if curvature else 0.0


def _rfd_report(
    descriptors: list[RegionFieldDescriptor],
    raw: list[dict[str, Any]],
    occupancy: np.ndarray,
    alpha_mask: np.ndarray,
    field_map: np.ndarray,
    silhouette_score: float,
) -> dict[str, Any]:
    centerline_scores = [
        min(1.0, len(item.centerline) / max(2.0, math.sqrt(max(float(raw[index].get("pixel_count", 1)), 1.0)) * 0.65))
        for index, item in enumerate(descriptors)
    ]
    thickness_values = [
        float(sample["value"])
        for descriptor in descriptors
        for sample in descriptor.thickness_function.get("samples", [])
    ]
    anisotropy_values = [float(item.anisotropy.get("depth", 1.0)) for item in descriptors]
    directional = [item for item in descriptors if item.directional_profile != "NEUTRAL"]
    field_continuity = _field_continuity_score(occupancy, alpha_mask)
    return {
        "schema": "spritespatial_rfd_report_v1",
        "rfd_enabled": True,
        "rfd_region_count": len(descriptors),
        "centerline_quality_score": float(sum(centerline_scores) / len(centerline_scores)) if centerline_scores else 0.0,
        "field_continuity_score": field_continuity,
        "thickness_profile_variance": float(np.var(np.asarray(thickness_values, dtype=np.float32))) if thickness_values else 0.0,
        "anisotropy_score": float(sum(anisotropy_values) / len(anisotropy_values)) if anisotropy_values else 0.0,
        "directional_field_coherence": min(1.0, 0.45 + 0.40 * float(np.mean(field_map[alpha_mask])) + 0.15 * (len(directional) / max(len(descriptors), 1))) if bool(np.any(alpha_mask)) else 0.0,
        "surface_flow_rfd_alignment": 0.0,
        "silhouette_constraint_preservation": silhouette_score,
        "semantic_regions": [
            {
                "region_id": item.region_id,
                "semantic_class": item.semantic_class,
                "centerline_point_count": len(item.centerline),
                "thickness_type": item.thickness_function.get("type", ""),
                "primitive_candidates": item.primitive_candidates,
            }
            for item in descriptors
        ],
    }


def _field_continuity_score(occupancy: np.ndarray, alpha_mask: np.ndarray) -> float:
    thickness = occupancy.sum(axis=2).astype(np.float32)
    jumps: list[float] = []
    height, width = alpha_mask.shape
    for y, x in np.argwhere(alpha_mask):
        for nx, ny in ((int(x) + 1, int(y)), (int(x), int(y) + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                jumps.append(abs(float(thickness[int(y), int(x)] - thickness[ny, nx])) / max(float(occupancy.shape[2]), 1.0))
    return max(0.0, min(1.0, 1.0 - (float(sum(jumps) / len(jumps)) if jumps else 0.0)))


def _label_grid(alpha_mask: np.ndarray, label_by_pixel: dict[Pixel, str]) -> np.ndarray:
    labels = np.full(alpha_mask.shape, "transparent", dtype=object)
    for y, x in np.argwhere(alpha_mask):
        labels[int(y), int(x)] = _canonical_label(str(label_by_pixel.get((int(x), int(y)), "unknown")))
    return labels


def _canonical_label(label: str) -> str:
    value = str(label or "unknown")
    return LABEL_ALIASES.get(value, value if value in SEMANTIC_LABEL_IDS else "unknown")


def _silhouette_seam(alpha_mask: np.ndarray) -> np.ndarray:
    seam = np.zeros_like(alpha_mask, dtype=bool)
    height, width = alpha_mask.shape
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height or not alpha_mask[ny, nx]:
                    seam[y, x] = True
                    break
    return seam


def _edt(mask: np.ndarray) -> np.ndarray:
    values = np.zeros(mask.shape, dtype=np.float32)
    inside = np.argwhere(mask)
    outside = np.argwhere(~mask)
    if inside.size == 0:
        return values
    if outside.size == 0:
        outside = np.array([[0, 0]], dtype=np.int32)
    for y, x in inside:
        delta = outside - np.array([y, x])
        values[int(y), int(x)] = float(np.sqrt((delta * delta).sum(axis=1).min()))
    return values


def _frame_alignment(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = np.asarray(left.get("tangent", [0.0, 1.0, 0.0])[:2], dtype=np.float32)
    b = np.asarray(right.get("tangent", [0.0, 1.0, 0.0])[:2], dtype=np.float32)
    norm = max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-6)
    return abs(max(-1.0, min(1.0, float(np.dot(a, b)) / norm)))


def _distance(left: list[float], right: list[float]) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=np.float32) - np.asarray(right, dtype=np.float32)))


def _descriptor_json(descriptor: RegionFieldDescriptor) -> dict[str, Any]:
    return asdict(descriptor)


def _centerline_json(descriptor: RegionFieldDescriptor) -> dict[str, Any]:
    return {
        "region_id": descriptor.region_id,
        "semantic_class": descriptor.semantic_class,
        "points": descriptor.centerline,
        "tangents": descriptor.tangent_vectors,
        "curvature_profile": descriptor.curvature_profile,
    }


def _write_centerlines(labels: np.ndarray, alpha_mask: np.ndarray, descriptors: list[RegionFieldDescriptor], path: Path) -> None:
    image = _label_canvas(labels, alpha_mask)
    draw = ImageDraw.Draw(image)
    for descriptor in descriptors:
        points = [(int(round(point[0])), int(round(point[1]))) for point in descriptor.centerline]
        if len(points) > 1:
            draw.line(points, fill=(255, 235, 90, 255), width=1)
        for point in points:
            draw.ellipse((point[0] - 1, point[1] - 1, point[0] + 1, point[1] + 1), fill=(90, 230, 255, 255))
    image.save(path, format="PNG")


def _write_anchors(alpha_mask: np.ndarray, descriptors: list[RegionFieldDescriptor], path: Path) -> None:
    image = Image.new("RGBA", (alpha_mask.shape[1], alpha_mask.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, x in np.argwhere(alpha_mask):
        draw.point((int(x), int(y)), fill=(50, 50, 50, 120))
    for descriptor in descriptors:
        for anchor in descriptor.attachment_anchors:
            x = int(round(float(anchor["point"][0])))
            y = int(round(float(anchor["point"][1])))
            draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(255, 100, 180, 255))
    image.save(path, format="PNG")


def _write_primitives(alpha_mask: np.ndarray, descriptors: list[RegionFieldDescriptor], path: Path) -> None:
    image = Image.new("RGBA", (alpha_mask.shape[1], alpha_mask.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    palette = [(90, 190, 255, 255), (255, 180, 70, 255), (140, 230, 125, 255), (205, 110, 255, 255)]
    for descriptor in descriptors:
        if not descriptor.centerline:
            continue
        first = descriptor.centerline[len(descriptor.centerline) // 2]
        colour = palette[descriptor.region_id % len(palette)]
        draw.text((int(round(first[0])), int(round(first[1]))), descriptor.primitive_candidates[0][:1].upper(), fill=colour)
    image.save(path, format="PNG")


def _write_heatmap(values: np.ndarray, path: Path, colour: tuple[int, int, int]) -> None:
    image = Image.new("RGBA", (values.shape[1], values.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    max_value = max(float(np.max(values)), 1e-6)
    for y, x in np.argwhere(values > 0):
        t = max(0.0, min(1.0, float(values[int(y), int(x)] / max_value)))
        pixels[int(x), int(y)] = (int(colour[0] * t), int(colour[1] * t), int(colour[2] * t), 255)
    image.save(path, format="PNG")


def _label_canvas(labels: np.ndarray, alpha_mask: np.ndarray) -> Image.Image:
    palette = {
        "outline": (15, 15, 15, 180),
        "head": (235, 87, 66, 180),
        "face": (255, 189, 107, 180),
        "hair/hat": (89, 46, 184, 180),
        "torso": (46, 138, 230, 180),
        "left_arm": (56, 184, 117, 180),
        "right_arm": (66, 163, 107, 180),
        "left_leg": (189, 133, 51, 180),
        "right_leg": (133, 179, 51, 180),
        "boots/feet": (107, 61, 31, 180),
        "equipment/shield/sword": (235, 209, 51, 180),
        "unknown": (160, 160, 160, 180),
    }
    image = Image.new("RGBA", (labels.shape[1], labels.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(alpha_mask):
        pixels[int(x), int(y)] = palette.get(str(labels[int(y), int(x)]), palette["unknown"])
    return image
