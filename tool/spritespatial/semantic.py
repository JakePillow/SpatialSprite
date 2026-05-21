from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from .topology import SpriteRegion, neighbours4

Pixel = tuple[int, int]
RGBA = tuple[int, int, int, int]

REQUIRED_LABELS = [
    "head",
    "hair/hat",
    "face",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
    "boots/feet",
    "equipment/shield/sword",
    "outline",
    "unknown",
]

SEMANTIC_COLOURS: dict[str, RGBA] = {
    "head": (245, 190, 126, 255),
    "hair/hat": (118, 78, 42, 255),
    "face": (255, 214, 156, 255),
    "torso": (48, 178, 220, 255),
    "left_arm": (255, 144, 74, 255),
    "right_arm": (252, 113, 109, 255),
    "left_leg": (62, 111, 226, 255),
    "right_leg": (91, 139, 255, 255),
    "boots/feet": (156, 80, 48, 255),
    "equipment/shield/sword": (220, 208, 92, 255),
    "outline": (8, 8, 8, 255),
    "unknown": (210, 70, 230, 255),
}

DEPTH_BY_LABEL = {
    "outline": 0.12,
    "hair/hat": 0.85,
    "head": 0.8,
    "face": 0.72,
    "torso": 0.55,
    "left_arm": 0.7,
    "right_arm": 0.7,
    "left_leg": 0.65,
    "right_leg": 0.65,
    "boots/feet": 1.1,
    "equipment/shield/sword": 0.4,
    "unknown": 0.45,
}


@dataclass
class SemanticRegion:
    region_id: int
    pixel_count: int
    bbox: list[int]
    centroid: list[float]
    dominant_colour: list[int]
    neighbour_regions: list[int]
    vertical_rank: float
    horizontal_rank: float
    confidence_score: float
    assigned_label: str
    assignment_reason: str
    pass_labels: dict[str, str]
    is_outline: bool


def run_semantic_rule_passes(
    image: Image.Image,
    regions: list[set[Pixel]],
    graph: list[SpriteRegion],
) -> tuple[list[SemanticRegion], dict, dict]:
    """Classify extracted colour components into explicit semantic labels.

    The function is intentionally rule-based and verbose. It is a debugging
    surface, not a final anatomy solver.
    """

    width, height = image.size
    mid_x = width * 0.5
    opaque_count = sum(1 for value in image.getchannel("A").tobytes() if value > 0)
    largest_region = max((region.pixel_count for region in graph), default=1)
    body_candidates = _body_candidate_scores(graph, width, height)
    semantic_regions: list[SemanticRegion] = []

    for region_info in graph:
        passes: dict[str, str] = {
            "A_connected_component": "region_%03d" % region_info.region_id,
            "B_colour_region": _colour_family(region_info.dominant_colour),
        }
        label = "unknown"
        confidence = 0.35
        reasons: list[str] = []

        if _is_outline_region(region_info):
            label = "outline"
            confidence = 0.96
            reasons.append("dark high-coverage component isolated as outline")
        passes["C_outline_isolation"] = label if label == "outline" else "not_outline"

        if label != "outline":
            anatomical_label, anatomical_conf, reason = _anatomical_label(
                region_info,
                width,
                height,
                mid_x,
                body_candidates,
                largest_region,
            )
            label = anatomical_label
            confidence = anatomical_conf
            reasons.append(reason)
        passes["D_anatomical_heuristics"] = label

        if label not in {"outline", "face", "head", "hair/hat", "torso", "left_arm", "right_arm", "left_leg", "right_leg", "boots/feet"}:
            equipment_label, equipment_conf, reason = _equipment_label(region_info, width, height)
            if equipment_conf > confidence:
                label = equipment_label
                confidence = equipment_conf
                reasons.append(reason)
        passes["E_equipment_detection"] = label if label == "equipment/shield/sword" else "not_equipment"

        label, lr_reason = _assign_left_right(label, region_info, mid_x)
        if lr_reason:
            reasons.append(lr_reason)
        passes["F_left_right_assignment"] = label

        confidence = _score_confidence(label, confidence, region_info, largest_region, opaque_count)
        passes["G_confidence_scoring"] = "%.3f" % confidence
        if confidence < 0.40:
            label = "unknown"
            reasons.append("confidence below fallback threshold")
        passes["H_unknown_fallback"] = label

        semantic_regions.append(
            SemanticRegion(
                region_id=region_info.region_id,
                pixel_count=region_info.pixel_count,
                bbox=region_info.bbox,
                centroid=region_info.centroid,
                dominant_colour=region_info.dominant_colour,
                neighbour_regions=region_info.neighbours,
                vertical_rank=round(region_info.centroid[1] / max(height - 1, 1), 4),
                horizontal_rank=round(region_info.centroid[0] / max(width - 1, 1), 4),
                confidence_score=round(confidence, 4),
                assigned_label=label,
                assignment_reason="; ".join(reasons) if reasons else "no rule matched strongly",
                pass_labels=passes,
                is_outline=region_info.is_outline,
            )
        )

    warnings = detect_semantic_warnings(semantic_regions, graph)
    pass_report = {
        "required_labels": REQUIRED_LABELS,
        "pass_order": [
            "Pass A: connected-component extraction",
            "Pass B: colour-region merging",
            "Pass C: outline isolation",
            "Pass D: anatomical heuristics",
            "Pass E: equipment detection",
            "Pass F: left/right assignment",
            "Pass G: confidence scoring",
            "Pass H: unknown-region fallback",
        ],
        "label_counts": dict(Counter(region.assigned_label for region in semantic_regions)),
        "regions": [asdict(region) for region in semantic_regions],
        "warnings": warnings,
    }
    return semantic_regions, pass_report, warnings


