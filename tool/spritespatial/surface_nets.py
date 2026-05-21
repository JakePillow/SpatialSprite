from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
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


def emit_surface_nets_input(
    sdf_volume: np.ndarray,
    semantic_volume: np.ndarray,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / "surface_nets_input.npz"
    np.savez_compressed(npz_path, sdf=sdf_volume.astype(np.float32), semantic=semantic_volume.astype(np.int32))
    loadable = False
    shape_valid = False
    sdf_dtype = str(sdf_volume.astype(np.float32).dtype)
    semantic_dtype = str(semantic_volume.astype(np.int32).dtype)
    try:
        loaded = np.load(npz_path)
        loadable = "sdf" in loaded and "semantic" in loaded
        shape_valid = bool(loadable and loaded["sdf"].shape == sdf_volume.shape and loaded["semantic"].shape == semantic_volume.shape)
        sdf_dtype = str(loaded["sdf"].dtype)
        semantic_dtype = str(loaded["semantic"].dtype)
    except Exception:
        loadable = False
    crossings = _estimated_crossings(sdf_volume)
    report = {
        "schema": "spritespatial_surface_nets_bridge_v1",
        "meshing_backend_used": "placeholder",
        "surface_nets_input_loadable": loadable,
        "surface_nets_input_shape_valid": shape_valid,
        "sdf_dtype": sdf_dtype,
        "semantic_dtype": semantic_dtype,
        "grid_dimensions": list(sdf_volume.shape),
        "semantic_label_count": int(len(set(int(value) for value in np.unique(semantic_volume) if int(value) != 0))),
        "sdf_min": float(sdf_volume.min()) if sdf_volume.size else 0.0,
        "sdf_max": float(sdf_volume.max()) if sdf_volume.size else 0.0,
        "estimated_cell_crossings": crossings,
    }
    (output_dir / "meshing_backend_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    preview = {
        "schema": "spritespatial_optional_closed_preview_mesh_v1",
        "note": "Phase 5A emits SDF infrastructure only; surface nets triangulation is deferred.",
        "vertices": [],
        "indices": [],
    }
    (output_dir / "optional_closed_preview_mesh.json").write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    return {
        "report": report,
        "paths": {
            "surface_nets_input": npz_path,
            "meshing_backend_report": output_dir / "meshing_backend_report.json",
            "optional_closed_preview_mesh": output_dir / "optional_closed_preview_mesh.json",
        },
    }


def load_surface_nets_input(path: Path) -> tuple[np.ndarray, np.ndarray]:
    loaded = np.load(path)
    if "sdf" not in loaded or "semantic" not in loaded:
        raise ValueError(f"{path} must contain 'sdf' and 'semantic' arrays.")
    sdf = loaded["sdf"].astype(np.float32, copy=False)
    semantic = loaded["semantic"].astype(np.int32, copy=False)
    if sdf.shape != semantic.shape:
        raise ValueError(f"SDF and semantic shapes differ: {sdf.shape} != {semantic.shape}")
    if sdf.ndim != 3:
        raise ValueError(f"SDF must be 3D, got shape {sdf.shape}")
    return sdf, semantic


def extract_surface_nets(
    sdf: np.ndarray,
    semantic: np.ndarray,
    iso_level: float = 0.0,
    smoothing_alpha: float = 0.65,
) -> dict[str, Any]:
    if sdf.shape != semantic.shape:
        raise ValueError(f"SDF and semantic shapes differ: {sdf.shape} != {semantic.shape}")
    alpha = max(0.0, min(1.0, float(smoothing_alpha)))
    vertices: list[list[float]] = []
    vertex_metadata: list[dict[str, Any]] = []
    active_cells: dict[tuple[int, int, int], int] = {}
    dims = sdf.shape

    for y in range(dims[0] - 1):
        for x in range(dims[1] - 1):
            for z in range(dims[2] - 1):
                values = np.array([sdf[y + dy, x + dx, z + dz] for dy, dx, dz in CELL_CORNERS], dtype=np.float32)
                if not _cell_active(values, iso_level):
                    continue
                crossings = _cell_crossings(values, y, x, z, iso_level)
                if not crossings:
                    continue
                average = np.mean(np.array(crossings, dtype=np.float32), axis=0)
                center = np.array([float(x) + 0.5, float(y) + 0.5, float(z) + 0.5], dtype=np.float32)
                position = center * (1.0 - alpha) + average * alpha
                labels = [int(semantic[y + dy, x + dx, z + dz]) for dy, dx, dz in CELL_CORNERS]
                label = _majority_label(labels)
                unique_labels = sorted(label_value for label_value in set(labels) if label_value != 0)
                index = len(vertices)
                vertices.append([float(position[0]), float(position[1]), float(position[2])])
                active_cells[(y, x, z)] = index
                vertex_metadata.append(
                    {
                        "semantic_label": label,
                        "source_cell": [int(y), int(x), int(z)],
                        "is_boundary_vertex": 0 in labels,
                        "is_silhouette_vertex": 0 in labels,
                        "is_semantic_boundary": len(unique_labels) > 1,
                        "neighbour_semantic_labels": unique_labels,
                    }
                )

    faces: list[list[int]] = []
    face_metadata: list[dict[str, Any]] = []
    boundary_edges: set[tuple[int, int]] = set()
    silhouette_vertices: set[int] = set()
    _connect_active_cells(sdf, semantic, active_cells, faces, face_metadata, boundary_edges, silhouette_vertices, iso_level)
    _mark_vertex_flags(vertex_metadata, faces, face_metadata, silhouette_vertices)
    indices = _triangulated_indices(faces, vertices)
    stats = _mesh_stats(vertices, faces, face_metadata, vertex_metadata, semantic, active_cells)
    metadata_silhouette_vertices = [
        index for index, metadata in enumerate(vertex_metadata)
        if metadata.get("is_silhouette_vertex", False)
    ]
    return {
        "schema": "spritespatial_surface_nets_mesh_v1",
        "vertices": vertices,
        "faces": faces,
        "indices": indices,
        "vertex_metadata": vertex_metadata,
        "face_metadata": face_metadata,
        "active_cells": {",".join(str(part) for part in key): value for key, value in active_cells.items()},
        "semantic_boundary_edges": [list(edge) for edge in sorted(boundary_edges)],
        "silhouette_vertices": metadata_silhouette_vertices,
        "stats": stats,
        "config": {
            "iso_level": float(iso_level),
            "surface_net_smoothing_alpha": alpha,
        },
    }


def write_mesh_json(mesh: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mesh, indent=2) + "\n", encoding="utf-8")
    return path


