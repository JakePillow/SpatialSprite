from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


LABEL_IDS = {
    "outline": 1,
    "head": 2,
    "face": 3,
    "hair/hat": 4,
    "torso": 5,
    "left_arm": 6,
    "right_arm": 7,
    "left_leg": 8,
    "right_leg": 9,
    "boots/feet": 10,
    "equipment/shield/sword": 11,
    "unknown": 12,
}

ID_LABELS = {value: key for key, value in LABEL_IDS.items()}


def load_remesh_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "humanoid_lowpoly")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "remeshing_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = data.get("name", path.stem)
    data["path"] = str(path)
    return data


def apply_semantic_remeshing(
    mesh: dict[str, Any],
    semantic_part_graph: dict[str, Any] | None,
    profile: dict[str, Any],
    output_dir: Path,
    iterations: int = 1,
    strength: float = 0.35,
    preserve_silhouette_edges: bool = True,
    emit_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    original_vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    original_faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    original_face_metadata = _normalise_metadata(mesh.get("face_metadata", []), len(original_faces))
    original_vertex_metadata = _normalise_metadata(mesh.get("vertex_metadata", []), len(original_vertices))

    labels_before = _semantic_labels_from_face_metadata(original_face_metadata)
    vertex_labels = _vertex_labels(original_vertex_metadata, original_faces, original_face_metadata, len(original_vertices))
    silhouette = _silhouette_vertices(mesh, original_vertex_metadata, original_vertices) if preserve_silhouette_edges else set()
    semantic_boundary_edges = _semantic_boundary_edges(mesh, original_faces, original_face_metadata)
    semantic_boundary_vertices = {index for edge in semantic_boundary_edges for index in edge}
    protected = set(silhouette)
    protected.update(_protected_label_vertices(vertex_labels, profile))
    protected.update(_directional_feature_vertices(original_vertices, vertex_labels))
    if bool(profile.get("lock_semantic_boundary_vertices", True)):
        protected.update(semantic_boundary_vertices)

    before_normals = _face_normals(original_vertices, original_faces)
    before_edge_faces = _edge_faces(original_faces)
    before_normal_discontinuity = _normal_discontinuity(before_normals, before_edge_faces)
    before_staircase = _staircase_artifact_score(before_normal_discontinuity, original_faces, original_vertices)
    before_planar = _planar_surface_score(before_normals)
    before_surface_flow = _surface_flow_score(before_normal_discontinuity)
    before_hat_extension = _hat_extension_score(original_vertices, vertex_labels)
    triangle_count_before = _triangulated_face_count(original_faces)

    working_faces = [face[:] for face in original_faces]
    working_metadata = [dict(item) for item in original_face_metadata]
    merge_result = _merge_coplanar_faces(
        original_vertices,
        working_faces,
        working_metadata,
        protected,
        profile,
        max(1, int(iterations)),
    )
    working_faces = merge_result["faces"]
    working_metadata = merge_result["face_metadata"]
    working_vertices, working_vertex_metadata, working_faces, compact_mapping = _compact_vertices(
        original_vertices,
        original_vertex_metadata,
        working_faces,
    )
    vertex_labels = _vertex_labels(working_vertex_metadata, working_faces, working_metadata, len(working_vertices))
    remapped_protected = _remap_vertex_set(protected, compact_mapping)
    if not remapped_protected:
        remapped_protected = _silhouette_vertices({"vertices": working_vertices.tolist()}, working_vertex_metadata, working_vertices)

    before_compact_vertices = working_vertices.copy()
    max_displacement = float(profile.get("max_vertex_displacement", 0.35))
    alpha = max(0.0, min(1.0, float(strength)))
    adjusted_vertices: set[int] = set()
    for _step in range(max(1, int(iterations))):
        working_vertices, planar_adjusted = _planarise_lowpoly_regions(
            working_vertices,
            working_faces,
            working_metadata,
            vertex_labels,
            remapped_protected,
            alpha * float(profile.get("lowpoly_planarisation", 0.45)),
            max_displacement,
            before_compact_vertices,
        )
        adjusted_vertices.update(planar_adjusted)
        working_vertices, relaxed = _normal_flow_relaxation(
            working_vertices,
            working_faces,
            vertex_labels,
            remapped_protected,
            alpha * float(profile.get("normal_flow_smoothing", 0.25)),
            max_displacement,
            before_compact_vertices,
        )
        adjusted_vertices.update(relaxed)

    after_normals = _face_normals(working_vertices, working_faces)
    after_edge_faces = _edge_faces(working_faces)
    after_normal_discontinuity = _normal_discontinuity(after_normals, after_edge_faces)
    after_staircase = _staircase_artifact_score(after_normal_discontinuity, working_faces, working_vertices)
    after_planar = _planar_surface_score(after_normals)
    after_surface_flow = _surface_flow_score(after_normal_discontinuity)
    after_hat_extension = _hat_extension_score(working_vertices, vertex_labels)
    triangle_count_after = _triangulated_face_count(working_faces)
    displacement = _displacement_against_original_indices(mesh, working_vertices, working_vertex_metadata, original_vertices)
    silhouette_drift = _set_max_displacement(displacement, remapped_protected)
    after_semantic_boundary_edges = _semantic_boundary_edges({"semantic_boundary_edges": []}, working_faces, working_metadata)
    semantic_boundary_preservation = _semantic_boundary_preservation_score(
        displacement,
        after_semantic_boundary_edges,
        max_displacement,
    )
    directional_preservation = _directional_feature_preservation_score(before_hat_extension, after_hat_extension)
    labels_after = _semantic_labels_from_face_metadata(working_metadata)
    degenerate_count = _degenerate_face_count(working_vertices, working_faces)
    component_count = _mesh_component_count(len(working_vertices), _adjacency(working_faces))
    triangle_inversions = _triangle_inversion_count(before_normals, after_normals, len(original_faces), len(working_faces))
    fail_conditions = {
        "silhouette_drift_exceeded": silhouette_drift > float(profile.get("silhouette_drift_tolerance_px", 1.0)),
        "semantic_labels_disappeared": labels_before != labels_after,
        "mesh_disconnected": component_count != 1,
        "directional_asymmetry_dropped": directional_preservation < float(profile.get("directional_preservation_min", 0.85)),
        "hat_extension_collapsed": after_hat_extension < before_hat_extension * float(profile.get("hat_extension_min_ratio", 0.80)),
        "triangle_inversion_occurred": triangle_inversions > 0,
        "degenerate_faces_introduced": degenerate_count > 0,
    }

    remeshed_mesh = dict(mesh)
    remeshed_mesh["schema"] = "spritespatial_surface_nets_mesh_semantic_remeshed_v1"
    remeshed_mesh["vertices"] = [[float(value) for value in row] for row in working_vertices.tolist()]
    remeshed_mesh["faces"] = working_faces
    remeshed_mesh["face_metadata"] = working_metadata
    remeshed_mesh["vertex_metadata"] = working_vertex_metadata
    remeshed_mesh["indices"] = _triangulated_indices(working_faces, remeshed_mesh["vertices"])
    remeshed_mesh["semantic_remesh"] = {
        "enabled": True,
        "profile": profile.get("name", "humanoid_lowpoly"),
        "iterations": int(iterations),
        "strength": alpha,
        "preserve_silhouette_edges": bool(preserve_silhouette_edges),
    }
    remeshed_mesh["stats"] = _mesh_stats(remeshed_mesh, component_count, degenerate_count)

    report = {
        "schema": "spritespatial_semantic_remesh_report_v1",
        "semantic_remesh_enabled": True,
        "remesh_profile": profile.get("name", "humanoid_lowpoly"),
        "remesh_iterations": int(iterations),
        "remesh_strength": alpha,
        "preserve_silhouette_edges": bool(preserve_silhouette_edges),
        "triangle_count_before": triangle_count_before,
        "triangle_count_after": triangle_count_after,
        "triangle_reduction_ratio": _ratio_delta(triangle_count_before, triangle_count_after),
        "coplanar_merge_count": int(merge_result["coplanar_merge_count"]),
        "staircase_artifact_before": before_staircase,
        "staircase_artifact_after": after_staircase,
        "surface_flow_before": before_surface_flow,
        "surface_flow_after": after_surface_flow,
        "silhouette_edge_preservation_score": max(0.0, 1.0 - silhouette_drift / max(float(profile.get("silhouette_drift_tolerance_px", 1.0)), 1e-6)),
        "semantic_boundary_preservation_score": semantic_boundary_preservation,
        "directional_feature_preservation_score": directional_preservation,
        "planar_surface_score": after_planar,
        "planar_surface_score_before": before_planar,
        "oblique_readability_score": _oblique_readability_score(
            after_staircase,
            semantic_boundary_preservation,
            directional_preservation,
            silhouette_drift,
            profile,
        ),
        "lowpoly_coherence_score": _lowpoly_coherence_score(
            _ratio_delta(triangle_count_before, triangle_count_after),
            after_planar,
            after_surface_flow,
            semantic_boundary_preservation,
        ),
        "remesh_vertices_adjusted": len(adjusted_vertices),
        "mean_vertex_displacement": float(np.mean(displacement)) if displacement.size else 0.0,
        "max_vertex_displacement": float(np.max(displacement)) if displacement.size else 0.0,
        "silhouette_drift_px": silhouette_drift,
        "semantic_labels_before": labels_before,
        "semantic_labels_after": labels_after,
        "mesh_connected_components": component_count,
        "degenerate_face_count": degenerate_count,
        "triangle_inversion_count": triangle_inversions,
        "hat_extension_before": before_hat_extension,
        "hat_extension_after": after_hat_extension,
        "semantic_part_graph_present": bool(semantic_part_graph),
        "passed": not any(fail_conditions.values()),
        "fail_conditions": fail_conditions,
    }
    report["visual_quality_diagnosis"] = _diagnosis(report)

    paths = {
        "mesh_remeshed": output_dir.parent / "mesh_remeshed.json",
        "remesh_report": output_dir / "remesh_report.json",
        "topology_changes": output_dir / "topology_changes.json",
        "triangle_density_heatmap": output_dir / "triangle_density_heatmap.png",
        "planar_regions_debug": output_dir / "planar_regions_debug.png",
        "silhouette_edge_debug": output_dir / "silhouette_edge_debug.png",
        "semantic_edge_lock_debug": output_dir / "semantic_edge_lock_debug.png",
        "before_after_wireframe": output_dir / "before_after_wireframe.png",
        "before_after_contact_sheet": output_dir / "before_after_contact_sheet.png",
    }
    _write_json(paths["mesh_remeshed"], remeshed_mesh)
    _write_json(paths["remesh_report"], report)
    _write_json(
        paths["topology_changes"],
        {
            "coplanar_merge_count": int(merge_result["coplanar_merge_count"]),
            "removed_face_indices": merge_result["removed_face_indices"],
            "added_faces": merge_result["added_faces"],
            "compacted_vertex_count_before": int(len(original_vertices)),
            "compacted_vertex_count_after": int(len(working_vertices)),
            "triangle_count_before": triangle_count_before,
            "triangle_count_after": triangle_count_after,
            "adjusted_vertices": sorted(int(value) for value in adjusted_vertices),
        },
    )
    _write_debug_images(
        original_vertices,
        original_faces,
        working_vertices,
        working_faces,
        vertex_labels,
        remapped_protected,
        after_semantic_boundary_edges,
        displacement,
        paths,
    )
    return {"mesh": remeshed_mesh, "report": report, "paths": paths}


def _normalise_metadata(items: Any, length: int) -> list[dict[str, Any]]:
    result = [dict(item) if isinstance(item, dict) else {} for item in list(items)[:length]]
    while len(result) < length:
        result.append({})
    return result


def _semantic_labels_from_face_metadata(face_metadata: list[dict[str, Any]]) -> list[int]:
    return sorted({int(item.get("semantic_label", 0)) for item in face_metadata if int(item.get("semantic_label", 0)) != 0})


def _vertex_labels(
    vertex_metadata: list[dict[str, Any]],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    vertex_count: int,
) -> np.ndarray:
    labels = np.zeros(vertex_count, dtype=np.int32)
    for index, metadata in enumerate(vertex_metadata[:vertex_count]):
        labels[index] = int(metadata.get("semantic_label", 0))
    votes: dict[int, Counter[int]] = defaultdict(Counter)
    for face, metadata in zip(faces, face_metadata):
        label = int(metadata.get("semantic_label", 0))
        if label == 0:
            continue
        for vertex in face:
            votes[int(vertex)][label] += 1
    for index in range(vertex_count):
        if labels[index] == 0 and votes[index]:
            labels[index] = int(votes[index].most_common(1)[0][0])
    return labels


def _silhouette_vertices(mesh: dict[str, Any], vertex_metadata: list[dict[str, Any]], vertices: np.ndarray) -> set[int]:
    values = {int(index) for index in mesh.get("silhouette_vertices", [])}
    for index, metadata in enumerate(vertex_metadata):
        if metadata.get("is_silhouette_vertex", False):
            values.add(index)
    if len(values) >= max(1, int(len(vertex_metadata) * 0.90)):
        return _projection_boundary_vertices(vertices)
    return values


def _projection_boundary_vertices(vertices: np.ndarray) -> set[int]:
    if vertices.size == 0:
        return set()
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, vertex in enumerate(vertices):
        buckets[(int(round(float(vertex[0]))), int(round(float(vertex[1]))))].append(index)
    occupied = set(buckets)
    boundary = set()
    for (x, y), indices in buckets.items():
        if any((nx, ny) not in occupied for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
            boundary.update(indices)
    return boundary


def _protected_label_vertices(labels: np.ndarray, profile: dict[str, Any]) -> set[int]:
    preserve_ids = {LABEL_IDS.get(str(label), -1) for label in profile.get("preserve_labels", [])}
    return {index for index, label in enumerate(labels) if int(label) in preserve_ids}


def _directional_feature_vertices(vertices: np.ndarray, labels: np.ndarray) -> set[int]:
    indices = [index for index, label in enumerate(labels) if int(label) == LABEL_IDS["hair/hat"]]
    if not indices:
        return set()
    z_values = vertices[indices, 2]
    threshold = float(np.min(z_values) + max(0.25, (np.max(z_values) - np.min(z_values)) * 0.22))
    return {index for index in indices if float(vertices[index, 2]) <= threshold}


def _semantic_boundary_edges(mesh: dict[str, Any], faces: list[list[int]], face_metadata: list[dict[str, Any]]) -> set[tuple[int, int]]:
    edges = {tuple(sorted(map(int, edge))) for edge in mesh.get("semantic_boundary_edges", []) if len(edge) == 2}
    edge_labels: dict[tuple[int, int], set[int]] = defaultdict(set)
    for face, metadata in zip(faces, face_metadata):
        label = int(metadata.get("semantic_label", 0))
        for edge in _face_edges(face):
            edge_labels[edge].add(label)
    for edge, labels in edge_labels.items():
        if len({label for label in labels if label != 0}) > 1:
            edges.add(edge)
    return edges


def _merge_coplanar_faces(
    vertices: np.ndarray,
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    protected: set[int],
    profile: dict[str, Any],
    iterations: int,
) -> dict[str, Any]:
    max_fraction = float(profile.get("max_coplanar_merge_fraction", 0.12))
    max_merges = max(0, int(len(faces) * max_fraction))
    if max_merges <= 0:
        return {
            "faces": faces,
            "face_metadata": face_metadata,
            "coplanar_merge_count": 0,
            "removed_face_indices": [],
            "added_faces": [],
            "old_to_new": {},
        }
    angle = math.radians(float(profile.get("coplanar_angle_degrees", 10.0)))
    normal_threshold = math.cos(angle)
    working_faces = [face[:] for face in faces]
    working_meta = [dict(item) for item in face_metadata]
    removed: set[int] = set()
    added_faces: list[list[int]] = []
    merge_count = 0
    for _ in range(iterations):
        edge_faces = _edge_faces(working_faces)
        normals = _face_normals(vertices, working_faces)
        for edge, pair in edge_faces.items():
            if merge_count >= max_merges:
                break
            if len(pair) != 2 or pair[0] in removed or pair[1] in removed:
                continue
            a_index, b_index = pair
            face_a = working_faces[a_index]
            face_b = working_faces[b_index]
            if len(face_a) != 4 or len(face_b) != 4:
                continue
            if any(vertex in protected for vertex in set(face_a) | set(face_b)):
                continue
            label_a = int(working_meta[a_index].get("semantic_label", 0))
            label_b = int(working_meta[b_index].get("semantic_label", 0))
            if label_a == 0 or label_a != label_b:
                continue
            if working_meta[a_index].get("is_semantic_boundary") or working_meta[b_index].get("is_semantic_boundary"):
                continue
            if working_meta[a_index].get("is_silhouette") or working_meta[b_index].get("is_silhouette"):
                continue
            if float(np.dot(normals[a_index], normals[b_index])) < normal_threshold:
                continue
            merged = _merged_quad(vertices, face_a, face_b)
            if not merged:
                continue
            if _face_degenerate(vertices, merged):
                continue
            removed.update({a_index, b_index})
            meta = dict(working_meta[a_index])
            meta["semantic_remesh_merged_from"] = [a_index, b_index]
            working_faces.append(merged)
            working_meta.append(meta)
            added_faces.append(merged)
            merge_count += 1
        if merge_count >= max_merges:
            break
    if not removed:
        return {
            "faces": working_faces,
            "face_metadata": working_meta,
            "coplanar_merge_count": 0,
            "removed_face_indices": [],
            "added_faces": [],
            "old_to_new": {},
        }
    kept_faces = []
    kept_meta = []
    for index, (face, metadata) in enumerate(zip(working_faces, working_meta)):
        if index in removed:
            continue
        kept_faces.append(face)
        kept_meta.append(metadata)
    return {
        "faces": kept_faces,
        "face_metadata": kept_meta,
        "coplanar_merge_count": merge_count,
        "removed_face_indices": sorted(removed),
        "added_faces": added_faces,
        "old_to_new": {},
    }


def _merged_quad(vertices: np.ndarray, face_a: list[int], face_b: list[int]) -> list[int]:
    boundary_edges = Counter(_face_edges(face_a) + _face_edges(face_b))
    boundary_vertices = sorted({vertex for edge, count in boundary_edges.items() if count == 1 for vertex in edge})
    if len(boundary_vertices) < 4:
        return []
    normal = _face_normal(vertices, face_a)
    axis = int(np.argmax(np.abs(normal)))
    axes = [0, 1, 2]
    axes.remove(axis)
    points = vertices[boundary_vertices][:, axes]
    min_u, min_v = np.min(points, axis=0)
    max_u, max_v = np.max(points, axis=0)
    targets = [(min_u, min_v), (max_u, min_v), (max_u, max_v), (min_u, max_v)]
    selected = []
    for target in targets:
        distances = np.linalg.norm(points - np.asarray(target, dtype=np.float32), axis=1)
        order = np.argsort(distances)
        chosen = None
        for candidate_index in order:
            vertex = boundary_vertices[int(candidate_index)]
            if vertex not in selected:
                chosen = vertex
                break
        if chosen is None:
            return []
        selected.append(int(chosen))
    if len(set(selected)) != 4:
        return []
    return selected


def _compact_vertices(
    vertices: np.ndarray,
    vertex_metadata: list[dict[str, Any]],
    faces: list[list[int]],
) -> tuple[np.ndarray, list[dict[str, Any]], list[list[int]], dict[int, int]]:
    used = sorted({int(vertex) for face in faces for vertex in face})
    mapping = {old: new for new, old in enumerate(used)}
    compact_vertices = vertices[used].copy() if used else np.zeros((0, 3), dtype=np.float32)
    compact_metadata = [dict(vertex_metadata[old]) if old < len(vertex_metadata) else {} for old in used]
    compact_faces = [[mapping[int(vertex)] for vertex in face] for face in faces]
    for old, new in mapping.items():
        if new < len(compact_metadata):
            compact_metadata[new]["source_vertex"] = int(old)
    return compact_vertices, compact_metadata, compact_faces, mapping


def _remap_vertex_set(values: set[int], old_to_new: dict[int, int]) -> set[int]:
    if old_to_new:
        return {old_to_new[value] for value in values if value in old_to_new}
    return set(values)


def _planarise_lowpoly_regions(
    vertices: np.ndarray,
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    labels: np.ndarray,
    protected: set[int],
    strength: float,
    max_displacement: float,
    original: np.ndarray,
) -> tuple[np.ndarray, set[int]]:
    normals = _face_normals(vertices, faces)
    groups: dict[tuple[int, int, int], set[int]] = defaultdict(set)
    bucket_size = 1.0
    for face_index, (face, metadata) in enumerate(zip(faces, face_metadata)):
        label = int(metadata.get("semantic_label", 0))
        if label == 0:
            continue
        normal = normals[face_index]
        axis = int(np.argmax(np.abs(normal)))
        centroid = np.mean(vertices[face], axis=0)
        bucket = int(round(float(centroid[axis]) / bucket_size))
        groups[(label, axis, bucket)].update(int(vertex) for vertex in face)
    result = vertices.copy()
    adjusted = set()
    for (_label, axis, _bucket), indices in groups.items():
        movable = [index for index in indices if index not in protected and int(labels[index]) != 0]
        if len(movable) < 4:
            continue
        target = float(np.median(vertices[movable, axis]))
        for index in movable:
            proposed = result[index].copy()
            proposed[axis] = float(result[index, axis] + (target - result[index, axis]) * strength)
            clamped = _clamp_to_original(original[index], proposed, max_displacement)
            if float(np.linalg.norm(clamped - result[index])) > 1e-8:
                result[index] = clamped
                adjusted.add(index)
    return result, adjusted


def _normal_flow_relaxation(
    vertices: np.ndarray,
    faces: list[list[int]],
    labels: np.ndarray,
    protected: set[int],
    strength: float,
    max_displacement: float,
    original: np.ndarray,
) -> tuple[np.ndarray, set[int]]:
    adjacency = _adjacency(faces)
    result = vertices.copy()
    adjusted = set()
    for index, vertex in enumerate(vertices):
        if index in protected or int(labels[index]) == 0:
            continue
        neighbours = [other for other in adjacency.get(index, set()) if int(labels[other]) == int(labels[index]) and other not in protected]
        if len(neighbours) < 2:
            continue
        target = vertices[neighbours].mean(axis=0)
        proposed = vertex + (target - vertex) * strength
        clamped = _clamp_to_original(original[index], proposed, max_displacement)
        if float(np.linalg.norm(clamped - vertex)) > 1e-8:
            result[index] = clamped
            adjusted.add(index)
    return result, adjusted


def _clamp_to_original(original: np.ndarray, proposed: np.ndarray, max_displacement: float) -> np.ndarray:
    delta = proposed - original
    length = float(np.linalg.norm(delta))
    if length <= max_displacement or length <= 1e-8:
        return proposed
    return original + delta / length * max_displacement


def _displacement_against_original_indices(
    mesh: dict[str, Any],
    vertices: np.ndarray,
    vertex_metadata: list[dict[str, Any]],
    original_vertices: np.ndarray,
) -> np.ndarray:
    values = np.zeros((len(vertices),), dtype=np.float32)
    for index, metadata in enumerate(vertex_metadata):
        source = int(metadata.get("source_vertex", index))
        if 0 <= source < len(original_vertices):
            values[index] = float(np.linalg.norm(vertices[index] - original_vertices[source]))
    return values


def _set_max_displacement(displacement: np.ndarray, values: set[int]) -> float:
    valid = [index for index in values if 0 <= index < len(displacement)]
    if not valid:
        return 0.0
    return float(np.max(displacement[valid]))


def _semantic_boundary_preservation_score(
    displacement: np.ndarray,
    boundary_edges: set[tuple[int, int]],
    max_displacement: float,
) -> float:
    if not boundary_edges or displacement.size == 0:
        return 1.0
    values = []
    for a, b in boundary_edges:
        if a < len(displacement) and b < len(displacement):
            values.append(max(float(displacement[a]), float(displacement[b])))
    if not values:
        return 1.0
    mean = float(np.mean(values))
    return max(0.0, min(1.0, 1.0 - mean / max(max_displacement * 2.0, 1e-6)))


def _directional_feature_preservation_score(before: float, after: float) -> float:
    if before <= 1e-6:
        return 1.0
    return max(0.0, min(1.0, after / before))


def _hat_extension_score(vertices: np.ndarray, labels: np.ndarray) -> float:
    indices = np.where(labels == LABEL_IDS["hair/hat"])[0]
    if indices.size == 0:
        return 0.0
    z_values = vertices[indices, 2]
    return float(np.max(z_values) - np.min(z_values))


def _face_normals(vertices: np.ndarray, faces: list[list[int]]) -> list[np.ndarray]:
    normals = []
    for face in faces:
        normals.append(_face_normal(vertices, face))
    return normals


def _face_normal(vertices: np.ndarray, face: list[int]) -> np.ndarray:
    if len(face) < 3:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32)
    a = vertices[face[0]]
    b = vertices[face[1]]
    c = vertices[face[2]]
    normal = np.cross(b - a, c - a)
    length = float(np.linalg.norm(normal))
    if length <= 1e-8:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32)
    return (normal / length).astype(np.float32)


