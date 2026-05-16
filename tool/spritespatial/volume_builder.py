from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class VolumeConfig:
    total_depth_slices: int = 12
    front_relief_ratio: float = 0.30
    core_ratio: float = 0.40
    back_relief_ratio: float = 0.30
    voxel_size: float = 0.05
    alpha_threshold: int = 16


def build_filled_volume(
    front_mask: list[list[bool]],
    back_mask: list[list[bool]],
    front_depth: Image.Image,
    back_depth: Image.Image,
    config: VolumeConfig,
) -> tuple[list[list[list[bool]]], dict]:
    if config.total_depth_slices < 3:
        raise ValueError("total_depth_slices must be at least 3.")
    height = len(front_mask)
    width = len(front_mask[0])
    slices = config.total_depth_slices
    front_pixels = front_depth.convert("L").load()
    back_pixels = back_depth.convert("L").load()
    volume = [[[False for _x in range(width)] for _y in range(height)] for _z in range(slices)]

    front_relief_slices = max(1, round(slices * config.front_relief_ratio))
    back_relief_slices = max(1, round(slices * config.back_relief_ratio))
    core_start = back_relief_slices
    core_end = max(core_start, slices - front_relief_slices)

    for z in range(slices):
        t = z / max(slices - 1, 1)
        for y in range(height):
            for x in range(width):
                front = front_mask[y][x]
                back = back_mask[y][x]
                occupied = front or back

                if not occupied:
                    occupied = _interpolated_near_mask(front_mask, back_mask, x, y, t)

                if core_start <= z <= core_end and (front or back):
                    occupied = True

                front_strength = front_pixels[x, y] / 255.0
                back_strength = back_pixels[x, y] / 255.0
                front_relief = max(1, round(front_strength * front_relief_slices)) if front_strength > 0 else 0
                back_relief = max(1, round(back_strength * back_relief_slices)) if back_strength > 0 else 0
                if front_relief and z >= slices - front_relief:
                    occupied = True
                if back_relief and z < back_relief:
                    occupied = True

                volume[z][y][x] = occupied

    stats = volume_stats(volume)
    stats.update(
        {
            "front_relief_slices": front_relief_slices,
            "core_start": core_start,
            "core_end": core_end,
            "back_relief_slices": back_relief_slices,
            "hollow_gap_ratio": hollow_gap_ratio(volume, front_mask, back_mask),
        }
    )
    return volume, stats


def volume_stats(volume: list[list[list[bool]]]) -> dict:
    occupied = sum(1 for slice_rows in volume for row in slice_rows for value in row if value)
    total = len(volume) * len(volume[0]) * len(volume[0][0])
    return {
        "occupied_voxel_count": occupied,
        "total_voxel_count": total,
        "occupied_ratio": occupied / total if total else 0.0,
        "depth_slices": len(volume),
    }


def hollow_gap_ratio(
    volume: list[list[list[bool]]],
    front_mask: list[list[bool]],
    back_mask: list[list[bool]],
) -> float:
    gaps = 0
    expected = 0
    for y in range(len(front_mask)):
        for x in range(len(front_mask[0])):
            if not (front_mask[y][x] or back_mask[y][x]):
                continue
            expected += len(volume)
            gaps += sum(1 for z in range(len(volume)) if not volume[z][y][x])
    return gaps / expected if expected else 0.0


def _interpolated_near_mask(
    front_mask: list[list[bool]],
    back_mask: list[list[bool]],
    x: int,
    y: int,
    t: float,
) -> bool:
    radius = 1 if 0.2 <= t <= 0.8 else 0
    height = len(front_mask)
    width = len(front_mask[0])
    for yy in range(max(0, y - radius), min(height, y + radius + 1)):
        for xx in range(max(0, x - radius), min(width, x + radius + 1)):
            if front_mask[yy][xx] or back_mask[yy][xx]:
                return True
    return False
