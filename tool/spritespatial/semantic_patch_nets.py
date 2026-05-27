from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.semantic_macro_patches import consolidate_macro_patches
from spritespatial.semantic_remeshing import (
    LABEL_IDS,
    _adjacency,
    _degenerate_face_count,
    _directional_feature_preservation_score,
    _directional_feature_vertices,
    _edge_faces,
    _face_edges,
    _face_normals,
    _hat_extension_score,
    _mesh_component_count,
    _mesh_stats,
    _normal_discontinuity,
    _normalise_metadata,
    _planar_surface_score,
    _projection_image,
    _semantic_boundary_edges,
    _semantic_labels_from_face_metadata,
    _silhouette_vertices,
    _staircase_artifact_score,
    _surface_flow_score,
    _triangulated_face_count,
    _triangulated_indices,
    _vertex_labels,
    _wireframe_image,
    _write_json,
)


def load_patch_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "humanoid_voxel")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "patch_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = data.get("name", path.stem)
    data["path"] = str(path)
    return data


def apply_semantic_patch_nets(
    mesh: dict[str, Any],
    sdf: np.ndarray,
    semantic: np.ndarray,
    semantic_part_graph: dict[str, Any] | None,
    directional_report: dict[str, Any] | None,
    profile: dict[str, Any],
    output_dir: Path,
    emit_debug: bool = False,
    macro_patch_profile: dict[str, Any] | None = None,
    macro_output_dir: Path | None = None,
    emit_macro_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    vertex_metadata = _normalise_metadata(mesh.get("vertex_metadata", []), len(vertices))
    face_metadata = _normalise_metadata(mesh.get("face_metadata", []), len(faces))
    labels_before = _semantic_labels_from_face_metadata(face_metadata)
    vertex_labels = _vertex_labels(vertex_metadata, faces, face_metadata, len(vertices))
    patches = _construct_patches(mesh, sdf, semantic, vertex_metadata, profile)
    macro_result: dict[str, Any] = {}
    stabilisation_patches = patches
    if macro_patch_profile:
        macro_result = consolidate_macro_patches(
            patches,
            sdf,
            semantic,
            semantic_part_graph,
            directional_report,
            macro_patch_profile,
            macro_output_dir or output_dir.parent / "macro_patches",
            emit_debug=emit_macro_debug,
        )
        stabilisation_patches = list(macro_result.get("patches", patches))
    cell_to_patch = {
        tuple(cell): int(patch["patch_id"])
        for patch in stabilisation_patches
        for cell in patch.get("cells", [])
        if isinstance(cell, list) and len(cell) == 3
    }
    patch_vertices = _patch_vertices(mesh, cell_to_patch)
    protected = _protected_vertices(mesh, vertex_metadata, vertices, vertex_labels, faces, face_metadata, profile)

    before_normals = _face_normals(vertices, faces)
    edge_faces = _edge_faces(faces)
    normal_before = _normal_discontinuity(before_normals, edge_faces)
    staircase_before = _staircase_artifact_score(normal_before, faces, vertices)
    surface_flow_before = _surface_flow_score(normal_before)
    planar_before = _planar_surface_score(before_normals)
    hat_before = _hat_extension_score(vertices, vertex_labels)
    triangle_before = _triangulated_face_count(faces)
    non_manifold_before = _non_manifold_edge_count(faces)
    qef_report = _qef_quality_report(mesh, vertices, faces)

    candidate, adjusted_vertices = _stabilise_vertices(vertices, stabilisation_patches, patch_vertices, protected, profile)
    candidate_metrics = _quality_metrics(candidate, faces)
    accepted = (
        candidate_metrics["staircase_artifact"] <= staircase_before + float(profile.get("metric_epsilon", 1e-6))
        and candidate_metrics["surface_flow"] >= surface_flow_before - float(profile.get("metric_epsilon", 1e-6))
    )
    if accepted:
        final_vertices = candidate
    else:
        final_vertices = vertices.copy()
        adjusted_vertices = set()
        candidate_metrics = _quality_metrics(final_vertices, faces)

    displacement = np.linalg.norm(final_vertices - vertices, axis=1) if len(vertices) else np.zeros(0, dtype=np.float32)
    final_normals = _face_normals(final_vertices, faces)
    normal_after = _normal_discontinuity(final_normals, edge_faces)
    staircase_after = _staircase_artifact_score(normal_after, faces, final_vertices)
    surface_flow_after = _surface_flow_score(normal_after)
    planar_after = _planar_surface_score(final_normals)
    hat_after = _hat_extension_score(final_vertices, vertex_labels)
    semantic_edges = _semantic_boundary_edges(mesh, faces, face_metadata)
    silhouette = _silhouette_vertices(mesh, vertex_metadata, vertices)
    silhouette_drift = _max_displacement(displacement, silhouette)
    semantic_boundary_preservation = _boundary_preservation_score(displacement, semantic_edges, profile)
    silhouette_preservation = max(
        0.0,
        1.0 - silhouette_drift / max(float(profile.get("silhouette_drift_tolerance_px", 1.0)), 1e-6),
    )
    directional_preservation = _directional_feature_preservation_score(hat_before, hat_after)
    labels_after = _semantic_labels_from_face_metadata(face_metadata)
    degenerate_count = _degenerate_face_count(final_vertices, faces)
    component_count = _mesh_component_count(len(final_vertices), _adjacency(faces))
    non_manifold_after = _non_manifold_edge_count(faces)
    triangle_after = _triangulated_face_count(faces)
    patch_stats = _patch_stats(patches)
    macro_report = dict(macro_result.get("report", {}))
    macro_enabled = bool(macro_report)
    max_non_manifold = non_manifold_before + int(profile.get("max_non_manifold_increase", 2))
    fail_conditions = {
        "zero_faces": triangle_after <= 0,
        "semantic_labels_disappeared": labels_before != labels_after,
        "mesh_disconnected": component_count != 1,
        "degenerate_faces_introduced": degenerate_count > 0,
        "silhouette_drift_exceeded": silhouette_drift > float(profile.get("silhouette_drift_tolerance_px", 1.0)),
        "hat_asymmetry_dropped": directional_preservation < float(profile.get("directional_preservation_min", 0.85)),
        "non_manifold_edge_count_increased": non_manifold_after > max_non_manifold,
    }
    if bool(qef_report.get("qef_enabled", False)):
        fail_conditions.update(
            {
                "qef_no_cells_accepted": int(qef_report.get("qef_cells_accepted", 0)) <= 0,
                "qef_max_displacement_exceeded": float(qef_report.get("qef_max_displacement", 0.0))
                > float(qef_report.get("qef_max_displacement_limit", 0.0)) + 1.0e-6,
            }
        )

    patch_mesh = dict(mesh)
    patch_mesh["schema"] = "spritespatial_surface_nets_mesh_semantic_patch_v1"
    patch_mesh["vertices"] = [[float(value) for value in row] for row in final_vertices.tolist()]
    patch_mesh["faces"] = faces
    patch_mesh["vertex_metadata"] = vertex_metadata
    patch_mesh["face_metadata"] = face_metadata
    patch_mesh["indices"] = _triangulated_indices(faces, patch_mesh["vertices"])
    patch_mesh["semantic_patch_nets"] = {
        "enabled": True,
        "profile": profile.get("name", "humanoid_voxel"),
        "patch_adjustment_accepted": accepted,
        "patch_count": len(patches),
    }
    if bool(qef_report.get("qef_enabled", False)):
        qef_payload = dict(patch_mesh.get("qef", {}))
        qef_payload["report"] = {**dict(qef_payload.get("report", {})), **qef_report}
        patch_mesh["qef"] = qef_payload
    patch_mesh["config"] = {**dict(patch_mesh.get("config", {})), "mesh_backend": "surface_nets_patch"}
    patch_mesh["stats"] = _mesh_stats(patch_mesh, component_count, degenerate_count)

    report = {
        "schema": "spritespatial_semantic_patch_nets_report_v1",
        "semantic_patch_nets_enabled": True,
        "patch_profile": profile.get("name", "humanoid_voxel"),
        "patch_count": len(patches),
        **patch_stats,
        "macro_patches_enabled": macro_enabled,
        "macro_patch_profile": macro_report.get("macro_patch_profile", ""),
        "micro_patch_count": int(macro_report.get("micro_patch_count", len(patches))) if macro_enabled else len(patches),
        "macro_patch_count": int(macro_report.get("macro_patch_count", 0)) if macro_enabled else 0,
        "macro_patch_reduction_ratio": float(macro_report.get("macro_patch_reduction_ratio", 0.0)) if macro_enabled else 0.0,
        "mean_macro_patch_size": float(macro_report.get("mean_macro_patch_size", 0.0)) if macro_enabled else 0.0,
        "small_macro_patch_ratio": float(macro_report.get("small_macro_patch_ratio", 0.0)) if macro_enabled else 0.0,
        "planar_macro_patch_count": int(macro_report.get("planar_macro_patch_count", 0)) if macro_enabled else 0,
        "curved_macro_patch_count": int(macro_report.get("curved_macro_patch_count", 0)) if macro_enabled else 0,
        "directional_feature_macro_patch_count": int(macro_report.get("directional_feature_macro_patch_count", 0)) if macro_enabled else 0,
        "noise_fragments_absorbed": int(macro_report.get("noise_fragments_absorbed", 0)) if macro_enabled else 0,
        "macro_patch_coherence_score": float(macro_report.get("macro_patch_coherence_score", 0.0)) if macro_enabled else 0.0,
        "triangle_count_before_patch": triangle_before,
        "triangle_count_after_patch": triangle_after,
        **qef_report,
        "staircase_artifact_before": staircase_before,
        "staircase_artifact_after": staircase_after,
        "surface_flow_before": surface_flow_before,
        "surface_flow_after": surface_flow_after,
        "patch_coherence_score": _patch_coherence_score(patch_stats, silhouette_preservation, semantic_boundary_preservation),
        "semantic_boundary_preservation_score": semantic_boundary_preservation,
        "silhouette_edge_preservation_score": silhouette_preservation,
        "directional_feature_preservation_score": directional_preservation,
        "planar_surface_score_before": planar_before,
        "planar_surface_score_after": planar_after,
        "patch_vertices_adjusted": len(adjusted_vertices),
        "mean_vertex_displacement": float(np.mean(displacement)) if displacement.size else 0.0,
        "max_vertex_displacement": float(np.max(displacement)) if displacement.size else 0.0,
        "silhouette_drift_px": silhouette_drift,
        "non_manifold_edge_count_before": non_manifold_before,
        "non_manifold_edge_count_after": non_manifold_after,
        "mesh_connected_components": component_count,
        "degenerate_face_count": degenerate_count,
        "semantic_labels_before": labels_before,
        "semantic_labels_after": labels_after,
        "hat_extension_before": hat_before,
        "hat_extension_after": hat_after,
        "patch_adjustment_accepted": accepted,
        "semantic_part_graph_present": bool(semantic_part_graph),
        "directional_report_present": bool(directional_report),
        "passed": not any(fail_conditions.values()),
        "fail_conditions": fail_conditions,
    }
    report["visual_quality_diagnosis"] = _diagnosis(report)
    if macro_enabled:
        macro_report.update(
            {
                "patch_adjustment_accepted": accepted,
                "staircase_artifact_before": staircase_before,
                "staircase_artifact_after": staircase_after,
                "surface_flow_before": surface_flow_before,
                "surface_flow_after": surface_flow_after,
                "semantic_boundary_preservation_score": semantic_boundary_preservation,
                "silhouette_edge_preservation_score": silhouette_preservation,
                "directional_feature_preservation_score": directional_preservation,
                "mean_vertex_displacement": report["mean_vertex_displacement"],
                "max_vertex_displacement": report["max_vertex_displacement"],
                "silhouette_drift_px": silhouette_drift,
                "mesh_connected_components": component_count,
                "degenerate_face_count": degenerate_count,
                "visual_quality_diagnosis": report["visual_quality_diagnosis"],
            }
        )
        macro_paths = macro_result.get("paths", {})
        macro_report_path = macro_paths.get("macro_patch_report")
        if isinstance(macro_report_path, Path):
            _write_json(macro_report_path, macro_report)
        _write_macro_before_after_outputs(vertices, final_vertices, faces, vertex_labels, macro_paths)
    patch_graph = {
        "schema": "spritespatial_semantic_patch_graph_v1",
        "profile": profile.get("name", "humanoid_voxel"),
        "patches": patches,
    }
    paths = {
        "mesh_patch": output_dir.parent / "mesh_patch.json",
        "patch_graph": output_dir / "patch_graph.json",
        "patch_report": output_dir / "patch_report.json",
        "patch_id_map": output_dir / "patch_id_map.png",
        "patch_boundary_debug": output_dir / "patch_boundary_debug.png",
        "patch_normal_debug": output_dir / "patch_normal_debug.png",
        "patch_curvature_debug": output_dir / "patch_curvature_debug.png",
        "patch_planar_projection_debug": output_dir / "patch_planar_projection_debug.png",
        "before_after_patch_wireframe": output_dir / "before_after_patch_wireframe.png",
        "before_after_contact_sheet": output_dir / "before_after_contact_sheet.png",
    }
    _write_json(paths["mesh_patch"], patch_mesh)
    _write_json(paths["patch_graph"], patch_graph)
    _write_json(paths["patch_report"], report)
    _write_debug_images(vertices, final_vertices, faces, patches, cell_to_patch, displacement, vertex_labels, semantic_edges, paths)
    combined_paths = dict(paths)
    for key, path in macro_result.get("paths", {}).items():
        if isinstance(path, Path):
            combined_paths[f"macro_{key}"] = path
    return {"mesh": patch_mesh, "report": report, "paths": combined_paths, "macro": macro_result}


def _construct_patches(
    mesh: dict[str, Any],
    sdf: np.ndarray,
    semantic: np.ndarray,
    vertex_metadata: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    active_cells: dict[tuple[int, int, int], int] = {}
    for key, value in mesh.get("active_cells", {}).items():
        try:
            cell = tuple(int(part) for part in str(key).split(","))
        except ValueError:
            continue
        if len(cell) == 3:
            active_cells[cell] = int(value)
    mesh_vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    silhouette_vertices = _silhouette_vertices(mesh, vertex_metadata, mesh_vertices)
    infos = {}
    for cell, vertex_index in active_cells.items():
        y, x, z = cell
        label = _cell_label(semantic, cell)
        normal = _cell_normal(sdf, y, x, z)
        normal_bucket = _normal_bucket(normal)
        curvature = _curvature_score(sdf, y, x, z, normal)
        metadata = vertex_metadata[vertex_index] if 0 <= vertex_index < len(vertex_metadata) else {}
        boundary = bool(metadata.get("is_semantic_boundary", False))
        silhouette = int(vertex_index) in silhouette_vertices
        infos[cell] = {
            "label": label,
            "normal": normal,
            "normal_bucket": normal_bucket,
            "curvature": curvature,
            "boundary": boundary,
            "silhouette": silhouette,
        }
    patches = []
    seen: set[tuple[int, int, int]] = set()
    min_count = int(profile.get("min_patch_cell_count", 2))
    for start in sorted(infos):
        if start in seen:
            continue
        info = infos[start]
        queue = deque([start])
        seen.add(start)
        cells = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            for neighbour in _cell_neighbours(cell):
                if neighbour in seen or neighbour not in infos:
                    continue
                other = infos[neighbour]
                if _same_patch_signature(info, other):
                    seen.add(neighbour)
                    queue.append(neighbour)
        patch_infos = [infos[cell] for cell in cells]
        normals = np.asarray([item["normal"] for item in patch_infos], dtype=np.float32)
        dominant = np.mean(normals, axis=0) if normals.size else np.array([0.0, 0.0, 1.0], dtype=np.float32)
        length = float(np.linalg.norm(dominant))
        if length > 1e-8:
            dominant = dominant / length
        curvature = float(np.mean([float(item["curvature"]) for item in patch_infos])) if patch_infos else 0.0
        patch_id = len(patches)
        patches.append(
            {
                "patch_id": patch_id,
                "semantic_label": _label_name(int(info["label"])),
                "semantic_label_id": int(info["label"]),
                "cell_count": len(cells),
                "dominant_normal": [float(value) for value in dominant.tolist()],
                "normal_bucket": list(info["normal_bucket"]),
                "curvature_score": curvature,
                "is_silhouette_patch": bool(any(item["silhouette"] for item in patch_infos)),
                "is_semantic_boundary_patch": bool(any(item["boundary"] for item in patch_infos)),
                "is_planar_patch": bool(len(cells) >= min_count and curvature <= float(profile.get("curvature_threshold", 0.20))),
                "cells": [list(cell) for cell in cells],
            }
        )
    return patches


def _same_patch_signature(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        int(a["label"]) == int(b["label"])
        and tuple(a["normal_bucket"]) == tuple(b["normal_bucket"])
        and bool(a["boundary"]) == bool(b["boundary"])
        and bool(a["silhouette"]) == bool(b["silhouette"])
    )


def _cell_neighbours(cell: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    y, x, z = cell
    return [
        (y - 1, x, z),
        (y + 1, x, z),
        (y, x - 1, z),
        (y, x + 1, z),
        (y, x, z - 1),
        (y, x, z + 1),
    ]


def _cell_label(semantic: np.ndarray, cell: tuple[int, int, int]) -> int:
    y, x, z = cell
    labels = []
    for dy in (0, 1):
        for dx in (0, 1):
            for dz in (0, 1):
                yy, xx, zz = y + dy, x + dx, z + dz
                if 0 <= yy < semantic.shape[0] and 0 <= xx < semantic.shape[1] and 0 <= zz < semantic.shape[2]:
                    value = int(semantic[yy, xx, zz])
                    if value != 0:
                        labels.append(value)
    if not labels:
        return 0
    return max(set(labels), key=labels.count)


def _cell_normal(sdf: np.ndarray, y: int, x: int, z: int) -> np.ndarray:
    yy = min(max(y, 1), sdf.shape[0] - 2)
    xx = min(max(x, 1), sdf.shape[1] - 2)
    zz = min(max(z, 1), sdf.shape[2] - 2)
    dy = float(sdf[yy + 1, xx, zz] - sdf[yy - 1, xx, zz])
    dx = float(sdf[yy, xx + 1, zz] - sdf[yy, xx - 1, zz])
    dz = float(sdf[yy, xx, zz + 1] - sdf[yy, xx, zz - 1])
    normal = np.array([dx, dy, dz], dtype=np.float32)
    length = float(np.linalg.norm(normal))
    if length <= 1e-8:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)
    return normal / length


def _normal_bucket(normal: np.ndarray) -> tuple[int, int]:
    axis = int(np.argmax(np.abs(normal)))
    sign = 1 if float(normal[axis]) >= 0.0 else -1
    return axis, sign


def _curvature_score(sdf: np.ndarray, y: int, x: int, z: int, normal: np.ndarray) -> float:
    values = []
    for yy, xx, zz in _cell_neighbours((y, x, z)):
        if 1 <= yy < sdf.shape[0] - 1 and 1 <= xx < sdf.shape[1] - 1 and 1 <= zz < sdf.shape[2] - 1:
            values.append(float(np.linalg.norm(_cell_normal(sdf, yy, xx, zz) - normal)))
    return float(np.mean(values)) if values else 0.0


def _patch_vertices(mesh: dict[str, Any], cell_to_patch: dict[tuple[int, int, int], int]) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for key, vertex in mesh.get("active_cells", {}).items():
        try:
            cell = tuple(int(part) for part in str(key).split(","))
        except ValueError:
            continue
        if cell in cell_to_patch:
            result[cell_to_patch[cell]].add(int(vertex))
    return result


def _protected_vertices(
    mesh: dict[str, Any],
    vertex_metadata: list[dict[str, Any]],
    vertices: np.ndarray,
    labels: np.ndarray,
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    profile: dict[str, Any],
) -> set[int]:
    protected = _silhouette_vertices(mesh, vertex_metadata, vertices)
    protected.update(_directional_feature_vertices(vertices, labels))
    preserve_ids = {LABEL_IDS.get(str(label), -1) for label in profile.get("preserve_labels", [])}
    protected.update(index for index, label in enumerate(labels) if int(label) in preserve_ids)
    boundary_edges = _semantic_boundary_edges(mesh, faces, face_metadata)
    if float(profile.get("semantic_boundary_lock_weight", 1.0)) >= 0.95:
        protected.update(index for edge in boundary_edges for index in edge)
    return protected


def _stabilise_vertices(
    vertices: np.ndarray,
    patches: list[dict[str, Any]],
    patch_vertices: dict[int, set[int]],
    protected: set[int],
    profile: dict[str, Any],
) -> tuple[np.ndarray, set[int]]:
    result = vertices.copy()
    adjusted = set()
    max_adjust = float(profile.get("max_patch_vertex_adjustment", 0.20))
    planar_strength = float(profile.get("planar_projection_strength", 0.35))
    curved_strength = float(profile.get("curved_patch_smoothing_strength", 0.12))
    for patch in patches:
        indices = [index for index in patch_vertices.get(int(patch["patch_id"]), set()) if index not in protected]
        if len(indices) < int(profile.get("min_patch_cell_count", 2)):
            continue
        if patch.get("is_silhouette_patch") or patch.get("is_semantic_boundary_patch"):
            continue
        normal = np.asarray(patch.get("dominant_normal", [0.0, 0.0, 1.0]), dtype=np.float32)
        axis = int(np.argmax(np.abs(normal)))
        if bool(patch.get("is_planar_patch", False)):
            target = float(np.median(vertices[indices, axis]))
            strength = planar_strength
            for index in indices:
                proposed = result[index].copy()
                proposed[axis] = float(result[index, axis] + (target - result[index, axis]) * strength)
                result[index] = _clamp(vertices[index], proposed, max_adjust)
                if float(np.linalg.norm(result[index] - vertices[index])) > 1e-8:
                    adjusted.add(index)
        else:
            centroid = vertices[indices].mean(axis=0)
            for index in indices:
                proposed = result[index] + (centroid - result[index]) * curved_strength
                result[index] = _clamp(vertices[index], proposed, max_adjust)
                if float(np.linalg.norm(result[index] - vertices[index])) > 1e-8:
                    adjusted.add(index)
    return result, adjusted


def _clamp(original: np.ndarray, proposed: np.ndarray, max_distance: float) -> np.ndarray:
    delta = proposed - original
    length = float(np.linalg.norm(delta))
    if length <= max_distance or length <= 1e-8:
        return proposed
    return original + delta / length * max_distance


def _quality_metrics(vertices: np.ndarray, faces: list[list[int]]) -> dict[str, float]:
    normals = _face_normals(vertices, faces)
    edge_faces = _edge_faces(faces)
    normal_discontinuity = _normal_discontinuity(normals, edge_faces)
    return {
        "normal_discontinuity": normal_discontinuity,
        "staircase_artifact": _staircase_artifact_score(normal_discontinuity, faces, vertices),
        "surface_flow": _surface_flow_score(normal_discontinuity),
    }


def _qef_quality_report(mesh: dict[str, Any], qef_vertices: np.ndarray, faces: list[list[int]]) -> dict[str, Any]:
    qef_payload = dict(mesh.get("qef", {}))
    base_report = dict(qef_payload.get("report", {}))
    if not bool(base_report.get("qef_enabled", False)):
        return {
            "surface_net_vertex_placement": str(mesh.get("config", {}).get("surface_net_vertex_placement", "average")),
            "qef_enabled": False,
            "qef_cells_processed": 0,
            "qef_cells_accepted": 0,
            "qef_cells_rejected": 0,
            "qef_acceptance_ratio": 0.0,
            "qef_mean_displacement": 0.0,
            "qef_max_displacement": 0.0,
            "qef_fallback_count": 0,
            "qef_condition_warning_count": 0,
            "staircase_artifact_before_qef": 0.0,
            "staircase_artifact_after_qef": 0.0,
            "surface_flow_before_qef": 0.0,
            "surface_flow_after_qef": 0.0,
            "planar_surface_score_before_qef": 0.0,
            "planar_surface_score_after_qef": 0.0,
            "qef_quality_metric_improved": False,
        }
    standard_vertices = np.asarray(qef_payload.get("standard_vertices", []), dtype=np.float32)
    if standard_vertices.shape != qef_vertices.shape:
        standard_vertices = qef_vertices.copy()
    before_normals = _face_normals(standard_vertices, faces)
    after_normals = _face_normals(qef_vertices, faces)
    before_edges = _edge_faces(faces)
    normal_before = _normal_discontinuity(before_normals, before_edges)
    normal_after = _normal_discontinuity(after_normals, before_edges)
    staircase_before = _staircase_artifact_score(normal_before, faces, standard_vertices)
    staircase_after = _staircase_artifact_score(normal_after, faces, qef_vertices)
    surface_flow_before = _surface_flow_score(normal_before)
    surface_flow_after = _surface_flow_score(normal_after)
    planar_before = _planar_surface_score(before_normals)
    planar_after = _planar_surface_score(after_normals)
    epsilon = 1.0e-6
    improved = (
        staircase_after < staircase_before - epsilon
        or surface_flow_after > surface_flow_before + epsilon
        or planar_after > planar_before + epsilon
    )
    return {
        **base_report,
        "staircase_artifact_before_qef": staircase_before,
        "staircase_artifact_after_qef": staircase_after,
        "surface_flow_before_qef": surface_flow_before,
        "surface_flow_after_qef": surface_flow_after,
        "planar_surface_score_before_qef": planar_before,
        "planar_surface_score_after_qef": planar_after,
        "qef_quality_metric_improved": bool(improved),
    }


def _patch_stats(patches: list[dict[str, Any]]) -> dict[str, Any]:
    sizes = [int(patch.get("cell_count", 0)) for patch in patches]
    total = max(len(sizes), 1)
    small = sum(1 for size in sizes if size <= 2)
    return {
        "mean_patch_size": float(np.mean(sizes)) if sizes else 0.0,
        "small_patch_ratio": float(small) / float(total),
        "planar_patch_count": sum(1 for patch in patches if patch.get("is_planar_patch", False)),
        "curved_patch_count": sum(1 for patch in patches if not patch.get("is_planar_patch", False)),
        "silhouette_patch_count": sum(1 for patch in patches if patch.get("is_silhouette_patch", False)),
        "semantic_boundary_patch_count": sum(1 for patch in patches if patch.get("is_semantic_boundary_patch", False)),
    }


def _patch_coherence_score(stats: dict[str, Any], silhouette_score: float, boundary_score: float) -> float:
    mean_size_score = min(1.0, float(stats.get("mean_patch_size", 0.0)) / 8.0)
    small_patch_score = 1.0 - float(stats.get("small_patch_ratio", 1.0))
    return float(max(0.0, min(1.0, 0.35 * mean_size_score + 0.25 * small_patch_score + 0.20 * silhouette_score + 0.20 * boundary_score)))


def _non_manifold_edge_count(faces: list[list[int]]) -> int:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for face in faces:
        for edge in _face_edges(face):
            counts[edge] += 1
    return sum(1 for count in counts.values() if count > 2)


def _max_displacement(displacement: np.ndarray, indices: set[int]) -> float:
    valid = [index for index in indices if 0 <= index < len(displacement)]
    if not valid:
        return 0.0
    return float(np.max(displacement[valid]))


def _boundary_preservation_score(displacement: np.ndarray, edges: set[tuple[int, int]], profile: dict[str, Any]) -> float:
    if not edges or displacement.size == 0:
        return 1.0
    values = []
    for a, b in edges:
        if a < len(displacement) and b < len(displacement):
            values.append(max(float(displacement[a]), float(displacement[b])))
    mean = float(np.mean(values)) if values else 0.0
    return max(0.0, min(1.0, 1.0 - mean / max(float(profile.get("max_patch_vertex_adjustment", 0.20)), 1e-6)))


def _label_name(label: int) -> str:
    return {
        1: "outline",
        2: "head",
        3: "face",
        4: "hair/hat",
        5: "torso",
        6: "left_arm",
        7: "right_arm",
        8: "left_leg",
        9: "right_leg",
        10: "boots/feet",
        11: "equipment/shield/sword",
    }.get(label, "unknown")


def _write_debug_images(
    before_vertices: np.ndarray,
    after_vertices: np.ndarray,
    faces: list[list[int]],
    patches: list[dict[str, Any]],
    cell_to_patch: dict[tuple[int, int, int], int],
    displacement: np.ndarray,
    labels: np.ndarray,
    semantic_edges: set[tuple[int, int]],
    paths: dict[str, Path],
) -> None:
    _write_patch_id_map(patches, paths["patch_id_map"])
    _write_patch_flag_map(patches, "is_semantic_boundary_patch", paths["patch_boundary_debug"])
    _write_patch_normal_map(patches, paths["patch_normal_debug"])
    _write_patch_curvature_map(patches, paths["patch_curvature_debug"])
    _write_displacement_map(after_vertices, displacement, paths["patch_planar_projection_debug"])
    _write_pair(_wireframe_image(before_vertices, faces), _wireframe_image(after_vertices, faces), paths["before_after_patch_wireframe"])
    _write_pair(_projection_image(before_vertices, labels), _projection_image(after_vertices, labels), paths["before_after_contact_sheet"])


def _write_macro_before_after_outputs(
    before_vertices: np.ndarray,
    after_vertices: np.ndarray,
    faces: list[list[int]],
    labels: np.ndarray,
    macro_paths: dict[str, Any],
) -> None:
    wire_path = macro_paths.get("before_after_macro_patch_wireframe")
    sheet_path = macro_paths.get("before_after_contact_sheet")
    if isinstance(wire_path, Path):
        _write_pair(_wireframe_image(before_vertices, faces), _wireframe_image(after_vertices, faces), wire_path)
    if isinstance(sheet_path, Path):
        _write_pair(_projection_image(before_vertices, labels), _projection_image(after_vertices, labels), sheet_path)


def _write_patch_id_map(patches: list[dict[str, Any]], path: Path) -> None:
    image = _patch_canvas(patches)
    draw = ImageDraw.Draw(image)
    scale = 6
    for patch in patches:
        color = _patch_color(int(patch["patch_id"]))
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=color)
    image.save(path, format="PNG")


def _write_patch_flag_map(patches: list[dict[str, Any]], flag: str, path: Path) -> None:
    image = _patch_canvas(patches)
    draw = ImageDraw.Draw(image)
    scale = 6
    for patch in patches:
        color = (255, 80, 80, 255) if patch.get(flag, False) else (60, 160, 180, 255)
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=color)
    image.save(path, format="PNG")