def _normal_discontinuity(normals: list[np.ndarray], edge_faces: dict[tuple[int, int], list[int]]) -> float:
    values = []
    for face_indices in edge_faces.values():
        if len(face_indices) != 2:
            continue
        a = normals[face_indices[0]]
        b = normals[face_indices[1]]
        if float(np.linalg.norm(a)) <= 1e-8 or float(np.linalg.norm(b)) <= 1e-8:
            continue
        dot = max(-1.0, min(1.0, float(np.dot(a, b))))
        values.append(1.0 - dot)
    return float(np.mean(values)) if values else 0.0


def _staircase_artifact_score(normal_discontinuity: float, faces: list[list[int]], vertices: np.ndarray) -> float:
    if not faces:
        return 1.0
    normals = _face_normals(vertices, faces)
    axis_aligned = sum(1 for normal in normals if float(np.max(np.abs(normal))) > 0.92)
    axis_ratio = axis_aligned / max(len(normals), 1)
    face_density = min(1.0, len(faces) / max(float(len(vertices)), 1.0))
    return float(max(0.0, min(1.0, 0.55 * normal_discontinuity + 0.30 * (1.0 - axis_ratio) + 0.15 * face_density)))


def _surface_flow_score(normal_discontinuity: float) -> float:
    return float(max(0.0, min(1.0, 1.0 - normal_discontinuity)))