def write_surface_nets_report(mesh: dict[str, Any], output_dir: Path, input_path: Path | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = dict(mesh.get("stats", {}))
    report = {
        "schema": "spritespatial_surface_nets_report_v1",
        "meshing_backend_used": "surface_nets",
        "surface_nets_input": str(input_path) if input_path else "",
        **stats,
        "surface_net_smoothing_alpha": mesh.get("config", {}).get("surface_net_smoothing_alpha", 0.65),
        "passed": bool(stats.get("surface_net_vertices", 0) > 0 and stats.get("surface_net_faces", 0) > 0),
    }
    (output_dir / "surface_nets_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def write_surface_nets_debug(mesh: dict[str, Any], sdf: np.ndarray, semantic: np.ndarray, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    active_path = output_dir / "active_cells.png"
    overlay_path = output_dir / "semantic_mesh_overlay.png"
    silhouette_path = output_dir / "silhouette_vertices.json"
    boundaries_path = output_dir / "semantic_boundaries.json"
    cells_path = output_dir / "surface_net_cells.json"
    stats_path = output_dir / "mesh_stats.json"
    _write_active_cell_sheet(mesh, sdf.shape, active_path)
    _write_semantic_overlay(mesh, semantic, overlay_path)
    silhouette_path.write_text(json.dumps({"vertices": mesh.get("silhouette_vertices", [])}, indent=2) + "\n", encoding="utf-8")
    boundaries_path.write_text(json.dumps({"edges": mesh.get("semantic_boundary_edges", [])}, indent=2) + "\n", encoding="utf-8")
    cells_path.write_text(json.dumps({"active_cells": mesh.get("active_cells", {})}, indent=2) + "\n", encoding="utf-8")
    stats_path.write_text(json.dumps(mesh.get("stats", {}), indent=2) + "\n", encoding="utf-8")
    return {
        "active_cells": active_path,
        "semantic_mesh_overlay": overlay_path,
        "silhouette_vertices": silhouette_path,
        "semantic_boundaries": boundaries_path,
        "surface_net_cells": cells_path,
        "mesh_stats": stats_path,
    }


def _cell_active(values: np.ndarray, iso_level: float) -> bool:
    return bool(np.any(values <= iso_level) and np.any(values > iso_level))


def _cell_crossings(values: np.ndarray, y: int, x: int, z: int, iso_level: float) -> list[list[float]]:
    crossings: list[list[float]] = []
    corner_positions = [
        np.array([float(x + dx), float(y + dy), float(z + dz)], dtype=np.float32)
        for dy, dx, dz in CELL_CORNERS
    ]
    for a, b in CELL_EDGES:
        va = float(values[a] - iso_level)
        vb = float(values[b] - iso_level)
        if (va <= 0.0) == (vb <= 0.0):
            continue
        denom = va - vb
        t = 0.5 if abs(denom) < 1e-8 else va / denom
        t = max(0.0, min(1.0, t))
        pos = corner_positions[a] + (corner_positions[b] - corner_positions[a]) * t
        crossings.append([float(pos[0]), float(pos[1]), float(pos[2])])
    return crossings


def _majority_label(labels: list[int]) -> int:
    nonzero = [label for label in labels if label != 0]
    if not nonzero:
        return 0
    return int(Counter(nonzero).most_common(1)[0][0])


def _connect_active_cells(
    sdf: np.ndarray,
    semantic: np.ndarray,
    active_cells: dict[tuple[int, int, int], int],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    boundary_edges: set[tuple[int, int]],
    silhouette_vertices: set[int],
    iso_level: float,
) -> None:
    dims = sdf.shape
    for y in range(dims[0]):
        for x in range(dims[1] - 1):
            for z in range(dims[2]):
                if (sdf[y, x, z] <= iso_level) == (sdf[y, x + 1, z] <= iso_level):
                    continue
                _try_add_face(
                    ((y - 1, x, z - 1), (y, x, z - 1), (y, x, z), (y - 1, x, z)),
                    semantic,
                    active_cells,
                    faces,
                    face_metadata,
                    boundary_edges,
                    silhouette_vertices,
                )
    for y in range(dims[0] - 1):
        for x in range(dims[1]):
            for z in range(dims[2]):
                if (sdf[y, x, z] <= iso_level) == (sdf[y + 1, x, z] <= iso_level):
                    continue
                _try_add_face(
                    ((y, x - 1, z - 1), (y, x, z - 1), (y, x, z), (y, x - 1, z)),
                    semantic,
                    active_cells,
                    faces,
                    face_metadata,
                    boundary_edges,
                    silhouette_vertices,
                )
    for y in range(dims[0]):
        for x in range(dims[1]):
            for z in range(dims[2] - 1):
                if (sdf[y, x, z] <= iso_level) == (sdf[y, x, z + 1] <= iso_level):
                    continue
                _try_add_face(
                    ((y - 1, x - 1, z), (y, x - 1, z), (y, x, z), (y - 1, x, z)),
                    semantic,
                    active_cells,
                    faces,
                    face_metadata,
                    boundary_edges,
                    silhouette_vertices,
                )


def _try_add_face(
    cells: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]],
    semantic: np.ndarray,
    active_cells: dict[tuple[int, int, int], int],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    boundary_edges: set[tuple[int, int]],
    silhouette_vertices: set[int],
) -> None:
    if any(cell not in active_cells for cell in cells):
        return
    face = [active_cells[cell] for cell in cells]
    if len(set(face)) < 3:
        return
    labels = [_cell_label(semantic, cell) for cell in cells]
    face_label = _majority_label(labels)
    nonzero_labels = sorted(label for label in set(labels) if label != 0)
    is_semantic_boundary = len(nonzero_labels) > 1
    is_silhouette = 0 in labels
    if is_semantic_boundary:
        for a, b in zip(face, face[1:] + face[:1]):
            boundary_edges.add(tuple(sorted((a, b))))
    if is_silhouette:
        silhouette_vertices.update(face)
    faces.append(face)
    face_metadata.append(
        {
            "semantic_label": face_label,
            "source_cells": [list(cell) for cell in cells],
            "is_semantic_boundary": is_semantic_boundary,
            "is_silhouette": is_silhouette,
            "neighbour_semantic_labels": nonzero_labels,
        }
    )


