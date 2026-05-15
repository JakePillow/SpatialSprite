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
    parser.add_argument(
        "pos_cell_width",
        nargs="?",
        type=int,
        help="Grid cell width in pixels. Prefer --cell-width for new calls.",
    )
    parser.add_argument(
        "pos_cell_height",
        nargs="?",
        type=int,
        help="Grid cell height in pixels. Prefer --cell-height for new calls.",
    )
    parser.add_argument("--cell-width", type=int, help="Grid cell width in pixels.")
    parser.add_argument("--cell-height", type=int, help="Grid cell height in pixels.")
    parser.add_argument("--row", type=int, help="Single sprite row coordinate.")
    parser.add_argument("--col", type=int, help="Single sprite column coordinate.")
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
    parser.add_argument("--front", type=parse_cell, help="Front sprite cell as row,col.")
    parser.add_argument("--back", type=parse_cell, help="Back sprite cell as row,col.")
    parser.add_argument("--left", type=parse_cell, help="Left sprite cell as row,col.")
    parser.add_argument("--right", type=parse_cell, help="Right sprite cell as row,col.")
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
        help="Deprecated alias for --tolerance.",
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        default=12,
        help="Per-channel RGB tolerance for transparent background matching. Defaults to 12.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for front.png, back.png, left.png, and right.png. Defaults to current directory.",
    )
    parser.add_argument("--output", type=Path, help="Output PNG path for single-cell extraction.")
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
) -> tuple[Image.Image, int]:
    if tolerance < 0:
        raise ValueError("Background tolerance must be 0 or greater.")

    result = image.convert("RGBA")
    source_pixels = result.load()
    output_pixels = result.load()
    transparent_count = 0

    for y in range(result.height):
        for x in range(result.width):
            red, green, blue, alpha = source_pixels[x, y]
            if (
                abs(red - bg_color[0]) <= tolerance
                and abs(green - bg_color[1]) <= tolerance
                and abs(blue - bg_color[2]) <= tolerance
            ):
                output_pixels[x, y] = (red, green, blue, 0)
                if alpha != 0:
                    transparent_count += 1
    return result, transparent_count


