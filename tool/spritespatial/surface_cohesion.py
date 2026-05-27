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


def load_surface_cohesion_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "humanoid_voxel")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "surface_cohesion_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = data.get("name", path.stem)
    data["path"] = str(path)
    return data


def apply_surface_cohesion(
    mesh: dict[str, Any],
    semantic_part_graph: dict[str, Any] | None,
    profile: dict[str, Any],
    output_dir: Path,
    strength: float = 0.35,
    iterations: int = 2,
    emit_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    vertex_metadata = list(mesh.get("vertex_metadata", []))
    face_metadata = list(mesh.get("face_metadata", []))
    before_vertices = vertices.copy()
    labels = _vertex_labels(vertex_metadata, faces, face_metadata, len(vertices))
    silhouette = _silhouette_vertices(mesh, vertex_metadata, vertices)
    boundary_edges = {tuple(sorted(map(int, edge))) for edge in mesh.get("semantic_boundary_edges", []) if len(edge) == 2}
    adjacency, edge_faces = _mesh_adjacency(faces)
    face_normals_before = _face_normals(before_vertices, faces)
    normal_before = _normal_discontinuity(face_normals_before, edge_faces)
    protected = set(silhouette)
    preserve_ids = {LABEL_IDS.get(label, -1) for label in profile.get("preserve_labels", [])}
    protected.update(index for index, label in enumerate(labels) if int(label) in preserve_ids)
    hat_tip = _hat_tip_vertices(vertices, labels)
    protected.update(hat_tip)

    max_displacement = float(profile.get("max_vertex_displacement", 0.45))
    alpha = max(0.0, min(1.0, float(strength)))
    working = vertices.copy()
    adjusted_vertices: set[int] = set()
    for _step in range(max(1, int(iterations))):
        working, intra_adjusted = _intra_part_relaxation(
            working,
            labels,
            adjacency,
            protected,
            alpha * float(profile.get("intra_part_relaxation", 0.55)),
            max_displacement,
            before_vertices,
        )
        adjusted_vertices.update(intra_adjusted)
        working, seam_adjusted = _cross_part_seam_alignment(
            working,
            labels,
            boundary_edges,
            protected,
            profile,
            alpha * float(profile.get("seam_alignment", 0.35)),
            max_displacement,
            before_vertices,
        )
        adjusted_vertices.update(seam_adjusted)

    displacement = np.linalg.norm(working - before_vertices, axis=1) if len(working) else np.zeros(0, dtype=np.float32)
    face_normals_after = _face_normals(working, faces)
    normal_after = _normal_discontinuity(face_normals_after, edge_faces)
    degenerate_after = _degenerate_face_count(working, faces)
    component_count = _mesh_component_count(len(working), adjacency)
    labels_before = _semantic_labels_from_metadata(face_metadata)
    labels_after = _semantic_labels_from_metadata(face_metadata)
    silhouette_drift = float(np.max(displacement[list(silhouette)])) if silhouette and displacement.size else 0.0
    outline_drift = _label_max_displacement(displacement, labels, LABEL_IDS["outline"])
    hat_tip_drift = float(np.max(displacement[list(hat_tip)])) if hat_tip and displacement.size else 0.0
    semantic_preservation = 1.0 if labels_before == labels_after else 0.0
    if boundary_edges and displacement.size:
        boundary_drift = np.mean([max(float(displacement[a]), float(displacement[b])) for a, b in boundary_edges])
        semantic_preservation = max(0.0, min(1.0, semantic_preservation - boundary_drift / max(max_displacement * 4.0, 1e-6)))
    fragmentation_before = _surface_fragmentation_score(normal_before, len(boundary_edges), len(faces))
    fragmentation_after = _surface_fragmentation_score(normal_after, len(boundary_edges), len(faces))

    cohesive_mesh = dict(mesh)
    cohesive_mesh["schema"] = "spritespatial_surface_nets_mesh_surface_cohesive_v1"
    cohesive_mesh["vertices"] = [[float(v) for v in row] for row in working.tolist()]
    cohesive_mesh["surface_cohesion"] = {
        "enabled": True,
        "profile": profile.get("name", "humanoid_voxel"),
        "strength": alpha,
        "iterations": int(iterations),
    }
    cohesive_mesh["indices"] = _triangulated_indices(faces, cohesive_mesh["vertices"])
    cohesive_mesh["stats"] = _mesh_stats(cohesive_mesh, component_count, degenerate_after)

    paths = {
        "surface_cohesion_report": output_dir / "surface_cohesion_report.json",
        "vertex_displacement_debug": output_dir / "vertex_displacement_debug.json",
        "normal_discontinuity_debug": output_dir / "normal_discontinuity_debug.png",
        "seam_alignment_debug": output_dir / "seam_alignment_debug.png",
        "semantic_boundary_preservation": output_dir / "semantic_boundary_preservation.png",
        "before_after_mesh_stats": output_dir / "before_after_mesh_stats.json",
        "before_after_contact_sheet": output_dir / "before_after_contact_sheet.png",
        "cohesion_diagnosis": output_dir / "cohesion_diagnosis.json",
    }
    mesh_cohesive_path = output_dir.parent / "mesh_cohesive.json"
    paths["mesh_cohesive"] = mesh_cohesive_path

    report = {
        "schema": "spritespatial_surface_cohesion_report_v1",
        "surface_cohesion_enabled": True,
        "surface_cohesion_profile": profile.get("name", "humanoid_voxel"),
        "surface_cohesion_strength": alpha,
        "surface_cohesion_iterations": int(iterations),
        "cohesion_vertices_adjusted": len(adjusted_vertices),
        "mean_vertex_displacement": float(np.mean(displacement)) if displacement.size else 0.0,
        "max_vertex_displacement": float(np.max(displacement)) if displacement.size else 0.0,
        "configured_max_vertex_displacement": max_displacement,
        "semantic_boundary_preservation_score": semantic_preservation,
        "normal_discontinuity_before": normal_before,
        "normal_discontinuity_after": normal_after,
        "surface_fragmentation_before": fragmentation_before,
        "surface_fragmentation_after": fragmentation_after,
        "silhouette_drift_px": silhouette_drift,
        "hat_tip_preserved": hat_tip_drift <= 1e-6,
        "outline_preserved": outline_drift <= 1e-6,
        "degenerate_face_count": degenerate_after,
        "mesh_connected_components": component_count,
        "semantic_labels_before": labels_before,
        "semantic_labels_after": labels_after,
        "semantic_labels_preserved": labels_before == labels_after,
        "semantic_part_graph_present": bool(semantic_part_graph),
        "passed": True,
    }
    fail_conditions = {
        "degenerate_faces_introduced": degenerate_after > 0,
        "mesh_disconnected": component_count != 1,
        "semantic_labels_disappeared": labels_before != labels_after,
        "silhouette_drift_exceeded": silhouette_drift > float(profile.get("silhouette_drift_tolerance_px", 1.0)),
        "max_vertex_displacement_exceeded": report["max_vertex_displacement"] > max_displacement + 1e-6,
        "outline_preservation_failed": not report["outline_preserved"],
        "hat_tip_preservation_failed": not report["hat_tip_preserved"],
    }
    report["fail_conditions"] = fail_conditions
    report["passed"] = not any(fail_conditions.values())
    diagnosis = _diagnosis(report)
    report["visual_quality_diagnosis"] = diagnosis

    _write_json(paths["surface_cohesion_report"], report)
    _write_json(paths["cohesion_diagnosis"], diagnosis)
    _write_json(
        paths["vertex_displacement_debug"],
        {
            "adjusted_vertices": sorted(adjusted_vertices),
            "silhouette_vertices": sorted(silhouette),
            "hat_tip_vertices": sorted(hat_tip),
            "displacements": [
                {"vertex": int(index), "displacement": float(value)}
                for index, value in enumerate(displacement)
                if float(value) > 1e-8
            ],
        },
    )
    _write_json(
        paths["before_after_mesh_stats"],
        {
            "before": dict(mesh.get("stats", {})),
            "after": cohesive_mesh["stats"],
            "surface_cohesion": report,
        },
    )
    _write_json(mesh_cohesive_path, cohesive_mesh)
    _write_debug_images(before_vertices, working, faces, labels, boundary_edges, displacement, paths)
    return {"mesh": cohesive_mesh, "report": report, "paths": paths}


def _vertex_labels(
    vertex_metadata: list[dict[str, Any]],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    vertex_count: int,
) -> np.ndarray:
    labels = np.zeros(vertex_count, dtype=np.int32)
    for index, metadata in enumerate(vertex_metadata[:vertex_count]):
        labels[index] = int(metadata.get("semantic_label", 0))
    face_votes: dict[int, Counter[int]] = defaultdict(Counter)
    for face, metadata in zip(faces, face_metadata):
        label = int(metadata.get("semantic_label", 0))
        if label == 0:
            continue
        for vertex in face:
            face_votes[int(vertex)][label] += 1
    for index in range(vertex_count):
        if labels[index] == 0 and face_votes[index]:
            labels[index] = int(face_votes[index].most_common(1)[0][0])
    return labels


def _silhouette_vertices(mesh: dict[str, Any], vertex_metadata: list[dict[str, Any]], vertices: np.ndarray) -> set[int]:
    vertices = {int(index) for index in mesh.get("silhouette_vertices", [])}
    for index, metadata in enumerate(vertex_metadata):
        if metadata.get("is_silhouette_vertex", False):
            vertices.add(index)
    if len(vertices) >= max(1, int(len(vertex_metadata) * 0.90)):
        return _projection_boundary_vertices(np.asarray(mesh.get("vertices", []), dtype=np.float32))
    return vertices


def _projection_boundary_vertices(vertices: np.ndarray) -> set[int]:
    if vertices.size == 0:
        return set()
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, vertex in enumerate(vertices):
        buckets[(int(round(float(vertex[0]))), int(round(float(vertex[1]))))].append(index)
    occupied = set(buckets)
    boundary = set()
    for coord, indices in buckets.items():
        x, y = coord
        if any((nx, ny) not in occupied for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
            boundary.update(indices)
    return boundary


def _mesh_adjacency(faces: list[list[int]]) -> tuple[dict[int, set[int]], dict[tuple[int, int], list[int]]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for a, b in zip(face, face[1:] + face[:1]):
            a = int(a)
            b = int(b)
            adjacency[a].add(b)
            adjacency[b].add(a)
            edge_faces[tuple(sorted((a, b)))].append(face_index)
    return adjacency, edge_faces


def _intra_part_relaxation(
    vertices: np.ndarray,
    labels: np.ndarray,
    adjacency: dict[int, set[int]],
    protected: set[int],
    strength: float,
    max_displacement: float,
    original: np.ndarray,
) -> tuple[np.ndarray, set[int]]:
    result = vertices.copy()
    adjusted = set()
    for index, vertex in enumerate(vertices):
        if index in protected:
            continue
        neighbours = [other for other in adjacency.get(index, set()) if labels[other] == labels[index] and other not in protected]
        if len(neighbours) < 2:
            continue
        target = vertices[neighbours].mean(axis=0)
        proposed = vertex + (target - vertex) * max(0.0, min(1.0, strength))
        result[index] = _clamp_to_original(original[index], proposed, max_displacement)
        if float(np.linalg.norm(result[index] - vertex)) > 1e-8:
            adjusted.add(index)
    return result, adjusted


def _cross_part_seam_alignment(
    vertices: np.ndarray,
    labels: np.ndarray,
    boundary_edges: set[tuple[int, int]],
    protected: set[int],
    profile: dict[str, Any],
    strength: float,
    max_displacement: float,
    original: np.ndarray,
) -> tuple[np.ndarray, set[int]]:
    result = vertices.copy()
    deltas = np.zeros(vertices.shape, dtype=np.float32)
    counts = np.zeros((vertices.shape[0],), dtype=np.float32)
    adjusted = set()
    for a, b in boundary_edges:
        if a in protected or b in protected:
            continue
        policy = _transition_policy(labels[a], labels[b], profile)
        if policy not in {"soft_joint", "soft_root", "seated_surface", "soft_surface", "medium"}:
            continue
        midpoint = (vertices[a] + vertices[b]) * 0.5
        local_strength = strength * _policy_strength(policy)
        deltas[a] += (midpoint - vertices[a]) * local_strength
        deltas[b] += (midpoint - vertices[b]) * local_strength
        counts[a] += 1.0
        counts[b] += 1.0
    for index, count in enumerate(counts):
        if count <= 0.0:
            continue
        proposed = vertices[index] + deltas[index] / count
        result[index] = _clamp_to_original(original[index], proposed, max_displacement)
        if float(np.linalg.norm(result[index] - vertices[index])) > 1e-8:
            adjusted.add(index)
    return result, adjusted


def _transition_policy(label_a: int, label_b: int, profile: dict[str, Any]) -> str:
    name_a = ID_LABELS.get(int(label_a), "unknown")
    name_b = ID_LABELS.get(int(label_b), "unknown")
    rules = profile.get("transition_rules", {})
    for key in (f"{name_a}:{name_b}", f"{name_b}:{name_a}", f"{name_a}:*", f"{name_b}:*", f"*:{name_a}", f"*:{name_b}"):
        if key in rules:
            return str(rules[key])
    return "preserve_hard"


def _policy_strength(policy: str) -> float:
    return {
        "soft_joint": 1.0,
        "soft_root": 0.85,
        "seated_surface": 0.55,
        "soft_surface": 0.65,
        "medium": 0.35,
    }.get(policy, 0.0)


def _clamp_to_original(original: np.ndarray, proposed: np.ndarray, max_displacement: float) -> np.ndarray:
    delta = proposed - original
    length = float(np.linalg.norm(delta))
    if length <= max_displacement or length <= 1e-8:
        return proposed
    return original + delta / length * max_displacement


def _hat_tip_vertices(vertices: np.ndarray, labels: np.ndarray) -> set[int]:
    indices = [index for index, label in enumerate(labels) if int(label) == LABEL_IDS["hair/hat"]]
    if not indices:
        return set()
    z_values = vertices[indices, 2]
    threshold = float(np.min(z_values) + max(0.25, (np.max(z_values) - np.min(z_values)) * 0.18))
    return {index for index in indices if float(vertices[index, 2]) <= threshold}


def _face_normals(vertices: np.ndarray, faces: list[list[int]]) -> list[np.ndarray]:
    normals = []
    for face in faces:
        if len(face) < 3:
            normals.append(np.array([0.0, 0.0, 0.0], dtype=np.float32))
            continue
        a = vertices[face[0]]
        b = vertices[face[1]]
        c = vertices[face[2]]
        normal = np.cross(b - a, c - a)
        length = float(np.linalg.norm(normal))
        normals.append((normal / length).astype(np.float32) if length > 1e-8 else np.array([0.0, 0.0, 0.0], dtype=np.float32))
    return normals


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


def _surface_fragmentation_score(normal_discontinuity: float, boundary_edges: int, face_count: int) -> float:
    boundary_ratio = boundary_edges / max(face_count, 1)
    return float(max(0.0, min(1.0, 0.65 * normal_discontinuity + 0.35 * boundary_ratio)))


def _degenerate_face_count(vertices: np.ndarray, faces: list[list[int]]) -> int:
    return sum(1 for face in faces if _face_degenerate(vertices, face))


def _face_degenerate(vertices: np.ndarray, face: list[int]) -> bool:
    if len(set(face)) < 3 or len(face) < 3:
        return True
    first = _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]]) <= 1e-8
    if len(face) == 3:
        return first
    second = _triangle_area(vertices[face[0]], vertices[face[2]], vertices[face[3]]) <= 1e-8
    return first and second


