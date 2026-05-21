from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw

from spritespatial.primitives import PrimitiveAssignment

Voxel = tuple[int, int, int]
Pixel = tuple[int, int]


POLICY_FUSE = "fuse"
POLICY_BRIDGE = "bridge"
POLICY_PRESERVE_GAP = "preserve_gap"
POLICY_SHELL_ATTACH = "shell_attach"
POLICY_RIGID_ATTACH = "rigid_attach"


@dataclass(frozen=True)
class ContinuityEdge:
    source_part_id: int
    target_part_id: int
    source_name: str
    target_name: str
    contact_length: int
    overlap_zones: int
    semantic_compatibility: float
    continuity_strength: float
    policy: str


@dataclass(frozen=True)
class BridgeReport:
    source_part_id: int
    target_part_id: int
    policy: str
    added_voxels: int
    contact_pixels: int


def build_semantic_adjacency_graph(
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    occupancy: set[Voxel],
    owner_by_voxel: dict[Voxel, int],
) -> dict[str, Any]:
    pixel_owner = _pixel_owner(parts)
    assignment_by_id = {item.part_id: item for item in assignments}
    contacts: Counter[tuple[int, int]] = Counter()
    overlap_zones: Counter[tuple[int, int]] = Counter()

    for (x, y), part_id in pixel_owner.items():
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            other = pixel_owner.get((nx, ny))
            if other is None or other == part_id:
                continue
            key = tuple(sorted((part_id, other)))
            contacts[key] += 1

    for a in range(len(parts)):
        for b in range(a + 1, len(parts)):
            key = (a, b)
            if key in contacts:
                continue
            source = assignment_by_id[a]
            target = assignment_by_id[b]
            policy = continuity_policy(source.name, target.name)
            if policy not in {POLICY_FUSE, POLICY_BRIDGE, POLICY_RIGID_ATTACH}:
                continue
            distance = _min_pixel_distance(parts[a].get("pixels", set()), parts[b].get("pixels", set()))
            if distance <= 3:
                contacts[key] = 1

    z_by_part_xy: dict[tuple[int, Pixel], set[int]] = {}
    for x, y, z in occupancy:
        part_id = owner_by_voxel.get((x, y, z))
        if part_id is None:
            continue
        z_by_part_xy.setdefault((part_id, (x, y)), set()).add(z)

    for key, contact_length in contacts.items():
        a, b = key
        a_pixels = parts[a].get("pixels", set())
        b_pixels = parts[b].get("pixels", set())
        overlaps = 0
        for ax, ay in a_pixels:
            for bx, by in ((ax - 1, ay), (ax + 1, ay), (ax, ay - 1), (ax, ay + 1)):
                if (bx, by) not in b_pixels:
                    continue
                za = z_by_part_xy.get((a, (ax, ay)), set())
                zb = z_by_part_xy.get((b, (bx, by)), set())
                if za and zb and max(za) >= min(zb) and max(zb) >= min(za):
                    overlaps += 1
        overlap_zones[key] = overlaps

    edges: list[ContinuityEdge] = []
    for a, b in sorted(contacts):
        source = assignment_by_id[a]
        target = assignment_by_id[b]
        policy = continuity_policy(source.name, target.name)
        compatibility = semantic_compatibility(source.name, target.name, policy)
        strength = min(1.0, contacts[(a, b)] / 12.0) * compatibility
        if policy == POLICY_FUSE:
            strength = max(strength, 0.92)
        elif policy == POLICY_BRIDGE:
            strength = max(strength, 0.72)
        elif policy == POLICY_SHELL_ATTACH:
            strength = min(max(strength, 0.35), 0.55)
        edges.append(
            ContinuityEdge(
                source_part_id=a,
                target_part_id=b,
                source_name=source.name,
                target_name=target.name,
                contact_length=contacts[(a, b)],
                overlap_zones=overlap_zones[(a, b)],
                semantic_compatibility=compatibility,
                continuity_strength=strength,
                policy=policy,
            )
        )

    return {
        "schema": "spritespatial_continuity_graph_v1",
        "edges": [asdict(edge) for edge in edges],
        "summary": {
            "edge_count": len(edges),
            "policy_counts": dict(Counter(edge.policy for edge in edges)),
        },
    }


