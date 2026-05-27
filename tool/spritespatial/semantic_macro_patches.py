from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


HARD_EDGE_LABELS = {"outline", "equipment/shield/sword"}


def load_macro_patch_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "humanoid_voxel")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "macro_patch_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = data.get("name", path.stem)
    data["path"] = str(path)
    return data


def consolidate_macro_patches(
    micro_patches: list[dict[str, Any]],
    sdf: np.ndarray,
    semantic: np.ndarray,
    semantic_part_graph: dict[str, Any] | None,
    directional_report: dict[str, Any] | None,
    profile: dict[str, Any],
    output_dir: Path,
    emit_debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    adjacency = _patch_adjacency(micro_patches)
    merge_sets = _connected_macro_sets(micro_patches, adjacency, profile)
    macro_patches = [_build_macro_patch(index, group, micro_patches, profile) for index, group in enumerate(merge_sets)]
    absorbed = _absorb_noise_fragments(macro_patches, profile)
    _renumber_macro_patches(macro_patches)
    stats = _macro_stats(micro_patches, macro_patches, absorbed)
    report = {
        "schema": "spritespatial_semantic_macro_patch_report_v1",
        "macro_patches_enabled": True,
        "macro_patch_profile": profile.get("name", "humanoid_voxel"),
        **stats,
        "semantic_part_graph_present": bool(semantic_part_graph),
        "directional_report_present": bool(directional_report),
        "passed": True,
        "fail_conditions": {},
    }
    graph = {
        "schema": "spritespatial_semantic_macro_patch_graph_v1",
        "profile": profile.get("name", "humanoid_voxel"),
        "macro_patches": macro_patches,
    }
    paths = {
        "macro_patch_graph": output_dir / "macro_patch_graph.json",
        "macro_patch_report": output_dir / "macro_patch_report.json",
        "micro_vs_macro_patch_map": output_dir / "micro_vs_macro_patch_map.png",
        "macro_patch_id_map": output_dir / "macro_patch_id_map.png",
        "macro_patch_boundary_debug": output_dir / "macro_patch_boundary_debug.png",
        "macro_patch_normal_debug": output_dir / "macro_patch_normal_debug.png",
        "absorbed_fragments_debug": output_dir / "absorbed_fragments_debug.png",
        "before_after_macro_patch_wireframe": output_dir / "before_after_macro_patch_wireframe.png",
        "before_after_contact_sheet": output_dir / "before_after_contact_sheet.png",
    }
    _write_json(paths["macro_patch_graph"], graph)
    _write_json(paths["macro_patch_report"], report)
    _write_debug_images(micro_patches, macro_patches, absorbed, paths)
    return {"patches": macro_patches, "report": report, "paths": paths, "micro_to_macro": _micro_to_macro(macro_patches)}


def _patch_adjacency(patches: list[dict[str, Any]]) -> dict[int, set[int]]:
    cell_to_patch = {}
    for patch in patches:
        patch_id = int(patch.get("patch_id", 0))
        for cell in patch.get("cells", []):
            if isinstance(cell, list) and len(cell) == 3:
                cell_to_patch[tuple(int(value) for value in cell)] = patch_id
    adjacency: dict[int, set[int]] = defaultdict(set)
    for cell, patch_id in cell_to_patch.items():
        for neighbour in _cell_neighbours(cell):
            other = cell_to_patch.get(neighbour)
            if other is not None and int(other) != int(patch_id):
                adjacency[int(patch_id)].add(int(other))
                adjacency[int(other)].add(int(patch_id))
    return adjacency


def _connected_macro_sets(
    patches: list[dict[str, Any]],
    adjacency: dict[int, set[int]],
    profile: dict[str, Any],
) -> list[list[int]]:
    by_id = {int(patch.get("patch_id", 0)): patch for patch in patches}
    remaining = set(by_id)
    groups = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        group = [start]
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for other in sorted(adjacency.get(current, set())):
                if other not in remaining:
                    continue
                if not _can_merge(by_id[current], by_id[other], profile):
                    continue
                remaining.remove(other)
                queue.append(other)
                group.append(other)
        groups.append(group)
    return groups


def _can_merge(a: dict[str, Any], b: dict[str, Any], profile: dict[str, Any]) -> bool:
    if int(a.get("semantic_label_id", 0)) != int(b.get("semantic_label_id", 0)):
        return False
    label = str(a.get("semantic_label", "unknown"))
    if label in HARD_EDGE_LABELS:
        return False
    if bool(profile.get("preserve_silhouette_bands", True)) and bool(a.get("is_silhouette_patch", False)) != bool(b.get("is_silhouette_patch", False)):
        return False
    if bool(profile.get("preserve_semantic_boundaries", True)) and bool(a.get("is_semantic_boundary_patch", False)) != bool(b.get("is_semantic_boundary_patch", False)):
        return False
    if _is_directional_feature(a) != _is_directional_feature(b):
        return False
    normal_a = np.asarray(a.get("dominant_normal", [0.0, 0.0, 1.0]), dtype=np.float32)
    normal_b = np.asarray(b.get("dominant_normal", [0.0, 0.0, 1.0]), dtype=np.float32)
    dot = float(np.dot(_safe_normal(normal_a), _safe_normal(normal_b)))
    angle = math.radians(float(profile.get("normal_merge_angle_deg", 38.0)))
    if dot < math.cos(angle):
        return False
    curvature_delta = abs(float(a.get("curvature_score", 0.0)) - float(b.get("curvature_score", 0.0)))
    if curvature_delta > float(profile.get("curvature_merge_threshold", 0.32)):
        return False
    return True


def _build_macro_patch(
    macro_id: int,
    group: list[int],
    micro_patches: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    by_id = {int(patch.get("patch_id", 0)): patch for patch in micro_patches}
    members = [by_id[index] for index in group]
    cells = [cell for patch in members for cell in patch.get("cells", [])]
    normals = np.asarray([patch.get("dominant_normal", [0.0, 0.0, 1.0]) for patch in members], dtype=np.float32)
    dominant = _safe_normal(np.mean(normals, axis=0) if normals.size else np.asarray([0.0, 0.0, 1.0], dtype=np.float32))
    curvature = float(np.mean([float(patch.get("curvature_score", 0.0)) for patch in members])) if members else 0.0
    cell_count = sum(int(patch.get("cell_count", 0)) for patch in members)
    semantic_label = str(members[0].get("semantic_label", "unknown")) if members else "unknown"
    semantic_label_id = int(members[0].get("semantic_label_id", 0)) if members else 0
    is_silhouette = any(bool(patch.get("is_silhouette_patch", False)) for patch in members)
    is_boundary = any(bool(patch.get("is_semantic_boundary_patch", False)) for patch in members)
    directional = any(_is_directional_feature(patch) for patch in members)
    macro_class = _macro_class(semantic_label, cell_count, curvature, is_silhouette, is_boundary, directional, profile)
    return {
        "macro_patch_id": macro_id,
        "patch_id": macro_id,
        "semantic_label": semantic_label,
        "semantic_label_id": semantic_label_id,
        "micro_patch_ids": sorted(group),
        "cell_count": cell_count,
        "dominant_normal": [float(value) for value in dominant.tolist()],
        "curvature_score": curvature,
        "is_silhouette_patch": is_silhouette,
        "is_semantic_boundary_patch": is_boundary,
        "is_planar_patch": macro_class == "planar_surface",
        "macro_patch_class": macro_class,
        "cells": cells,
    }


def _absorb_noise_fragments(macro_patches: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    min_size = int(profile.get("min_macro_patch_size", 8))
    adjacency = _patch_adjacency(
        [
            {
                "patch_id": patch["macro_patch_id"],
                "semantic_label_id": patch["semantic_label_id"],
                "cells": patch["cells"],
            }
            for patch in macro_patches
        ]
    )
    by_id = {int(patch["macro_patch_id"]): patch for patch in macro_patches}
    absorbed = []
    for patch in list(macro_patches):
        patch_id = int(patch["macro_patch_id"])
        if int(patch.get("cell_count", 0)) >= min_size:
            continue
        if patch.get("is_silhouette_patch") or patch.get("macro_patch_class") == "directional_feature":
            continue
        candidates = [
            by_id[other]
            for other in adjacency.get(patch_id, set())
            if int(by_id[other].get("semantic_label_id", 0)) == int(patch.get("semantic_label_id", 0))
            and int(by_id[other].get("cell_count", 0)) >= int(patch.get("cell_count", 0))
        ]
        if not candidates:
            continue
        target = max(candidates, key=lambda item: int(item.get("cell_count", 0)))
        target["cells"].extend(patch.get("cells", []))
        target["micro_patch_ids"].extend(patch.get("micro_patch_ids", []))
        target["cell_count"] = int(target.get("cell_count", 0)) + int(patch.get("cell_count", 0))
        patch["absorbed_into"] = int(target["macro_patch_id"])
        patch["macro_patch_class"] = "noise_fragment"
        absorbed.append(
            {
                "macro_patch_id": patch_id,
                "absorbed_into": int(target["macro_patch_id"]),
                "cell_count": int(patch.get("cell_count", 0)),
                "semantic_label": patch.get("semantic_label", "unknown"),
            }
        )
    if absorbed:
        macro_patches[:] = [patch for patch in macro_patches if "absorbed_into" not in patch]
    return absorbed


def _renumber_macro_patches(macro_patches: list[dict[str, Any]]) -> None:
    for index, patch in enumerate(macro_patches):
        patch["macro_patch_id"] = index
        patch["patch_id"] = index


def _macro_class(
    label: str,
    cell_count: int,
    curvature: float,
    is_silhouette: bool,
    is_boundary: bool,
    directional: bool,
    profile: dict[str, Any],
) -> str:
    if directional:
        return "directional_feature"
    if is_silhouette and bool(profile.get("preserve_silhouette_bands", True)):
        return "silhouette_band"
    if is_boundary and bool(profile.get("preserve_semantic_boundaries", True)):
        return "semantic_boundary_band"
    if cell_count < int(profile.get("min_macro_patch_size", 8)):
        return "noise_fragment"
    if curvature <= float(profile.get("planar_curvature_threshold", profile.get("curvature_merge_threshold", 0.35))):
        return "planar_surface"
    return "curved_surface"


def _macro_stats(
    micro_patches: list[dict[str, Any]],
    macro_patches: list[dict[str, Any]],
    absorbed: list[dict[str, Any]],
) -> dict[str, Any]:
    sizes = [int(patch.get("cell_count", 0)) for patch in macro_patches]
    total = max(len(sizes), 1)
    small = sum(1 for size in sizes if size <= 2)
    micro_count = len(micro_patches)
    macro_count = len(macro_patches)
    return {
        "micro_patch_count": micro_count,
        "macro_patch_count": macro_count,
        "macro_patch_reduction_ratio": float(micro_count - macro_count) / float(max(micro_count, 1)),
        "mean_macro_patch_size": float(np.mean(sizes)) if sizes else 0.0,
        "small_macro_patch_ratio": float(small) / float(total),
        "planar_macro_patch_count": sum(1 for patch in macro_patches if patch.get("macro_patch_class") == "planar_surface"),
        "curved_macro_patch_count": sum(1 for patch in macro_patches if patch.get("macro_patch_class") == "curved_surface"),
        "directional_feature_macro_patch_count": sum(1 for patch in macro_patches if patch.get("macro_patch_class") == "directional_feature"),
        "silhouette_macro_patch_count": sum(1 for patch in macro_patches if patch.get("macro_patch_class") == "silhouette_band"),
        "semantic_boundary_macro_patch_count": sum(1 for patch in macro_patches if patch.get("macro_patch_class") == "semantic_boundary_band"),
        "noise_fragments_absorbed": len(absorbed),
        "macro_patch_coherence_score": _coherence_score(micro_count, macro_count, sizes, small),
    }


def _coherence_score(micro_count: int, macro_count: int, sizes: list[int], small: int) -> float:
    reduction = float(micro_count - macro_count) / float(max(micro_count, 1))
    mean_score = min(1.0, (float(np.mean(sizes)) if sizes else 0.0) / 10.0)
    small_score = 1.0 - float(small) / float(max(len(sizes), 1))
    return float(max(0.0, min(1.0, 0.45 * reduction + 0.30 * mean_score + 0.25 * small_score)))


def _micro_to_macro(macro_patches: list[dict[str, Any]]) -> dict[int, int]:
    result = {}
    for macro in macro_patches:
        macro_id = int(macro["macro_patch_id"])
        for micro_id in macro.get("micro_patch_ids", []):
            result[int(micro_id)] = macro_id
    return result


def _is_directional_feature(patch: dict[str, Any]) -> bool:
    if str(patch.get("semantic_label", "")) != "hair/hat":
        return False
    cells = patch.get("cells", [])
    if not cells:
        return False
    z_values = [int(cell[2]) for cell in cells if isinstance(cell, list) and len(cell) == 3]
    if not z_values:
        return False
    return min(z_values) <= min(z_values) + 1


def _cell_neighbours(cell: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    y, x, z = cell
    return [(y - 1, x, z), (y + 1, x, z), (y, x - 1, z), (y, x + 1, z), (y, x, z - 1), (y, x, z + 1)]


def _safe_normal(normal: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(normal))
    if length <= 1e-8:
        return np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    return normal / length


def _write_debug_images(
    micro_patches: list[dict[str, Any]],
    macro_patches: list[dict[str, Any]],
    absorbed: list[dict[str, Any]],
    paths: dict[str, Path],
) -> None:
    _write_patch_map(macro_patches, paths["macro_patch_id_map"], "macro")
    _write_patch_map(macro_patches, paths["macro_patch_boundary_debug"], "boundary")
    _write_patch_map(macro_patches, paths["macro_patch_normal_debug"], "normal")
    _write_micro_vs_macro(micro_patches, macro_patches, paths["micro_vs_macro_patch_map"])
    _write_absorbed(absorbed, macro_patches, paths["absorbed_fragments_debug"])


def _write_patch_map(patches: list[dict[str, Any]], path: Path, mode: str) -> None:
    image = _patch_canvas(patches)
    draw = ImageDraw.Draw(image)
    scale = 6
    for patch in patches:
        if mode == "boundary":
            color = (255, 80, 80, 255) if patch.get("is_semantic_boundary_patch") else (60, 160, 180, 255)
        elif mode == "normal":
            normal = np.asarray(patch.get("dominant_normal", [0, 0, 1]), dtype=np.float32)
            axis = int(np.argmax(np.abs(normal)))
            color = [(240, 80, 80, 255), (80, 220, 120, 255), (100, 150, 255, 255)][axis]
        else:
            color = _patch_color(int(patch["macro_patch_id"]))
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=color)
    image.save(path, format="PNG")


def _write_micro_vs_macro(
    micro_patches: list[dict[str, Any]],
    macro_patches: list[dict[str, Any]],
    path: Path,
) -> None:
    left = _patch_canvas(micro_patches)
    right = _patch_canvas(macro_patches)
    _paint_patch_ids(left, micro_patches, "patch_id")
    _paint_patch_ids(right, macro_patches, "macro_patch_id")
    width = max(left.width, right.width)
    height = max(left.height, right.height)
    sheet = Image.new("RGBA", (width * 2, height), (0, 0, 0, 255))
    sheet.alpha_composite(left, (0, 0))
    sheet.alpha_composite(right, (width, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((2, 2), "micro", fill=(255, 255, 255, 255))
    draw.text((width + 2, 2), "macro", fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _paint_patch_ids(image: Image.Image, patches: list[dict[str, Any]], key: str) -> None:
    draw = ImageDraw.Draw(image)
    scale = 6
    for patch in patches:
        color = _patch_color(int(patch.get(key, 0)))
        for y, x, _z in patch.get("cells", []):
            draw.rectangle((x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1), fill=color)


def _write_absorbed(absorbed: list[dict[str, Any]], macro_patches: list[dict[str, Any]], path: Path) -> None:
    image = _patch_canvas(macro_patches)
    draw = ImageDraw.Draw(image)
    draw.text((2, 2), f"absorbed: {len(absorbed)}", fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _patch_canvas(patches: list[dict[str, Any]], scale: int = 6) -> Image.Image:
    cells = [cell for patch in patches for cell in patch.get("cells", [])]
    if not cells:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 255))
    height = max(int(cell[0]) for cell in cells) + 2
    width = max(int(cell[1]) for cell in cells) + 2
    return Image.new("RGBA", (width * scale, height * scale), (0, 45, 55, 255))


def _patch_color(index: int) -> tuple[int, int, int, int]:
    return (int((index * 73) % 255), int((index * 151 + 80) % 255), int((index * 199 + 130) % 255), 255)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