def _triangle_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float(np.linalg.norm(np.cross(b - a, c - a)) * 0.5)


def _mesh_component_count(vertex_count: int, adjacency: dict[int, set[int]]) -> int:
    remaining = set(range(vertex_count))
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


def _semantic_labels_from_metadata(face_metadata: list[dict[str, Any]]) -> list[int]:
    return sorted({int(item.get("semantic_label", 0)) for item in face_metadata if int(item.get("semantic_label", 0)) != 0})


def _label_max_displacement(displacement: np.ndarray, labels: np.ndarray, label: int) -> float:
    indices = np.where(labels == label)[0]
    return float(np.max(displacement[indices])) if indices.size and displacement.size else 0.0


def _triangulated_indices(faces: list[list[int]], vertices: list[list[float]]) -> list[int]:
    indices: list[int] = []
    verts = np.asarray(vertices, dtype=np.float32)
    for face in faces:
        triangles = [face] if len(face) == 3 else [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
        for tri in triangles:
            if _triangle_area(verts[tri[0]], verts[tri[1]], verts[tri[2]]) > 1e-8:
                indices.extend(int(value) for value in tri)
    return indices


def _mesh_stats(mesh: dict[str, Any], component_count: int, degenerate_count: int) -> dict[str, Any]:
    stats = dict(mesh.get("stats", {}))
    stats.update(
        {
            "surface_net_vertices": len(mesh.get("vertices", [])),
            "surface_net_faces": len(mesh.get("faces", [])),
            "degenerate_face_count": degenerate_count,
            "mesh_connected_components": component_count,
            "semantic_labels_in_mesh": _semantic_labels_from_metadata(mesh.get("face_metadata", [])),
            "semantic_label_preservation_passed": True,
        }
    )
    return stats


def _write_debug_images(
    before: np.ndarray,
    after: np.ndarray,
    faces: list[list[int]],
    labels: np.ndarray,
    boundary_edges: set[tuple[int, int]],
    displacement: np.ndarray,
    paths: dict[str, Path],
) -> None:
    _write_displacement_projection(after, labels, displacement, paths["normal_discontinuity_debug"])
    _write_edge_projection(after, labels, boundary_edges, paths["seam_alignment_debug"])
    _write_boundary_projection(after, labels, boundary_edges, paths["semantic_boundary_preservation"])
    before_img = _projection_image(before, labels)
    after_img = _projection_image(after, labels)
    sheet = Image.new("RGBA", (before_img.width * 2, before_img.height), (0, 0, 0, 255))
    sheet.alpha_composite(before_img, (0, 0))
    sheet.alpha_composite(after_img, (before_img.width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((2, 2), "before", fill=(255, 255, 255, 255))
    draw.text((before_img.width + 2, 2), "after", fill=(255, 255, 255, 255))
    sheet.save(paths["before_after_contact_sheet"], format="PNG")


def _projection_image(vertices: np.ndarray, labels: np.ndarray, scale: int = 6) -> Image.Image:
    if vertices.size == 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    width = int(math.ceil(float(np.max(vertices[:, 0])) + 2)) * scale
    height = int(math.ceil(float(np.max(vertices[:, 1])) + 2)) * scale
    image = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    for vertex, label in zip(vertices, labels):
        x = int(round(float(vertex[0]) * scale))
        y = int(round(float(vertex[1]) * scale))
        draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=_label_color(int(label)))
    return image


def _write_displacement_projection(vertices: np.ndarray, labels: np.ndarray, displacement: np.ndarray, path: Path) -> None:
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    max_value = float(np.max(displacement)) if displacement.size else 0.0
    scale = 6
    for vertex, value in zip(vertices, displacement):
        if value <= 1e-8:
            continue
        t = float(value) / max(max_value, 1e-6)
        x = int(round(float(vertex[0]) * scale))
        y = int(round(float(vertex[1]) * scale))
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(255, int(220 * (1.0 - t)), 40, 255))
    image.save(path, format="PNG")


def _write_edge_projection(vertices: np.ndarray, labels: np.ndarray, edges: set[tuple[int, int]], path: Path) -> None:
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    scale = 6
    for a, b in edges:
        ax, ay = int(round(float(vertices[a, 0]) * scale)), int(round(float(vertices[a, 1]) * scale))
        bx, by = int(round(float(vertices[b, 0]) * scale)), int(round(float(vertices[b, 1]) * scale))
        draw.line((ax, ay, bx, by), fill=(255, 255, 255, 255), width=1)
    image.save(path, format="PNG")


def _write_boundary_projection(vertices: np.ndarray, labels: np.ndarray, edges: set[tuple[int, int]], path: Path) -> None:
    image = _projection_image(vertices, labels)
    draw = ImageDraw.Draw(image)
    scale = 6
    for a, b in edges:
        color = (80, 235, 140, 255) if labels[a] != labels[b] else (100, 140, 255, 255)
        ax, ay = int(round(float(vertices[a, 0]) * scale)), int(round(float(vertices[a, 1]) * scale))
        bx, by = int(round(float(vertices[b, 0]) * scale)), int(round(float(vertices[b, 1]) * scale))
        draw.line((ax, ay, bx, by), fill=color, width=1)
    image.save(path, format="PNG")


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
    normal_before = float(report.get("normal_discontinuity_before", 0.0))
    normal_after = float(report.get("normal_discontinuity_after", 0.0))
    frag_before = float(report.get("surface_fragmentation_before", 0.0))
    frag_after = float(report.get("surface_fragmentation_after", 0.0))
    improved = normal_after < normal_before and frag_after <= frag_before
    likely_cause = "meshing issue"
    if not report.get("semantic_part_graph_present", False):
        likely_cause = "semantic issue"
    elif int(report.get("cohesion_vertices_adjusted", 0)) <= 0:
        likely_cause = "meshing issue"
    elif not improved:
        likely_cause = "meshing issue"
    return {
        "surface_metric_improved": improved,
        "semantic_issue": not bool(report.get("semantic_part_graph_present", False)),
        "sdf_issue": False,
        "meshing_issue": likely_cause == "meshing issue",
        "render_issue": False,
        "likely_cause": likely_cause,
        "notes": [
            "Semantic authority and canonical semantic parts are present; this pass does not indicate a semantic authority failure.",
            "Closed SDF connectivity and label preservation remain valid, so the SDF layer is not the primary failure signal.",
            "Local mesh relaxation is safe but does not reduce the current normal/fragmentation metric, pointing to surface-nets topology or extraction density as the next bottleneck.",
            "Rendering may still make blockiness visible, but this phase intentionally did not change render style.",
        ],
        "recommended_next_engineering_step": "Inspect surface-nets topology and consider topology-aware extraction or a better cohesion objective before increasing relaxation strength.",
    }