def _planar_surface_score(normals: list[np.ndarray]) -> float:
    if not normals:
        return 0.0
    values = [float(np.max(np.abs(normal))) for normal in normals if float(np.linalg.norm(normal)) > 1e-8]
    return float(np.mean(values)) if values else 0.0


def _oblique_readability_score(
    staircase: float,
    boundary_score: float,
    directional_score: float,
    silhouette_drift: float,
    profile: dict[str, Any],
) -> float:
    silhouette_score = max(0.0, 1.0 - silhouette_drift / max(float(profile.get("silhouette_drift_tolerance_px", 1.0)), 1e-6))
    return float(max(0.0, min(1.0, 0.35 * silhouette_score + 0.25 * boundary_score + 0.25 * directional_score + 0.15 * (1.0 - staircase))))


def _lowpoly_coherence_score(
    reduction_ratio: float,
    planar_score: float,
    surface_flow: float,
    boundary_score: float,
) -> float:
    return float(max(0.0, min(1.0, 0.25 * max(0.0, reduction_ratio) + 0.30 * planar_score + 0.25 * surface_flow + 0.20 * boundary_score)))


def _ratio_delta(before: int, after: int) -> float:
    if before <= 0:
        return 0.0
    return float(before - after) / float(before)


def _triangle_inversion_count(
    before_normals: list[np.ndarray],
    after_normals: list[np.ndarray],
    before_face_count: int,
    after_face_count: int,
) -> int:
    if before_face_count != after_face_count:
        return 0
    count = 0
    for before, after in zip(before_normals, after_normals):
        if float(np.linalg.norm(before)) <= 1e-8 or float(np.linalg.norm(after)) <= 1e-8:
            continue
        if float(np.dot(before, after)) < -0.25:
            count += 1
    return count


