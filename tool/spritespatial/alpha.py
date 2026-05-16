from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


RGB = tuple[int, int, int]


@dataclass(frozen=True)
class AlphaRemovalResult:
    image: Image.Image
    sampled_colours: tuple[RGB, ...]
    tolerance: int
    transparent_pixels: int

    @property
    def transparent_ratio(self) -> float:
        total = self.image.width * self.image.height
        if total == 0:
            return 0.0
        alpha = self.image.getchannel("A")
        transparent = sum(1 for value in alpha.getdata() if value == 0)
        return transparent / total


def load_rgba_png(path: Path) -> Image.Image:
    if path.suffix.lower() != ".png":
        raise ValueError("Only PNG files are supported.")
    return Image.open(path).convert("RGBA")


def save_png_rgba(image: Image.Image, path: Path) -> None:
    rgba = image.convert("RGBA")
    if rgba.mode != "RGBA":
        raise ValueError("Output image is not RGBA.")
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(path, format="PNG")


def has_alpha(image: Image.Image) -> bool:
    return image.mode == "RGBA" or "A" in image.getbands()


def remove_background_from_border(
    image: Image.Image,
    tolerance: int = 12,
    max_sample_colours: int = 4,
) -> AlphaRemovalResult:
    if tolerance < 0:
        raise ValueError("Background tolerance must be 0 or greater.")

    result = image.convert("RGBA")
    pixels = result.load()
    sampled_colours = _sample_background_colours(result, max_sample_colours)
    visited: set[tuple[int, int]] = set()
    queue: list[tuple[int, int]] = []
    transparent_pixels = 0

    def enqueue_if_background(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        red, green, blue, _ = pixels[x, y]
        if _matches_any_background((red, green, blue), sampled_colours, tolerance):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(result.width):
        enqueue_if_background(x, 0)
        enqueue_if_background(x, result.height - 1)
    for y in range(result.height):
        enqueue_if_background(0, y)
        enqueue_if_background(result.width - 1, y)

    while queue:
        x, y = queue.pop()
        red, green, blue, alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if alpha != 0:
            transparent_pixels += 1

        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if next_x < 0 or next_y < 0 or next_x >= result.width or next_y >= result.height:
                continue
            enqueue_if_background(next_x, next_y)

    return AlphaRemovalResult(
        image=result,
        sampled_colours=sampled_colours,
        tolerance=tolerance,
        transparent_pixels=transparent_pixels,
    )


def create_alpha_debug_image(image: Image.Image, tile_size: int = 4) -> Image.Image:
    source = image.convert("RGBA")
    debug = Image.new("RGBA", source.size)
    source_pixels = source.load()
    debug_pixels = debug.load()
    light = (190, 190, 190, 255)
    dark = (120, 120, 120, 255)

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source_pixels[x, y]
            if alpha == 0:
                debug_pixels[x, y] = light if ((x // tile_size) + (y // tile_size)) % 2 == 0 else dark
            else:
                debug_pixels[x, y] = (red, green, blue, alpha)

    return debug


def alpha_debug_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_alpha_debug.png")


def validate_rgba(image: Image.Image) -> None:
    if image.mode != "RGBA":
        raise ValueError(f"Output is not RGBA: {image.mode}")
    if not has_alpha(image):
        raise ValueError("Output does not have an alpha channel.")


def _sample_background_colours(image: Image.Image, max_colours: int) -> tuple[RGB, ...]:
    pixels = image.load()
    ring: list[RGB] = []

    for x in range(image.width):
        ring.append(pixels[x, 0][:3])
        ring.append(pixels[x, image.height - 1][:3])
    for y in range(1, image.height - 1):
        ring.append(pixels[0, y][:3])
        ring.append(pixels[image.width - 1, y][:3])

    sampled: list[RGB] = []
    corner_colours = [
        pixels[0, 0][:3],
        pixels[image.width - 1, 0][:3],
        pixels[0, image.height - 1][:3],
        pixels[image.width - 1, image.height - 1][:3],
    ]

    for colour in corner_colours:
        if _is_protected_outline_colour(colour):
            continue
        if not any(_rgb_close(colour, existing, 0) for existing in sampled):
            sampled.append(colour)

    counter = Counter(
        colour
        for colour in ring
        if not _is_protected_outline_colour(colour)
        and any(_rgb_close(colour, corner, 16) for corner in sampled)
    )

    for colour, _ in counter.most_common(max_colours):
        if not any(_rgb_close(colour, existing, 0) for existing in sampled):
            sampled.append(colour)

    return tuple(sampled)


def _matches_any_background(colour: RGB, backgrounds: tuple[RGB, ...], tolerance: int) -> bool:
    if _is_protected_outline_colour(colour):
        return False
    return any(_rgb_close(colour, background, tolerance) for background in backgrounds)


def _rgb_close(a: RGB, b: RGB, tolerance: int) -> bool:
    return (
        abs(a[0] - b[0]) <= tolerance
        and abs(a[1] - b[1]) <= tolerance
        and abs(a[2] - b[2]) <= tolerance
    )


def _is_protected_outline_colour(colour: RGB) -> bool:
    darkest = min(colour)
    brightest = max(colour)
    return brightest <= 72 and brightest - darkest <= 18