def _cell_label(semantic: np.ndarray, cell: tuple[int, int, int]) -> int:
    y, x, z = cell
    labels = []
    for dy, dx, dz in CELL_CORNERS:
        yy, xx, zz = y + dy, x + dx, z + dz
        if 0 <= yy < semantic.shape[0] and 0 <= xx < semantic.shape[1] and 0 <= zz < semantic.shape[2]:
            labels.append(int(semantic[yy, xx, zz]))
    return _majority_label(labels)


def _mark_vertex_flags(
    vertex_metadata: list[dict[str, Any]],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    silhouette_vertices: set[int],
) -> None:
    for vertex_index in silhouette_vertices:
        if 0 <= vertex_index < len(vertex_metadata):
            vertex_metadata[vertex_index]["is_silhouette_vertex"] = True
            vertex_metadata[vertex_index]["is_boundary_vertex"] = True
    for face, metadata in zip(faces, face_metadata):
        if metadata.get("is_semantic_boundary", False):
            for vertex_index in face:
                vertex_metadata[vertex_index]["is_semantic_boundary"] = True
                vertex_metadata[vertex_index]["is_boundary_vertex"] = True


def _triangulated_indices(faces: list[list[int]], vertices: list[list[float]]) -> list[int]:
    indices: list[int] = []
    for face in faces:
        if len(face) == 3:
            triangles = [face]
        else:
            triangles = [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
        for tri in triangles:
            if _triangle_area(vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]) > 1e-8:
                indices.extend(tri)
    return indices


