from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from spritespatial.asset_schema import AssetSchema, SOURCE_DIRECTIONS

UPSCALE_NEAREST_INTEGER = "nearest_integer"
UPSCALE_SCALE2X = "scale2x"
UPSCALE_SCALE3X = "scale3x"
UPSCALE_EXTERNAL_ML = "external_ml"
UPSCALE_MODES = {
    UPSCALE_NEAREST_INTEGER,
    UPSCALE_SCALE2X,
    UPSCALE_SCALE3X,
    UPSCALE_EXTERNAL_ML,
}


@dataclass(frozen=True)
class UpscaleValidation:
    method: str
    scale_factor: int
    original_size: tuple[int, int]
    output_size: tuple[int, int]
    original_palette_size: int
    output_palette_size: int
    introduced_colours: set[tuple[int, int, int, int]]
    alpha_silhouette_similarity: float

    @property
    def is_lossless_palette(self) -> bool:
        return not self.introduced_colours

    @property
    def dimensions_match_scale(self) -> bool:
        return self.output_size == (
            self.original_size[0] * self.scale_factor,
            self.original_size[1] * self.scale_factor,
        )


def upscale_image(
    image: Image.Image,
    scale_factor: int = 2,
    mode: str = UPSCALE_NEAREST_INTEGER,
) -> Image.Image:
    """Return an upscaled RGBA image without generating new art content."""
    _validate_mode(mode)
    _validate_scale(scale_factor)

    source = image.convert("RGBA")
    if mode == UPSCALE_EXTERNAL_ML:
        raise NotImplementedError(
            "external_ml is a placeholder only. SpriteSpatial does not ship generative upscaling."
        )

    if mode == UPSCALE_NEAREST_INTEGER:
        return source.resize(
            (source.width * scale_factor, source.height * scale_factor),
            Image.Resampling.NEAREST,
        )

    if mode == UPSCALE_SCALE2X:
        if scale_factor != 2:
            raise ValueError("scale2x requires scale_factor=2")
        return _scale2x(source)

    if mode == UPSCALE_SCALE3X:
        if scale_factor != 3:
            raise ValueError("scale3x requires scale_factor=3")
        return _scale3x(source)

    raise ValueError(f"Unsupported upscale mode: {mode}")


