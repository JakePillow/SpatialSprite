from __future__ import annotations

import argparse
import sys
from pathlib import Path

workspace_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_root / "tool"))

from spritespatial.extraction import ExtractionResult, GridSpec, extract_cell


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
        description="Extract sprites from a sheet with border-ring alpha removal."
    )
    parser.add_argument("sprite_sheet", type=Path, help="Path to the source sprite sheet PNG.")
    parser.add_argument("--cell-width", required=True, type=int, help="Grid cell width in pixels.")
    parser.add_argument("--cell-height", required=True, type=int, help="Grid cell height in pixels.")
    parser.add_argument("--row", type=int, help="Single sprite row coordinate.")
    parser.add_argument("--col", type=int, help="Single sprite column coordinate.")
    parser.add_argument("--padding", type=int, default=0, help="Pixels trimmed inside each cell.")
    parser.add_argument("--bg-tolerance", type=int, default=12, help="RGB tolerance for background removal.")
    parser.add_argument("--output", type=Path, help="Output PNG path for single-cell extraction.")
    parser.add_argument("--front", type=parse_cell, help="Front sprite cell as row,col.")
    parser.add_argument("--back", type=parse_cell, help="Back sprite cell as row,col.")
    parser.add_argument("--left", type=parse_cell, help="Left sprite cell as row,col.")
    parser.add_argument("--right", type=parse_cell, help="Right sprite cell as row,col.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for directional extraction outputs.",
    )
    return parser.parse_args()


def is_single_cell_mode(args: argparse.Namespace) -> bool:
    return args.row is not None or args.col is not None or args.output is not None


def print_result(label: str, result: ExtractionResult) -> None:
    alpha_result = result.alpha_result
    colours = ", ".join(str(colour) for colour in alpha_result.sampled_colours)
    print(f"{label}: sampled background colours [{colours}]")
    print(f"{label}: tolerance used {alpha_result.tolerance}")
    print(f"{label}: pixels made transparent {alpha_result.transparent_pixels}")
    print(f"{label}: final mode {result.image.mode}")
    print(f"{label}: transparent ratio {alpha_result.transparent_ratio:.3f}")
    print(f"{label}: wrote {result.output_path}")
    print(f"{label}: wrote alpha debug {result.alpha_debug_path}")


def run_single(args: argparse.Namespace, grid: GridSpec) -> None:
    if args.row is None or args.col is None or args.output is None:
        raise ValueError("Single-cell extraction requires --row, --col, and --output.")

    result = extract_cell(
        args.sprite_sheet,
        grid,
        args.row,
        args.col,
        args.output,
        bg_tolerance=args.bg_tolerance,
    )
    print_result("sprite", result)


def run_directional(args: argparse.Namespace, grid: GridSpec) -> None:
    cells = {direction: getattr(args, direction) for direction in DIRECTIONS}
    missing = [direction for direction, cell in cells.items() if cell is None]
    if missing:
        raise ValueError(
            "Directional extraction requires --front, --back, --left, and --right. "
            f"Missing: {', '.join(missing)}"
        )

    for direction in DIRECTIONS:
        row, col = cells[direction]
        result = extract_cell(
            args.sprite_sheet,
            grid,
            row,
            col,
            args.output_dir / f"{direction}.png",
            bg_tolerance=args.bg_tolerance,
        )
        print_result(direction, result)


def main() -> int:
    args = parse_args()
    try:
        grid = GridSpec(args.cell_width, args.cell_height, args.padding)
        if is_single_cell_mode(args):
            run_single(args, grid)
        else:
            run_directional(args, grid)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
