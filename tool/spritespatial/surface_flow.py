from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.rfd import RegionFieldDescriptor, descriptor_alignment

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


def _canonical_label(label: str) -> str:
    value = str(label or "unknown")
    return LABEL_ALIASES.get(value, value if value in SEMANTIC_LABEL_IDS else "unknown")


def _key(label_a: str, label_b: str) -> tuple[str, str]:
    a = _canonical_label(label_a)
    b = _canonical_label(label_b)
    return tuple(sorted((a, b)))


@dataclass(frozen=True)
class SurfaceTransitionRule:
    continuity_type: str
    transition_mode: str
    transition_strength: float
    blending_radius: int
    directional_transition_bias: str
    overlap_allowed: bool


DEFAULT_RULES: dict[tuple[str, str], SurfaceTransitionRule] = {
    _key("head", "hair/hat"): SurfaceTransitionRule(
        continuity_type="seated_surface",
        transition_mode="SEATED_SURFACE",
        transition_strength=0.74,
        blending_radius=2,
        directional_transition_bias="backward_down",
        overlap_allowed=False,
    ),
    _key("head", "face"): SurfaceTransitionRule(
        continuity_type="facial_surface",
        transition_mode="SOFT_BLEND",
        transition_strength=0.60,
        blending_radius=1,
        directional_transition_bias="forward",
        overlap_allowed=False,
    ),
    _key("torso", "left_arm"): SurfaceTransitionRule(
        continuity_type="articulated_joint",
        transition_mode="ARTICULATED_JOINT",
        transition_strength=0.66,
        blending_radius=2,
        directional_transition_bias="lateral",
        overlap_allowed=True,
    ),
    _key("torso", "right_arm"): SurfaceTransitionRule(
        continuity_type="articulated_joint",
        transition_mode="ARTICULATED_JOINT",
        transition_strength=0.66,
        blending_radius=2,
        directional_transition_bias="lateral",
        overlap_allowed=True,
    ),
    _key("torso", "left_leg"): SurfaceTransitionRule(
        continuity_type="anatomical_root",
        transition_mode="TAPERED_BRIDGE",
        transition_strength=0.70,
        blending_radius=2,
        directional_transition_bias="downward",
        overlap_allowed=True,
    ),
    _key("torso", "right_leg"): SurfaceTransitionRule(
        continuity_type="anatomical_root",
        transition_mode="TAPERED_BRIDGE",
        transition_strength=0.70,
        blending_radius=2,
        directional_transition_bias="downward",
        overlap_allowed=True,
    ),
    _key("left_leg", "boots/feet"): SurfaceTransitionRule(
        continuity_type="boot_socket",
        transition_mode="TAPERED_BRIDGE",
        transition_strength=0.55,
        blending_radius=1,
        directional_transition_bias="downward",
        overlap_allowed=True,
    ),
    _key("right_leg", "boots/feet"): SurfaceTransitionRule(
        continuity_type="boot_socket",
        transition_mode="TAPERED_BRIDGE",
        transition_strength=0.55,
        blending_radius=1,
        directional_transition_bias="downward",
        overlap_allowed=True,
    ),
    _key("outline", "*"): SurfaceTransitionRule(
        continuity_type="outline_shell",
        transition_mode="SHELL_WRAP",
        transition_strength=0.20,
        blending_radius=1,
        directional_transition_bias="rim",
        overlap_allowed=False,
    ),
    _key("equipment/shield/sword", "*"): SurfaceTransitionRule(
        continuity_type="rigid_attachment",
        transition_mode="SHELL_WRAP",
        transition_strength=0.28,
        blending_radius=1,
        directional_transition_bias="rigid",
        overlap_allowed=False,
    ),
}


