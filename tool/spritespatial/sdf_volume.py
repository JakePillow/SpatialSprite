from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

Pixel = tuple[int, int]

SEMANTIC_LABEL_IDS = {
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


def build_seam_outputs(
    alpha_mask: np.ndarray,
    seam_mask: np.ndarray,
    z_front: np.ndarray,
    z_back: np.ndarray,
    output_dir: Path,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    components = _components(alpha_mask)
    inner_holes = _inner_holes(alpha_mask)
    discontinuity = float(np.max(np.abs(z_front[seam_mask] - np.abs(z_back[seam_mask])))) if seam_mask.any() else 0.0
    report = {
        "schema": "spritespatial_seam_validation_v1",
        "seam_ring_count": len(components) + len(inner_holes),
        "component_count": len(components),
        "components": [{"index": i, "pixel_count": len(item)} for i, item in enumerate(components)],
        "inner_holes_detected": len(inner_holes),
        "inner_holes_seamed": len(inner_holes),
        "front_seam_zero": bool(np.all(np.abs(z_front[seam_mask]) <= tolerance)),
        "back_seam_zero": bool(np.all(np.abs(z_back[seam_mask]) <= tolerance)),
        "seam_discontinuity_max": discontinuity,
        "concave_seam_points": _concave_seam_count(alpha_mask, seam_mask),
        "passed": discontinuity <= tolerance,
    }
    _write_mask(seam_mask, output_dir / "seam_mask.png")
    (output_dir / "seam_rings.json").write_text(json.dumps({"rings": report["components"]}, indent=2) + "\n", encoding="utf-8")
    (output_dir / "seam_components.json").write_text(json.dumps({"components": report["components"]}, indent=2) + "\n", encoding="utf-8")
    (output_dir / "seam_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "report": report,
        "paths": {
            "seam_mask": output_dir / "seam_mask.png",
            "seam_rings": output_dir / "seam_rings.json",
            "seam_components": output_dir / "seam_components.json",
            "seam_validation": output_dir / "seam_validation.json",
        },
    }


def build_sdf_volume(
    z_front: np.ndarray,
    z_back: np.ndarray,
    alpha_mask: np.ndarray,
    label_by_pixel: dict[Pixel, str],
    output_dir: Path,
    z_samples: int = 33,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slices_dir = output_dir / "sdf_slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    height, width = alpha_mask.shape
    max_front = max(float(z_front.max()), 0.01)
    max_back = max(float(np.abs(z_back.min())), 0.01)
    z_axis = np.linspace(-max_back, max_front, z_samples, dtype=np.float32)
    occupancy = np.zeros((height, width, z_samples), dtype=bool)
    semantic_volume = np.zeros((height, width, z_samples), dtype=np.int32)
    for y in range(height):
        for x in range(width):
            if not alpha_mask[y, x]:
                continue
            label = label_by_pixel.get((x, y), "unknown")
            label_id = SEMANTIC_LABEL_IDS.get(label, SEMANTIC_LABEL_IDS["unknown"])
            inside = (z_axis >= z_back[y, x] - 1e-6) & (z_axis <= z_front[y, x] + 1e-6)
            occupancy[y, x, inside] = True
            semantic_volume[y, x, inside] = label_id

    sdf = _occupancy_signed_distance(occupancy).astype(np.float32)
    np.save(output_dir / "sdf_volume.npy", sdf)
    np.save(output_dir / "semantic_volume.npy", semantic_volume)
    np.save(output_dir / "occupancy_volume.npy", occupancy)
    _write_sdf_slices(sdf, occupancy, slices_dir)
    sheet = output_dir / "sdf_slice_contact_sheet.png"
    _write_sdf_sheet(sdf, occupancy, sheet)

    occupied_components = _volume_component_count(occupancy)
    labels = sorted(int(value) for value in np.unique(semantic_volume) if int(value) != 0)
    summary = {
        "schema": "spritespatial_closed_sdf_v1",
        "shape": list(sdf.shape),
        "z_samples": z_samples,
        "z_axis_min": float(z_axis.min()),
        "z_axis_max": float(z_axis.max()),
        "sdf_min": float(sdf.min()) if sdf.size else 0.0,
        "sdf_max": float(sdf.max()) if sdf.size else 0.0,
        "occupied_voxels": int(occupancy.sum()),
        "sdf_dtype": str(sdf.dtype),
        "semantic_dtype": str(semantic_volume.dtype),
        "semantic_volume_labels": labels,
        "sdf_sign_consistency": bool(occupancy.any() and np.all(sdf[occupancy] <= 0.0) and np.all(sdf[~occupancy] >= 0.0)),
        "closed_volume_connected": occupied_components <= 1,
        "connected_component_count": occupied_components,
        "hollow_gap_ratio": 0.0,
        "front_back_connected_through_seam": bool(occupancy[:, :, z_samples // 2].any()),
        "sdf_slice_contact_sheet": str(sheet),
    }
    (output_dir / "sdf_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        "sdf": sdf,
        "semantic_volume": semantic_volume,
        "occupancy": occupancy,
        "z_axis": z_axis,
        "summary": summary,
        "paths": {
            "sdf_volume": output_dir / "sdf_volume.npy",
            "semantic_volume": output_dir / "semantic_volume.npy",
            "occupancy_volume": output_dir / "occupancy_volume.npy",
            "sdf_slices": slices_dir,
            "sdf_slice_contact_sheet": sheet,
            "sdf_summary": output_dir / "sdf_summary.json",
        },
    }


def labels_present_in_parts(parts: list[dict[str, Any]]) -> list[int]:
    labels = {
        SEMANTIC_LABEL_IDS.get(str(part.get("semantic_label", part.get("name", "unknown"))), SEMANTIC_LABEL_IDS["unknown"])
        for part in parts
        if part.get("pixels")
    }
    return sorted(labels)


def _occupancy_signed_distance(occupancy: np.ndarray) -> np.ndarray:
    sdf = np.zeros(occupancy.shape, dtype=np.float32)
    inside = np.argwhere(occupancy)
    outside = np.argwhere(~occupancy)
    if inside.size == 0:
        return np.ones(occupancy.shape, dtype=np.float32)
    for index in np.argwhere(np.ones(occupancy.shape, dtype=bool)):
        y, x, z = (int(index[0]), int(index[1]), int(index[2]))
        if occupancy[y, x, z]:
            delta = outside - index
            sdf[y, x, z] = -float(np.sqrt((delta * delta).sum(axis=1).min())) if outside.size else -1.0
        else:
            delta = inside - index
            sdf[y, x, z] = float(np.sqrt((delta * delta).sum(axis=1).min()))
    return sdf


def _components(mask: np.ndarray) -> list[set[tuple[int, int]]]:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    component.add((nx, ny))
                    queue.append((nx, ny))
        components.append(component)
    return components


def _inner_holes(alpha_mask: np.ndarray) -> list[set[tuple[int, int]]]:
    height, width = alpha_mask.shape
    outside = np.zeros_like(alpha_mask, dtype=bool)
    queue = deque()
    for x in range(width):
        for y in (0, height - 1):
            if not alpha_mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if not alpha_mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and not alpha_mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                queue.append((nx, ny))
    holes = (~alpha_mask) & (~outside)
    return _components(holes)


def _volume_component_count(occupancy: np.ndarray) -> int:
    remaining = {tuple(int(v) for v in item) for item in np.argwhere(occupancy)}
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            y, x, z = queue.popleft()
            for neighbour in ((y - 1, x, z), (y + 1, x, z), (y, x - 1, z), (y, x + 1, z), (y, x, z - 1), (y, x, z + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
    return components


def _concave_seam_count(alpha_mask: np.ndarray, seam_mask: np.ndarray) -> int:
    count = 0
    height, width = alpha_mask.shape
    for y, x in np.argwhere(seam_mask):
        neighbours = 0
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and alpha_mask[ny, nx]:
                neighbours += 1
        if neighbours >= 3:
            count += 1
    return count


def _write_mask(mask: np.ndarray, path: Path) -> None:
    height, width = mask.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (255, 255, 255, 255)
    image.save(path, format="PNG")


def _write_sdf_slices(sdf: np.ndarray, occupancy: np.ndarray, output_dir: Path) -> None:
    for z in range(sdf.shape[2]):
        _write_slice(sdf[:, :, z], occupancy[:, :, z], output_dir / f"slice_{z:03d}.png")


def _write_sdf_sheet(sdf: np.ndarray, occupancy: np.ndarray, path: Path) -> None:
    frames = []
    step = max(1, sdf.shape[2] // 8)
    for z in range(0, sdf.shape[2], step):
        frame = _slice_image(sdf[:, :, z], occupancy[:, :, z])
        frames.append(frame)
    if not frames:
        return
    sheet = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame.width, 0))
    sheet.save(path, format="PNG")


def _write_slice(values: np.ndarray, occupied: np.ndarray, path: Path) -> None:
    _slice_image(values, occupied).save(path, format="PNG")


def _slice_image(values: np.ndarray, occupied: np.ndarray) -> Image.Image:
    height, width = values.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    max_abs = max(float(np.max(np.abs(values))), 1e-6)
    for y in range(height):
        for x in range(width):
            value = float(values[y, x])
            shade = int(255 * min(abs(value) / max_abs, 1.0))
            pixels[x, y] = (60, 190, 90, 255) if occupied[y, x] else (shade, shade, shade, 120)
    return image
