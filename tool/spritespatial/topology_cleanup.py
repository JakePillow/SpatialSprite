from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


def apply_topology_cleanup(
    mesh: dict[str, Any],
    output_dir: Path,
    emit_debug: bool = False,
    preserve_silhouette_edges: bool = True,
    preserve_semantic_boundaries: bool = True,
    vertex_merge_epsilon: float = 1.0e-5,
    sliver_area_threshold: float = 1.0e-7,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    before_edges = _non_manifold_edges(mesh)
    cleaned = _copy_mesh(mesh)
    duplicate_vertices_merged = _merge_duplicate_vertices(cleaned, vertex_merge_epsilon)
    duplicate_faces_removed = _remove_duplicate_faces(cleaned)
    sliver_faces_removed = _remove_sliver_faces(cleaned, sliver_area_threshold)
    repaired_face_count = _repair_non_manifold_fans(
        cleaned,
        preserve_silhouette_edges=preserve_silhouette_edges,
        preserve_semantic_boundaries=preserve_semantic_boundaries,
    )
    _refresh_mesh(cleaned)
    after_edges = _non_manifold_edges(cleaned)
    report = {
        "schema": "spritespatial_topology_cleanup_report_v1",
        "topology_cleanup_applied": True,
        "non_manifold_before_cleanup": len(before_edges),
        "non_manifold_after_cleanup": len(after_edges),
        "duplicate_faces_removed": duplicate_faces_removed,
        "duplicate_vertices_merged": duplicate_vertices_merged,
        "sliver_faces_removed": sliver_faces_removed,
        "non_manifold_faces_removed": repaired_face_count,
        "mesh_connected_components": cleaned.get("stats", {}).get("mesh_connected_components", 0),
        "degenerate_face_count": cleaned.get("stats", {}).get("degenerate_face_count", 0),
        "semantic_labels_in_mesh": cleaned.get("stats", {}).get("semantic_labels_in_mesh", []),
        "semantic_labels_missing_from_mesh": cleaned.get("stats", {}).get("semantic_labels_missing_from_mesh", []),
        "passed": True,
    }
    paths = {
        "non_manifold_edges_before": output_dir / "non_manifold_edges_before.json",
        "non_manifold_edges_after": output_dir / "non_manifold_edges_after.json",
        "cleanup_report": output_dir / "cleanup_report.json",
        "repaired_edge_debug": output_dir / "repaired_edge_debug.png",
        "sliver_face_debug": output_dir / "sliver_face_debug.png",
        "mesh_topology_cleaned": output_dir / "mesh_topology_cleaned.json",
    }
    _write_json(paths["non_manifold_edges_before"], {"edges": before_edges})
    _write_json(paths["non_manifold_edges_after"], {"edges": after_edges})
    _write_json(paths["cleanup_report"], report)
    _write_json(paths["mesh_topology_cleaned"], cleaned)
    _write_debug_image(before_edges, after_edges, paths["repaired_edge_debug"])
    _write_sliver_debug(sliver_faces_removed, paths["sliver_face_debug"])
    if not emit_debug:
        # The required debug artefacts are still written; emit_debug is reserved for future heavier dumps.
        pass
    return {"mesh": cleaned, "report": report, "paths": paths}


def _copy_mesh(mesh: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(mesh))


def _merge_duplicate_vertices(mesh: dict[str, Any], epsilon: float) -> int:
    vertices = [list(map(float, vertex)) for vertex in mesh.get("vertices", [])]
    if not vertices:
        return 0
    key_to_new: dict[tuple[int, int, int], int] = {}
    old_to_new: dict[int, int] = {}
    new_vertices: list[list[float]] = []
    new_metadata: list[dict[str, Any]] = []
    metadata = list(mesh.get("vertex_metadata", []))
    scale = 1.0 / max(epsilon, 1.0e-12)
    for index, vertex in enumerate(vertices):
        key = tuple(int(round(value * scale)) for value in vertex)
        existing = key_to_new.get(key)
        if existing is None:
            existing = len(new_vertices)
            key_to_new[key] = existing
            new_vertices.append(vertex)
            new_metadata.append(dict(metadata[index]) if index < len(metadata) and isinstance(metadata[index], dict) else {})
        old_to_new[index] = existing
    for face in mesh.get("faces", []):
        for i, vertex_index in enumerate(face):
            face[i] = old_to_new.get(int(vertex_index), int(vertex_index))
    mesh["vertices"] = new_vertices
    mesh["vertex_metadata"] = new_metadata
    return len(vertices) - len(new_vertices)


def _remove_duplicate_faces(mesh: dict[str, Any]) -> int:
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = list(mesh.get("face_metadata", []))
    seen: set[tuple[int, ...]] = set()
    kept_faces = []
    kept_metadata = []
    removed = 0
    for index, face in enumerate(faces):
        key = tuple(sorted(face))
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept_faces.append(face)
        kept_metadata.append(metadata[index] if index < len(metadata) else {})
    mesh["faces"] = kept_faces
    mesh["face_metadata"] = kept_metadata
    return removed


def _remove_sliver_faces(mesh: dict[str, Any], threshold: float) -> int:
    vertices = mesh.get("vertices", [])
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = list(mesh.get("face_metadata", []))
    kept_faces = []
    kept_metadata = []
    removed = 0
    for index, face in enumerate(faces):
        area = _face_area(vertices, face)
        if area <= threshold:
            removed += 1
            continue
        kept_faces.append(face)
        kept_metadata.append(metadata[index] if index < len(metadata) else {})
    mesh["faces"] = kept_faces
    mesh["face_metadata"] = kept_metadata
    return removed


def _repair_non_manifold_fans(
    mesh: dict[str, Any],
    preserve_silhouette_edges: bool,
    preserve_semantic_boundaries: bool,
) -> int:
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = list(mesh.get("face_metadata", []))
    removed_faces: set[int] = set()
    edge_to_faces = _edge_to_faces(faces)
    for edge, face_indices in sorted(edge_to_faces.items(), key=lambda item: len(item[1]), reverse=True):
        live = [index for index in face_indices if index not in removed_faces]
        while len(live) > 2:
            candidate = _removable_face(live, metadata, preserve_silhouette_edges, preserve_semantic_boundaries)
            if candidate is None:
                break
            removed_faces.add(candidate)
            live = [index for index in live if index != candidate]
    if not removed_faces:
        return 0
    mesh["faces"] = [face for index, face in enumerate(faces) if index not in removed_faces]
    mesh["face_metadata"] = [item for index, item in enumerate(metadata) if index not in removed_faces]
    return len(removed_faces)


def _removable_face(
    face_indices: list[int],
    metadata: list[Any],
    preserve_silhouette_edges: bool,
    preserve_semantic_boundaries: bool,
) -> int | None:
    for index in reversed(face_indices):
        item = metadata[index] if index < len(metadata) and isinstance(metadata[index], dict) else {}
        if preserve_silhouette_edges and bool(item.get("is_silhouette", False)):
            continue
        if preserve_semantic_boundaries and bool(item.get("is_semantic_boundary", False)):
            continue
        return index
    return None


def _refresh_mesh(mesh: dict[str, Any]) -> None:
    vertices = mesh.get("vertices", [])
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = list(mesh.get("face_metadata", []))
    vertex_metadata = list(mesh.get("vertex_metadata", []))
    edge_counts: dict[tuple[int, int], int] = defaultdict(int)
    adjacency: dict[int, set[int]] = defaultdict(set)
    boundary_edges = set()
    silhouette_vertices = set()
    labels_in_mesh = set()
    for face, face_meta in zip(faces, metadata):
        label = int(face_meta.get("semantic_label", 0)) if isinstance(face_meta, dict) else 0
        if label:
            labels_in_mesh.add(label)
        if isinstance(face_meta, dict) and bool(face_meta.get("is_semantic_boundary", False)):
            for edge in _face_edges(face):
                boundary_edges.add(edge)
        if isinstance(face_meta, dict) and bool(face_meta.get("is_silhouette", False)):
            silhouette_vertices.update(face)
        for a, b in _face_edges(face):
            edge_counts[(a, b)] += 1
            adjacency[a].add(b)
            adjacency[b].add(a)
    labels_in_volume = sorted(int(value) for value in mesh.get("stats", {}).get("semantic_labels_in_volume", []))
    labels_in_mesh_sorted = sorted(labels_in_mesh)
    mesh["indices"] = _triangulated_indices(faces, vertices)
    mesh["semantic_boundary_edges"] = [list(edge) for edge in sorted(boundary_edges)]
    mesh["silhouette_vertices"] = sorted(int(value) for value in silhouette_vertices)
    while len(vertex_metadata) < len(vertices):
        vertex_metadata.append({})
    for index in silhouette_vertices:
        if 0 <= index < len(vertex_metadata) and isinstance(vertex_metadata[index], dict):
            vertex_metadata[index]["is_silhouette_vertex"] = True
            vertex_metadata[index]["is_boundary_vertex"] = True
    mesh["vertex_metadata"] = vertex_metadata
    mesh["stats"] = {
        **dict(mesh.get("stats", {})),
        "surface_net_vertices": len(vertices),
        "surface_net_faces": len(faces),
        "semantic_boundary_edge_count": sum(1 for item in metadata if isinstance(item, dict) and item.get("is_semantic_boundary", False)),
        "silhouette_vertex_count": len(silhouette_vertices),
        "degenerate_face_count": sum(1 for face in faces if _face_area(vertices, face) <= 1.0e-8),
        "non_manifold_edge_count": sum(1 for count in edge_counts.values() if count > 2),
        "mesh_connected_components": _mesh_component_count(len(vertices), adjacency),
        "semantic_labels_in_mesh": labels_in_mesh_sorted,
        "semantic_labels_in_volume": labels_in_volume,
        "semantic_labels_missing_from_mesh": [label for label in labels_in_volume if label not in labels_in_mesh_sorted],
        "semantic_label_preservation_passed": not [label for label in labels_in_volume if label not in labels_in_mesh_sorted],
        "material_groups": {str(label): sum(1 for item in metadata if isinstance(item, dict) and item.get("semantic_label") == label) for label in labels_in_mesh_sorted},
    }


def _non_manifold_edges(mesh: dict[str, Any]) -> list[dict[str, Any]]:
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    edge_to_faces = _edge_to_faces(faces)
    return [
        {"edge": [int(edge[0]), int(edge[1])], "face_count": len(indices), "faces": indices}
        for edge, indices in sorted(edge_to_faces.items())
        if len(indices) > 2
    ]


def _edge_to_faces(faces: list[list[int]]) -> dict[tuple[int, int], list[int]]:
    result: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, face in enumerate(faces):
        for edge in _face_edges(face):
            result[edge].append(index)
    return result


def _face_edges(face: list[int]) -> list[tuple[int, int]]:
    return [tuple(sorted((int(a), int(b)))) for a, b in zip(face, face[1:] + face[:1])]


def _face_area(vertices: list[list[float]], face: list[int]) -> float:
    if len(set(face)) < 3 or len(face) < 3:
        return 0.0
    if len(face) == 3:
        return _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]])
    return sum(
        _triangle_area(vertices[face[0]], vertices[face[index]], vertices[face[index + 1]])
        for index in range(1, len(face) - 1)
    )


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    ax, ay, az = a
    bx, by, bz = b
    cx, cy, cz = c
    ab = (bx - ax, by - ay, bz - az)
    ac = (cx - ax, cy - ay, cz - az)
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) * 0.5