def _write_patch_normal_map(patches: list[dict[str, Any]], path: Path) -> None:
    image = _patch_canvas(patches)
    draw = ImageDraw.Draw(image)
    scale = 6
    colors = [(240, 80, 80, 255), (80, 220, 120, 255), (100, 150, 255, 255)]
    for patch in patches:
        normal = np.asarray(patch.get("dominant_normal", [0, 0, 1]), dtype=np.float32)
        axis = int(np.argmax(np.abs(normal)))
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=colors[axis])
    image.save(path, format="PNG")


def _write_patch_curvature_map(patches: list[dict[str, Any]], path: Path) -> None:
    image = _patch_canvas(patches)
    draw = ImageDraw.Draw(image)
    scale = 6
    max_value = max((float(patch.get("curvature_score", 0.0)) for patch in patches), default=1.0)
    for patch in patches:
        t = float(patch.get("curvature_score", 0.0)) / max(max_value, 1e-6)
        color = (int(255 * t), int(220 * (1.0 - t)), 60, 255)
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=color)
    image.save(path, format="PNG")


def _write_displacement_map(vertices: np.ndarray, displacement: np.ndarray, path: Path) -> None:
    labels = np.zeros((len(vertices),), dtype=np.int32)
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    scale = 6
    max_value = float(np.max(displacement)) if displacement.size else 0.0
    for vertex, value in zip(vertices, displacement):
        if value <= 1e-8:
            continue
        t = float(value) / max(max_value, 1e-6)
        x = int(round(float(vertex[0]) * scale))
        y = int(round(float(vertex[1]) * scale))
        draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=(255, int(220 * (1.0 - t)), 40, 255))
    image.save(path, format="PNG")


