from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable

from spritespatial.asset_schema import AssetSchema, SOURCE_DIRECTIONS
from spritespatial.upscale import UPSCALE_EXTERNAL_ML, UPSCALE_MODES, UPSCALE_NEAREST_INTEGER

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def inspect_png(path: Path) -> tuple[int, int, bool]:
    with path.open("rb") as stream:
        signature = stream.read(8)
        if signature != PNG_SIGNATURE:
            raise ValueError(f"File is not a PNG: {path}")

        width = height = None
        has_alpha = False

        while True:
            header = stream.read(8)
            if len(header) < 8:
                break
            length, chunk_type = struct.unpack(">I4s", header)
            chunk_data = stream.read(length)
            stream.read(4)

            if chunk_type == b"IHDR":
                if len(chunk_data) != 13:
                    raise ValueError("Invalid IHDR chunk")
                width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk_data)
                if color_type in (4, 6):
                    has_alpha = True
            elif chunk_type == b"tRNS":
                has_alpha = True
            elif chunk_type == b"IEND":
                break

        if width is None or height is None:
            raise ValueError(f"PNG missing IHDR chunk: {path}")

        return width, height, has_alpha


def validate_asset_schema(asset: AssetSchema) -> None:
    if asset.pixel_scale <= 0:
        raise ValueError("pixel_scale must be greater than 0")

    if not isinstance(asset.collision, dict):
        raise ValueError("collision must be an object")

    collision_type = asset.collision.get("type")
    if collision_type != "capsule":
        raise ValueError("collision.type must be 'capsule' for directional_sprite_3d assets")

    if asset.collision.get("height") is None or asset.collision.get("radius") is None:
        raise ValueError("collision must include height and radius")

    validate_upscaling_config(asset)

    sprite_sizes: list[tuple[int, int]] = []
    for direction in SOURCE_DIRECTIONS:
        sprite_path = asset.sprite_path(direction)
        if not sprite_path.exists():
            raise FileNotFoundError(f"Missing sprite image for {direction}: {sprite_path}")
        if sprite_path.suffix.lower() != ".png":
            raise ValueError("Sprite images must be PNG files")

        width, height, has_alpha = inspect_png(sprite_path)
        if not has_alpha:
            raise ValueError(f"Sprite image does not contain an alpha channel: {sprite_path}")
        sprite_sizes.append((width, height))

    first_size = sprite_sizes[0]
    for direction, size in zip(SOURCE_DIRECTIONS, sprite_sizes):
        if size != first_size:
            raise ValueError(
                "All source sprites must have the same dimensions. "
                f"{direction} has size {size}, expected {first_size}."
            )


def validate_upscaling_config(asset: AssetSchema) -> None:
    if not isinstance(asset.upscaling, dict):
        raise ValueError("upscaling must be an object when provided")

    method = asset.upscaling.get("method", UPSCALE_NEAREST_INTEGER)
    if method not in UPSCALE_MODES:
        raise ValueError(f"Unsupported upscaling.method: {method}")

    if method == UPSCALE_EXTERNAL_ML:
        raise ValueError(
            "upscaling.method='external_ml' is a placeholder only and is not implemented"
        )

    scale_factor = int(asset.upscaling.get("scale_factor", 1))
    if scale_factor <= 0:
        raise ValueError("upscaling.scale_factor must be greater than 0")

    generates_new_art = asset.upscaling.get("generates_new_art_content", False)
    if generates_new_art:
        raise ValueError("SpriteSpatial upscaling must not generate new art content")


def validate_paths_exist(asset: AssetSchema) -> None:
    for direction in SOURCE_DIRECTIONS:
        sprite_path = asset.sprite_path(direction)
        if not sprite_path.exists():
            raise FileNotFoundError(f"Missing sprite image for {direction}: {sprite_path}")


def validate_image_dimensions(asset: AssetSchema) -> None:
    widths = []
    heights = []
    for direction in SOURCE_DIRECTIONS:
        width, height, _ = inspect_png(asset.sprite_path(direction))
        widths.append(width)
        heights.append(height)
    if len(set(widths)) != 1 or len(set(heights)) != 1:
        raise ValueError("Sprite dimensions must match between front, back, left, and right images")


def validate_alpha_channels(asset: AssetSchema) -> None:
    for direction in SOURCE_DIRECTIONS:
        _, _, has_alpha = inspect_png(asset.sprite_path(direction))
        if not has_alpha:
            raise ValueError(f"Missing alpha channel in sprite: {direction}")
