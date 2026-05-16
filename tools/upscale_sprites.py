from __future__ import annotations

import argparse
import sys
from pathlib import Path

workspace_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_root / "tool"))

from spritespatial.asset_schema import AssetSchema
from spritespatial.upscale import (
    UPSCALE_MODES,
    UPSCALE_NEAREST_INTEGER,
    UPSCALE_SCALE2X,
    UPSCALE_SCALE3X,
    record_upscaling_method,
    upscale_asset_sprites,
    upscale_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministically upscale SpriteSpatial PNG sprites.")
    parser.add_argument(
        "--mode",
        choices=sorted(UPSCALE_MODES),
        default=UPSCALE_NEAREST_INTEGER,
        help="Upscale mode. Defaults to nearest_integer.",
    )
    parser.add_argument(
        "--scale",
        type=int,
        help="Integer scale factor. Defaults to 2 for nearest/scale2x and 3 for scale3x.",
    )
    parser.add_argument("--spriteasset", type=Path, help="Path to spriteasset_v1.json.")
    parser.add_argument("--input", type=Path, help="Single input PNG.")
    parser.add_argument("--output", type=Path, help="Single output PNG.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Output directory for spriteasset directional PNGs.",
    )
    parser.add_argument(
        "--record-metadata",
        action="store_true",
        help="Record the selected upscale method in spriteasset_v1.json.",
    )
    return parser.parse_args()


def default_scale_for_mode(mode: str) -> int:
    if mode == UPSCALE_SCALE3X:
        return 3
    return 2


def validate_args(args: argparse.Namespace) -> None:
    single_mode = args.input is not None or args.output is not None
    asset_mode = args.spriteasset is not None

    if single_mode and asset_mode:
        raise ValueError("Use either --spriteasset or --input/--output, not both.")
    if not single_mode and not asset_mode:
        raise ValueError("Provide --spriteasset or --input and --output.")
    if single_mode and (args.input is None or args.output is None):
        raise ValueError("Single-file mode requires both --input and --output.")
    if asset_mode and args.output_dir is None:
        raise ValueError("Asset mode requires --output-dir.")


def print_validation(label: str, validation) -> None:
    print(
        f"{label}: {validation.method} {validation.scale_factor}x "
        f"{validation.original_size} -> {validation.output_size}; "
        f"palette {validation.original_palette_size}->{validation.output_palette_size}; "
        f"introduced_colours={len(validation.introduced_colours)}; "
        f"alpha_similarity={validation.alpha_silhouette_similarity:.3f}"
    )


def run_single(args: argparse.Namespace, scale: int) -> None:
    validation = upscale_file(args.input, args.output, scale_factor=scale, mode=args.mode)
    print_validation(args.output.name, validation)
    print(f"Wrote {args.output}")


def run_asset(args: argparse.Namespace, scale: int) -> None:
    asset = AssetSchema.load_from_file(args.spriteasset)
    validations = upscale_asset_sprites(asset, args.output_dir, scale_factor=scale, mode=args.mode)
    for direction, validation in validations.items():
        print_validation(direction, validation)

    if args.record_metadata:
        record_upscaling_method(
            args.spriteasset,
            method=args.mode,
            scale_factor=scale,
            output_dir=args.output_dir,
        )
        print(f"Recorded upscaling metadata in {args.spriteasset}")

    print(f"Wrote upscaled sprites to {args.output_dir}")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        scale = args.scale or default_scale_for_mode(args.mode)
        if args.mode == UPSCALE_SCALE2X and scale != 2:
            raise ValueError("scale2x requires --scale 2")
        if args.mode == UPSCALE_SCALE3X and scale != 3:
            raise ValueError("scale3x requires --scale 3")

        if args.spriteasset:
            run_asset(args, scale)
        else:
            run_single(args, scale)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