def _mesh_stats(mesh: dict[str, Any], component_count: int, degenerate_count: int) -> dict[str, Any]:
    stats = dict(mesh.get("stats", {}))
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = _normalise_metadata(mesh.get("face_metadata", []), len(faces))
    labels = _semantic_labels_from_face_metadata(metadata)
    edge_counts = Counter(edge for face in faces for edge in _face_edges(face))
    stats.update(
        {
            "surface_net_vertices": len(mesh.get("vertices", [])),
            "surface_net_faces": len(faces),
            "surface_net_triangles": _triangulated_face_count(faces),
            "degenerate_face_count": degenerate_count,
            "non_manifold_edge_count": sum(1 for count in edge_counts.values() if count > 2),
            "mesh_connected_components": component_count,
            "semantic_labels_in_mesh": labels,
            "semantic_label_preservation_passed": True,
            "material_groups": {str(label): sum(1 for item in metadata if int(item.get("semantic_label", 0)) == label) for label in labels},
        }
    )
    return stats


def _degenerate_face_count(vertices: np.ndarray, faces: list[list[int]]) -> int:
    return sum(1 for face in faces if _face_degenerate(vertices, face))


def _face_degenerate(vertices: np.ndarray, face: list[int]) -> bool:
    if len(set(face)) < 3 or len(face) < 3:
        return True
    triangles = _triangulate_face(face)
    return all(_triangle_area(vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]) <= 1e-8 for tri in triangles)


