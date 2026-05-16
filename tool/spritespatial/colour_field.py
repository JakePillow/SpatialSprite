from __future__ import annotations

from typing import Literal

from PIL import Image

SideColourMode = Literal["nearest_front", "nearest_back", "blend_front_back", "nearest_valid_edge"]
RGBA = tuple[int, int, int, int]


def nearest_colour_grid(image: Image.Image, alpha_threshold: int = 16) -> list[list[RGBA]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    opaque: list[tuple[int, int, RGBA]] = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            pixel = pixels[x, y]
            if pixel[3] > alpha_threshold:
                opaque.append((x, y, pixel))
    if not opaque:
        return [[(32, 32, 32, 255) for _x in range(rgba.width)] for _y in range(rgba.height)]

    grid: list[list[RGBA]] = []
    for y in range(rgba.height):
        row: list[RGBA] = []
        for x in range(rgba.width):
            pixel = pixels[x, y]
            if pixel[3] > alpha_threshold:
                row.append(pixel)
                continue
            nearest = min(opaque, key=lambda item: (item[0] - x) ** 2 + (item[1] - y) ** 2)
            row.append(nearest[2])
        grid.append(row)
    return grid


def build_colour_field(
    front: Image.Image,
    back: Image.Image,
    volume: list[list[list[bool]]],
    mode: SideColourMode = "blend_front_back",
    alpha_threshold: int = 16,
) -> tuple[list[list[list[RGBA]]], dict]:
    front_rgba = front.convert("RGBA")
    back_rgba = back.convert("RGBA")
    front_pixels = front_rgba.load()
    back_pixels = back_rgba.load()
    front_nearest = nearest_colour_grid(front_rgba, alpha_threshold)
    back_nearest = nearest_colour_grid(back_rgba, alpha_threshold)
    depth_slices = len(volume)
    height = front_rgba.height
    width = front_rgba.width
    fallback_count = 0

    colour_field: list[list[list[RGBA]]] = []
    for z in range(depth_slices):
        t = z / max(depth_slices - 1, 1)
        slice_rows: list[list[RGBA]] = []
        for y in range(height):
            row: list[RGBA] = []
            for x in range(width):
                if not volume[z][y][x]:
                    row.append((0, 0, 0, 0))
                    continue
                if z == 0 and back_pixels[x, y][3] > alpha_threshold:
                    colour = back_pixels[x, y]
                elif z == depth_slices - 1 and front_pixels[x, y][3] > alpha_threshold:
                    colour = front_pixels[x, y]
                else:
                    front_colour = front_nearest[y][x]
                    back_colour = back_nearest[y][x]
                    colour = side_colour(front_colour, back_colour, mode, t)
                    if colour[:3] == (0, 0, 0) and front_colour[:3] != (0, 0, 0) and back_colour[:3] != (0, 0, 0):
                        fallback_count += 1
                row.append(colour)
            slice_rows.append(row)
        colour_field.append(slice_rows)
    return colour_field, {"fallback_colour_count": fallback_count}


def side_colour(front: RGBA, back: RGBA, mode: SideColourMode, t: float) -> RGBA:
    if mode == "nearest_front":
        base = front
    elif mode == "nearest_back":
        base = back
    elif mode == "nearest_valid_edge":
        base = front if t >= 0.5 else back
    else:
        base = (
            int(front[0] * t + back[0] * (1.0 - t)),
            int(front[1] * t + back[1] * (1.0 - t)),
            int(front[2] * t + back[2] * (1.0 - t)),
            255,
        )
    return (int(base[0] * 0.78), int(base[1] * 0.78), int(base[2] * 0.78), 255)


def is_blackish(colour: RGBA) -> bool:
    return colour[3] > 0 and max(colour[0], colour[1], colour[2]) <= 8