def _triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    av = np.array(a, dtype=np.float32)
    bv = np.array(b, dtype=np.float32)
    cv = np.array(c, dtype=np.float32)
    return float(np.linalg.norm(np.cross(bv - av, cv - av)) * 0.5)


def _mesh_stats(
    vertices: list[list[float]],
    faces: list[list[int]],
    face_metadata: list[dict[str, Any]],
    vertex_metadata: list[dict[str, Any]],
    semantic: np.ndarray,
    active_cells: dict[tuple[int, int, int], int],
) -> dict[str, Any]:
    degenerate = sum(1 for face in faces if _face_degenerate(face, vertices))
    edge_counts: dict[tuple[int, int], int] = defaultdict(int)
    adjacency: dict[int, set[int]] = defaultdict(set)
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            edge_counts[edge] += 1
            adjacency[a].add(b)
            adjacency[b].add(a)
    non_manifold_edges = sum(1 for count in edge_counts.values() if count > 2)
    labels_in_mesh = sorted({int(item.get("semantic_label", 0)) for item in face_metadata if int(item.get("semantic_label", 0)) != 0})
    labels_in_volume = sorted(int(value) for value in np.unique(semantic) if int(value) != 0)
    missing = [label for label in labels_in_volume if label not in labels_in_mesh]
    silhouette_vertices = {index for index, metadata in enumerate(vertex_metadata) if metadata.get("is_silhouette_vertex", False)}
    return {
        "surface_net_vertices": len(vertices),
        "surface_net_faces": len(faces),
        "active_cell_count": len(active_cells),
        "semantic_boundary_edge_count": sum(1 for item in face_metadata if item.get("is_semantic_boundary", False)),
        "silhouette_vertex_count": len(silhouette_vertices),
        "degenerate_face_count": degenerate,
        "non_manifold_edge_count": non_manifold_edges,
        "mesh_connected_components": _mesh_component_count(len(vertices), adjacency),
        "semantic_labels_in_mesh": labels_in_mesh,
        "semantic_labels_in_volume": labels_in_volume,
        "semantic_labels_missing_from_mesh": missing,
        "semantic_label_preservation_passed": not missing,
        "material_groups": {str(label): sum(1 for item in face_metadata if item.get("semantic_label") == label) for label in labels_in_mesh},
    }