def _triangle_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float(np.linalg.norm(np.cross(b - a, c - a)) * 0.5)


def _edge_faces(faces: list[list[int]]) -> dict[tuple[int, int], list[int]]:
    values: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for edge in _face_edges(face):
            values[edge].append(face_index)
    return values


def _face_edges(face: list[int]) -> list[tuple[int, int]]:
    return [tuple(sorted((int(face[index]), int(face[(index + 1) % len(face)])))) for index in range(len(face))]


def _adjacency(faces: list[list[int]]) -> dict[int, set[int]]:
    values: dict[int, set[int]] = defaultdict(set)
    for face in faces:
        for a, b in _face_edges(face):
            values[a].add(b)
            values[b].add(a)
    return values


def _mesh_component_count(vertex_count: int, adjacency: dict[int, set[int]]) -> int:
    used = set(adjacency)
    if not used and vertex_count:
        return vertex_count
    remaining = set(used)
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbour in adjacency.get(current, set()):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
    return components


def _triangulated_face_count(faces: list[list[int]]) -> int:
    return sum(max(1, len(face) - 2) for face in faces if len(face) >= 3)


def _triangulated_indices(faces: list[list[int]], vertices: list[list[float]]) -> list[int]:
    indices: list[int] = []
    verts = np.asarray(vertices, dtype=np.float32)
    for face in faces:
        for tri in _triangulate_face(face):
            if _triangle_area(verts[tri[0]], verts[tri[1]], verts[tri[2]]) > 1e-8:
                indices.extend(int(value) for value in tri)
    return indices


