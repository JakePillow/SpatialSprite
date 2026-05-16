from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from spritespatial.asset_schema import AssetSchema, SOURCE_DIRECTIONS
from spritespatial.upscale import UPSCALE_MODES, UPSCALE_NEAREST_INTEGER

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CORNER_OPACITY_LIMIT = 0.05
ALPHA_AREA_DRIFT_LIMIT = 0.005


def inspect_png(path: Path) -> tuple[int, int, bool]:
    with path.open("rb") as stream:
        signature = stream.read(8)
        if signature != PNG_SIGNATURE:
            raise ValueError(f"File is not a PNG: {path}")

        width = height = None
        has_alpha = False

        while True:
            header = stream.read(8)
            if len(header) < 8:
                break
            length, chunk_type = struct.unpack(">I4s", header)
            chunk_data = stream.read(length)
            stream.read(4)

            if chunk_type == b"IHDR":
                if len(chunk_data) != 13:
                    raise ValueError("Invalid IHDR chunk")
                width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk_data)
                if color_type in (4, 6):
                    has_alpha = True
            elif chunk_type == b"tRNS":
                has_alpha = True
            elif chunk_type == b"IEND":
                break

        if width is None or height is None:
            raise ValueError(f"PNG missing IHDR chunk: {path}")

        return width, height, has_alpha


def validate_asset_schema(asset: AssetSchema) -> None:
    if asset.pixel_scale <= 0:
        raise ValueError("pixel_scale must be greater than 0")

    if not isinstance(asset.collision, dict):
        raise ValueError("collision must be an object")

    collision_type = asset.collision.get("type")
    if collision_type != "capsule":
        raise ValueError("collision.type must be 'capsule' for directional_sprite_3d assets")

    if asset.collision.get("height") is None or asset.collision.get("radius") is None:
        raise ValueError("collision must include height and radius")

    validate_upscaling_config(asset)

    sprite_sizes: list[tuple[int, int]] = []
    for direction in SOURCE_DIRECTIONS:
        sprite_path = asset.sprite_path(direction)
        if not sprite_path.exists():
            raise FileNotFoundError(f"Missing sprite image for {direction}: {sprite_path}")
        if sprite_path.suffix.lower() != ".png":
            raise ValueError("Sprite images must be PNG files")

        width, height, has_alpha = inspect_png(sprite_path)
        if not has_alpha:
            raise ValueError(f"Sprite image does not contain an alpha channel: {sprite_path}")
        sprite_sizes.append((width, height))

    first_size = sprite_sizes[0]
    for direction, size in zip(SOURCE_DIRECTIONS, sprite_sizes):
        if size != first_size:
            raise ValueError(
                "All source sprites must have the same dimensions. "
                f"{direction} has size {size}, expected {first_size}."
            )


def validate_upscaling_config(asset: AssetSchema) -> None:
    if not isinstance(asset.upscaling, dict):
        raise ValueError("upscaling must be an object when provided")

    method = asset.upscaling.get("method", UPSCALE_NEAREST_INTEGER)
    if method not in UPSCALE_MODES:
        raise ValueError(f"Unsupported upscaling.method: {method}")

    scale_factor = int(asset.upscaling.get("scale_factor", 1))
    if scale_factor <= 0:
        raise ValueError("upscaling.scale_factor must be greater than 0")

    generates_new_art = asset.upscaling.get("generates_new_art_content", False)
    if generates_new_art:
        raise ValueError("SpriteSpatial upscaling must not generate new art content")


def validate_paths_exist(asset: AssetSchema) -> None:
    for direction in SOURCE_DIRECTIONS:
        sprite_path = asset.sprite_path(direction)
        if not sprite_path.exists():
            raise FileNotFoundError(f"Missing sprite image for {direction}: {sprite_path}")


def validate_image_dimensions(asset: AssetSchema) -> None:
    widths = []
    heights = []
    for direction in SOURCE_DIRECTIONS:
        width, height, _ = inspect_png(asset.sprite_path(direction))
        widths.append(width)
        heights.append(height)
    if len(set(widths)) != 1 or len(set(heights)) != 1:
        raise ValueError("Sprite dimensions must match between front, back, left, and right images")


def validate_alpha_channels(asset: AssetSchema) -> None:
    for direction in SOURCE_DIRECTIONS:
        _, _, has_alpha = inspect_png(asset.sprite_path(direction))
        if not has_alpha:
            raise ValueError(f"Missing alpha channel in sprite: {direction}")


