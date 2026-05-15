from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

try:
    from PIL import Image
except ImportError as exc:
    raise ImportError(
        "Pillow is required for sprite image manipulation. "
        "Install it with `pip install pillow`."
    ) from exc


def mirror_horizontal(source_path: Path, target_path: Path) -> None:
    """Write a horizontally mirrored copy of a PNG sprite."""
    with Image.open(source_path) as image:
        flipped = image.transpose(Image.FLIP_LEFT_RIGHT)
        flipped.save(target_path, format="PNG")


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def mirror_sprite_to_left_right(source_path: Path, left_path: Path, right_path: Path) -> None:
    ensure_dir(left_path)
    ensure_dir(right_path)
    mirror_horizontal(source_path, left_path)
    with Image.open(source_path) as image:
        image.save(right_path, format="PNG")