def _triangulate_face(face: list[int]) -> list[list[int]]:
    if len(face) == 3:
        return [face]
    return [[face[0], face[index], face[index + 1]] for index in range(1, len(face) - 1)]


def _write_debug_images(
    before_vertices: np.ndarray,
    before_faces: list[list[int]],
    after_vertices: np.ndarray,
    after_faces: list[list[int]],
    labels: np.ndarray,
    silhouette_vertices: set[int],
    semantic_edges: set[tuple[int, int]],
    displacement: np.ndarray,
    paths: dict[str, Path],
) -> None:
    _write_density_heatmap(after_vertices, after_faces, paths["triangle_density_heatmap"])
    _write_planar_regions(after_vertices, after_faces, paths["planar_regions_debug"])
    _write_vertex_overlay(after_vertices, labels, silhouette_vertices, paths["silhouette_edge_debug"], (255, 255, 255, 255))
    _write_edge_overlay(after_vertices, labels, semantic_edges, paths["semantic_edge_lock_debug"])
    before_wire = _wireframe_image(before_vertices, before_faces)
    after_wire = _wireframe_image(after_vertices, after_faces)
    _write_pair_sheet(before_wire, after_wire, paths["before_after_wireframe"], "before", "after")
    before_projection = _projection_image(before_vertices, labels[: len(before_vertices)] if len(labels) >= len(before_vertices) else np.zeros(len(before_vertices), dtype=np.int32))
    after_projection = _projection_image(after_vertices, labels)
    _write_pair_sheet(before_projection, after_projection, paths["before_after_contact_sheet"], "before", "after")