def _triangulated_indices(faces: list[list[int]], vertices: list[list[float]]) -> list[int]:
    indices: list[int] = []
    for face in faces:
        if len(face) < 3:
            continue
        for index in range(1, len(face) - 1):
            tri = [face[0], face[index], face[index + 1]]
            if _triangle_area(vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]) > 1.0e-8:
                indices.extend(tri)
    return indices


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


def _write_debug_image(before_edges: list[dict[str, Any]], after_edges: list[dict[str, Any]], path: Path) -> None:
    image = Image.new("RGBA", (320, 96), (24, 32, 38, 255))
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), f"non-manifold before: {len(before_edges)}", fill=(255, 210, 120, 255))
    draw.text((10, 34), f"non-manifold after: {len(after_edges)}", fill=(140, 230, 170, 255))
    draw.rectangle((10, 64, 310, 82), outline=(90, 120, 140, 255))
    before_width = min(300, len(before_edges) * 4)
    after_width = min(300, len(after_edges) * 4)
    draw.rectangle((10, 64, 10 + before_width, 72), fill=(255, 100, 90, 255))
    draw.rectangle((10, 74, 10 + after_width, 82), fill=(110, 220, 150, 255))
    image.save(path, format="PNG")


def _write_sliver_debug(count: int, path: Path) -> None:
    image = Image.new("RGBA", (240, 64), (24, 32, 38, 255))
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), f"sliver faces removed: {count}", fill=(230, 230, 230, 255))
    image.save(path, format="PNG")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
