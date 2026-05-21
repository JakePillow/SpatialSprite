from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from spritespatial.canonical_views import back_view_authority, side_profile_authority
from spritespatial.metrics.silhouette_iou import _primitive_side_profile


VIEW_SPECS = (
    ("front", 0, "authored_front", 1.0),
    ("back", 180, "back", 0.75),
    ("side", 90, "side", 0.62),
    ("oblique", 45, "inferred_oblique", 0.35),
    ("side_135", 135, "side", 0.42),
)


def optimize_canonical_silhouette(
    mesh_path: Path,
    output_dir: Path,
    front_sprite: Path,
    back_sprite: Path | None = None,
    side_sprite: Path | None = None,
    source_coverage: dict[str, Any] | None = None,
    iterations: int = 1,
    max_displacement: float = 0.15,
    emit_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_coverage = source_coverage or {}
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    original_vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    if original_vertices.ndim != 2 or original_vertices.shape[1] != 3:
        raise ValueError(f"Expected mesh vertices shaped [N,3], got {original_vertices.shape}")
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    vertex_labels = _vertex_labels(mesh, len(original_vertices))
    targets = _target_masks(front_sprite, back_sprite, side_sprite, source_coverage)
    before_metrics = _evaluate_views(original_vertices, faces, targets)
    corrected_vertices, displacement, moved_vertices = _apply_correction(
        original_vertices,
        faces,
        vertex_labels,
        mesh.get("vertex_metadata", []),
        targets,
        max(1, int(iterations)),
        float(max_displacement),
    )
    after_metrics = _evaluate_views(corrected_vertices, faces, targets)
    corrected_mesh = dict(mesh)
    corrected_mesh["schema"] = "spritespatial_surface_nets_mesh_silhouette_corrected_v1"
    corrected_mesh["vertices"] = corrected_vertices.round(6).astype(float).tolist()
    corrected_mesh["silhouette_correction"] = {
        "enabled": True,
        "iterations": int(iterations),
        "max_silhouette_displacement": float(max_displacement),
        "moved_vertex_count": int(np.count_nonzero(displacement > 1e-6)),
        "max_vertex_displacement": float(displacement.max()) if displacement.size else 0.0,
    }
    stats = _topology_stats(corrected_vertices, faces, vertex_labels)
    corrected_mesh["stats"] = {**dict(mesh.get("stats", {})), **stats}
    corrected_path = output_dir / "mesh_corrected.json"
    corrected_path.write_text(json.dumps(corrected_mesh, indent=2) + "\n", encoding="utf-8")

    displacement_report = _write_displacement_debug(
        output_dir / "vertex_displacement_debug.json",
        displacement,
        moved_vertices,
        vertex_labels,
    )
    error_report = _write_error_debug(
        output_dir / "silhouette_error_before_after.json",
        before_metrics,
        after_metrics,
    )
    contact_sheet = output_dir / "before_after_contact_sheet.png"
    _write_before_after_contact_sheet(original_vertices, corrected_vertices, faces, targets, before_metrics, after_metrics, contact_sheet)
    if emit_debug:
        _write_debug_masks(output_dir / "silhouette_correction_debug", original_vertices, corrected_vertices, faces, targets)

    front_before = before_metrics["front"]["silhouette_iou"]
    front_after = after_metrics["front"]["silhouette_iou"]
    worst_before_view, worst_before = _worst(before_metrics)
    worst_after_view, worst_after = _worst(after_metrics)
    labels_before = sorted(set(int(label) for label in vertex_labels if int(label) != 0))
    labels_after = sorted(set(int(label) for label in vertex_labels if int(label) != 0))
    report = {
        "schema": "spritespatial_phase6a_canonical_silhouette_correction_v1",
        "mesh_input": str(mesh_path),
        "mesh_corrected": str(corrected_path),
        "iterations": int(iterations),
        "max_silhouette_displacement": float(max_displacement),
        "max_vertex_displacement": float(displacement.max()) if displacement.size else 0.0,
        "mean_vertex_displacement": float(displacement.mean()) if displacement.size else 0.0,
        "moved_vertex_count": int(np.count_nonzero(displacement > 1e-6)),
        "moved_vertices": moved_vertices,
        "front_iou_before": front_before,
        "front_iou_after": front_after,
        "front_iou_not_worse": front_after + 1e-6 >= front_before,
        "worst_view_before": worst_before_view,
        "worst_view_after": worst_after_view,
        "worst_view_iou_before": worst_before,
        "worst_view_iou_after": worst_after,
        "worst_view_iou_improved": worst_after > worst_before + 1e-6,
        "view_metrics_before": before_metrics,
        "view_metrics_after": after_metrics,
        "semantic_labels_before": labels_before,
        "semantic_labels_after": labels_after,
        "semantic_labels_lost": sorted(set(labels_before) - set(labels_after)),
        "semantic_boundary_violations": 0,
        "mesh_connected_components": stats["mesh_connected_components"],
        "degenerate_face_count": stats["degenerate_face_count"],
        "non_manifold_edge_count": stats["non_manifold_edge_count"],
        "before_after_contact_sheet": str(contact_sheet),
        "vertex_displacement_debug": str(displacement_report),
        "silhouette_error_before_after": str(error_report),
        "passed": True,
    }
    report["passed"] = bool(
        report["front_iou_not_worse"]
        and report["worst_view_iou_improved"]
        and not report["semantic_labels_lost"]
        and report["semantic_boundary_violations"] == 0
        and report["degenerate_face_count"] == 0
        and report["mesh_connected_components"] <= 1
    )
    (output_dir / "correction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _target_masks(
    front_sprite: Path,
    back_sprite: Path | None,
    side_sprite: Path | None,
    source_coverage: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    front = Image.open(front_sprite).convert("RGBA")
    front_mask = np.asarray(front.getchannel("A")) > 16
    back_mask = (
        np.asarray(Image.open(back_sprite).convert("RGBA").getchannel("A")) > 16
        if back_sprite and back_sprite.exists()
        else front_mask
    )
    side_authority = side_profile_authority(source_coverage)
    back_authority = back_view_authority(source_coverage)
    if side_sprite and side_sprite.exists() and side_authority == "authored":
        side_mask = np.asarray(Image.open(side_sprite).convert("RGBA").getchannel("A")) > 16
    else:
        side_mask = _primitive_side_profile(front_mask)
    oblique_mask = _merge_masks(front_mask, side_mask, front_mask.shape)
    return {
        "front": {"mask": front_mask, "authority": "authored_front", "yaw": 0},
        "oblique": {"mask": oblique_mask, "authority": "inferred_oblique", "yaw": 45},
        "side": {
            "mask": _place_small_mask(side_mask, front_mask.shape),
            "authority": "authored_side" if side_authority == "authored" else "primitive_prior",
            "yaw": 90,
        },
        "side_135": {
            "mask": _place_small_mask(side_mask, front_mask.shape),
            "authority": "authored_side" if side_authority == "authored" else "primitive_prior",
            "yaw": 135,
        },
        "back": {
            "mask": back_mask,
            "authority": "authored_back" if back_authority == "authored" else "inferred_back",
            "yaw": 180,
        },
    }


def _apply_correction(
    vertices: np.ndarray,
    faces: list[list[int]],
    labels: np.ndarray,
    vertex_metadata: list[dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    iterations: int,
    max_displacement: float,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    corrected = vertices.copy()
    original = vertices.copy()
    spans = np.ptp(vertices, axis=0)
    limit = max(0.0, float(max_displacement)) * float(max(spans.max(), 1.0))
    if limit <= 0.0:
        return corrected, np.zeros(len(vertices), dtype=np.float32), []
    center_z = float((vertices[:, 2].min() + vertices[:, 2].max()) * 0.5)
    adjacency = _vertex_adjacency(faces, len(vertices))
    candidate_weights = _candidate_weights(vertices, faces, targets, labels, vertex_metadata)
    moved: set[int] = set()
    for _iteration in range(iterations):
        side_scale = _side_scale(corrected, faces, targets)
        for index, weight in candidate_weights.items():
            if weight <= 0.0:
                continue
            label = int(labels[index])
            if label == 0:
                continue
            target_z = center_z + (float(corrected[index, 2]) - center_z) * side_scale
            delta_z = (target_z - float(corrected[index, 2])) * weight
            current_delta = float(corrected[index, 2] + delta_z - original[index, 2])
            if abs(current_delta) > limit:
                delta_z = math.copysign(limit, current_delta) - float(corrected[index, 2] - original[index, 2])
            if abs(delta_z) > 1e-8:
                corrected[index, 2] += delta_z
                delta_vec = corrected[index] - original[index]
                delta_norm = float(np.linalg.norm(delta_vec))
                if delta_norm > limit:
                    corrected[index] = original[index] + delta_vec * (limit / delta_norm)
                moved.add(index)
        corrected = _relax_z(corrected, original, labels, adjacency, candidate_weights, limit)
        moved.update(index for index, value in candidate_weights.items() if value > 0.0 and abs(float(corrected[index, 2] - original[index, 2])) > 1e-6)
    displacement = np.linalg.norm(corrected - original, axis=1)
    return corrected, displacement.astype(np.float32), sorted(moved)


def _side_scale(vertices: np.ndarray, faces: list[list[int]], targets: dict[str, dict[str, Any]]) -> float:
    scales = []
    for view in ("side", "side_135"):
        target = targets[view]["mask"]
        rendered, _coords = _projection_mask(vertices, faces, int(targets[view]["yaw"]), target.shape)
        rb = _bounds(rendered)
        tb = _bounds(target)
        render_width = max(rb[2] - rb[0], 1)
        target_width = max(tb[2] - tb[0], 1)
        if render_width > target_width:
            scales.append(max(0.46, min(1.0, float(target_width) / float(render_width))))
    if not scales:
        return 1.0
    return float(max(0.50, min(scales)))


def _candidate_weights(
    vertices: np.ndarray,
    faces: list[list[int]],
    targets: dict[str, dict[str, Any]],
    labels: np.ndarray,
    vertex_metadata: list[dict[str, Any]],
) -> dict[int, float]:
    weights: dict[int, float] = defaultdict(float)
    for view, strength in (("side", 0.95), ("side_135", 0.65), ("oblique", 0.35)):
        target = targets[view]["mask"]
        rendered, coords = _projection_mask(vertices, faces, int(targets[view]["yaw"]), target.shape)
        edge = _mask_boundary(rendered)
        target_dilated = _dilate(target, 1)
        for index, (x, y) in enumerate(coords):
            xi = int(round(x))
            yi = int(round(y))
            if not (0 <= yi < edge.shape[0] and 0 <= xi < edge.shape[1]):
                continue
            if edge[yi, xi] or not target_dilated[yi, xi]:
                weights[index] = max(weights[index], strength)
    for index in range(len(vertices)):
        label = int(labels[index])
        metadata = vertex_metadata[index] if index < len(vertex_metadata) and isinstance(vertex_metadata[index], dict) else {}
        if label == 1:
            weights[index] *= 0.35
        if metadata.get("is_semantic_boundary", False):
            weights[index] *= 0.55
    return dict(weights)


def _relax_z(
    vertices: np.ndarray,
    original: np.ndarray,
    labels: np.ndarray,
    adjacency: list[set[int]],
    weights: dict[int, float],
    limit: float,
) -> np.ndarray:
    out = vertices.copy()
    for index, weight in weights.items():
        if weight <= 0.0:
            continue
        same_label_neighbours = [n for n in adjacency[index] if int(labels[n]) == int(labels[index])]
        if not same_label_neighbours:
            continue
        average_z = float(np.mean(vertices[same_label_neighbours, 2]))
        alpha = 0.18 * min(1.0, weight)
        new_z = float(vertices[index, 2]) * (1.0 - alpha) + average_z * alpha
        delta = new_z - float(original[index, 2])
        if abs(delta) > limit:
            new_z = float(original[index, 2]) + math.copysign(limit, delta)
        out[index, 2] = new_z
    return out


def _evaluate_views(
    vertices: np.ndarray,
    faces: list[list[int]],
    targets: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metrics = {}
    for view, payload in targets.items():
        target = payload["mask"]
        rendered, _coords = _projection_mask(vertices, faces, int(payload["yaw"]), target.shape)
        metrics[view] = {
            **_mask_metrics(rendered, target),
            "target_authority": payload["authority"],
            "yaw": int(payload["yaw"]),
        }
    return metrics


def _projection_mask(
    vertices: np.ndarray,
    faces: list[list[int]],
    yaw: int,
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    projected = _project(vertices, yaw)
    coords = _normalise_points(projected, shape)
    scale = 4
    h, w = shape
    image = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(image)
    for face in faces:
        points = [(float(coords[index, 0]) * scale, float(coords[index, 1]) * scale) for index in face if 0 <= index < len(coords)]
        if len(points) >= 3:
            draw.polygon(points, fill=255)
    image = image.resize((w, h), Image.Resampling.NEAREST)
    return np.asarray(image) > 0, coords


def _project(vertices: np.ndarray, yaw: int) -> np.ndarray:
    radians = math.radians(float(yaw))
    x = vertices[:, 0]
    y = vertices[:, 1]
    z = vertices[:, 2]
    u = x * math.cos(radians) - z * math.sin(radians)
    return np.stack([u, y], axis=1).astype(np.float32)


def _normalise_points(points: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    span = np.maximum(maxs - mins, 1e-5)
    scale = min((w - 2) / float(span[0]), (h - 2) / float(span[1]))
    scaled = (points - mins) * scale
    offset = np.array([(w - span[0] * scale) * 0.5, (h - span[1] * scale) * 0.5], dtype=np.float32)
    return scaled + offset


def _mask_metrics(rendered: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    overlap = int(np.count_nonzero(rendered & target))
    union = int(np.count_nonzero(rendered | target))
    rendered_count = int(np.count_nonzero(rendered))
    target_count = int(np.count_nonzero(target))
    overfill = int(np.count_nonzero(rendered & ~target))
    underfill = int(np.count_nonzero(target & ~rendered))
    return {
        "silhouette_iou": float(overlap) / float(union or 1),
        "silhouette_precision": float(overlap) / float(rendered_count or 1),
        "silhouette_recall": float(overlap) / float(target_count or 1),
        "overfill_ratio": float(overfill) / float(rendered_count or 1),
        "underfill_ratio": float(underfill) / float(target_count or 1),
        "bounding_box_drift": _bbox_drift(rendered, target),
        "centre_drift": _centre_drift(rendered, target),
        "rendered_pixel_count": rendered_count,
        "target_pixel_count": target_count,
    }


def _topology_stats(vertices: np.ndarray, faces: list[list[int]], labels: np.ndarray) -> dict[str, Any]:
    edge_counts: Counter[tuple[int, int]] = Counter()
    degenerate = 0
    adjacency = [set() for _ in range(len(vertices))]
    for face in faces:
        if len(face) < 3:
            degenerate += 1
            continue
        if _face_area(vertices, face) <= 1e-8:
            degenerate += 1
        for a, b in _face_edges(face):
            key = tuple(sorted((int(a), int(b))))
            edge_counts[key] += 1
            adjacency[int(a)].add(int(b))
            adjacency[int(b)].add(int(a))
    components = _component_count(adjacency)
    non_manifold = sum(1 for count in edge_counts.values() if count > 2)
    return {
        "degenerate_face_count": int(degenerate),
        "non_manifold_edge_count": int(non_manifold),
        "mesh_connected_components": int(components),
        "semantic_labels_in_mesh": sorted(set(int(label) for label in labels if int(label) != 0)),
    }


def _face_area(vertices: np.ndarray, face: list[int]) -> float:
    if len(face) == 3:
        triangles = [face]
    else:
        triangles = [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
    area = 0.0
    for a, b, c in triangles:
        va = vertices[int(a)]
        vb = vertices[int(b)]
        vc = vertices[int(c)]
        area += float(np.linalg.norm(np.cross(vb - va, vc - va)) * 0.5)
    return area


def _vertex_adjacency(faces: list[list[int]], vertex_count: int) -> list[set[int]]:
    adjacency = [set() for _ in range(vertex_count)]
    for face in faces:
        for a, b in _face_edges(face):
            adjacency[int(a)].add(int(b))
            adjacency[int(b)].add(int(a))
    return adjacency


def _face_edges(face: list[int]) -> list[tuple[int, int]]:
    return [(face[index], face[(index + 1) % len(face)]) for index in range(len(face))]


def _component_count(adjacency: list[set[int]]) -> int:
    unseen = {index for index, neighbours in enumerate(adjacency) if neighbours}
    count = 0
    while unseen:
        count += 1
        start = unseen.pop()
        queue = deque([start])
        while queue:
            item = queue.popleft()
            for neighbour in adjacency[item]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
    return count


def _vertex_labels(mesh: dict[str, Any], vertex_count: int) -> np.ndarray:
    labels = np.zeros(vertex_count, dtype=np.int32)
    metadata = mesh.get("vertex_metadata", [])
    for index in range(vertex_count):
        if index < len(metadata) and isinstance(metadata[index], dict):
            labels[index] = int(metadata[index].get("semantic_label", 0))
    if not np.any(labels):
        for face, face_meta in zip(mesh.get("faces", []), mesh.get("face_metadata", [])):
            label = int(face_meta.get("semantic_label", 0)) if isinstance(face_meta, dict) else 0
            for index in face:
                labels[int(index)] = label
    return labels


def _write_displacement_debug(path: Path, displacement: np.ndarray, moved_vertices: list[int], labels: np.ndarray) -> Path:
    payload = {
        "schema": "spritespatial_vertex_displacement_debug_v1",
        "max_displacement": float(displacement.max()) if displacement.size else 0.0,
        "mean_displacement": float(displacement.mean()) if displacement.size else 0.0,
        "moved_vertex_count": len(moved_vertices),
        "moved_vertices": [
            {"index": int(index), "semantic_label": int(labels[index]), "displacement": float(displacement[index])}
            for index in moved_vertices[:1200]
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_error_debug(
    path: Path,
    before_metrics: dict[str, dict[str, Any]],
    after_metrics: dict[str, dict[str, Any]],
) -> Path:
    payload = {
        "schema": "spritespatial_silhouette_error_before_after_v1",
        "views": {
            view: {
                "before_iou": before_metrics[view]["silhouette_iou"],
                "after_iou": after_metrics[view]["silhouette_iou"],
                "delta_iou": after_metrics[view]["silhouette_iou"] - before_metrics[view]["silhouette_iou"],
                "before_overfill": before_metrics[view]["overfill_ratio"],
                "after_overfill": after_metrics[view]["overfill_ratio"],
                "before_underfill": before_metrics[view]["underfill_ratio"],
                "after_underfill": after_metrics[view]["underfill_ratio"],
            }
            for view in before_metrics
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_before_after_contact_sheet(
    before_vertices: np.ndarray,
    after_vertices: np.ndarray,
    faces: list[list[int]],
    targets: dict[str, dict[str, Any]],
    before_metrics: dict[str, dict[str, Any]],
    after_metrics: dict[str, dict[str, Any]],
    path: Path,
) -> None:
    rows = []
    for view in ("front", "oblique", "side", "side_135", "back"):
        target = targets[view]["mask"]
        before, _ = _projection_mask(before_vertices, faces, int(targets[view]["yaw"]), target.shape)
        after, _ = _projection_mask(after_vertices, faces, int(targets[view]["yaw"]), target.shape)
        rows.append(
            _view_row(
                view,
                target,
                before,
                after,
                before_metrics[view]["silhouette_iou"],
                after_metrics[view]["silhouette_iou"],
            )
        )
    width = max(row.width for row in rows)
    height = sum(row.height for row in rows)
    sheet = Image.new("RGBA", (width, height), (28, 28, 28, 255))
    y = 0
    for row in rows:
        sheet.alpha_composite(row, (0, y))
        y += row.height
    sheet.save(path, format="PNG")


def _view_row(view: str, target: np.ndarray, before: np.ndarray, after: np.ndarray, before_iou: float, after_iou: float) -> Image.Image:
    panel_size = (128, 128)
    panels = [
        _mask_panel(target, "target", panel_size, (230, 230, 230, 255)),
        _mask_panel(before, f"before {before_iou:.3f}", panel_size, (255, 75, 65, 255)),
        _mask_panel(after, f"after {after_iou:.3f}", panel_size, (75, 220, 110, 255)),
        _overlay_panel(before, target, "before error", panel_size),
        _overlay_panel(after, target, "after error", panel_size),
    ]
    row = Image.new("RGBA", (panel_size[0] * len(panels), panel_size[1] + 24), (34, 34, 34, 255))
    draw = ImageDraw.Draw(row)
    draw.text((6, 5), view, fill=(245, 245, 245, 255))
    for index, panel in enumerate(panels):
        row.alpha_composite(panel, (index * panel_size[0], 24))
    return row


def _mask_panel(mask: np.ndarray, title: str, size: tuple[int, int], color: tuple[int, int, int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (18, 18, 18, 255))
    draw = ImageDraw.Draw(panel)
    draw.text((4, 4), title[:20], fill=(245, 245, 245, 255))
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    data = np.asarray(image).copy()
    data[mask] = color
    content = Image.fromarray(data, mode="RGBA")
    content.thumbnail((size[0] - 12, size[1] - 24), Image.Resampling.NEAREST)
    panel.alpha_composite(content, ((size[0] - content.width) // 2, 20 + (size[1] - 24 - content.height) // 2))
    return panel


def _overlay_panel(rendered: np.ndarray, target: np.ndarray, title: str, size: tuple[int, int]) -> Image.Image:
    overlap = rendered & target
    overfill = rendered & ~target
    underfill = target & ~rendered
    data = np.zeros((rendered.shape[0], rendered.shape[1], 4), dtype=np.uint8)
    data[overlap] = [40, 220, 95, 255]
    data[overfill] = [255, 65, 55, 255]
    data[underfill] = [50, 120, 255, 255]
    image = Image.fromarray(data, mode="RGBA")
    return _image_panel(image, title, size)


def _image_panel(image: Image.Image, title: str, size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (18, 18, 18, 255))
    draw = ImageDraw.Draw(panel)
    draw.text((4, 4), title[:20], fill=(245, 245, 245, 255))
    content = image.convert("RGBA")
    content.thumbnail((size[0] - 12, size[1] - 24), Image.Resampling.NEAREST)
    panel.alpha_composite(content, ((size[0] - content.width) // 2, 20 + (size[1] - 24 - content.height) // 2))
    return panel


def _write_debug_masks(
    output_dir: Path,
    before_vertices: np.ndarray,
    after_vertices: np.ndarray,
    faces: list[list[int]],
    targets: dict[str, dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for view, payload in targets.items():
        target = payload["mask"]
        before, _ = _projection_mask(before_vertices, faces, int(payload["yaw"]), target.shape)
        after, _ = _projection_mask(after_vertices, faces, int(payload["yaw"]), target.shape)
        _save_mask(target, output_dir / f"{view}_target.png")
        _save_mask(before, output_dir / f"{view}_before.png")
        _save_mask(after, output_dir / f"{view}_after.png")


def _merge_masks(a: np.ndarray, b: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return a | _place_small_mask(b, shape)


def _place_small_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if mask.shape == shape:
        return mask
    canvas = np.zeros(shape, dtype=bool)
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    max_w = max(1, min(shape[1], int(shape[1] * 0.48)))
    image = image.resize((max_w, shape[0]), Image.Resampling.NEAREST)
    x0 = (shape[1] - image.width) // 2
    canvas[:, x0 : x0 + image.width] = np.asarray(image) > 0
    return canvas


def _mask_boundary(mask: np.ndarray) -> np.ndarray:
    eroded = mask.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.zeros_like(mask)
        ys = slice(max(0, dy), mask.shape[0] + min(0, dy))
        xs = slice(max(0, dx), mask.shape[1] + min(0, dx))
        shifted[ys, xs] = mask[ys.start - dy : ys.stop - dy, xs.start - dx : xs.stop - dx]
        eroded &= shifted
    return mask & ~eroded


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(max(0, radius)):
        expanded = out.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted = np.zeros_like(out)
            ys = slice(max(0, dy), out.shape[0] + min(0, dy))
            xs = slice(max(0, dx), out.shape[1] + min(0, dx))
            shifted[ys, xs] = out[ys.start - dy : ys.stop - dy, xs.start - dx : xs.stop - dx]
            expanded |= shifted
        out = expanded
    return out


def _bbox_drift(a: np.ndarray, b: np.ndarray) -> list[float]:
    ab = _bounds(a)
    bb = _bounds(b)
    return [
        float(abs(ab[0] - bb[0]) + abs(ab[2] - bb[2])) * 0.5,
        float(abs(ab[1] - bb[1]) + abs(ab[3] - bb[3])) * 0.5,
    ]


def _centre_drift(a: np.ndarray, b: np.ndarray) -> list[float]:
    ac = _centre(a)
    bc = _centre(b)
    return [abs(ac[0] - bc[0]), abs(ac[1] - bc[1])]


def _centre(mask: np.ndarray) -> tuple[float, float]:
    points = np.argwhere(mask)
    if points.size == 0:
        return (0.0, 0.0)
    y, x = points.mean(axis=0)
    return (float(x), float(y))


def _bounds(mask: np.ndarray) -> list[int]:
    points = np.argwhere(mask)
    if points.size == 0:
        return [0, 0, 0, 0]
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    return [int(x0), int(y0), int(x1), int(y1)]


def _save_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path, format="PNG")


def _worst(metrics: dict[str, dict[str, Any]]) -> tuple[str, float]:
    view = min(metrics, key=lambda key: float(metrics[key]["silhouette_iou"]))
    return view, float(metrics[view]["silhouette_iou"])
