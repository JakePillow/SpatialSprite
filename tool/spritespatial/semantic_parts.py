from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

Pixel = tuple[int, int]

CANONICAL_LABELS = [
    "outline",
    "head",
    "face",
    "hair/hat",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "boots/feet",
    "equipment/shield/sword",
    "unknown",
]

REQUIRED_HUMANOID_LABELS = {"head", "torso", "left_leg", "right_leg"}

PALETTE = {
    "outline": (8, 8, 8, 255),
    "head": (235, 92, 66, 255),
    "face": (255, 193, 112, 255),
    "hair/hat": (104, 70, 210, 255),
    "torso": (52, 153, 222, 255),
    "left_arm": (63, 184, 121, 255),
    "right_arm": (50, 162, 106, 255),
    "left_leg": (196, 138, 52, 255),
    "right_leg": (143, 178, 55, 255),
    "boots/feet": (128, 73, 41, 255),
    "equipment/shield/sword": (230, 213, 72, 255),
    "unknown": (190, 83, 210, 255),
}


def consolidate_semantic_parts(
    source: Image.Image,
    semantic_parts: list[dict[str, Any]],
    raw_regions: list[set[Pixel]],
    part_graph: list[Any],
    override_masks: dict[str, set[Pixel]] | None,
    semantic_authority_report: dict[str, Any] | None,
    output_dir: Path,
    emit_debug: bool = False,
    tiny_orphan_threshold: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "masks"
    masks_dir.mkdir(exist_ok=True)

    raw_region_count = len(part_graph)
    initial_groups = _groups_by_label(semantic_parts)
    seam = _source_seam(source)
    absorbed_pixels: dict[Pixel, str] = {}
    outline_debris: set[Pixel] = set()
    groups = {label: set(pixels) for label, pixels in initial_groups.items()}

    for label in list(CANONICAL_LABELS):
        pixels = set(groups.get(label, set()))
        if not pixels:
            continue
        for component in _components(pixels):
            if len(component) > tiny_orphan_threshold:
                continue
            if label == "outline" and component & seam:
                continue
            target = _nearest_compatible_label(component, groups, label)
            if target is None:
                continue
            groups[label].difference_update(component)
            groups.setdefault(target, set()).update(component)
            for pixel in component:
                absorbed_pixels[pixel] = target
            if label == "outline":
                outline_debris.update(component)

    parts = []
    graph_parts = []
    pixel_owner = _pixel_owner(groups)
    for label in CANONICAL_LABELS:
        pixels = groups.get(label, set())
        if not pixels:
            continue
        part_id = _part_id(label)
        mask_path = masks_dir / f"{part_id}.png"
        _write_mask(source.size, pixels, mask_path)
        region_ids = _region_ids_for_pixels(pixels, raw_regions)
        attachments = _attachment_labels(pixels, pixel_owner, label, source.size)
        part = {
            "name": part_id,
            "semantic_label": label,
            "pixels": pixels,
            "bbox": _bbox(pixels),
            "dominant_colour": _dominant_colour(source, pixels),
            "geometry_authority": "canonical_part",
            "region_ids": region_ids,
        }
        parts.append(part)
        graph_parts.append(
            {
                "part_id": part_id,
                "semantic_label": label,
                "region_ids": region_ids,
                "merged_mask": str(mask_path),
                "pixel_count": len(pixels),
                "bbox": _bbox(pixels),
                "centroid": _centroid(pixels),
                "component_count": _component_count(pixels),
                "attachment_labels": attachments,
                "geometry_authority": "canonical_part",
            }
        )

    canonical_part_count = len(parts)
    required_missing = sorted(label for label in REQUIRED_HUMANOID_LABELS if not groups.get(label))
    report = {
        "schema": "spritespatial_semantic_part_graph_v1",
        "semantic_parts_enabled": True,
        "raw_region_count": raw_region_count,
        "raw_semantic_part_count": len([part for part in semantic_parts if part.get("pixels")]),
        "canonical_part_count": canonical_part_count,
        "part_reduction_ratio": float((raw_region_count - canonical_part_count) / max(raw_region_count, 1)),
        "tiny_orphans_absorbed": len(absorbed_pixels),
        "outline_debris_removed": len(outline_debris),
        "geometry_uses_canonical_parts": True,
        "canonical_required_parts_present": not required_missing,
        "missing_required_parts": required_missing,
        "canonical_part_count_warning": canonical_part_count > 20,
        "semantic_authority_passed": bool((semantic_authority_report or {}).get("passed", True)),
        "override_mask_labels_present": sorted(_override_labels(override_masks or {})),
        "parts": graph_parts,
        "warnings": ["Canonical part count exceeds expected prototype humanoid range."]
        if canonical_part_count > 20
        else [],
        "passed": not required_missing,
    }

    paths = {
        "semantic_part_graph": output_dir / "semantic_part_graph.json",
        "canonical_parts_overlay": output_dir / "canonical_parts_overlay.png",
        "raw_vs_canonical_parts": output_dir / "raw_vs_canonical_parts.png",
        "orphan_absorption_debug": output_dir / "orphan_absorption_debug.png",
        "outline_debris_debug": output_dir / "outline_debris_debug.png",
        "part_reduction_report": output_dir / "part_reduction_report.json",
    }
    _write_json(paths["semantic_part_graph"], report)
    _write_json(paths["part_reduction_report"], {key: value for key, value in report.items() if key != "parts"})
    _write_overlay(source.size, groups, paths["canonical_parts_overlay"])
    _write_raw_vs_canonical(source.size, semantic_parts, groups, paths["raw_vs_canonical_parts"])
    _write_absorption_debug(source.size, absorbed_pixels, paths["orphan_absorption_debug"])
    _write_pixels(source.size, outline_debris, (255, 235, 65, 255), paths["outline_debris_debug"])

    if emit_debug:
        components_dir = output_dir / "components"
        components_dir.mkdir(exist_ok=True)
        for item in graph_parts:
            _write_mask(source.size, groups[item["semantic_label"]], components_dir / f"{item['part_id']}_components.png")
        paths["components"] = components_dir

    return {"parts": parts, "report": report, "paths": paths}


def _groups_by_label(parts: list[dict[str, Any]]) -> dict[str, set[Pixel]]:
    groups = {label: set() for label in CANONICAL_LABELS}
    for part in parts:
        label = _canonical_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        groups.setdefault(label, set()).update({(int(x), int(y)) for x, y in part.get("pixels", set())})
    return groups


def _canonical_label(label: str) -> str:
    return {
        "hair": "hair/hat",
        "hat_hair": "hair/hat",
        "cap": "hair/hat",
        "left_foot": "boots/feet",
        "right_foot": "boots/feet",
        "boots_feet": "boots/feet",
        "equipment": "equipment/shield/sword",
        "shield": "equipment/shield/sword",
        "sword": "equipment/shield/sword",
    }.get(label, label if label in CANONICAL_LABELS else "unknown")


def _part_id(label: str) -> str:
    return label.replace("/", "_")


def _source_seam(source: Image.Image) -> set[Pixel]:
    rgba = source.convert("RGBA")
    pixels = rgba.load()
    opaque = {
        (x, y)
        for y in range(rgba.height)
        for x in range(rgba.width)
        if pixels[x, y][3] > 16
    }
    seam = set()
    for x, y in opaque:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= rgba.width or ny >= rgba.height or (nx, ny) not in opaque:
                seam.add((x, y))
                break
    return seam


def _nearest_compatible_label(component: set[Pixel], groups: dict[str, set[Pixel]], source_label: str) -> str | None:
    candidates: Counter[str] = Counter()
    for x, y in component:
        for nx, ny in _neighbours8(x, y):
            for label, pixels in groups.items():
                if label == source_label or not pixels:
                    continue
                if (nx, ny) in pixels and _compatible(source_label, label):
                    candidates[label] += 1
    return candidates.most_common(1)[0][0] if candidates else None


def _compatible(source_label: str, target_label: str) -> bool:
    if source_label == "outline":
        return target_label != "outline"
    if source_label == "unknown":
        return target_label != "outline"
    if source_label == "boots/feet":
        return target_label in {"left_leg", "right_leg"}
    return target_label in CANONICAL_LABELS and target_label != "outline"


def _pixel_owner(groups: dict[str, set[Pixel]]) -> dict[Pixel, str]:
    owner = {}
    for label, pixels in groups.items():
        for pixel in pixels:
            owner[pixel] = label
    return owner


def _attachment_labels(pixels: set[Pixel], owner: dict[Pixel, str], label: str, size: tuple[int, int]) -> list[str]:
    width, height = size
    attachments = set()
    for x, y in pixels:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                other = owner.get((nx, ny))
                if other and other != label:
                    attachments.add(other)
    return sorted(attachments)


def _region_ids_for_pixels(pixels: set[Pixel], raw_regions: list[set[Pixel]]) -> list[int]:
    ids = []
    for index, region in enumerate(raw_regions):
        if pixels & region:
            ids.append(index)
    return ids


def _components(pixels: set[Pixel]) -> list[set[Pixel]]:
    remaining = set(pixels)
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for neighbour in _neighbours8(x, y):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
                    component.add(neighbour)
        components.append(component)
    return components


def _component_count(pixels: set[Pixel]) -> int:
    return len(_components(pixels)) if pixels else 0


def _neighbours8(x: int, y: int) -> tuple[Pixel, ...]:
    return (
        (x - 1, y - 1),
        (x, y - 1),
        (x + 1, y - 1),
        (x - 1, y),
        (x + 1, y),
        (x - 1, y + 1),
        (x, y + 1),
        (x + 1, y + 1),
    )


def _bbox(pixels: set[Pixel]) -> list[int]:
    if not pixels:
        return [0, 0, 0, 0]
    xs = [x for x, _y in pixels]
    ys = [y for _x, y in pixels]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def _centroid(pixels: set[Pixel]) -> list[float]:
    if not pixels:
        return [0.0, 0.0]
    return [
        round(sum(x for x, _y in pixels) / len(pixels), 3),
        round(sum(y for _x, y in pixels) / len(pixels), 3),
    ]


def _dominant_colour(source: Image.Image, pixels: set[Pixel]) -> tuple[int, int, int, int]:
    rgba = source.convert("RGBA").load()
    colours = [rgba[x, y] for x, y in pixels if rgba[x, y][3] > 16]
    return Counter(colours).most_common(1)[0][0] if colours else (255, 0, 255, 255)


def _override_labels(masks: dict[str, set[Pixel]]) -> set[str]:
    labels = set()
    for name, pixels in masks.items():
        if pixels:
            labels.add(_canonical_label(name))
    return labels


def _write_mask(size: tuple[int, int], pixels_set: set[Pixel], path: Path) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for x, y in pixels_set:
        pixels[x, y] = (255, 255, 255, 255)
    image.save(path, format="PNG")


def _write_overlay(size: tuple[int, int], groups: dict[str, set[Pixel]], path: Path) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for label, part_pixels in groups.items():
        colour = PALETTE.get(label, PALETTE["unknown"])
        for x, y in part_pixels:
            pixels[x, y] = colour
    image.save(path, format="PNG")


def _write_raw_vs_canonical(
    size: tuple[int, int],
    raw_parts: list[dict[str, Any]],
    groups: dict[str, set[Pixel]],
    path: Path,
) -> None:
    raw_groups = _groups_by_label(raw_parts)
    raw = Image.new("RGBA", size, (0, 0, 0, 0))
    canonical = Image.new("RGBA", size, (0, 0, 0, 0))
    raw_pixels = raw.load()
    canonical_pixels = canonical.load()
    for label, part_pixels in raw_groups.items():
        colour = PALETTE.get(label, PALETTE["unknown"])
        for x, y in part_pixels:
            raw_pixels[x, y] = colour
    for label, part_pixels in groups.items():
        colour = PALETTE.get(label, PALETTE["unknown"])
        for x, y in part_pixels:
            canonical_pixels[x, y] = colour
    sheet = Image.new("RGBA", (size[0] * 2, size[1]), (0, 0, 0, 0))
    sheet.alpha_composite(raw, (0, 0))
    sheet.alpha_composite(canonical, (size[0], 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((1, 1), "raw", fill=(255, 255, 255, 255))
    draw.text((size[0] + 1, 1), "canonical", fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def _write_absorption_debug(size: tuple[int, int], absorbed: dict[Pixel, str], path: Path) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for (x, y), target in absorbed.items():
        pixels[x, y] = PALETTE.get(target, (255, 0, 255, 255))
    image.save(path, format="PNG")


def _write_pixels(size: tuple[int, int], pixels_set: set[Pixel], colour: tuple[int, int, int, int], path: Path) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for pixel in pixels_set:
        draw.point(pixel, fill=colour)
    image.save(path, format="PNG")


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(key): _json_safe(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_json_safe(value) for value in data]
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(data), indent=2) + "\n", encoding="utf-8")
