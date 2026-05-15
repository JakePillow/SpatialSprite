from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "spriteasset_v1"
RENDER_MODE_DIRECTIONAL = "directional_sprite_3d"
SOURCE_DIRECTIONS = ("front", "back", "left", "right")


@dataclass(frozen=True)
class AssetSchema:
    schema_version: str
    asset_name: str
    asset_type: str
    source_sprites: dict[str, str]
    render_mode: str
    pixel_scale: float
    collision: dict[str, Any]
    upscaling: dict[str, Any]
    source_dir: Path

    @classmethod
    def load_from_file(cls, file_path: Path) -> "AssetSchema":
        if not file_path.exists():
            raise FileNotFoundError(f"Asset schema file not found: {file_path}")

        with file_path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)

        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version: {data.get('schema_version')} "
                f"(expected {SCHEMA_VERSION})"
            )

        if data.get("render_mode") != RENDER_MODE_DIRECTIONAL:
            raise ValueError(
                f"Unsupported render_mode: {data.get('render_mode')} "
                f"(expected {RENDER_MODE_DIRECTIONAL})"
            )

        source_sprites = data.get("source_sprites")
        if not isinstance(source_sprites, dict):
            raise ValueError("source_sprites must be an object mapping directions to file names")

        missing = [direction for direction in SOURCE_DIRECTIONS if direction not in source_sprites]
        if missing:
            raise ValueError(f"source_sprites missing required directions: {missing}")

        return cls(
            schema_version=data["schema_version"],
            asset_name=data["asset_name"],
            asset_type=data["asset_type"],
            source_sprites={direction: source_sprites[direction] for direction in SOURCE_DIRECTIONS},
            render_mode=data["render_mode"],
            pixel_scale=float(data["pixel_scale"]),
            collision=data["collision"],
            upscaling=data.get("upscaling", {"method": "nearest_integer"}),
            source_dir=file_path.parent,
        )

    def sprite_path(self, direction: str) -> Path:
        if direction not in SOURCE_DIRECTIONS:
            raise ValueError(f"Unknown sprite direction: {direction}")
        return self.source_dir / self.source_sprites[direction]