def _face_degenerate(face: list[int], vertices: list[list[float]]) -> bool:
    if len(set(face)) < 3:
        return True
    if len(face) == 3:
        return _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]]) <= 1e-8
    return (
        _triangle_area(vertices[face[0]], vertices[face[1]], vertices[face[2]]) <= 1e-8
        and _triangle_area(vertices[face[0]], vertices[face[2]], vertices[face[3]]) <= 1e-8
    )


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


def _write_active_cell_sheet(mesh: dict[str, Any], shape: tuple[int, int, int], path: Path) -> None:
    active = np.zeros((shape[0] - 1, shape[1] - 1, shape[2] - 1), dtype=bool)
    for key in mesh.get("active_cells", {}):
        y, x, z = (int(part) for part in key.split(","))
        if 0 <= y < active.shape[0] and 0 <= x < active.shape[1] and 0 <= z < active.shape[2]:
            active[y, x, z] = True
    frames = [_mask_image(active[:, :, z]) for z in range(active.shape[2])]
    _write_contact_sheet(frames, path)


def _write_semantic_overlay(mesh: dict[str, Any], semantic: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (semantic.shape[1], semantic.shape[0]), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    for vertex, meta in zip(mesh.get("vertices", []), mesh.get("vertex_metadata", [])):
        x = int(round(vertex[0]))
        y = int(round(vertex[1]))
        if 0 <= x < semantic.shape[1] and 0 <= y < semantic.shape[0]:
            label = int(meta.get("semantic_label", 0))
            color = _label_color(label)
            draw.point((x, y), fill=color)
    image.save(path, format="PNG")


def _mask_image(mask: np.ndarray) -> Image.Image:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 255))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (255, 255, 255, 255)
    return image.resize((mask.shape[1] * 4, mask.shape[0] * 4), Image.Resampling.NEAREST)


def _write_contact_sheet(frames: list[Image.Image], path: Path) -> None:
    if not frames:
        Image.new("RGBA", (1, 1), (0, 0, 0, 255)).save(path, format="PNG")
        return
    cols = min(8, len(frames))
    rows = (len(frames) + cols - 1) // cols
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    sheet = Image.new("RGBA", (cols * width, rows * height), (0, 70, 70, 255))
    for index, frame in enumerate(frames):
        x = (index % cols) * width
        y = (index // cols) * height
        sheet.alpha_composite(frame, (x, y))
    sheet.save(path, format="PNG")


def _label_color(label: int) -> tuple[int, int, int, int]:
    palette = [
        (0, 0, 0, 255),
        (20, 20, 20, 255),
        (240, 80, 80, 255),
        (255, 210, 120, 255),
        (140, 80, 210, 255),
        (80, 180, 240, 255),
        (60, 210, 140, 255),
        (210, 160, 60, 255),
        (120, 200, 80, 255),
        (80, 120, 220, 255),
        (180, 120, 60, 255),
        (230, 230, 80, 255),
        (180, 180, 180, 255),
    ]
    return palette[label % len(palette)]


def _estimated_crossings(sdf: np.ndarray) -> int:
    count = 0
    for axis in range(3):
        a = np.take(sdf, range(0, sdf.shape[axis] - 1), axis=axis)
        b = np.take(sdf, range(1, sdf.shape[axis]), axis=axis)
        count += int(np.count_nonzero((a <= 0.0) != (b <= 0.0)))
    return count