def build_semantic_parts(
    image: Image.Image,
    regions: list[set[Pixel]],
    semantic_regions: list[SemanticRegion],
) -> list[dict]:
    semantic_by_id = {region.region_id: region for region in semantic_regions}
    parts: dict[str, set[Pixel]] = defaultdict(set)

    for region_id, pixels in enumerate(regions):
        semantic = semantic_by_id.get(region_id)
        label = semantic.assigned_label if semantic else "unknown"
        if label == "hair/hat":
            parts["hair"].update(pixels)
        elif label == "boots/feet":
            _split_pixels_by_midline(pixels, image.width * 0.5, parts, "left_foot", "right_foot")
        elif label == "equipment/shield/sword":
            parts["equipment"].update(pixels)
        elif label in {"left_leg", "right_leg", "left_arm", "right_arm", "torso", "outline", "head", "face", "unknown"}:
            parts[label].update(pixels)

    merged: list[dict] = []
    for name in [
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
    ]:
        pixels = parts.get(name, set())
        if not pixels:
            continue
        merged.append(
            {
                "name": name,
                "semantic_label": _part_to_semantic_label(name),
                "pixels": pixels,
                "bbox": _pixel_bbox(pixels),
                "dominant_colour": _dominant_colour(image, pixels),
            }
        )
    return merged