def has_alpha(image: Image.Image) -> bool:
    return image.mode == "RGBA" or "A" in image.getbands()


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
                checker = light if ((x // tile_size) + (y // tile_size)) % 2 == 0 else dark
                debug_pixels[x, y] = checker
            else:
                debug_pixels[x, y] = (red, green, blue, alpha)

    return debug


def alpha_debug_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_alpha_debug.png")


def validate_background_corners_are_transparent(image: Image.Image) -> None:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    sample_size = max(1, min(rgba.width, rgba.height, 8) // 2)
    corners = [
        (0, 0),
        (max(rgba.width - sample_size, 0), 0),
        (0, max(rgba.height - sample_size, 0)),
        (max(rgba.width - sample_size, 0), max(rgba.height - sample_size, 0)),
    ]

    total = 0
    opaque = 0
    for start_x, start_y in corners:
        for y in range(start_y, min(start_y + sample_size, rgba.height)):
            for x in range(start_x, min(start_x + sample_size, rgba.width)):
                total += 1
                if pixels[x, y][3] != 0:
                    opaque += 1

    if total == 0:
        return

    opaque_ratio = opaque / total
    if opaque_ratio > 0.2:
        raise ValueError(
            "Background transparency validation failed: "
            f"{opaque_ratio:.1%} of sampled corner/background pixels remain opaque "
            f"({opaque}/{total}). Increase --bg-tolerance or adjust the cell crop."
        )


def debug_print(
    label: str,
    bg_color: tuple[int, int, int],
    transparent_count: int,
    image: Image.Image,
) -> None:
    print(f"{label}: sampled background RGB {bg_color}")
    print(f"{label}: made {transparent_count} pixels transparent")
    print(f"{label}: final image mode {image.mode}")
    print(f"{label}: alpha channel exists {'yes' if has_alpha(image) else 'no'}")


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
        resolved_bg_color = bg_color or sprite.getpixel((0, 0))[:3]
        transparent_count = 0
        if transparent_bg:
            sprite, transparent_count = make_background_transparent(
                sprite,
                resolved_bg_color,
                bg_tolerance,
            )
            validate_background_corners_are_transparent(sprite)

        output_path = output_dir / f"{direction}.png"
        sprite.save(output_path, format="PNG")
        create_alpha_debug_image(sprite).save(alpha_debug_path(output_path), format="PNG")
        debug_print(direction, resolved_bg_color, transparent_count, sprite)


def extract_single_sprite(
    sprite_sheet: Path,
    cell_width: int,
    cell_height: int,
    x_offset: int,
    y_offset: int,
    x_stride: int,
    y_stride: int,
    row: int,
    col: int,
    output_path: Path,
    bg_color: tuple[int, int, int] | None,
    bg_tolerance: int,
) -> None:
    image = Image.open(sprite_sheet).convert("RGBA")
    validate_cell_inside_sheet(
        "sprite",
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
    resolved_bg_color = bg_color or sprite.getpixel((0, 0))[:3]
    sprite, transparent_count = make_background_transparent(
        sprite,
        resolved_bg_color,
        bg_tolerance,
    )
    validate_background_corners_are_transparent(sprite)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sprite.save(output_path, format="PNG")
    debug_path = alpha_debug_path(output_path)
    create_alpha_debug_image(sprite).save(debug_path, format="PNG")
    debug_print("sprite", resolved_bg_color, transparent_count, sprite)
    print(f"sprite: wrote alpha debug image {debug_path}")


def resolve_cell_size(args: argparse.Namespace) -> tuple[int, int]:
    cell_width = args.cell_width if args.cell_width is not None else args.pos_cell_width
    cell_height = args.cell_height if args.cell_height is not None else args.pos_cell_height
    if cell_width is None or cell_height is None:
        raise ValueError("Provide --cell-width and --cell-height.")
    return cell_width, cell_height


def is_single_cell_mode(args: argparse.Namespace) -> bool:
    return args.row is not None or args.col is not None or args.output is not None


def main() -> int:
    args = parse_args()
    tolerance = args.bg_tolerance if args.bg_tolerance is not None else args.tolerance

    try:
        cell_width, cell_height = resolve_cell_size(args)
        x_stride = args.x_stride or cell_width
        y_stride = args.y_stride or cell_height
        bg_color = parse_rgb(args.bg_color) if args.bg_color else None

        validate_args(args.sprite_sheet, cell_width, cell_height)
        if is_single_cell_mode(args):
            if args.row is None or args.col is None or args.output is None:
                raise ValueError("Single-cell extraction requires --row, --col, and --output.")
            extract_single_sprite(
                args.sprite_sheet,
                cell_width,
                cell_height,
                args.x_offset,
                args.y_offset,
                x_stride,
                y_stride,
                args.row,
                args.col,
                args.output,
                bg_color,
                tolerance,
            )
            print(f"Wrote {args.output}")
        else:
            cells = {direction: getattr(args, direction) for direction in DIRECTIONS}
            missing = [direction for direction, cell in cells.items() if cell is None]
            if missing:
                raise ValueError(
                    "Directional extraction requires --front, --back, --left, and --right. "
                    f"Missing: {', '.join(missing)}"
                )
            extract_directional_sprites(
                args.sprite_sheet,
                cell_width,
                cell_height,
                args.x_offset,
                args.y_offset,
                x_stride,
                y_stride,
                cells,
                args.output_dir,
                args.transparent_bg,
                bg_color,
                tolerance,
            )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if not is_single_cell_mode(args):
        for direction in DIRECTIONS:
            print(f"Wrote {args.output_dir / f'{direction}.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