def upscale_file(
    source_path: Path,
    output_path: Path,
    scale_factor: int = 2,
    mode: str = UPSCALE_NEAREST_INTEGER,
) -> UpscaleValidation:
    with Image.open(source_path) as image:
        source = image.convert("RGBA")

    upscaled = upscale_image(source, scale_factor=scale_factor, mode=mode)
    validation = validate_upscale(source, upscaled, scale_factor=scale_factor, method=mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    upscaled.save(output_path, format="PNG")
    return validation


def upscale_asset_sprites(
    asset: AssetSchema,
    output_dir: Path,
    scale_factor: int = 2,
    mode: str = UPSCALE_NEAREST_INTEGER,
) -> dict[str, UpscaleValidation]:
    validations: dict[str, UpscaleValidation] = {}
    output_dir.mkdir(parents=True, exist_ok=True)

    for direction in SOURCE_DIRECTIONS:
        source_path = asset.sprite_path(direction)
        output_path = output_dir / source_path.name
        validations[direction] = upscale_file(
            source_path,
            output_path,
            scale_factor=scale_factor,
            mode=mode,
        )

    return validations


def record_upscaling_method(
    spriteasset_path: Path,
    method: str = UPSCALE_NEAREST_INTEGER,
    scale_factor: int = 2,
    output_dir: Path | None = None,
) -> None:
    _validate_mode(method)
    _validate_scale(scale_factor)

    with spriteasset_path.open("r", encoding="utf-8") as stream:
        data: dict[str, Any] = json.load(stream)

    upscaling: dict[str, Any] = {
        "method": method,
        "scale_factor": scale_factor,
        "generates_new_art_content": False,
    }
    if output_dir is not None:
        upscaling["output_dir"] = output_dir.as_posix()

    data["upscaling"] = upscaling

    with spriteasset_path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def validate_upscale(
    original: Image.Image,
    output: Image.Image,
    scale_factor: int,
    method: str,
) -> UpscaleValidation:
    _validate_mode(method)
    _validate_scale(scale_factor)

    original_rgba = original.convert("RGBA")
    output_rgba = output.convert("RGBA")
    original_palette = _palette(original_rgba)
    output_palette = _palette(output_rgba)
    introduced = output_palette - original_palette

    validation = UpscaleValidation(
        method=method,
        scale_factor=scale_factor,
        original_size=original_rgba.size,
        output_size=output_rgba.size,
        original_palette_size=len(original_palette),
        output_palette_size=len(output_palette),
        introduced_colours=introduced,
        alpha_silhouette_similarity=_alpha_silhouette_similarity(
            original_rgba,
            output_rgba,
            scale_factor,
        ),
    )

    if not validation.dimensions_match_scale:
        raise ValueError(
            f"Upscaled dimensions {validation.output_size} do not match "
            f"{validation.original_size} at {scale_factor}x."
        )

    if method in {UPSCALE_NEAREST_INTEGER, UPSCALE_SCALE2X, UPSCALE_SCALE3X} and introduced:
        raise ValueError(
            f"{method} introduced {len(introduced)} new colours, which is not allowed."
        )

    min_similarity = 1.0 if method == UPSCALE_NEAREST_INTEGER else 0.9
    if validation.alpha_silhouette_similarity < min_similarity:
        raise ValueError(
            "Upscaled alpha silhouette differs too much from the expected "
            f"nearest-neighbour silhouette: {validation.alpha_silhouette_similarity:.3f}."
        )

    return validation


def _scale2x(source: Image.Image) -> Image.Image:
    width, height = source.size
    output = Image.new("RGBA", (width * 2, height * 2))
    src = source.load()
    dst = output.load()

    for y in range(height):
        for x in range(width):
            a = _get_pixel(src, width, height, x, y - 1)
            b = _get_pixel(src, width, height, x - 1, y)
            c = _get_pixel(src, width, height, x + 1, y)
            d = _get_pixel(src, width, height, x, y + 1)
            p = src[x, y]

            if b != c and a != d:
                e0 = b if a == b else p
                e1 = c if a == c else p
                e2 = b if d == b else p
                e3 = c if d == c else p
            else:
                e0 = e1 = e2 = e3 = p

            ox = x * 2
            oy = y * 2
            dst[ox, oy] = e0
            dst[ox + 1, oy] = e1
            dst[ox, oy + 1] = e2
            dst[ox + 1, oy + 1] = e3

    return output


def _scale3x(source: Image.Image) -> Image.Image:
    width, height = source.size
    output = Image.new("RGBA", (width * 3, height * 3))
    src = source.load()
    dst = output.load()

    for y in range(height):
        for x in range(width):
            a = _get_pixel(src, width, height, x - 1, y - 1)
            b = _get_pixel(src, width, height, x, y - 1)
            c = _get_pixel(src, width, height, x + 1, y - 1)
            d = _get_pixel(src, width, height, x - 1, y)
            e = src[x, y]
            f = _get_pixel(src, width, height, x + 1, y)
            g = _get_pixel(src, width, height, x - 1, y + 1)
            h = _get_pixel(src, width, height, x, y + 1)
            i = _get_pixel(src, width, height, x + 1, y + 1)

            if d != f and b != h:
                block = [
                    d if d == b else e,
                    b if (d == b and e != c) or (b == f and e != a) else e,
                    f if b == f else e,
                    d if (d == b and e != g) or (d == h and e != a) else e,
                    e,
                    f if (b == f and e != i) or (h == f and e != c) else e,
                    d if d == h else e,
                    h if (d == h and e != i) or (h == f and e != g) else e,
                    f if h == f else e,
                ]
            else:
                block = [e] * 9

            ox = x * 3
            oy = y * 3
            for row in range(3):
                for col in range(3):
                    dst[ox + col, oy + row] = block[row * 3 + col]

    return output


def _get_pixel(pixels: Any, width: int, height: int, x: int, y: int) -> tuple[int, int, int, int]:
    clamped_x = min(max(x, 0), width - 1)
    clamped_y = min(max(y, 0), height - 1)
    return pixels[clamped_x, clamped_y]


def _palette(image: Image.Image) -> set[tuple[int, int, int, int]]:
    return set(image.convert("RGBA").getdata())


def _alpha_silhouette_similarity(
    original: Image.Image,
    output: Image.Image,
    scale_factor: int,
) -> float:
    expected_alpha = original.getchannel("A").resize(
        (original.width * scale_factor, original.height * scale_factor),
        Image.Resampling.NEAREST,
    )
    output_alpha = output.getchannel("A")
    if expected_alpha.size != output_alpha.size:
        return 0.0

    expected = expected_alpha.load()
    actual = output_alpha.load()
    total = expected_alpha.width * expected_alpha.height
    if total == 0:
        return 1.0

    matches = 0
    for y in range(expected_alpha.height):
        for x in range(expected_alpha.width):
            if expected[x, y] == actual[x, y]:
                matches += 1

    return matches / total


def _validate_mode(mode: str) -> None:
    if mode not in UPSCALE_MODES:
        raise ValueError(f"Unsupported upscale mode: {mode}")


def _validate_scale(scale_factor: int) -> None:
    if scale_factor <= 0:
        raise ValueError("scale_factor must be greater than 0")
    if int(scale_factor) != scale_factor:
        raise ValueError("scale_factor must be an integer")
