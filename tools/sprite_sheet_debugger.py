from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overlay a labeled grid on a sprite sheet PNG."
    )
    parser.add_argument("sprite_sheet", type=Path, help="Path to the source sprite sheet PNG.")
    parser.add_argument("cell_width", type=int, help="Grid cell width in pixels.")
    parser.add_argument("cell_height", type=int, help="Grid cell height in pixels.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("debug_grid.png"),
        help="Output PNG path. Defaults to debug_grid.png.",
    )
    return parser.parse_args()


def validate_args(sprite_sheet: Path, cell_width: int, cell_height: int) -> None:
    if not sprite_sheet.exists():
        raise FileNotFoundError(f"Sprite sheet not found: {sprite_sheet}")
    if sprite_sheet.suffix.lower() != ".png":
        raise ValueError("Sprite sheet must be a PNG file.")
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError("Cell width and height must be greater than 0.")


def draw_labeled_grid(
    sprite_sheet: Path,
    cell_width: int,
    cell_height: int,
    output_path: Path,
) -> None:
    image = Image.open(sprite_sheet).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size

    grid_color = (255, 0, 255, 220)
    major_grid_color = (255, 255, 0, 240)
    label_bg = (0, 0, 0, 170)
    label_fg = (255, 255, 255, 255)
    font = ImageFont.load_default()

    for x in range(0, width + 1, cell_width):
        color = major_grid_color if x == 0 or x >= width else grid_color
        draw.line([(x, 0), (x, height)], fill=color, width=1)

    for y in range(0, height + 1, cell_height):
        color = major_grid_color if y == 0 or y >= height else grid_color
        draw.line([(0, y), (width, y)], fill=color, width=1)

    rows = (height + cell_height - 1) // cell_height
    cols = (width + cell_width - 1) // cell_width
    for row in range(rows):
        for col in range(cols):
            x = col * cell_width
            y = row * cell_height
            label = f"{row},{col}"
            box = draw.textbbox((0, 0), label, font=font)
            label_width = box[2] - box[0]
            label_height = box[3] - box[1]
            padding = 2
            draw.rectangle(
                [
                    x + 1,
                    y + 1,
                    x + label_width + padding * 2 + 1,
                    y + label_height + padding * 2 + 1,
                ],
                fill=label_bg,
            )
            draw.text((x + padding + 1, y + padding + 1), label, fill=label_fg, font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args.sprite_sheet, args.cell_width, args.cell_height)
        draw_labeled_grid(args.sprite_sheet, args.cell_width, args.cell_height, args.output)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote debug grid: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