def _patch_canvas(patches: list[dict[str, Any]], scale: int = 6) -> Image.Image:
    cells = [cell for patch in patches for cell in patch.get("cells", [])]
    if not cells:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    height = max(int(cell[0]) for cell in cells) + 2
    width = max(int(cell[1]) for cell in cells) + 2
    return Image.new("RGBA", (width * scale, height * scale), (0, 45, 55, 255))


def _patch_color(index: int) -> tuple[int, int, int, int]:
    return (
        int((index * 73) % 255),
        int((index * 151 + 80) % 255),
        int((index * 199 + 130) % 255),
        255,
    )


def _write_pair(left: Image.Image, right: Image.Image, path: Path) -> None:
    width = max(left.width, right.width)
    height = max(left.height, right.height)
    sheet = Image.new("RGBA", (width * 2, height), (0, 0, 0, 255))
    sheet.alpha_composite(left, (0, 0))
    sheet.alpha_composite(right, (width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((2, 2), "before", fill=(255, 255, 255, 255))
    draw.text((width + 2, 2), "after", fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _diagnosis(report: dict[str, Any]) -> dict[str, Any]:
    staircase_before = float(report.get("staircase_artifact_before", 0.0))
    staircase_after = float(report.get("staircase_artifact_after", 0.0))
    flow_before = float(report.get("surface_flow_before", 0.0))
    flow_after = float(report.get("surface_flow_after", 0.0))
    improved = staircase_after <= staircase_before and flow_after >= flow_before
    accepted = bool(report.get("patch_adjustment_accepted", False))
    likely = "none" if improved and accepted else "surface-net vertex placement"
    if float(report.get("patch_coherence_score", 0.0)) < 0.35 or float(report.get("small_patch_ratio", 0.0)) > 0.55 or int(report.get("planar_patch_count", 0)) == 0:
        likely = "patch grouping thresholds"
    return {
        "patch_metric_improved_or_preserved": improved,
        "sdf_resolution_too_low": False,
        "surface_net_vertex_placement_issue": likely == "surface-net vertex placement",
        "authored_side_view_missing": False,
        "render_material_readability_issue": False,
        "patch_grouping_threshold_issue": likely == "patch grouping thresholds",
        "likely_cause": likely,
        "notes": [
            "Patch grouping is built from active SDF cells, semantic labels, normal buckets, curvature, silhouette state, and semantic boundary state.",
            "Patch vertex stabilisation is guarded; if it worsens staircase or surface-flow metrics, the standard surface-net placement is retained.",
            "This backend preserves semantics and silhouette authority before render/material assignment.",
        ],
        "recommended_next_engineering_step": (
            "Inspect patch_graph.json and patch debug maps; tune patch thresholds only after checking whether patch cells are too fragmented."
        ),
    }
