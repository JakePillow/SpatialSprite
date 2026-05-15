from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


DIRECTIONS = ("front", "back", "left", "right")


def parse_cell(value: str) -> tuple[int, int]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Cell coordinates must use row,col format.")

    try:
        row = int(parts[0])
        col = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Cell row and column must be integers.") from exc

    if row < 0 or col < 0:
        raise argparse.ArgumentTypeError("Cell row and column must be non-negative.")

    return row, col


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract directional sprites from a sprite sheet by row/column cell coordinates."
    )
    parser.add_argument("sprite_sheet", type=Path, help="Path to the source sprite sheet PNG.")
    parser.add_argument("cell_width", type=int, help="Grid cell width in pixels.")
    parser.add_argument("cell_height", type=int, help="Grid cell height in pixels.")
    parser.add_argument("--x-offset", type=int, default=0, help="Left pixel offset before the first cell.")
    parser.add_argument("--y-offset", type=int, default=0, help="Top pixel offset before the first cell.")
    parser.add_argument(
        "--x-stride",
        type=int,
        help="Horizontal distance between cell starts. Defaults to cell width.",
    )
    parser.add_argument(
        "--y-stride",
        type=int,
        help="Vertical distance between cell starts. Defaults to cell height.",
    )
    parser.add_argument("--front", required=True, type=parse_cell, help="Front sprite cell as row,col.")
    parser.add_argument("--back", required=True, type=parse_cell, help="Back sprite cell as row,col.")
    parser.add_argument("--left", required=True, type=parse_cell, help="Left sprite cell as row,col.")
    parser.add_argument("--right", required=True, type=parse_cell, help="Right sprite cell as row,col.")
    parser.add_argument(
        "--transparent-bg",
        action="store_true",
        help="Convert a flat background color to alpha in extracted sprites.",
    )
    parser.add_argument(
        "--bg-color",
        help="Background color to make transparent as R,G,B. Defaults to the sheet's top-left pixel.",
    )
    parser.add_argument(
        "--bg-tolerance",
        type=int,
        default=0,
        help="Per-channel tolerance for transparent background matching. Defaults to 0.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for front.png, back.png, left.png, and right.png. Defaults to current directory.",
    )
    return parser.parse_args()


def parse_rgb(value: str) -> tuple[int, int, int]:
    parts = value.split(",")
    if len(parts) != 3:
        raise ValueError("Background color must use R,G,B format.")

    try:
        rgb = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("Background color channels must be integers.") from exc

    if any(channel < 0 or channel > 255 for channel in rgb):
        raise ValueError("Background color channels must be between 0 and 255.")

    return rgb


def make_background_transparent(
    image: Image.Image,
    bg_color: tuple[int, int, int],
    tolerance: int,
) -> Image.Image:
    if tolerance < 0:
        raise ValueError("Background tolerance must be 0 or greater.")

    result = image.convert("RGBA")
    pixels = []
    for red, green, blue, alpha in result.getdata():
        if (
            abs(red - bg_color[0]) <= tolerance
            and abs(green - bg_color[1]) <= tolerance
            and abs(blue - bg_color[2]) <= tolerance
        ):
            pixels.append((red, green, blue, 0))
        else:
            pixels.append((red, green, blue, alpha))
    result.putdata(pixels)
    return result


def validate_args(sprite_sheet: Path, cell_width: int, cell_height: int) -> None:
    if not sprite_sheet.exists():
        raise FileNotFoundError(f"Sprite sheet not found: {sprite_sheet}")
    if sprite_sheet.suffix.lower() != ".png":
        raise ValueError("Sprite sheet must be a PNG file.")
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError("Cell width and height must be greater than 0.")


def cell_box(
    row: int,
    col: int,
    cell_width: int,
    cell_height: int,
    x_offset: int,
    y_offset: int,
    x_stride: int,
    y_stride: int,
) -> tuple[int, int, int, int]:
    left = x_offset + col * x_stride
    top = y_offset + row * y_stride
    return left, top, left + cell_width, top + cell_height


def validate_cell_inside_sheet(
    direction: str,
    row: int,
    col: int,
    cell_width: int,
    cell_height: int,
    x_offset: int,
    y_offset: int,
    x_stride: int,
    y_stride: int,
    sheet_size: tuple[int, int],
) -> None:
    _, _, right, bottom = cell_box(
        row,
        col,
        cell_width,
        cell_height,
        x_offset,
        y_offset,
        x_stride,
        y_stride,
    )
    width, height = sheet_size
    if right > width or bottom > height:
        raise ValueError(
            f"{direction} cell {row},{col} exceeds sheet bounds "
            f"{width}x{height} with cell size {cell_width}x{cell_height}."
        )


def extract_directional_sprites(
    sprite_sheet: Path,
    cell_width: int,
    cell_height: int,
    x_offset: int,
    y_offset: int,
    x_stride: int,
    y_stride: int,
    cells: dict[str, tuple[int, int]],
    output_dir: Path,
    transparent_bg: bool,
    bg_color: tuple[int, int, int] | None,
    bg_tolerance: int,
) -> None:
    image = Image.open(sprite_sheet).convert("RGBA")
    resolved_bg_color = bg_color or image.getpixel((0, 0))[:3]
    output_dir.mkdir(parents=True, exist_ok=True)

    for direction in DIRECTIONS:
        row, col = cells[direction]
        validate_cell_inside_sheet(
            direction,
            row,
            col,
            cell_width,
            cell_height,
            x_offset,
            y_offset,
            x_stride,
            y_stride,
            image.size,
        )
        sprite = image.crop(
            cell_box(row, col, cell_width, cell_height, x_offset, y_offset, x_stride, y_stride)
        )
        if transparent_bg:
            sprite = make_background_transparent(sprite, resolved_bg_color, bg_tolerance)
        sprite.save(output_dir / f"{direction}.png", format="PNG")


def main() -> int:
    args = parse_args()
    cells = {direction: getattr(args, direction) for direction in DIRECTIONS}
    x_stride = args.x_stride or args.cell_width
    y_stride = args.y_stride or args.cell_height
    bg_color = parse_rgb(args.bg_color) if args.bg_color else None

    try:
        validate_args(args.sprite_sheet, args.cell_width, args.cell_height)
        extract_directional_sprites(
            args.sprite_sheet,
            args.cell_width,
            args.cell_height,
            args.x_offset,
            args.y_offset,
            x_stride,
            y_stride,
            cells,
            args.output_dir,
            args.transparent_bg,
            bg_color,
            args.bg_tolerance,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    for direction in DIRECTIONS:
        print(f"Wrote {args.output_dir / f'{direction}.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