def apply_semantic_continuity(
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    occupancy: set[Voxel],
    owner_by_voxel: dict[Voxel, int],
    total_depth_slices: int,
    output_dir: Path | None = None,
    size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    graph = build_semantic_adjacency_graph(parts, assignments, occupancy, owner_by_voxel)
    assignment_by_id = {item.part_id: item for item in assignments}
    pixel_owner = _pixel_owner(parts)
    z_by_pixel_part = _z_by_pixel_part(occupancy, owner_by_voxel)
    bridge_reports: list[BridgeReport] = []
    bridge_voxels: set[Voxel] = set()
    clipped_shell_voxels: set[Voxel] = set()

    for edge_data in graph["edges"]:
        edge = ContinuityEdge(**edge_data)
        if edge.policy not in {POLICY_FUSE, POLICY_BRIDGE, POLICY_RIGID_ATTACH}:
            continue
        added = _bridge_edge(
            edge,
            parts,
            assignment_by_id,
            z_by_pixel_part,
            total_depth_slices,
            bridge_voxels,
            owner_by_voxel,
        )
        if added:
            bridge_reports.append(
                BridgeReport(
                    source_part_id=edge.source_part_id,
                    target_part_id=edge.target_part_id,
                    policy=edge.policy,
                    added_voxels=added,
                    contact_pixels=edge.contact_length,
                )
            )

    internal_voxels = _add_internal_primitive_continuity(
        parts,
        assignments,
        z_by_pixel_part,
        total_depth_slices,
        owner_by_voxel,
    )
    bridge_voxels.update(internal_voxels)
    occupancy.update(bridge_voxels)

    # Shell correction: keep outline on the front rim and remove shell voxels
    # that sit directly over internal body mass in the same pixel column.
    body_xy = {
        (x, y)
        for x, y, z in occupancy
        if assignment_by_id.get(owner_by_voxel.get((x, y, z), -1))
        and assignment_by_id[owner_by_voxel[(x, y, z)]].primitive_type != "shell"
    }
    for voxel in list(occupancy):
        part = assignment_by_id.get(owner_by_voxel.get(voxel, -1))
        if not part or part.primitive_type != "shell":
            continue
        x, y, z = voxel
        if (x, y) in body_xy and z < total_depth_slices - 1:
            occupancy.remove(voxel)
            owner_by_voxel.pop(voxel, None)
            clipped_shell_voxels.add(voxel)

    metrics = continuity_metrics(parts, assignments, occupancy, owner_by_voxel, graph, bridge_reports)
    debug_paths = {}
    if output_dir and size:
        debug_paths = write_continuity_debug_outputs(
            size,
            parts,
            assignments,
            graph,
            bridge_voxels,
            clipped_shell_voxels,
            occupancy,
            owner_by_voxel,
            output_dir,
        )

    return {
        "graph": graph,
        "bridge_reports": [asdict(report) for report in bridge_reports],
        "bridge_voxels": bridge_voxels,
        "clipped_shell_voxels": clipped_shell_voxels,
        "metrics": metrics,
        "debug_paths": debug_paths,
    }


def continuity_metrics(
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    occupancy: set[Voxel],
    owner_by_voxel: dict[Voxel, int],
    graph: dict[str, Any],
    bridge_reports: list[BridgeReport],
) -> dict[str, Any]:
    assignment_by_id = {item.part_id: item for item in assignments}
    body_voxels = {
        voxel
        for voxel in occupancy
        if assignment_by_id.get(owner_by_voxel.get(voxel, -1))
        and assignment_by_id[owner_by_voxel[voxel]].primitive_type != "shell"
    }
    shell_voxels = {
        voxel
        for voxel in occupancy
        if assignment_by_id.get(owner_by_voxel.get(voxel, -1))
        and assignment_by_id[owner_by_voxel[voxel]].primitive_type == "shell"
    }
    components = _components(body_voxels)
    floating = max(0, len(components) - 1)
    bridgeable_edges = [
        edge for edge in graph["edges"]
        if edge["policy"] in {POLICY_FUSE, POLICY_BRIDGE, POLICY_RIGID_ATTACH}
    ]
    overlap_after = _edge_overlap_after(bridgeable_edges, occupancy, parts)
    score = overlap_after / max(len(bridgeable_edges), 1)
    shell_dominance = len(shell_voxels) / max(len(body_voxels) + len(shell_voxels), 1)
    return {
        "disconnected_mass_count": len(components),
        "floating_fragment_count": floating,
        "side_silhouette_continuity_score": score,
        "semantic_bridge_count": len(bridge_reports),
        "shell_dominance_ratio": shell_dominance,
    }


def write_continuity_debug_outputs(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    graph: dict[str, Any],
    bridge_voxels: set[Voxel],
    clipped_shell_voxels: set[Voxel],
    occupancy: set[Voxel],
    owner_by_voxel: dict[Voxel, int],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / "continuity_graph.json"
    overlay_path = output_dir / "continuity_overlay.png"
    bridge_path = output_dir / "bridge_debug.png"
    silhouette_path = output_dir / "side_silhouette_debug.png"
    shell_path = output_dir / "shell_overlap_debug.png"

    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    _write_continuity_overlay(size, parts, assignments, graph, overlay_path)
    _write_voxel_projection(size, bridge_voxels, bridge_path, (255, 90, 40, 230))
    _write_voxel_projection(size, occupancy, silhouette_path, (80, 150, 255, 210))
    _write_voxel_projection(size, clipped_shell_voxels, shell_path, (255, 255, 255, 230))
    return {
        "continuity_graph": graph_path,
        "continuity_overlay": overlay_path,
        "bridge_debug": bridge_path,
        "side_silhouette_debug": silhouette_path,
        "shell_overlap_debug": shell_path,
    }


def continuity_policy(a: str, b: str) -> str:
    names = {a, b}
    if "outline" in names:
        return POLICY_SHELL_ATTACH
    if "equipment" in names:
        return POLICY_RIGID_ATTACH
    if names <= {"head", "face", "hair"} or names == {"head", "face"}:
        return POLICY_FUSE
    if "torso" in names and names & {"left_arm", "right_arm", "left_leg", "right_leg", "head", "face"}:
        return POLICY_BRIDGE
    if names & {"left_arm", "right_arm"} and names & {"head", "face"}:
        return POLICY_PRESERVE_GAP
    if names & {"left_leg", "right_leg"} and names & {"left_foot", "right_foot"}:
        return POLICY_BRIDGE
    return POLICY_PRESERVE_GAP


def semantic_compatibility(a: str, b: str, policy: str) -> float:
    return {
        POLICY_FUSE: 1.0,
        POLICY_BRIDGE: 0.82,
        POLICY_RIGID_ATTACH: 0.62,
        POLICY_SHELL_ATTACH: 0.48,
        POLICY_PRESERVE_GAP: 0.15,
    }[policy]


def _bridge_edge(
    edge: ContinuityEdge,
    parts: list[dict[str, Any]],
    assignment_by_id: dict[int, PrimitiveAssignment],
    z_by_pixel_part: dict[tuple[int, Pixel], set[int]],
    total_depth_slices: int,
    bridge_voxels: set[Voxel],
    owner_by_voxel: dict[Voxel, int],
) -> int:
    contacts = _contact_pairs(parts[edge.source_part_id]["pixels"], parts[edge.target_part_id]["pixels"])
    if not contacts:
        contacts = _nearest_pairs(parts[edge.source_part_id]["pixels"], parts[edge.target_part_id]["pixels"], max_pairs=3)
    added = 0
    if not contacts:
        return added
    for a_pixel, b_pixel in contacts:
        za = z_by_pixel_part.get((edge.source_part_id, a_pixel), set())
        zb = z_by_pixel_part.get((edge.target_part_id, b_pixel), set())
        if not za or not zb:
            continue
        z_min = min(min(za), min(zb))
        z_max = max(max(za), max(zb))
        if edge.policy == POLICY_BRIDGE:
            z_min = max(0, z_min - 1)
            z_max = min(total_depth_slices - 1, z_max + 1)
        elif edge.policy == POLICY_RIGID_ATTACH:
            z_min = max(min(za), min(zb))
            z_max = min(max(za), max(zb))
            if z_min > z_max:
                z_min = min(min(za), min(zb))
                z_max = max(max(za), max(zb))
        owner = edge.source_part_id if assignment_by_id[edge.source_part_id].name == "torso" else edge.target_part_id
        for pixel in _line_pixels(a_pixel, b_pixel):
            for z in range(z_min, z_max + 1):
                key = (pixel[0], pixel[1], z)
                if key in bridge_voxels:
                    continue
                bridge_voxels.add(key)
                owner_by_voxel[key] = owner
                added += 1
    return added


def _add_internal_primitive_continuity(
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    z_by_pixel_part: dict[tuple[int, Pixel], set[int]],
    total_depth_slices: int,
    owner_by_voxel: dict[Voxel, int],
) -> set[Voxel]:
    added: set[Voxel] = set()
    assignment_by_id = {item.part_id: item for item in assignments}
    for part_id, part in enumerate(parts):
        assignment = assignment_by_id[part_id]
        if assignment.primitive_type == "shell":
            continue
        pixels = set(part.get("pixels", set()))
        for x, y in pixels:
            za = z_by_pixel_part.get((part_id, (x, y)), set())
            if not za:
                continue
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if (nx, ny) not in pixels:
                    continue
                zb = z_by_pixel_part.get((part_id, (nx, ny)), set())
                if not zb:
                    continue
                z_min = max(0, min(min(za), min(zb)) - 1)
                z_max = min(total_depth_slices - 1, max(max(za), max(zb)) + 1)
                for pixel in ((x, y), (nx, ny)):
                    for z in range(z_min, z_max + 1):
                        key = (pixel[0], pixel[1], z)
                        added.add(key)
                        owner_by_voxel[key] = part_id
    return added


def _pixel_owner(parts: list[dict[str, Any]]) -> dict[Pixel, int]:
    result: dict[Pixel, int] = {}
    for part_id, part in enumerate(parts):
        for pixel in part.get("pixels", set()):
            result[pixel] = part_id
    return result


def _z_by_pixel_part(occupancy: set[Voxel], owner_by_voxel: dict[Voxel, int]) -> dict[tuple[int, Pixel], set[int]]:
    result: dict[tuple[int, Pixel], set[int]] = {}
    for x, y, z in occupancy:
        part_id = owner_by_voxel.get((x, y, z))
        if part_id is None:
            continue
        result.setdefault((part_id, (x, y)), set()).add(z)
    return result


def _contact_pairs(a_pixels: Iterable[Pixel], b_pixels: Iterable[Pixel]) -> list[tuple[Pixel, Pixel]]:
    b = set(b_pixels)
    pairs: list[tuple[Pixel, Pixel]] = []
    for x, y in a_pixels:
        for other in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if other in b:
                pairs.append(((x, y), other))
    return pairs


def _nearest_pairs(a_pixels: Iterable[Pixel], b_pixels: Iterable[Pixel], max_pairs: int = 1) -> list[tuple[Pixel, Pixel]]:
    candidates = []
    b = list(b_pixels)
    for a in a_pixels:
        for other in b:
            distance = abs(a[0] - other[0]) + abs(a[1] - other[1])
            candidates.append((distance, a, other))
    candidates.sort(key=lambda item: item[0])
    return [(a, b) for _distance, a, b in candidates[:max_pairs]]


def _min_pixel_distance(a_pixels: Iterable[Pixel], b_pixels: Iterable[Pixel]) -> int:
    best = 999999
    b = list(b_pixels)
    for a in a_pixels:
        for other in b:
            best = min(best, abs(a[0] - other[0]) + abs(a[1] - other[1]))
            if best <= 1:
                return best
    return best


def _line_pixels(a: Pixel, b: Pixel) -> list[Pixel]:
    x0, y0 = a
    x1, y1 = b
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    pixels = []
    for index in range(steps + 1):
        t = index / steps
        pixels.append((round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)))
    return pixels


def _components(voxels: set[Voxel]) -> list[set[Voxel]]:
    remaining = set(voxels)
    components: list[set[Voxel]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            x, y, z = queue.popleft()
            for neighbour in ((x - 1, y, z), (x + 1, y, z), (x, y - 1, z), (x, y + 1, z), (x, y, z - 1), (x, y, z + 1)):
                if neighbour not in remaining:
                    continue
                remaining.remove(neighbour)
                component.add(neighbour)
                queue.append(neighbour)
        components.append(component)
    return components


def _edge_overlap_after(edges: list[dict[str, Any]], occupancy: set[Voxel], parts: list[dict[str, Any]]) -> int:
    count = 0
    for edge in edges:
        pairs = _contact_pairs(parts[edge["source_part_id"]]["pixels"], parts[edge["target_part_id"]]["pixels"])
        if not pairs:
            pairs = _nearest_pairs(parts[edge["source_part_id"]]["pixels"], parts[edge["target_part_id"]]["pixels"], max_pairs=3)
        for a_pixel, b_pixel in pairs:
            za = {z for x, y, z in occupancy if (x, y) == a_pixel}
            zb = {z for x, y, z in occupancy if (x, y) == b_pixel}
            if za and zb and max(za) >= min(zb) and max(zb) >= min(za):
                count += 1
                break
    return count


def _write_continuity_overlay(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    assignments: list[PrimitiveAssignment],
    graph: dict[str, Any],
    path: Path,
) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for assignment in assignments:
        x0, y0, x1, y1 = assignment.bbox
        colour = (70, 180, 255, 160) if assignment.primitive_type != "shell" else (30, 30, 30, 190)
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=colour, width=1)
    centers = {
        index: _bbox_center(part.get("bbox", [0, 0, 0, 0]))
        for index, part in enumerate(parts)
    }
    policy_colours = {
        POLICY_FUSE: (255, 210, 80, 220),
        POLICY_BRIDGE: (255, 100, 60, 220),
        POLICY_SHELL_ATTACH: (255, 255, 255, 200),
        POLICY_RIGID_ATTACH: (180, 180, 80, 220),
        POLICY_PRESERVE_GAP: (120, 120, 120, 110),
    }
    for edge in graph["edges"]:
        colour = policy_colours.get(edge["policy"], (255, 0, 255, 200))
        draw.line((centers[edge["source_part_id"]], centers[edge["target_part_id"]]), fill=colour, width=1)
    image.save(path, format="PNG")


def _write_voxel_projection(size: tuple[int, int], voxels: set[Voxel], path: Path, colour: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for x, y, _z in voxels:
        draw.point((x, y), fill=colour)
    image.save(path, format="PNG")


def _bbox_center(bbox: list[int]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5)
