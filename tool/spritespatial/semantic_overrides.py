from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

Pixel = tuple[int, int]

OVERRIDE_FILES = {
    "head.png": ("head", "head"),
    "face.png": ("face", "face"),
    "hat_hair.png": ("hair", "hair/hat"),
    "torso.png": ("torso", "torso"),
    "left_arm.png": ("left_arm", "left_arm"),
    "right_arm.png": ("right_arm", "right_arm"),
    "left_leg.png": ("left_leg", "left_leg"),
    "right_leg.png": ("right_leg", "right_leg"),
    "boots_feet.png": ("boots_feet", "boots/feet"),
    "equipment.png": ("equipment", "equipment/shield/sword"),
    "outline.png": ("outline", "outline"),
}

PART_ORDER = [
    "outline",
    "head",
    "face",
    "hair",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "left_foot",
    "right_foot",
    "equipment",
    "unknown",
]

OVERRIDE_PRIORITY = [
    "outline",
    "equipment",
    "hair",
    "face",
    "head",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "left_foot",
    "right_foot",
    "boots_feet",
    "unknown",
]

SEMANTIC_COLOURS = {
    "outline": (8, 8, 8, 255),
    "head": (245, 190, 126, 255),
    "face": (255, 214, 156, 255),
    "hair": (118, 78, 42, 255),
    "torso": (48, 178, 220, 255),
    "left_arm": (255, 144, 74, 255),
    "right_arm": (252, 113, 109, 255),
    "left_leg": (62, 111, 226, 255),
    "right_leg": (91, 139, 255, 255),
    "left_foot": (156, 80, 48, 255),
    "right_foot": (156, 80, 48, 255),
    "equipment": (220, 208, 92, 255),
    "unknown": (210, 70, 230, 255),
}


def load_semantic_overrides(
    override_dir: Path | None,
    size: tuple[int, int],
    mode: str = "supplement",
) -> dict[str, Any]:
    if mode not in {"none", "supplement", "replace", "strict"}:
        raise ValueError(f"Unsupported semantic override mode: {mode}")
    masks: dict[str, set[Pixel]] = {}
    report: dict[str, Any] = {
        "schema": "spritespatial_semantic_override_report_v1",
        "mode": mode,
        "override_dir": str(override_dir) if override_dir else "",
        "loaded_masks": {},
        "missing_masks": [],
        "dimension_mismatches": [],
        "override_pixels_applied": 0,
        "override_overlap_count": 0,
        "overlap_pixels": [],
        "passed": True,
        "failures": [],
    }
    if mode == "none" or not override_dir or not override_dir.exists():
        return {"masks": masks, "report": report}

    owner_count: Counter[Pixel] = Counter()
    for filename, (part_name, _semantic_label) in OVERRIDE_FILES.items():
        path = override_dir / filename
        if not path.exists():
            report["missing_masks"].append(filename)
            continue
        image = Image.open(path).convert("RGBA")
        if image.size != size:
            report["dimension_mismatches"].append(
                {"file": filename, "size": list(image.size), "expected": list(size)}
            )
            continue
        pixels = _mask_pixels(image)
        masks[part_name] = pixels
        for pixel in pixels:
            owner_count[pixel] += 1
        report["loaded_masks"][part_name] = {
            "file": str(path),
            "pixel_count": len(pixels),
            "coverage": len(pixels) / max(size[0] * size[1], 1),
        }

    overlap_pixels = [pixel for pixel, count in owner_count.items() if count > 1]
    report["override_pixels_applied"] = sum(len(pixels) for pixels in masks.values())
    report["override_overlap_count"] = len(overlap_pixels)
    report["override_overlap_ratio"] = len(overlap_pixels) / max(int(report["override_pixels_applied"]), 1)
    report["overlap_pixels"] = [list(pixel) for pixel in overlap_pixels[:200]]
    if report["dimension_mismatches"]:
        report["passed"] = False
        report["failures"].append("override dimensions mismatch")
    if mode == "strict" and overlap_pixels:
        report["passed"] = False
        report["failures"].append("strict mode does not allow overlapping override masks")
    return {"masks": masks, "report": report}


