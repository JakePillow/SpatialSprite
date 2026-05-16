from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.front_back_volume import FrontBackConfig, build_front_back_model  # noqa: E402
from spritespatial.texture_projection import write_front_back_model_test_scene  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic front/back constrained SpriteSpatial proxy model."
    )
    parser.add_argument("--front", type=Path, required=True, help="Transparent front PNG.")
    parser.add_argument("--back", type=Path, required=True, help="Transparent back PNG.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=WORKSPACE_ROOT / "outputs" / "front_back_model",
        help="Output directory for model JSON, textures, metadata, and debug images.",
    )
    parser.add_argument("--model-depth-units", type=float, default=0.48)
    parser.add_argument("--depth-slices", type=int, default=7)
    parser.add_argument("--voxel-size", type=float, default=0.06)
    parser.add_argument(
        "--side-colour-mode",
        choices=("nearest_front", "nearest_back", "blended"),
        default="blended",
    )
    parser.add_argument(
        "--smoothing-mode",
        choices=("none", "merge_faces", "low_poly"),
        default="merge_faces",
    )
    parser.add_argument(
        "--upscale-mode",
        choices=("none", "nearest_integer", "scale2x", "scale3x"),
        default="none",
    )
    parser.add_argument(
        "--ml-cleanup-enabled",
        action="store_true",
        help="Reserved for future non-generative cleanup. Currently rejected if enabled.",
    )
    parser.add_argument("--alpha-threshold", type=int, default=16)
    parser.add_argument(
        "--front-depth",
        type=Path,
        help="Optional user-edited front depth PNG. Must match aligned sprite dimensions.",
    )
    parser.add_argument(
        "--back-depth",
        type=Path,
        help="Optional user-edited back depth PNG. Must match aligned sprite dimensions.",
    )
    parser.add_argument(
        "--scene-path",
        type=Path,
        default=WORKSPACE_ROOT / "scenes" / "front_back_model_test.tscn",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = FrontBackConfig(
        model_depth_units=args.model_depth_units,
        depth_slices=args.depth_slices,
        voxel_size=args.voxel_size,
        side_colour_mode=args.side_colour_mode,
        smoothing_mode=args.smoothing_mode,
        upscale_mode=args.upscale_mode,
        ml_cleanup_enabled=args.ml_cleanup_enabled,
        alpha_threshold=args.alpha_threshold,
        front_depth_path=str(args.front_depth.resolve()) if args.front_depth else None,
        back_depth_path=str(args.back_depth.resolve()) if args.back_depth else None,
    )

    try:
        result = build_front_back_model(
            args.front.resolve(),
            args.back.resolve(),
            args.output_dir.resolve(),
            config,
        )
        write_front_back_model_test_scene(
            args.scene_path.resolve(),
            result.output_scene_data.resolve(),
            (WORKSPACE_ROOT / "scripts" / "front_back_model_viewer.gd").resolve(),
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Built front/back SpriteSpatial model")
    print(f"  Model data: {result.output_scene_data}")
    print(f"  Metadata: {result.metadata_path}")
    print(f"  Debug: {result.debug_dir}")
    print(f"  Scene: {args.scene_path}")
    print(f"  Vertices: {result.vertex_count}")
    print(f"  Triangles: {result.triangle_count}")
    print(f"  Canvas: {result.canvas_size[0]}x{result.canvas_size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