def apply_surface_flow(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    z_axis: np.ndarray,
    output_dir: Path | None = None,
    strength: float = 0.45,
    iterations: int = 2,
    emit_debug: bool = False,
    rfd_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strength = max(0.0, min(1.0, float(strength)))
    iterations = max(1, int(iterations))
    labels = _label_grid(alpha_mask, label_by_pixel)
    seam = _silhouette_seam(alpha_mask)
    graph = build_semantic_surface_graph(labels, alpha_mask, strength)
    rfd_descriptors = _rfd_descriptors(rfd_result)
    rfd_alignment_by_pair = _annotate_rfd_alignment(graph["transitions"], rfd_descriptors)
    contacts: list[dict[str, Any]] = graph["contacts"]
    before_continuity = _continuity_score(occupancy, contacts)

    refined = occupancy.copy()
    refined_semantic = semantic_volume.copy()
    transition_zone = np.zeros(alpha_mask.shape, dtype=bool)
    mode_grid = np.full(alpha_mask.shape, "", dtype=object)
    flow_x = np.zeros(alpha_mask.shape, dtype=np.float32)
    flow_y = np.zeros(alpha_mask.shape, dtype=np.float32)
    center_index = int(np.argmin(np.abs(z_axis))) if z_axis.size else occupancy.shape[2] // 2
    added_voxels = 0

    for _ in range(iterations):
        next_refined = refined.copy()
        for contact in contacts:
            y = int(contact["a"][1])
            x = int(contact["a"][0])
            ny = int(contact["b"][1])
            nx = int(contact["b"][0])
            label_a = str(contact["label_a"])
            label_b = str(contact["label_b"])
            rule = _rule_for_pair(label_a, label_b)
            transition_zone[y, x] = True
            transition_zone[ny, nx] = True
            mode_grid[y, x] = rule.transition_mode
            mode_grid[ny, nx] = rule.transition_mode
            flow_x[y, x] += float(nx - x) * rule.transition_strength
            flow_y[y, x] += float(ny - y) * rule.transition_strength
            flow_x[ny, nx] += float(x - nx) * rule.transition_strength
            flow_y[ny, nx] += float(y - ny) * rule.transition_strength
            if _preserve_pair(label_a, label_b, seam[y, x], seam[ny, nx]):
                continue
            alignment = rfd_alignment_by_pair.get(_key(label_a, label_b), 0.0)
            local_strength = strength * rule.transition_strength * (0.88 + 0.24 * alignment)
            added_voxels += _blend_column_pair(
                next_refined,
                refined_semantic,
                labels,
                y,
                x,
                ny,
                nx,
                rule,
                local_strength,
            )
        refined = next_refined
        refined[~alpha_mask, :] = False
        refined[seam, :] = False
        refined[seam, center_index] = True

    for y, x in np.argwhere(alpha_mask):
        label = str(labels[int(y), int(x)])
        label_id = SEMANTIC_LABEL_IDS.get(label, SEMANTIC_LABEL_IDS["unknown"])
        fill_mask = refined[int(y), int(x), :] & (refined_semantic[int(y), int(x), :] == 0)
        refined_semantic[int(y), int(x), fill_mask] = label_id
        refined_semantic[int(y), int(x), ~refined[int(y), int(x), :]] = 0

    curvature = _curvature_field(refined, alpha_mask)
    after_continuity = _continuity_score(refined, contacts)
    side_projection = refined.any(axis=1)
    oblique_projection = _oblique_projection(refined)
    fragmentation = _fragmentation_score(side_projection)
    staircase = _staircase_score(refined, alpha_mask)
    oblique_readability = max(0.0, min(1.0, 0.58 * _entropy(oblique_projection.sum(axis=0)) + 0.42 * (1.0 - fragmentation)))
    semantic_seam_score = after_continuity
    anatomical_flow_score = max(
        0.0,
        min(
            1.0,
            0.38 * after_continuity
            + 0.24 * semantic_seam_score
            + 0.22 * oblique_readability
            + 0.16 * (1.0 - staircase),
        ),
    )
    report = {
        "schema": "spritespatial_surface_flow_v1",
        "surface_flow_enabled": True,
        "surface_flow_strength": strength,
        "surface_flow_iterations": iterations,
        "semantic_transition_count": len(graph["transitions"]),
        "transition_contact_count": len(contacts),
        "surface_continuity_score": after_continuity,
        "surface_continuity_before": before_continuity,
        "surface_continuity_delta": after_continuity - before_continuity,
        "semantic_seam_score": semantic_seam_score,
        "oblique_surface_readability": oblique_readability,
        "surface_fragmentation_score": fragmentation,
        "staircase_artifact_score": staircase,
        "anatomical_flow_score": anatomical_flow_score,
        "added_surface_flow_voxels": int(added_voxels),
        "surface_flow_rfd_alignment": float(sum(rfd_alignment_by_pair.values()) / len(rfd_alignment_by_pair)) if rfd_alignment_by_pair else 0.0,
        "front_silhouette_preserved": True,
        "semantic_ownership_preserved": True,
        "directional_morphology_preserved": True,
    }
    graph_report = {
        "schema": "spritespatial_semantic_surface_graph_v1",
        "transitions": graph["transitions"],
        "contact_count": len(contacts),
    }
    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = write_surface_flow_debug(
            output_dir,
            refined,
            labels,
            transition_zone,
            mode_grid,
            flow_x,
            flow_y,
            curvature,
            graph_report,
            report,
            emit_debug,
        )
    return {
        "occupancy": refined,
        "semantic_volume": refined_semantic,
        "transition_volume": _transition_volume(transition_zone, refined),
        "transition_zone": transition_zone,
        "report": report,
        "graph": graph_report,
        "paths": paths,
    }


def smooth_surface_flow_sdf(
    sdf: np.ndarray,
    occupancy: np.ndarray,
    transition_volume: np.ndarray,
    strength: float,
    iterations: int,
) -> np.ndarray:
    if not np.any(transition_volume):
        return sdf
    result = sdf.astype(np.float32, copy=True)
    alpha = max(0.02, min(0.35, float(strength) * 0.24))
    dims = result.shape
    for _ in range(max(1, int(iterations))):
        previous = result.copy()
        for y, x, z in np.argwhere(transition_volume):
            y_i, x_i, z_i = int(y), int(x), int(z)
            sign = previous[y_i, x_i, z_i] <= 0.0
            samples = []
            for dy, dx, dz in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)):
                ny, nx, nz = y_i + dy, x_i + dx, z_i + dz
                if 0 <= ny < dims[0] and 0 <= nx < dims[1] and 0 <= nz < dims[2]:
                    if (previous[ny, nx, nz] <= 0.0) == sign:
                        samples.append(float(previous[ny, nx, nz]))
            if not samples:
                continue
            blended = (1.0 - alpha) * float(previous[y_i, x_i, z_i]) + alpha * float(sum(samples) / len(samples))
            if occupancy[y_i, x_i, z_i]:
                result[y_i, x_i, z_i] = min(-1e-4, blended)
            else:
                result[y_i, x_i, z_i] = max(1e-4, blended)
    return result.astype(np.float32)


