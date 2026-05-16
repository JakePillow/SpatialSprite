from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

RGBA = tuple[int, int, int, int]


@dataclass
class SpriteRegion:
    region_id: int
    pixel_count: int
    bbox: list[int]
    centroid: list[float]
    dominant_colour: list[int]
    neighbours: list[int]
    contact_lengths: dict[str, int]
    vertical_position: str
    horizontal_position: str
    likely_label: str
    is_outline: bool


@dataclass
class DepthAssignment:
    region_id: int
    label: str
    z_offset: float
    local_depth: float
    smoothing_strength: float
    merge_policy: str


def load_rgba(path: Path) -> Image.Image:
    image = Image.open(path)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image


def quantized_colour(pixel: RGBA, bucket: int = 24) -> RGBA:
    if pixel[3] == 0:
        return (0, 0, 0, 0)
    return (
        int(round(pixel[0] / bucket) * bucket),
        int(round(pixel[1] / bucket) * bucket),
        int(round(pixel[2] / bucket) * bucket),
        255,
    )


def extract_regions(
    image: Image.Image,
    alpha_threshold: int = 16,
    colour_bucket: int = 24,
) -> tuple[list[set[tuple[int, int]]], list[list[int]]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    visited: set[tuple[int, int]] = set()
    regions: list[set[tuple[int, int]]] = []
    region_map = [[-1 for _x in range(rgba.width)] for _y in range(rgba.height)]

    for y in range(rgba.height):
        for x in range(rgba.width):
            if (x, y) in visited or pixels[x, y][3] <= alpha_threshold:
                continue
            target = quantized_colour(pixels[x, y], colour_bucket)
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited.add((x, y))
            component: set[tuple[int, int]] = set()
            while queue:
                cx, cy = queue.popleft()
                component.add((cx, cy))
                for nx, ny in neighbours4(cx, cy, rgba.width, rgba.height):
                    if (nx, ny) in visited or pixels[nx, ny][3] <= alpha_threshold:
                        continue
                    if quantized_colour(pixels[nx, ny], colour_bucket) != target:
                        continue
                    visited.add((nx, ny))
                    queue.append((nx, ny))
            region_id = len(regions)
            for px, py in component:
                region_map[py][px] = region_id
            regions.append(component)
    return regions, region_map


def merge_tiny_regions(
    image: Image.Image,
    regions: list[set[tuple[int, int]]],
    region_map: list[list[int]],
    min_pixels: int = 3,
    outline_luma_threshold: int = 72,
) -> tuple[list[set[tuple[int, int]]], list[list[int]]]:
    pixels = image.convert("RGBA").load()
    active = [set(region) for region in regions]
    for region_id, region in enumerate(regions):
        if len(region) >= min_pixels or _region_is_outline(region, pixels, outline_luma_threshold):
            continue
        neighbour_counts: Counter[int] = Counter()
        for x, y in region:
            for nx, ny in neighbours4(x, y, image.width, image.height):
                other = region_map[ny][nx]
                if other >= 0 and other != region_id:
                    neighbour_counts[other] += 1
        if not neighbour_counts:
            continue
        target, _count = neighbour_counts.most_common(1)[0]
        active[target].update(region)
        active[region_id].clear()
        for x, y in region:
            region_map[y][x] = target

    remap: dict[int, int] = {}
    merged: list[set[tuple[int, int]]] = []
    for old_id, region in enumerate(active):
        if not region:
            continue
        remap[old_id] = len(merged)
        merged.append(region)
    new_map = [[-1 for _x in range(image.width)] for _y in range(image.height)]
    for old_id, new_id in remap.items():
        for x, y in active[old_id]:
            new_map[y][x] = new_id
    return merged, new_map


def build_part_graph(
    image: Image.Image,
    regions: list[set[tuple[int, int]]],
    region_map: list[list[int]],
    outline_luma_threshold: int = 72,
) -> list[SpriteRegion]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    graph: list[SpriteRegion] = []
    for region_id, region in enumerate(regions):
        xs = [x for x, _y in region]
        ys = [y for _x, y in region]
        colours = [pixels[x, y] for x, y in region]
        dominant = Counter(colours).most_common(1)[0][0]
        contacts: Counter[int] = Counter()
        for x, y in region:
            for nx, ny in neighbours4(x, y, rgba.width, rgba.height):
                other = region_map[ny][nx]
                if other >= 0 and other != region_id:
                    contacts[other] += 1
        bbox = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
        centroid = [sum(xs) / len(xs), sum(ys) / len(ys)]
        vertical = _vertical_band(centroid[1], rgba.height)
        horizontal = _horizontal_band(centroid[0], rgba.width)
        is_outline = _region_is_outline(region, pixels, outline_luma_threshold)
        graph.append(
            SpriteRegion(
                region_id=region_id,
                pixel_count=len(region),
                bbox=bbox,
                centroid=[round(centroid[0], 3), round(centroid[1], 3)],
                dominant_colour=[dominant[0], dominant[1], dominant[2], dominant[3]],
                neighbours=sorted(contacts),
                contact_lengths={str(key): value for key, value in sorted(contacts.items())},
                vertical_position=vertical,
                horizontal_position=horizontal,
                likely_label=_likely_label(dominant, vertical, horizontal, bbox, rgba.size, is_outline),
                is_outline=is_outline,
            )
        )
    return graph


def assign_depths(graph: list[SpriteRegion]) -> list[DepthAssignment]:
    assignments: list[DepthAssignment] = []
    for region in graph:
        label = region.likely_label
        if label == "outline":
            z_offset, local_depth, smoothing, policy = 0.0, 0.18, 0.15, "rim_bevel"
        elif label in {"face", "head"}:
            z_offset, local_depth, smoothing, policy = 0.18, 0.42, 0.35, "part"
        elif label in {"hat", "hair"}:
            z_offset, local_depth, smoothing, policy = 0.08, 0.38, 0.30, "part"
        elif label in {"left_arm", "right_arm", "equipment"}:
            z_offset, local_depth, smoothing, policy = 0.12, 0.36, 0.25, "bridge_contacts"
        elif label in {"legs", "boots"}:
            z_offset, local_depth, smoothing, policy = -0.04, 0.34, 0.25, "bridge_contacts"
        elif label == "torso":
            z_offset, local_depth, smoothing, policy = 0.0, 0.48, 0.35, "core"
        else:
            z_offset, local_depth, smoothing, policy = 0.0, 0.32, 0.20, "part"
        assignments.append(
            DepthAssignment(
                region_id=region.region_id,
                label=label,
                z_offset=z_offset,
                local_depth=local_depth,
                smoothing_strength=smoothing,
                merge_policy=policy,
            )
        )
    return assignments


def write_region_debug_images(
    image: Image.Image,
    regions: list[set[tuple[int, int]]],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    palette = _debug_palette(len(regions))
    id_map = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay = image.convert("RGBA").copy()
    overlay_pixels = overlay.load()
    id_pixels = id_map.load()
    for region_id, region in enumerate(regions):
        colour = palette[region_id]
        for x, y in region:
            id_pixels[x, y] = colour
            source = overlay_pixels[x, y]
            overlay_pixels[x, y] = (
                int(source[0] * 0.55 + colour[0] * 0.45),
                int(source[1] * 0.55 + colour[1] * 0.45),
                int(source[2] * 0.55 + colour[2] * 0.45),
                source[3],
            )
    draw = ImageDraw.Draw(overlay)
    for region_id, region in enumerate(regions):
        xs = [x for x, _y in region]
        ys = [y for _x, y in region]
        if not xs:
            continue
        draw.text((min(xs), min(ys)), str(region_id), fill=(255, 255, 255, 255))
    id_path = output_dir / "region_id_map.png"
    overlay_path = output_dir / "region_overlay.png"
    id_map.save(id_path, format="PNG")
    overlay.save(overlay_path, format="PNG")
    return id_path, overlay_path


def region_mask_image(size: tuple[int, int], region: Iterable[tuple[int, int]]) -> Image.Image:
    mask = Image.new("L", size, 0)
    pixels = mask.load()
    for x, y in region:
        pixels[x, y] = 255
    return mask


def graph_to_json(graph: list[SpriteRegion]) -> list[dict]:
    return [asdict(region) for region in graph]


def assignments_to_json(assignments: list[DepthAssignment]) -> list[dict]:
    return [asdict(item) for item in assignments]


def neighbours4(x: int, y: int, width: int, height: int) -> Iterable[tuple[int, int]]:
    if x > 0:
        yield x - 1, y
    if x + 1 < width:
        yield x + 1, y
    if y > 0:
        yield x, y - 1
    if y + 1 < height:
        yield x, y + 1


def _region_is_outline(region: set[tuple[int, int]], pixels, threshold: int) -> bool:
    if not region:
        return False
    dark = 0
    for x, y in region:
        pixel = pixels[x, y]
        if max(pixel[0], pixel[1], pixel[2]) <= threshold:
            dark += 1
    return dark / len(region) >= 0.70


def _vertical_band(y: float, height: int) -> str:
    t = y / max(height - 1, 1)
    if t < 0.32:
        return "upper"
    if t < 0.66:
        return "middle"
    return "lower"


def _horizontal_band(x: float, width: int) -> str:
    t = x / max(width - 1, 1)
    if t < 0.40:
        return "left"
    if t > 0.60:
        return "right"
    return "center"


def _likely_label(
    colour: RGBA,
    vertical: str,
    horizontal: str,
    bbox: list[int],
    size: tuple[int, int],
    is_outline: bool,
) -> str:
    if is_outline:
        return "outline"
    red, green, blue, _alpha = colour
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if vertical == "upper" and green > red and green > blue:
        return "hat"
    if red > 150 and green > 90 and blue < 120:
        if vertical == "upper":
            return "face"
        return "left_arm" if horizontal == "left" else "right_arm" if horizontal == "right" else "head"
    if green > 130 and vertical == "middle":
        return "torso"
    if vertical == "lower" and (green > 100 or red > 120):
        return "legs" if height > 2 or width > 2 else "boots"
    if horizontal in {"left", "right"} and vertical in {"middle", "lower"}:
        return "left_arm" if horizontal == "left" else "right_arm"
    if width <= 2 or height <= 2:
        return "equipment"
    return "unknown"


def _debug_palette(count: int) -> list[RGBA]:
    palette: list[RGBA] = []
    for i in range(count):
        hue = (i * 47) % 360
        c = _hsv_to_rgb(hue / 360.0, 0.78, 0.96)
        palette.append((c[0], c[1], c[2], 255))
    return palette


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6
    values = {
        0: (v, t, p),
        1: (q, v, p),
        2: (p, v, t),
        3: (p, q, v),
        4: (t, p, v),
        5: (v, p, q),
    }[i]
    return tuple(int(channel * 255) for channel in values)