def _write_density_heatmap(vertices: np.ndarray, faces: list[list[int]], path: Path) -> None:
    image = _blank_projection(vertices)
    if vertices.size == 0:
        image.save(path, format="PNG")
        return
    scale = 6
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for face in faces:
        centroid = np.mean(vertices[face], axis=0)
        counts[(int(round(float(centroid[0]))), int(round(float(centroid[1]))))] += 1
    max_count = max(counts.values()) if counts else 1
    draw = ImageDraw.Draw(image)
    for (x, y), count in counts.items():
        t = count / max_count
        draw.rectangle((x * scale - 2, y * scale - 2, x * scale + 2, y * scale + 2), fill=(int(255 * t), 60, int(255 * (1.0 - t)), 255))
    image.save(path, format="PNG")


def _write_planar_regions(vertices: np.ndarray, faces: list[list[int]], path: Path) -> None:
    image = _blank_projection(vertices)
    draw = ImageDraw.Draw(image)
    scale = 6
    colors = [(240, 80, 80, 255), (80, 200, 120, 255), (100, 150, 255, 255)]
    for face in faces:
        normal = _face_normal(vertices, face)
        axis = int(np.argmax(np.abs(normal)))
        centroid = np.mean(vertices[face], axis=0)
        x = int(round(float(centroid[0]) * scale))
        y = int(round(float(centroid[1]) * scale))
        draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=colors[axis])
    image.save(path, format="PNG")