def _rfd_descriptors(rfd_result: dict[str, Any] | None) -> list[RegionFieldDescriptor]:
    if not rfd_result:
        return []
    return [item for item in rfd_result.get("descriptors", []) if isinstance(item, RegionFieldDescriptor)]


def _annotate_rfd_alignment(
    transitions: list[dict[str, Any]],
    descriptors: list[RegionFieldDescriptor],
) -> dict[tuple[str, str], float]:
    if not descriptors:
        return {}
    result: dict[tuple[str, str], float] = {}
    for transition in transitions:
        semantic_a = str(transition.get("semantic_a", "unknown"))
        semantic_b = str(transition.get("semantic_b", "unknown"))
        alignment = descriptor_alignment(descriptors, semantic_a, semantic_b)
        transition["rfd_alignment"] = alignment
        transition["centerline_guided"] = alignment > 0.0
        result[_key(semantic_a, semantic_b)] = alignment
    return result


def build_semantic_surface_graph(labels: np.ndarray, alpha_mask: np.ndarray, strength: float) -> dict[str, Any]:
    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    contacts: list[dict[str, Any]] = []
    height, width = alpha_mask.shape
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            label_a = str(labels[y, x])
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx >= width or ny >= height or not alpha_mask[ny, nx]:
                    continue
                label_b = str(labels[ny, nx])
                if label_a == label_b:
                    continue
                key = _key(label_a, label_b)
                rule = _rule_for_pair(label_a, label_b)
                entry = transitions.setdefault(
                    key,
                    {
                        "semantic_a": key[0],
                        "semantic_b": key[1],
                        "contact_length": 0,
                        "transition_strength": min(1.0, strength * rule.transition_strength),
                        "anatomical_continuity_class": rule.continuity_type,
                        "continuity_type": rule.continuity_type,
                        "transition_mode": rule.transition_mode,
                        "allowed_blending_radius": rule.blending_radius,
                        "directional_transition_bias": rule.directional_transition_bias,
                        "overlap_allowed": rule.overlap_allowed,
                    },
                )
                entry["contact_length"] = int(entry["contact_length"]) + 1
                contacts.append(
                    {
                        "a": [int(x), int(y)],
                        "b": [int(nx), int(ny)],
                        "label_a": label_a,
                        "label_b": label_b,
                        "transition_mode": rule.transition_mode,
                    }
                )
    return {"transitions": list(transitions.values()), "contacts": contacts}