def write_validation_report(
    asset: AssetSchema,
    report_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = workspace_root or Path.cwd()
    report = build_validation_report(asset, workspace_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return report


def build_validation_report(asset: AssetSchema, workspace_root: Path | None = None) -> dict[str, Any]:
    workspace_root = workspace_root or Path.cwd()
    method = asset.upscaling.get("method", UPSCALE_NEAREST_INTEGER)
    scale_factor = int(asset.upscaling.get("scale_factor", 1))
    report: dict[str, Any] = {
        "asset_name": asset.asset_name,
        "directions": list(SOURCE_DIRECTIONS),
        "upscaling": asset.upscaling,
        "strict_gates": {
            "rgba_required": True,
            "corner_opacity_max": CORNER_OPACITY_LIMIT,
            "alpha_area_drift_max_for_deterministic": ALPHA_AREA_DRIFT_LIMIT,
            "introduced_colours_for_nearest": 0,
            "dimensions_match_across_directions": True,
        },
        "source_sprites": {},
        "upscaled_sprites": {},
        "overall_pass": True,
        "failures": [],
    }

    source_metrics: dict[str, dict[str, Any]] = {}
    for direction in SOURCE_DIRECTIONS:
        source_metrics[direction] = sprite_validation_metrics(asset.sprite_path(direction))
    report["source_sprites"] = source_metrics
    _apply_dimension_gate("source_sprites", source_metrics, report)
    _apply_sprite_gates("source_sprites", source_metrics, report)

    output_dir = asset.upscaling.get("output_dir")
    if output_dir:
        upscaled_dir = Path(output_dir)
        if not upscaled_dir.is_absolute():
            upscaled_dir = workspace_root / upscaled_dir

        upscaled_metrics: dict[str, dict[str, Any]] = {}
        for direction in SOURCE_DIRECTIONS:
            original_path = asset.sprite_path(direction)
            upscaled_path = upscaled_dir / original_path.name
            upscaled_metrics[direction] = sprite_validation_metrics(
                upscaled_path,
                reference_path=original_path,
                scale_factor=scale_factor,
                method=method,
            )
        report["upscaled_sprites"] = upscaled_metrics
        _apply_dimension_gate("upscaled_sprites", upscaled_metrics, report)
        _apply_sprite_gates("upscaled_sprites", upscaled_metrics, report, method=method)

    report["overall_pass"] = not report["failures"]
    return report


def sprite_validation_metrics(
    sprite_path: Path,
    reference_path: Path | None = None,
    scale_factor: int = 1,
    method: str = UPSCALE_NEAREST_INTEGER,
) -> dict[str, Any]:
    if not sprite_path.exists():
        return {
            "path": str(sprite_path),
            "exists": False,
            "passes": False,
            "failures": [f"Missing sprite: {sprite_path}"],
        }

    image = Image.open(sprite_path).convert("RGBA")
    metrics: dict[str, Any] = {
        "path": str(sprite_path),
        "exists": True,
        "mode": image.mode,
        "size": list(image.size),
        "alpha_channel_present": "A" in image.getbands(),
        "transparent_ratio": _transparent_ratio(image),
        "corner_opacity": _corner_opacity(image),
        "palette_size": len(_palette(image)),
        "introduced_colour_count": 0,
        "alpha_area_drift_vs_nearest_baseline": 0.0,
        "mask_ssim": None,
        "hausdorff_distance": None,
        "passes": True,
        "failures": [],
    }

    if reference_path is not None and reference_path.exists():
        reference = Image.open(reference_path).convert("RGBA")
        baseline_alpha = reference.getchannel("A").resize(image.size, Image.Resampling.NEAREST)
        reference_palette = _palette(reference)
        image_palette = _palette(image)
        metrics["introduced_colour_count"] = len(image_palette - reference_palette)
        metrics["alpha_area_drift_vs_nearest_baseline"] = _alpha_area_drift(
            baseline_alpha,
            image.getchannel("A"),
        )
        optional = _optional_mask_metrics(baseline_alpha, image.getchannel("A"))
        metrics["mask_ssim"] = optional["mask_ssim"]
        metrics["hausdorff_distance"] = optional["hausdorff_distance"]

    _mark_sprite_metric_failures(metrics, method)
    return metrics


def _apply_sprite_gates(
    group_name: str,
    metrics_by_direction: dict[str, dict[str, Any]],
    report: dict[str, Any],
    method: str = UPSCALE_NEAREST_INTEGER,
) -> None:
    for direction, metrics in metrics_by_direction.items():
        _mark_sprite_metric_failures(metrics, method)
        for failure in metrics["failures"]:
            report["failures"].append(f"{group_name}.{direction}: {failure}")


def _apply_dimension_gate(
    group_name: str,
    metrics_by_direction: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    sizes = {
        direction: tuple(metrics.get("size", []))
        for direction, metrics in metrics_by_direction.items()
        if metrics.get("exists")
    }
    unique_sizes = set(sizes.values())
    if len(unique_sizes) > 1:
        report["failures"].append(f"{group_name}: dimensions do not match across directions: {sizes}")


def _mark_sprite_metric_failures(metrics: dict[str, Any], method: str) -> None:
    failures = metrics.setdefault("failures", [])
    failures.clear()

    if not metrics.get("exists", False):
        failures.append("sprite is missing")
    if metrics.get("mode") != "RGBA" or not metrics.get("alpha_channel_present"):
        failures.append("RGBA required")
    if metrics.get("corner_opacity", 1.0) > CORNER_OPACITY_LIMIT:
        failures.append(
            f"corner opacity {metrics['corner_opacity']:.3f} exceeds {CORNER_OPACITY_LIMIT:.3f}"
        )
    if (
        metrics.get("alpha_area_drift_vs_nearest_baseline", 0.0) > ALPHA_AREA_DRIFT_LIMIT
        and method in UPSCALE_MODES
    ):
        failures.append(
            "alpha area drift "
            f"{metrics['alpha_area_drift_vs_nearest_baseline']:.4f} exceeds "
            f"{ALPHA_AREA_DRIFT_LIMIT:.4f}"
        )
    if method == UPSCALE_NEAREST_INTEGER and metrics.get("introduced_colour_count", 0) != 0:
        failures.append(
            f"nearest introduced {metrics['introduced_colour_count']} colours"
        )

    metrics["passes"] = not failures


def _transparent_ratio(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    total = alpha.width * alpha.height
    if total == 0:
        return 0.0
    transparent = sum(1 for value in alpha.getdata() if value == 0)
    return transparent / total


def _corner_opacity(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    sample_size = max(1, min(alpha.width, alpha.height, 8) // 2)
    corners = (
        (0, 0),
        (max(alpha.width - sample_size, 0), 0),
        (0, max(alpha.height - sample_size, 0)),
        (max(alpha.width - sample_size, 0), max(alpha.height - sample_size, 0)),
    )
    total = 0
    opaque = 0
    for start_x, start_y in corners:
        for y in range(start_y, min(start_y + sample_size, alpha.height)):
            for x in range(start_x, min(start_x + sample_size, alpha.width)):
                total += 1
                if pixels[x, y] != 0:
                    opaque += 1
    if total == 0:
        return 0.0
    return opaque / total


def _alpha_area_drift(baseline_alpha: Image.Image, output_alpha: Image.Image) -> float:
    if baseline_alpha.size != output_alpha.size:
        return 1.0
    baseline_area = sum(1 for value in baseline_alpha.getdata() if value != 0)
    output_area = sum(1 for value in output_alpha.getdata() if value != 0)
    if baseline_area == 0:
        return 0.0 if output_area == 0 else 1.0
    return abs(output_area - baseline_area) / baseline_area


def _optional_mask_metrics(baseline_alpha: Image.Image, output_alpha: Image.Image) -> dict[str, Any]:
    try:
        import numpy as np
        from skimage.metrics import hausdorff_distance, structural_similarity
    except Exception:
        return {"mask_ssim": None, "hausdorff_distance": None}

    baseline_mask = np.array(baseline_alpha) > 0
    output_mask = np.array(output_alpha) > 0
    if baseline_mask.shape != output_mask.shape:
        return {"mask_ssim": None, "hausdorff_distance": None}

    return {
        "mask_ssim": float(
            structural_similarity(
                baseline_mask.astype("uint8"),
                output_mask.astype("uint8"),
                data_range=1,
            )
        ),
        "hausdorff_distance": float(hausdorff_distance(baseline_mask, output_mask)),
    }


def _palette(image: Image.Image) -> set[tuple[int, int, int, int]]:
    return set(image.convert("RGBA").getdata())
