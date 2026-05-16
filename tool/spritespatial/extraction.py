from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from spritespatial.alpha import (
    AlphaRemovalResult,
    alpha_debug_path,
    create_alpha_debug_image,
    load_rgba_png,
    remove_background_from_border,
    save_png_rgba,
    validate_rgba,
)


@dataclass(frozen=True)
class GridSpec:
    cell_width: int
    cell_height: int
    padding: int = 0

    def validate(self) -> None:
        if self.cell_width <= 0 or self.cell_height <= 0:
            raise ValueError("Cell width and height must be greater than 0.")
        if self.padding < 0:
            raise ValueError("Padding must be 0 or greater.")
        if self.padding * 2 >= self.cell_width or self.padding * 2 >= self.cell_height:
            raise ValueError("Padding is too large for the requested cell size.")


@dataclass(frozen=True)
class ExtractionResult:
    image: Image.Image
    alpha_result: AlphaRemovalResult
    output_path: Path
    alpha_debug_path: Path


def cell_box(row: int, col: int, grid: GridSpec) -> tuple[int, int, int, int]:
    if row < 0 or col < 0:
        raise ValueError("Row and column must be non-negative.")

    left = col * grid.cell_width + grid.padding
    top = row * grid.cell_height + grid.padding
    right = (col + 1) * grid.cell_width - grid.padding
    bottom = (row + 1) * grid.cell_height - grid.padding
    return left, top, right, bottom


def extract_cell(
    sheet_path: Path,
    grid: GridSpec,
    row: int,
    col: int,
    output_path: Path,
    bg_tolerance: int = 12,
) -> ExtractionResult:
    grid.validate()
    sheet = load_rgba_png(sheet_path)
    box = cell_box(row, col, grid)
    if box[2] > sheet.width or box[3] > sheet.height:
        raise ValueError(f"Cell {row},{col} exceeds sheet bounds {sheet.size}.")

    crop = sheet.crop(box).convert("RGBA")
    alpha_result = remove_background_from_border(crop, tolerance=bg_tolerance)
    validate_rgba(alpha_result.image)
    save_png_rgba(alpha_result.image, output_path)

    debug_path = alpha_debug_path(output_path)
    save_png_rgba(create_alpha_debug_image(alpha_result.image), debug_path)

    return ExtractionResult(
        image=alpha_result.image,
        alpha_result=alpha_result,
        output_path=output_path,
        alpha_debug_path=debug_path,
    )


def draw_debug_grid(
    sheet_path: Path,
    grid: GridSpec,
    output_path: Path,
) -> None:
    grid.validate()
    image = load_rgba_png(sheet_path)
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    font = ImageFont.load_default()

    grid_color = (255, 0, 255, 220)
    label_bg = (0, 0, 0, 170)
    label_fg = (255, 255, 255, 255)

    for x in range(0, width + 1, grid.cell_width):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height + 1, grid.cell_height):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    rows = (height + grid.cell_height - 1) // grid.cell_height
    cols = (width + grid.cell_width - 1) // grid.cell_width
    for row in range(rows):
        for col in range(cols):
            x = col * grid.cell_width + 1
            y = row * grid.cell_height + 1
            label = f"{row},{col}"
            text_box = draw.textbbox((0, 0), label, font=font)
            label_width = text_box[2] - text_box[0]
            label_height = text_box[3] - text_box[1]
            draw.rectangle((x, y, x + label_width + 4, y + label_height + 4), fill=label_bg)
            draw.text((x + 2, y + 2), label, fill=label_fg, font=font)

    save_png_rgba(image, output_path)