def write_surface_flow_debug(
    output_dir: Path,
    occupancy: np.ndarray,
    labels: np.ndarray,
    transition_zone: np.ndarray,
    mode_grid: np.ndarray,
    flow_x: np.ndarray,
    flow_y: np.ndarray,
    curvature: np.ndarray,
    graph_report: dict[str, Any],
    report: dict[str, Any],
    emit_debug: bool,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "semantic_surface_graph": output_dir / "semantic_surface_graph.json",
        "transition_zones": output_dir / "transition_zones.png",
        "flow_vectors": output_dir / "flow_vectors.png",
        "continuity_normals": output_dir / "continuity_normals.png",
        "curvature_heatmap": output_dir / "curvature_heatmap.png",
        "anatomical_transition_debug": output_dir / "anatomical_transition_debug.png",
        "hat_head_transition_debug": output_dir / "hat_head_transition_debug.png",
        "torso_arm_transition_debug": output_dir / "torso_arm_transition_debug.png",
        "surface_flow_report": output_dir / "surface_flow_report.json",
    }
    paths["semantic_surface_graph"].write_text(json.dumps(graph_report, indent=2) + "\n", encoding="utf-8")
    paths["surface_flow_report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_mask(transition_zone, paths["transition_zones"], (255, 210, 60, 255))
    _write_flow_vectors(transition_zone, flow_x, flow_y, paths["flow_vectors"])
    _write_normals(transition_zone, flow_x, flow_y, paths["continuity_normals"])
    _write_heatmap(curvature, paths["curvature_heatmap"])
    _write_mode_overlay(labels, transition_zone, mode_grid, paths["anatomical_transition_debug"])
    _write_pair_debug(labels, transition_zone, {"head", "hair/hat"}, paths["hat_head_transition_debug"])
    _write_pair_debug(labels, transition_zone, {"torso", "left_arm", "right_arm"}, paths["torso_arm_transition_debug"])
    if emit_debug:
        _write_projection(occupancy.any(axis=1).T, output_dir / "surface_flow_side_projection.png")
        paths["surface_flow_side_projection"] = output_dir / "surface_flow_side_projection.png"
    return paths


def _blend_column_pair(
    occupancy: np.ndarray,
    semantic_volume: np.ndarray,
    labels: np.ndarray,
    y: int,
    x: int,
    ny: int,
    nx: int,
    rule: SurfaceTransitionRule,
    strength: float,
) -> int:
    before = int(np.count_nonzero(occupancy[y, x, :])) + int(np.count_nonzero(occupancy[ny, nx, :]))
    new_a = _blend_column(occupancy[y, x, :], occupancy[ny, nx, :], rule, strength)
    new_b = _blend_column(occupancy[ny, nx, :], occupancy[y, x, :], rule, strength)
    occupancy[y, x, :] = new_a
    occupancy[ny, nx, :] = new_b
    for py, px in ((y, x), (ny, nx)):
        label_id = SEMANTIC_LABEL_IDS.get(str(labels[py, px]), SEMANTIC_LABEL_IDS["unknown"])
        fill = occupancy[py, px, :] & (semantic_volume[py, px, :] == 0)
        semantic_volume[py, px, fill] = label_id
        semantic_volume[py, px, ~occupancy[py, px, :]] = 0
    after = int(np.count_nonzero(occupancy[y, x, :])) + int(np.count_nonzero(occupancy[ny, nx, :]))
    return max(0, after - before)


def _blend_column(current: np.ndarray, other: np.ndarray, rule: SurfaceTransitionRule, strength: float) -> np.ndarray:
    if not bool(np.any(current)) or not bool(np.any(other)):
        return current.copy()
    result = current.copy()
    own = np.where(current)[0]
    neighbour = np.where(other)[0]
    own_min, own_max = int(own.min()), int(own.max())
    other_min, other_max = int(neighbour.min()), int(neighbour.max())
    mode_boost = {
        "SOFT_BLEND": 1,
        "SEATED_SURFACE": 2,
        "TAPERED_BRIDGE": 2,
        "ARTICULATED_JOINT": 1,
        "SHELL_WRAP": 0,
    }.get(rule.transition_mode, 1)
    if rule.transition_mode == "SHELL_WRAP":
        return result
    allowed = max(1, min(4, int(round(rule.blending_radius + mode_boost + strength * 2.0))))
    new_min = own_min
    new_max = own_max
    if other_min < own_min:
        new_min = max(other_min, own_min - allowed)
    if other_max > own_max:
        new_max = min(other_max, own_max + allowed)
    if own_max < other_min:
        new_max = min(other_min, own_max + allowed)
    elif other_max < own_min:
        new_min = max(other_max, own_min - allowed)
    result[new_min : new_max + 1] = True
    result = _fill_small_holes(result, allowed)
    return result


def _fill_small_holes(column: np.ndarray, max_gap: int) -> np.ndarray:
    result = column.copy()
    occupied = np.where(result)[0]
    if occupied.size < 2:
        return result
    start, end = int(occupied.min()), int(occupied.max())
    index = start
    while index <= end:
        if result[index]:
            index += 1
            continue
        gap_start = index
        while index <= end and not result[index]:
            index += 1
        gap_end = index - 1
        if gap_end - gap_start + 1 <= max_gap:
            result[gap_start : gap_end + 1] = True
    return result


def _preserve_pair(label_a: str, label_b: str, seam_a: bool, seam_b: bool) -> bool:
    if seam_a or seam_b:
        return True
    if label_a == "outline" or label_b == "outline":
        return True
    if label_a == "equipment/shield/sword" and label_b == "equipment/shield/sword":
        return True
    return False


def _rule_for_pair(label_a: str, label_b: str) -> SurfaceTransitionRule:
    key = _key(label_a, label_b)
    if key in DEFAULT_RULES:
        return DEFAULT_RULES[key]
    if _key("outline", "*") in {_key(label_a, "*"), _key(label_b, "*")} or "outline" in key:
        return DEFAULT_RULES[_key("outline", "*")]
    if "equipment/shield/sword" in key:
        return DEFAULT_RULES[_key("equipment/shield/sword", "*")]
    return SurfaceTransitionRule(
        continuity_type="semantic_neighbour",
        transition_mode="SOFT_BLEND",
        transition_strength=0.42,
        blending_radius=1,
        directional_transition_bias="local",
        overlap_allowed=False,
    )


def _continuity_score(occupancy: np.ndarray, contacts: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for contact in contacts:
        y = int(contact["a"][1])
        x = int(contact["a"][0])
        ny = int(contact["b"][1])
        nx = int(contact["b"][0])
        a = occupancy[y, x, :]
        b = occupancy[ny, nx, :]
        ca = int(np.count_nonzero(a))
        cb = int(np.count_nonzero(b))
        if ca == 0 or cb == 0:
            values.append(0.0)
            continue
        overlap = int(np.count_nonzero(a & b))
        values.append(float(overlap / max(1, min(ca, cb))))
    return float(sum(values) / len(values)) if values else 1.0


def _curvature_field(occupancy: np.ndarray, alpha_mask: np.ndarray) -> np.ndarray:
    thickness = occupancy.sum(axis=2).astype(np.float32)
    curvature = np.zeros(alpha_mask.shape, dtype=np.float32)
    height, width = alpha_mask.shape
    for y, x in np.argwhere(alpha_mask):
        values = []
        for nx, ny in ((int(x) - 1, int(y)), (int(x) + 1, int(y)), (int(x), int(y) - 1), (int(x), int(y) + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                values.append(abs(float(thickness[int(y), int(x)] - thickness[ny, nx])))
        curvature[int(y), int(x)] = float(sum(values) / len(values)) if values else 0.0
    return curvature


def _transition_volume(transition_zone: np.ndarray, occupancy: np.ndarray) -> np.ndarray:
    volume = np.zeros_like(occupancy, dtype=bool)
    for y, x in np.argwhere(transition_zone):
        col = occupancy[int(y), int(x), :]
        if not bool(np.any(col)):
            continue
        z0 = max(0, int(np.where(col)[0].min()) - 1)
        z1 = min(occupancy.shape[2] - 1, int(np.where(col)[0].max()) + 1)
        volume[int(y), int(x), z0 : z1 + 1] = True
    return volume


def _staircase_score(occupancy: np.ndarray, alpha_mask: np.ndarray) -> float:
    thickness = occupancy.sum(axis=2).astype(np.float32)
    values = []
    height, width = alpha_mask.shape
    for y, x in np.argwhere(alpha_mask):
        for nx, ny in ((int(x) + 1, int(y)), (int(x), int(y) + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                values.append(abs(float(thickness[int(y), int(x)] - thickness[ny, nx])) / max(1.0, occupancy.shape[2]))
    return max(0.0, min(1.0, float(sum(values) / len(values)) if values else 0.0))


def _fragmentation_score(mask: np.ndarray) -> float:
    components = _component_count_2d(mask)
    if components <= 1:
        return 0.0
    return max(0.0, min(1.0, (components - 1) / max(components + 3, 1)))


def _component_count_2d(mask: np.ndarray) -> int:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    queue.append((nx, ny))
    return components


def _oblique_projection(occupancy: np.ndarray) -> np.ndarray:
    height, width, depth = occupancy.shape
    canvas = np.zeros((height, width + depth), dtype=bool)
    for y, x, z in np.argwhere(occupancy):
        u = int(x) + int(round(int(z) * 0.58))
        if 0 <= u < canvas.shape[1]:
            canvas[int(y), u] = True
    return canvas


def _entropy(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=np.float32).reshape(-1)
    total = float(data.sum())
    if total <= 1e-6:
        return 0.0
    p = data[data > 0] / total
    entropy = -float(np.sum(p * np.log2(p)))
    return entropy / max(math.log2(len(data)), 1e-6)


def _label_grid(alpha_mask: np.ndarray, label_by_pixel: dict[Pixel, str]) -> np.ndarray:
    labels = np.full(alpha_mask.shape, "transparent", dtype=object)
    for y, x in np.argwhere(alpha_mask):
        raw = label_by_pixel.get((int(x), int(y)), "unknown")
        labels[int(y), int(x)] = _canonical_label(str(raw))
    return labels


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

def _write_mask(mask: np.ndarray, path: Path, colour: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = colour
    image.save(path, format="PNG")


def _write_projection(mask: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (90, 230, 175, 255)
    image.save(path, format="PNG")


def _write_flow_vectors(transition_zone: np.ndarray, flow_x: np.ndarray, flow_y: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (transition_zone.shape[1], transition_zone.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, x in np.argwhere(transition_zone):
        fx = float(flow_x[int(y), int(x)])
        fy = float(flow_y[int(y), int(x)])
        draw.point((int(x), int(y)), fill=(255, 220, 75, 255))
        if abs(fx) + abs(fy) > 1e-6:
            tx = int(x + max(-2.0, min(2.0, fx)))
            ty = int(y + max(-2.0, min(2.0, fy)))
            draw.line((int(x), int(y), tx, ty), fill=(95, 200, 255, 255))
    image.save(path, format="PNG")


def _write_normals(transition_zone: np.ndarray, flow_x: np.ndarray, flow_y: np.ndarray, path: Path) -> None:
    magnitude = np.sqrt(flow_x * flow_x + flow_y * flow_y)
    image = Image.new("RGBA", (transition_zone.shape[1], transition_zone.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    max_mag = max(float(magnitude.max()), 1e-6)
    for y, x in np.argwhere(transition_zone):
        t = float(magnitude[int(y), int(x)] / max_mag)
        pixels[int(x), int(y)] = (int(80 + 175 * t), int(255 - 90 * t), 210, 255)
    image.save(path, format="PNG")


def _write_heatmap(values: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (values.shape[1], values.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    max_value = max(float(values.max()), 1e-6)
    for y, x in np.argwhere(values > 0):
        t = max(0.0, min(1.0, float(values[int(y), int(x)] / max_value)))
        pixels[int(x), int(y)] = (int(255 * t), int(220 * (1.0 - t)), 100, 255)
    image.save(path, format="PNG")


def _write_mode_overlay(labels: np.ndarray, transition_zone: np.ndarray, mode_grid: np.ndarray, path: Path) -> None:
    palette = {
        "SOFT_BLEND": (90, 210, 255, 255),
        "TAPERED_BRIDGE": (255, 180, 80, 255),
        "SEATED_SURFACE": (165, 100, 255, 255),
        "SHELL_WRAP": (35, 35, 35, 255),
        "ARTICULATED_JOINT": (100, 230, 145, 255),
    }
    image = Image.new("RGBA", (labels.shape[1], labels.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(transition_zone):
        pixels[int(x), int(y)] = palette.get(str(mode_grid[int(y), int(x)]), (220, 220, 220, 255))
    image.save(path, format="PNG")


def _write_pair_debug(labels: np.ndarray, transition_zone: np.ndarray, allowed_labels: set[str], path: Path) -> None:
    image = Image.new("RGBA", (labels.shape[1], labels.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(transition_zone):
        label = str(labels[int(y), int(x)])
        if label in allowed_labels:
            pixels[int(x), int(y)] = (255, 90, 205, 255) if label in {"hair/hat", "left_arm", "right_arm"} else (90, 210, 255, 255)
    image.save(path, format="PNG")