def apply_semantic_overrides_to_parts(
    source: Image.Image,
    heuristic_parts: list[dict[str, Any]],
    masks: dict[str, set[Pixel]],
    mode: str = "supplement",
    output_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Path]]:
    if mode == "none" or not masks:
        return heuristic_parts, _empty_apply_report(source), {}

    opaque = _opaque_pixels(source)
    outline_seam = _opaque_seam(opaque, source.size)
    override_owner: dict[Pixel, str] = {}
    overlap_pixels: set[Pixel] = set()
    priority_index = {name: index for index, name in enumerate(OVERRIDE_PRIORITY)}
    rgba = source.convert("RGBA").load()
    for label, pixels in masks.items():
        for pixel in pixels:
            if pixel not in opaque:
                continue
            owner_label = _normalise_part_name(label, pixel, source.width)
            if pixel in override_owner and override_owner[pixel] != owner_label:
                overlap_pixels.add(pixel)
                current = override_owner[pixel]
                owner_priority = _effective_priority_name(owner_label, pixel, rgba, outline_seam)
                current_priority = _effective_priority_name(current, pixel, rgba, outline_seam)
                if priority_index.get(owner_priority, 999) < priority_index.get(current_priority, 999):
                    override_owner[pixel] = owner_label
                continue
            override_owner[pixel] = owner_label

    heuristic_owner = _heuristic_owner(heuristic_parts)
    grouped: dict[str, set[Pixel]] = {name: set() for name in PART_ORDER}

    for pixel in opaque:
        if pixel in override_owner:
            grouped[_normalise_part_name(override_owner[pixel], pixel, source.width)].add(pixel)
        elif mode in {"supplement", "replace", "strict"}:
            owner = heuristic_owner.get(pixel, "unknown")
            grouped[_normalise_part_name(owner, pixel, source.width)].add(pixel)

    parts = _parts_from_groups(source, grouped)
    report = _override_apply_report(source, grouped, overlap_pixels, mode)
    debug_paths = {}
    if output_dir:
        debug_paths = write_override_debug_outputs(
            source,
            heuristic_parts,
            parts,
            override_owner,
            overlap_pixels,
            output_dir,
        )
        _write_json(output_dir / "override_report.json", report)
    return parts, report, debug_paths


def write_override_debug_outputs(
    source: Image.Image,
    before_parts: list[dict[str, Any]],
    after_parts: list[dict[str, Any]],
    override_owner: dict[Pixel, str],
    overlap_pixels: set[Pixel],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay = output_dir / "semantic_override_overlay.png"
    conflicts = output_dir / "semantic_override_conflicts.png"
    before_after = output_dir / "semantic_before_after_override.png"
    unlabelled = output_dir / "unlabelled_pixels.png"
    overlaps = output_dir / "overlap_pixels.png"

    _draw_parts(source.size, after_parts).save(overlay, format="PNG")
    _draw_pixels(source.size, overlap_pixels, (255, 0, 255, 255)).save(conflicts, format="PNG")
    before = _draw_parts(source.size, before_parts)
    after = _draw_parts(source.size, after_parts)
    sheet = Image.new("RGBA", (source.width * 2, source.height), (0, 0, 0, 0))
    sheet.alpha_composite(before, (0, 0))
    sheet.alpha_composite(after, (source.width, 0))
    sheet.save(before_after, format="PNG")
    labelled = {pixel for part in after_parts for pixel in part.get("pixels", set())}
    _draw_pixels(source.size, _opaque_pixels(source) - labelled, (255, 0, 0, 255)).save(unlabelled, format="PNG")
    _draw_pixels(source.size, overlap_pixels, (255, 255, 255, 255)).save(overlaps, format="PNG")
    return {
        "semantic_override_overlay": overlay,
        "semantic_override_conflicts": conflicts,
        "semantic_before_after_override": before_after,
        "unlabelled_pixels": unlabelled,
        "overlap_pixels": overlaps,
    }


def override_warning_counts(parts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "torso_head_overlap_count_after_override": _torso_head_overlap(parts),
        "disconnected_critical_labels_after_override": _disconnected_critical(parts),
    }


def _empty_apply_report(source: Image.Image) -> dict[str, Any]:
    return {
        "override_pixels_applied": 0,
        "override_overlap_count": 0,
        "override_overlap_ratio": 0.0,
        "unlabelled_opaque_pixel_ratio": 0.0,
        "critical_label_coverage": {},
        "torso_head_overlap_count_after_override": 0,
        "disconnected_critical_labels_after_override": 0,
        "passed": True,
        "failures": [],
    }


def _override_apply_report(
    source: Image.Image,
    grouped: dict[str, set[Pixel]],
    overlap_pixels: set[Pixel],
    mode: str,
) -> dict[str, Any]:
    opaque = _opaque_pixels(source)
    labelled = set().union(*grouped.values()) if grouped else set()
    critical = {
        "head": len(grouped.get("head", set())),
        "torso": len(grouped.get("torso", set())),
        "left_leg": len(grouped.get("left_leg", set())),
        "right_leg": len(grouped.get("right_leg", set())),
    }
    report = {
        "override_pixels_applied": sum(len(pixels) for pixels in grouped.values()),
        "override_overlap_count": len(overlap_pixels),
        "override_overlap_ratio": len(overlap_pixels) / max(sum(len(pixels) for pixels in grouped.values()), 1),
        "unlabelled_opaque_pixel_ratio": len(opaque - labelled) / max(len(opaque), 1),
        "critical_label_coverage": critical,
        "torso_head_overlap_count_after_override": _torso_head_overlap_from_groups(grouped),
        "disconnected_critical_labels_after_override": _disconnected_critical_from_groups(grouped),
        "passed": True,
        "failures": [],
    }
    if mode == "strict" and report["unlabelled_opaque_pixel_ratio"] > 0:
        report["passed"] = False
        report["failures"].append("strict mode requires every opaque pixel to be labelled")
    return report


def _parts_from_groups(source: Image.Image, grouped: dict[str, set[Pixel]]) -> list[dict[str, Any]]:
    parts = []
    for name in PART_ORDER:
        pixels = grouped.get(name, set())
        if not pixels:
            continue
        parts.append(
            {
                "name": name,
                "semantic_label": _semantic_label(name),
                "pixels": pixels,
                "bbox": _bbox(pixels),
                "dominant_colour": _dominant_colour(source, pixels),
            }
        )
    return parts


def _normalise_part_name(name: str, pixel: Pixel, width: int) -> str:
    if name == "hair/hat":
        return "hair"
    if name in {"boots_feet", "boots/feet"}:
        return "left_foot" if pixel[0] < width * 0.5 else "right_foot"
    if name == "equipment/shield/sword":
        return "equipment"
    return name


def _priority_name(name: str) -> str:
    if name in {"left_foot", "right_foot", "boots/feet"}:
        return "boots_feet"
    if name == "hair/hat":
        return "hair"
    if name == "equipment/shield/sword":
        return "equipment"
    return name


def _effective_priority_name(name: str, pixel: Pixel, rgba, outline_seam: set[Pixel]) -> str:
    priority = _priority_name(name)
    if priority == "outline" and not _is_outline_authoritative(pixel, rgba, outline_seam):
        return "unknown"
    return priority


def _is_outline_authoritative(pixel: Pixel, rgba, outline_seam: set[Pixel]) -> bool:
    red, green, blue, alpha = rgba[pixel[0], pixel[1]]
    if alpha <= 16:
        return False
    return pixel in outline_seam and max(red, green, blue) <= 64


def _opaque_seam(opaque: set[Pixel], size: tuple[int, int]) -> set[Pixel]:
    width, height = size
    seam = set()
    for x, y in opaque:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) not in opaque:
                seam.add((x, y))
                break
    return seam


