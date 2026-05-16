from __future__ import annotations

import argparse
import sys
from pathlib import Path

workspace_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_root / "tool"))

from spritespatial.extraction import GridSpec, draw_debug_grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Overlay a labeled grid on a sprite sheet PNG.")
    parser.add_argument("sprite_sheet", type=Path, help="Path to the source sprite sheet PNG.")
    parser.add_argument("--cell-width", required=True, type=int, help="Grid cell width in pixels.")
    parser.add_argument("--cell-height", required=True, type=int, help="Grid cell height in pixels.")
    parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="Cell padding used by extraction. Labels still show full cell coordinates.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("debug_grid.png"),
        help="Output PNG path. Defaults to debug_grid.png.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        grid = GridSpec(args.cell_width, args.cell_height, args.padding)
        draw_debug_grid(args.sprite_sheet, grid, args.output)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote debug grid: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
