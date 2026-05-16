from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.depth_annotation import generate_depth_assets  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate editable SpriteSpatial depth maps.")
    parser.add_argument("--front", type=Path, required=True, help="Clean transparent front PNG.")
    parser.add_argument("--back", type=Path, help="Optional clean transparent back PNG.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=WORKSPACE_ROOT / "outputs" / "hero",
        help="Output directory for front_depth.png, back_depth.png, regions.json, and debug files.",
    )
    parser.add_argument("--manual-front-depth", type=Path)
    parser.add_argument("--manual-back-depth", type=Path)
    parser.add_argument("--alpha-threshold", type=int, default=16)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = generate_depth_assets(
            args.front.resolve(),
            args.output_dir.resolve(),
            back_path=args.back.resolve() if args.back else None,
            manual_front_depth=args.manual_front_depth.resolve() if args.manual_front_depth else None,
            manual_back_depth=args.manual_back_depth.resolve() if args.manual_back_depth else None,
            alpha_threshold=args.alpha_threshold,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Generated SpriteSpatial depth assets")
    print(f"  front_depth: {result['front_depth']}")
    print(f"  back_depth: {result['back_depth']}")
    print(f"  regions: {result['regions']}")
    print(f"  overlay: {result['depth_debug_overlay']}")
    print(f"  volume_debug: {args.output_dir / 'volume_debug.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