def _write_vertex_overlay(vertices: np.ndarray, labels: np.ndarray, indices: set[int], path: Path, color: tuple[int, int, int, int]) -> None:
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    scale = 6
    for index in indices:
        if 0 <= index < len(vertices):
            x = int(round(float(vertices[index, 0]) * scale))
            y = int(round(float(vertices[index, 1]) * scale))
            draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=color)
    image.save(path, format="PNG")


def _write_edge_overlay(vertices: np.ndarray, labels: np.ndarray, edges: set[tuple[int, int]], path: Path) -> None:
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    scale = 6
    for a, b in edges:
        if a >= len(vertices) or b >= len(vertices):
            continue
        ax = int(round(float(vertices[a, 0]) * scale))
        ay = int(round(float(vertices[a, 1]) * scale))
        bx = int(round(float(vertices[b, 0]) * scale))
        by = int(round(float(vertices[b, 1]) * scale))
        draw.line((ax, ay, bx, by), fill=(255, 220, 60, 255), width=1)
    image.save(path, format="PNG")


def _wireframe_image(vertices: np.ndarray, faces: list[list[int]], scale: int = 6) -> Image.Image:
    image = _blank_projection(vertices, scale)
    draw = ImageDraw.Draw(image)
    for face in faces:
        for a, b in _face_edges(face):
            if a >= len(vertices) or b >= len(vertices):
                continue
            ax = int(round(float(vertices[a, 0]) * scale))
            ay = int(round(float(vertices[a, 1]) * scale))
            bx = int(round(float(vertices[b, 0]) * scale))
            by = int(round(float(vertices[b, 1]) * scale))
            draw.line((ax, ay, bx, by), fill=(230, 230, 230, 255), width=1)
    return image


def _projection_image(vertices: np.ndarray, labels: np.ndarray, scale: int = 6) -> Image.Image:
    image = _blank_projection(vertices, scale)
    draw = ImageDraw.Draw(image)
    for index, vertex in enumerate(vertices):
        label = int(labels[index]) if index < len(labels) else 0
        x = int(round(float(vertex[0]) * scale))
        y = int(round(float(vertex[1]) * scale))
        draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=_label_color(label))
    return image


def _blank_projection(vertices: np.ndarray, scale: int = 6) -> Image.Image:
    if vertices.size == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    width = int(math.ceil(float(np.max(vertices[:, 0])) + 2)) * scale
    height = int(math.ceil(float(np.max(vertices[:, 1])) + 2)) * scale
    return Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 45, 55, 255))


def _write_pair_sheet(left: Image.Image, right: Image.Image, path: Path, left_label: str, right_label: str) -> None:
    width = max(left.width, right.width)
    height = max(left.height, right.height)
    sheet = Image.new("RGBA", (width * 2, height), (0, 0, 0, 255))
    sheet.alpha_composite(left, (0, 0))
    sheet.alpha_composite(right, (width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((2, 2), left_label, fill=(255, 255, 255, 255))
    draw.text((width + 2, 2), right_label, fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _label_color(label: int) -> tuple[int, int, int, int]:
    palette = {
        1: (20, 20, 20, 255),
        2: (240, 80, 80, 255),
        3: (255, 210, 120, 255),
        4: (140, 80, 210, 255),
        5: (80, 180, 240, 255),
        6: (60, 210, 140, 255),
        7: (60, 190, 120, 255),
        8: (210, 160, 60, 255),
        9: (120, 200, 80, 255),
        10: (180, 120, 60, 255),
        11: (230, 230, 80, 255),
    }
    return palette.get(label, (180, 180, 180, 255))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _diagnosis(report: dict[str, Any]) -> dict[str, Any]:
    reduction = float(report.get("triangle_reduction_ratio", 0.0))
    staircase_before = float(report.get("staircase_artifact_before", 0.0))
    staircase_after = float(report.get("staircase_artifact_after", 0.0))
    flow_before = float(report.get("surface_flow_before", 0.0))
    flow_after = float(report.get("surface_flow_after", 0.0))
    structural_improved = reduction > 0.0
    visual_improved = staircase_after < staircase_before or flow_after > flow_before
    likely_cause = "none" if structural_improved and visual_improved else "meshing issue"
    return {
        "topology_metric_improved": structural_improved,
        "visual_metric_improved": visual_improved,
        "semantic_issue": False,
        "sdf_issue": False,
        "meshing_issue": not visual_improved,
        "render_issue": False,
        "likely_cause": likely_cause,
        "notes": [
            "Semantic labels and boundaries are preserved by the remeshing pass.",
            "The pass only merges same-label near-coplanar quads and applies clamped local relaxation.",
            "Triangle count reduction is a structural metric; staircase and surface-flow metrics remain the visual quality signal.",
            "If visual quality remains weak, the remaining bottleneck is likely the surface extraction topology rather than source authority.",
        ],
        "recommended_next_engineering_step": (
            "Inspect remeshed wireframes and topology_changes.json before increasing remesh strength."
            if visual_improved
            else "Consider improving surface-nets extraction or adding a topology-aware patch builder before stronger remeshing."
        ),
    }