def write_semantic_debug_outputs(
    image: Image.Image,
    regions: list[set[Pixel]],
    semantic_regions: list[SemanticRegion],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_id = {region.region_id: region for region in semantic_regions}

    id_map = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay = image.convert("RGBA").copy()
    bbox_overlay = image.convert("RGBA").copy()
    depth_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    outline_only = Image.new("RGBA", image.size, (0, 0, 0, 0))
    unknown_only = Image.new("RGBA", image.size, (0, 0, 0, 0))
    occupancy = Image.new("RGBA", image.size, (0, 0, 0, 0))

    source_pixels = image.convert("RGBA").load()
    id_pixels = id_map.load()
    overlay_pixels = overlay.load()
    depth_pixels = depth_overlay.load()
    outline_pixels = outline_only.load()
    unknown_pixels = unknown_only.load()
    occupancy_pixels = occupancy.load()

    for region_id, pixels in enumerate(regions):
        semantic = by_id.get(region_id)
        label = semantic.assigned_label if semantic else "unknown"
        colour = SEMANTIC_COLOURS.get(label, SEMANTIC_COLOURS["unknown"])
        depth_value = int(DEPTH_BY_LABEL.get(label, 0.45) * 255)
        for x, y in pixels:
            source = source_pixels[x, y]
            id_pixels[x, y] = colour
            overlay_pixels[x, y] = _blend(source, colour, 0.42)
            depth_pixels[x, y] = _blend((depth_value, depth_value, depth_value, source[3]), colour, 0.25)
            occupancy_pixels[x, y] = (255, 255, 255, source[3])
            if label == "outline":
                outline_pixels[x, y] = source
            if label == "unknown":
                unknown_pixels[x, y] = _blend(source, SEMANTIC_COLOURS["unknown"], 0.55)

    bbox_draw = ImageDraw.Draw(bbox_overlay)
    overlay_draw = ImageDraw.Draw(overlay)
    for semantic in semantic_regions:
        colour = SEMANTIC_COLOURS.get(semantic.assigned_label, SEMANTIC_COLOURS["unknown"])
        x0, y0, x1, y1 = semantic.bbox
        bbox_draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=colour, width=1)
        text = "%d:%s" % (semantic.region_id, _short_label(semantic.assigned_label))
        bbox_draw.text((x0, y0), text, fill=colour)
        overlay_draw.text((x0, max(0, y0 - 7)), str(semantic.region_id), fill=(255, 255, 255, 255))

    paths = {
        "semantic_region_overlay": output_dir / "semantic_region_overlay.png",
        "semantic_id_map": output_dir / "semantic_id_map.png",
        "semantic_bbox_overlay": output_dir / "semantic_bbox_overlay.png",
        "semantic_depth_overlay": output_dir / "semantic_depth_overlay.png",
        "semantic_outline_only": output_dir / "semantic_outline_only.png",
        "semantic_unknown_regions": output_dir / "semantic_unknown_regions.png",
        "semantic_occupancy": output_dir / "semantic_occupancy.png",
    }
    overlay.save(paths["semantic_region_overlay"], format="PNG")
    id_map.save(paths["semantic_id_map"], format="PNG")
    bbox_overlay.save(paths["semantic_bbox_overlay"], format="PNG")
    depth_overlay.save(paths["semantic_depth_overlay"], format="PNG")
    outline_only.save(paths["semantic_outline_only"], format="PNG")
    unknown_only.save(paths["semantic_unknown_regions"], format="PNG")
    occupancy.save(paths["semantic_occupancy"], format="PNG")
    return paths


def detect_semantic_warnings(semantic_regions: list[SemanticRegion], graph: list[SpriteRegion]) -> dict:
    warnings: dict[str, list[dict]] = {
        "disconnected_body_parts": [],
        "tiny_orphan_regions": [],
        "ambiguous_assignment": [],
        "outline_regions_merged_into_body": [],
        "left_right_confusion": [],
        "torso_head_overlap": [],
        "equipment_merged_into_body": [],
        "depth_discontinuities": [],
    }
    by_id = {region.region_id: region for region in semantic_regions}
    by_label: dict[str, list[SemanticRegion]] = defaultdict(list)
    for semantic in semantic_regions:
        by_label[semantic.assigned_label].append(semantic)
        if semantic.pixel_count <= 2 and semantic.assigned_label != "outline":
            warnings["tiny_orphan_regions"].append(_warning(semantic, "tiny non-outline region"))
        if semantic.confidence_score < 0.58:
            warnings["ambiguous_assignment"].append(_warning(semantic, "low semantic confidence"))
        if semantic.is_outline and semantic.assigned_label != "outline":
            warnings["outline_regions_merged_into_body"].append(_warning(semantic, "outline source flag lost during semantic assignment"))
        if semantic.assigned_label.startswith("left_") and semantic.horizontal_rank > 0.62:
            warnings["left_right_confusion"].append(_warning(semantic, "left label appears on right half"))
        if semantic.assigned_label.startswith("right_") and semantic.horizontal_rank < 0.38:
            warnings["left_right_confusion"].append(_warning(semantic, "right label appears on left half"))

    for label in ("head", "face", "torso", "left_arm", "right_arm", "left_leg", "right_leg", "boots/feet"):
        if len(by_label[label]) > 1:
            warnings["disconnected_body_parts"].append(
                {
                    "label": label,
                    "region_ids": [region.region_id for region in by_label[label]],
                    "message": "label is split across multiple disconnected regions",
                }
            )

    for torso in by_label["torso"]:
        for head in by_label["head"] + by_label["face"]:
            if _bbox_overlap_ratio(torso.bbox, head.bbox) > 0.15:
                warnings["torso_head_overlap"].append(
                    {
                        "torso_region_id": torso.region_id,
                        "head_region_id": head.region_id,
                        "message": "torso/head bounding boxes overlap unusually",
                    }
                )

    body_labels = {"torso", "head", "face"}
    for semantic in semantic_regions:
        if semantic.assigned_label in body_labels and _looks_like_equipment(semantic):
            warnings["equipment_merged_into_body"].append(_warning(semantic, "thin side or high aspect component may be equipment"))

    for source in graph:
        semantic = by_id[source.region_id]
        if semantic.assigned_label == "outline":
            continue
        source_depth = DEPTH_BY_LABEL.get(semantic.assigned_label, 0.45)
        for neighbour_id in source.neighbours:
            other = by_id.get(neighbour_id)
            if not other:
                continue
            if other.assigned_label == "outline":
                continue
            other_depth = DEPTH_BY_LABEL.get(other.assigned_label, 0.45)
            if abs(source_depth - other_depth) > 0.58:
                warnings["depth_discontinuities"].append(
                    {
                        "region_id": semantic.region_id,
                        "neighbour_region_id": other.region_id,
                        "labels": [semantic.assigned_label, other.assigned_label],
                        "depth_values": [source_depth, other_depth],
                        "message": "neighbouring regions have a large semantic depth step",
                    }
                )
    return warnings