def _semantic_label(name: str) -> str:
    return {
        "hair": "hair/hat",
        "left_foot": "boots/feet",
        "right_foot": "boots/feet",
        "equipment": "equipment/shield/sword",
    }.get(name, name)


def _heuristic_owner(parts: list[dict[str, Any]]) -> dict[Pixel, str]:
    owner = {}
    for part in parts:
        for pixel in part.get("pixels", set()):
            owner[pixel] = part["name"]
    return owner


def _mask_pixels(image: Image.Image) -> set[Pixel]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    result = set()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 16 and max(red, green, blue) > 96:
                result.add((x, y))
    return result


def _opaque_pixels(source: Image.Image) -> set[Pixel]:
    rgba = source.convert("RGBA")
    pixels = rgba.load()
    return {
        (x, y)
        for y in range(rgba.height)
        for x in range(rgba.width)
        if pixels[x, y][3] > 16
    }


def _bbox(pixels: set[Pixel]) -> list[int]:
    xs = [x for x, _y in pixels]
    ys = [y for _x, y in pixels]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def _dominant_colour(source: Image.Image, pixels: set[Pixel]) -> tuple[int, int, int, int]:
    rgba = source.convert("RGBA").load()
    colours = [rgba[x, y] for x, y in pixels if rgba[x, y][3] > 16]
    return Counter(colours).most_common(1)[0][0] if colours else (255, 0, 255, 255)


def _draw_parts(size: tuple[int, int], parts: list[dict[str, Any]]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for part in parts:
        colour = SEMANTIC_COLOURS.get(part["name"], SEMANTIC_COLOURS["unknown"])
        for x, y in part.get("pixels", set()):
            pixels[x, y] = colour
    return image


def _draw_pixels(size: tuple[int, int], pixels_set: set[Pixel], colour: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for pixel in pixels_set:
        draw.point(pixel, fill=colour)
    return image


def _torso_head_overlap(parts: list[dict[str, Any]]) -> int:
    return _torso_head_overlap_from_groups({part["name"]: part.get("pixels", set()) for part in parts})


def _torso_head_overlap_from_groups(grouped: dict[str, set[Pixel]]) -> int:
    torso = grouped.get("torso", set())
    head = grouped.get("head", set()) | grouped.get("face", set())
    if not torso or not head:
        return 0
    return len(torso & head)


def _disconnected_critical(parts: list[dict[str, Any]]) -> int:
    return _disconnected_critical_from_groups({part["name"]: part.get("pixels", set()) for part in parts})


def _disconnected_critical_from_groups(grouped: dict[str, set[Pixel]]) -> int:
    count = 0
    for label in ("head", "torso", "left_leg", "right_leg"):
        pixels = grouped.get(label, set())
        if pixels and _component_count(pixels) > 1:
            count += 1
    return count


def _component_count(pixels: set[Pixel]) -> int:
    remaining = set(pixels)
    components = 0
    while remaining:
        components += 1
        start = remaining.pop()
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx == 0 and dy == 0:
                        continue
                    if abs(dx) + abs(dy) > 2:
                        continue
                    neighbour = (x + dx, y + dy)
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        queue.append(neighbour)
    return components


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