def _body_candidate_scores(graph: list[SpriteRegion], width: int, height: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for region in graph:
        x0, y0, x1, y1 = region.bbox
        cx, cy = region.centroid
        centrality = 1.0 - min(abs(cx - width * 0.5) / max(width * 0.5, 1), 1.0)
        middle = 1.0 - min(abs(cy - height * 0.5) / max(height * 0.5, 1), 1.0)
        area = region.pixel_count / max(width * height, 1)
        box_area = (x1 - x0) * (y1 - y0) / max(width * height, 1)
        scores[region.region_id] = centrality * 0.35 + middle * 0.25 + min(area * 10, 1.0) * 0.25 + min(box_area * 6, 1.0) * 0.15
    return scores


def _anatomical_label(
    region: SpriteRegion,
    width: int,
    height: int,
    mid_x: float,
    body_candidates: dict[int, float],
    largest_region: int,
) -> tuple[str, float, str]:
    red, green, blue, _alpha = region.dominant_colour
    x0, y0, x1, y1 = region.bbox
    box_w = x1 - x0
    box_h = y1 - y0
    cx, cy = region.centroid
    vertical = cy / max(height - 1, 1)
    horizontal = cx / max(width - 1, 1)
    colour = _colour_family(region.dominant_colour)

    if _is_skin(region.dominant_colour):
        if vertical < 0.36 and 0.30 <= horizontal <= 0.70:
            return "face", 0.88, "upper central skin region classified as face"
        if vertical < 0.42:
            return "head", 0.76, "upper skin region classified as head"
        if horizontal < 0.43:
            return "left_arm", 0.82, "side skin region left of centre classified as left arm"
        if horizontal > 0.57:
            return "right_arm", 0.82, "side skin region right of centre classified as right arm"

    if vertical < 0.34 and (colour in {"brown", "green", "blue", "dark"} or box_w >= 3):
        return "hair/hat", 0.78, "upper non-skin region classified as hair/hat"

    if 0.30 <= vertical <= 0.68 and body_candidates.get(region.region_id, 0.0) > 0.45:
        return "torso", 0.82, "central middle high-area component classified as torso"

    if vertical >= 0.54:
        if colour in {"brown", "dark"} and vertical > 0.74:
            return "boots/feet", 0.83, "lower brown/dark component classified as boots/feet"
        if horizontal < 0.50:
            return "left_leg", 0.76, "lower component left of centre classified as left leg"
        return "right_leg", 0.76, "lower component right of centre classified as right leg"

    if horizontal < 0.34 and 0.32 <= vertical <= 0.78:
        return "left_arm", 0.66, "side component classified as left arm by position"
    if horizontal > 0.66 and 0.32 <= vertical <= 0.78:
        return "right_arm", 0.66, "side component classified as right arm by position"

    if region.pixel_count >= max(largest_region * 0.22, 4) and vertical < 0.72:
        return "torso", 0.58, "large component fallback to torso"
    return "unknown", 0.32, "no anatomical rule matched"


def _equipment_label(region: SpriteRegion, width: int, height: int) -> tuple[str, float, str]:
    if _looks_like_equipment(region):
        return "equipment/shield/sword", 0.64, "thin/side component classified as equipment candidate"
    return "unknown", 0.0, "not equipment-like"


def _assign_left_right(label: str, region: SpriteRegion, mid_x: float) -> tuple[str, str]:
    if label == "left_leg" and region.centroid[0] >= mid_x:
        return "right_leg", "leg side corrected using horizontal centreline"
    if label == "right_leg" and region.centroid[0] < mid_x:
        return "left_leg", "leg side corrected using horizontal centreline"
    if label == "left_arm" and region.centroid[0] >= mid_x:
        return "right_arm", "arm side corrected using horizontal centreline"
    if label == "right_arm" and region.centroid[0] < mid_x:
        return "left_arm", "arm side corrected using horizontal centreline"
    return label, ""


def _score_confidence(label: str, base: float, region: SpriteRegion, largest_region: int, opaque_count: int) -> float:
    score = base
    if label == "unknown":
        score -= 0.08
    if region.pixel_count <= 2:
        score -= 0.15
    if region.pixel_count >= max(largest_region * 0.5, 4):
        score += 0.08
    if region.pixel_count / max(opaque_count, 1) > 0.22 and label in {"torso", "outline"}:
        score += 0.06
    return max(0.0, min(1.0, score))


def _split_pixels_by_midline(pixels: Iterable[Pixel], mid_x: float, parts: dict[str, set[Pixel]], left: str, right: str) -> None:
    for pixel in pixels:
        parts[left if pixel[0] < mid_x else right].add(pixel)


def _part_to_semantic_label(name: str) -> str:
    return {
        "hair": "hair/hat",
        "left_foot": "boots/feet",
        "right_foot": "boots/feet",
        "equipment": "equipment/shield/sword",
    }.get(name, name)


def _is_outline_region(region: SpriteRegion) -> bool:
    colour = region.dominant_colour
    return region.is_outline or max(colour[0], colour[1], colour[2]) <= 56


def _is_skin(colour: list[int]) -> bool:
    red, green, blue, _alpha = colour
    return red >= 170 and green >= 90 and blue <= 170 and red > blue + 35


def _looks_like_equipment(region: SemanticRegion | SpriteRegion) -> bool:
    x0, y0, x1, y1 = region.bbox
    width = x1 - x0
    height = y1 - y0
    aspect = max(width, height) / max(min(width, height), 1)
    if isinstance(region, SemanticRegion):
        side_region = region.horizontal_rank < 0.32 or region.horizontal_rank > 0.68
    else:
        side_region = region.horizontal_position in {"left", "right"}
    return aspect >= 3.2 and (side_region or width <= 2)


def _colour_family(colour: list[int]) -> str:
    red, green, blue, _alpha = colour
    if max(red, green, blue) <= 72:
        return "dark"
    if _is_skin(colour):
        return "skin"
    if green > red + 25 and green > blue:
        return "green"
    if blue > red + 30 and blue > green * 0.85:
        return "blue"
    if red > 80 and green < 140 and blue < 120:
        return "brown"
    if red > 160 and green > 130 and blue < 120:
        return "yellow"
    return "mixed"


def _pixel_bbox(pixels: set[Pixel]) -> list[int]:
    xs = [x for x, _y in pixels]
    ys = [y for _x, y in pixels]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def _dominant_colour(image: Image.Image, pixels: set[Pixel]) -> RGBA:
    source = image.convert("RGBA").load()
    colours = [source[x, y] for x, y in pixels if source[x, y][3] > 0]
    if not colours:
        return (255, 0, 255, 255)
    return Counter(colours).most_common(1)[0][0]


def _blend(source: RGBA, colour: RGBA, amount: float) -> RGBA:
    return (
        int(source[0] * (1.0 - amount) + colour[0] * amount),
        int(source[1] * (1.0 - amount) + colour[1] * amount),
        int(source[2] * (1.0 - amount) + colour[2] * amount),
        source[3],
    )


def _short_label(label: str) -> str:
    return {
        "hair/hat": "hair",
        "boots/feet": "feet",
        "equipment/shield/sword": "equip",
    }.get(label, label)


def _bbox_overlap_ratio(a: list[int], b: list[int]) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    overlap = (x1 - x0) * (y1 - y0)
    area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return overlap / max(area, 1)


def _warning(region: SemanticRegion, message: str) -> dict:
    return {
        "region_id": region.region_id,
        "assigned_label": region.assigned_label,
        "bbox": region.bbox,
        "confidence_score": region.confidence_score,
        "message": message,
    }
