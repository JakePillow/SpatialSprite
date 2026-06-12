from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

Pixel = tuple[int, int]


def build_view_authority_constraints(
    front: Image.Image,
    parts: list[dict[str, Any]],
    source_coverage: dict[str, Any],
    back_sprite_path: Path | None,
    left_sprite_path: Path | None,
    right_sprite_path: Path | None,
    output_dir: Path,
    mode: str = "auto",
    emit_debug: bool = False,
    semantic_overrides_dir: Path | None = None,
    allow_mirrored_side_fallback: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    front_alpha = _alpha_mask(front, front.size)
    back_status = str(source_coverage.get("back", "missing"))
    left_status = str(source_coverage.get("left", "missing"))
    right_status = str(source_coverage.get("right", "missing"))
    back_authority = "authored_back" if back_status == "authored" and _path_exists(back_sprite_path) else "semantic_rules"
    if mode not in {"front_back_sprite", "front_back_side", "auto"}:
        mode = "auto"
    side_paths, side_status, side_mirror_fallback = _authoritative_side(
        left_sprite_path,
        right_sprite_path,
        left_status,
        right_status,
        mode,
        allow_mirrored_side_fallback,
    )
    side_alpha = _union_alpha_from_paths(side_paths, front.size)
    back_alpha = _alpha_from_path(back_sprite_path, front.size) if back_authority == "authored_back" else None
    side_authority = side_status if side_alpha is not None and not side_mirror_fallback else _side_authority_label(left_status, right_status)
    side_used = bool(side_alpha is not None and mode in {"front_back_side", "auto"})
    correspondence = _front_back_correspondence(parts, back_alpha, back_sprite_path, back_authority)
    side_semantic = _load_side_semantic_masks(semantic_overrides_dir, front.size)
    derived_side_semantic = _derive_side_semantic_masks_from_colour(parts, side_paths, front.size)
    side_label_masks = _merge_label_masks(side_semantic["label_masks"], derived_side_semantic["label_masks"])
    side_semantic_authority = (
        "semantic_masks"
        if side_semantic["label_masks"]
        else ("colour_correspondence" if derived_side_semantic["label_masks"] else ("silhouette_only" if side_alpha is not None else "missing"))
    )
    side_depth_extents = _side_depth_extents(side_label_masks)
    side_correspondence = _side_correspondence(parts, side_alpha, side_paths, side_authority, side_semantic_authority, side_label_masks)
    conflict_mask = np.zeros(front_alpha.shape, dtype=bool)
    if back_alpha is not None:
        conflict_mask = front_alpha ^ back_alpha
    initial_projection = {
        "front_back_alpha_iou": _mask_iou(front_alpha, back_alpha) if back_alpha is not None else 0.0,
        "front_pixel_count": int(np.count_nonzero(front_alpha)),
        "back_pixel_count": int(np.count_nonzero(back_alpha)) if back_alpha is not None else 0,
        "front_only_pixel_count": int(np.count_nonzero(front_alpha & ~back_alpha)) if back_alpha is not None else 0,
        "back_only_pixel_count": int(np.count_nonzero(back_alpha & ~front_alpha)) if back_alpha is not None else 0,
        "side_pixel_count": int(np.count_nonzero(side_alpha)) if side_alpha is not None else 0,
    }
    side_correspondence_passed = bool(side_correspondence["passed"]) if side_used else True
    report = {
        "schema": "spritespatial_view_authority_v1",
        "multi_view_authority_enabled": True,
        "view_authority_mode": mode,
        "front_geometry_authority": "authored_front",
        "back_geometry_authority": back_authority,
        "side_geometry_authority": side_authority,
        "side_semantic_authority": side_semantic_authority,
        "front_back_sprite_backend_enabled": back_authority == "authored_back",
        "front_back_side_backend_enabled": mode == "front_back_side",
        "side_authority_used": side_used,
        "side_mirror_fallback_used": side_mirror_fallback,
        "front_back_correspondence_passed": bool(correspondence["passed"]),
        "side_view_correspondence_passed": side_correspondence_passed,
        "view_constraint_conflict_count": int(np.count_nonzero(conflict_mask)),
        "side_constraint_conflict_count": 0,
        "side_semantic_label_count": len(side_label_masks),
        "side_depth_extents": side_depth_extents,
        "initial_projection": initial_projection,
        "back_sprite_path": str(back_sprite_path) if back_sprite_path else "",
        "side_sprite_path": ";".join(str(path) for path in side_paths),
        "warnings": _warnings(back_authority, side_authority, side_used),
        "passed": back_authority == "authored_back" and bool(correspondence["passed"]) and side_correspondence_passed,
    }
    side_report = {
        "schema": "spritespatial_side_authority_report_v1",
        "side_geometry_authority": side_authority,
        "side_semantic_authority": side_semantic_authority,
        "side_authority_used": side_used,
        "side_mirror_fallback_used": side_mirror_fallback,
        "side_sprite_paths": [str(path) for path in side_paths],
        "left_status": left_status,
        "right_status": right_status,
        "side_view_correspondence_passed": side_correspondence_passed,
        "side_semantic_label_count": len(side_label_masks),
        "side_depth_extents": side_depth_extents,
        "warnings": report["warnings"],
    }
    paths = {
        "front_back_view_correspondence": output_dir / "front_back_view_correspondence.json",
        "side_view_correspondence": output_dir / "side_view_correspondence.json",
        "side_authority_report": output_dir / "side_authority_report.json",
        "view_authority_report": output_dir / "view_authority_report.json",
        "front_constraint_mask": output_dir / "front_constraint_mask.png",
        "back_constraint_mask": output_dir / "back_constraint_mask.png",
        "side_constraint_mask": output_dir / "side_constraint_mask.png",
        "side_projection_mask": output_dir / "side_projection_mask.png",
        "side_conflict_map": output_dir / "side_conflict_map.png",
        "front_back_side_conflict_map": output_dir / "front_back_side_conflict_map.png",
        "front_back_conflict_map": output_dir / "front_back_conflict_map.png",
        "semantic_correspondence_overlay": output_dir / "semantic_correspondence_overlay.png",
        "semantic_side_correspondence_overlay": output_dir / "semantic_side_correspondence_overlay.png",
        "projection_iou_report": output_dir / "projection_iou_report.json",
    }
    _write_json(paths["front_back_view_correspondence"], correspondence)
    _write_json(paths["side_view_correspondence"], side_correspondence)
    _write_json(paths["side_authority_report"], side_report)
    _write_json(paths["view_authority_report"], report)
    _write_json(paths["projection_iou_report"], initial_projection)
    _write_mask(front_alpha, paths["front_constraint_mask"])
    _write_mask(back_alpha if back_alpha is not None else np.zeros_like(front_alpha), paths["back_constraint_mask"])
    _write_mask(side_alpha if side_alpha is not None else np.zeros_like(front_alpha), paths["side_constraint_mask"])
    _write_mask(np.zeros_like(front_alpha), paths["side_projection_mask"])
    _write_conflict(front_alpha, back_alpha, paths["front_back_conflict_map"])
    _write_side_conflict(side_alpha, front_alpha, back_alpha, paths["side_conflict_map"])
    _write_front_back_side_conflict(front_alpha, back_alpha, side_alpha, paths["front_back_side_conflict_map"])
    _write_correspondence_overlay(front.size, parts, back_alpha, paths["semantic_correspondence_overlay"])
    _write_side_correspondence_overlay(front.size, side_alpha, side_label_masks, paths["semantic_side_correspondence_overlay"])
    if not emit_debug:
        # Required debug artefacts are intentionally always written; this flag is reserved for future heavy dumps.
        pass
    return {
        "constraints": {
            "enabled": True,
            "mode": mode,
            "front_alpha": front_alpha,
            "back_alpha": back_alpha,
            "side_alpha": side_alpha if side_used else None,
            "side_semantic_masks": side_label_masks if side_used else {},
            "side_depth_extents": side_depth_extents if side_used else {},
            "front_geometry_authority": "authored_front",
            "back_geometry_authority": back_authority,
            "side_geometry_authority": side_authority,
            "side_semantic_authority": side_semantic_authority,
            "side_authority_used": side_used,
            "front_back_side_backend_enabled": mode == "front_back_side",
            "side_mirror_fallback_used": side_mirror_fallback,
            "correspondence": correspondence,
            "side_correspondence": side_correspondence,
            "report": report,
        },
        "report": report,
        "paths": paths,
    }


def _alpha_mask(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(image.convert("RGBA").resize(size, Image.Resampling.NEAREST).getchannel("A"), dtype=np.uint8) > 16


def _alpha_from_path(path: Path | None, size: tuple[int, int]) -> np.ndarray | None:
    if not _path_exists(path):
        return None
    return _alpha_mask(Image.open(path).convert("RGBA"), size)


def _path_exists(path: Path | None) -> bool:
    return bool(path and Path(path).exists())


def _authoritative_side(
    left: Path | None,
    right: Path | None,
    left_status: str,
    right_status: str,
    mode: str,
    allow_mirrored_side_fallback: bool,
) -> tuple[list[Path], str, bool]:
    if mode == "front_back_sprite":
        return [], "not_requested", False
    paths = []
    if _is_authored_side(left_status) and _path_exists(left):
        paths.append(Path(left))
    if _is_authored_side(right_status) and _path_exists(right):
        paths.append(Path(right))
    if paths:
        if "authored_side_fixture" in {left_status, right_status}:
            return paths, "authored_side_fixture", False
        return paths, "authored_side", False
    if mode in {"front_back_side", "auto"} and allow_mirrored_side_fallback:
        if left_status == "mirrored_placeholder" and _path_exists(left):
            return [Path(left)], "mirrored_placeholder", True
        if right_status == "mirrored_placeholder" and _path_exists(right):
            return [Path(right)], "mirrored_placeholder", True
    return [], left_status if left_status != "missing" else right_status, False


def _is_authored_side(status: str) -> bool:
    return status in {"authored", "authored_left", "authored_right", "authored_side", "authored_side_fixture"}


def _union_alpha_from_paths(paths: list[Path], size: tuple[int, int]) -> np.ndarray | None:
    if not paths:
        return None
    union: np.ndarray | None = None
    for path in paths:
        mask = _alpha_from_path(path, size)
        if mask is None:
            continue
        union = mask if union is None else (union | mask)
    return union


def _side_authority_label(left_status: str, right_status: str) -> str:
    statuses = {left_status, right_status}
    if "authored_side_fixture" in statuses:
        return "authored_side_fixture"
    if any(_is_authored_side(status) for status in statuses):
        return "authored_side"
    if "mirrored_placeholder" in statuses:
        return "placeholder"
    if "inferred" in statuses:
        return "inferred"
    return "missing"


def _load_side_semantic_masks(root: Path | None, size: tuple[int, int]) -> dict[str, Any]:
    label_masks: dict[str, np.ndarray] = {}
    if root is None:
        return {"label_masks": label_masks, "dirs_checked": []}
    dirs = [Path(root) / name for name in ("side", "left", "right")]
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.png")):
            label = _canonical_label(path.stem)
            mask = _alpha_from_path(path, size)
            if mask is None:
                continue
            label_masks[label] = mask if label not in label_masks else (label_masks[label] | mask)
    return {"label_masks": label_masks, "dirs_checked": [str(path) for path in dirs]}


def _derive_side_semantic_masks_from_colour(
    parts: list[dict[str, Any]],
    side_paths: list[Path],
    size: tuple[int, int],
) -> dict[str, Any]:
    label_colours = _label_colour_signatures(parts)
    label_masks: dict[str, np.ndarray] = {}
    if not side_paths or not label_colours:
        return {"label_masks": label_masks, "method": "disabled"}
    threshold = 64.0
    for path in side_paths:
        if not path.exists():
            continue
        image = Image.open(path).convert("RGBA").resize(size, Image.Resampling.NEAREST)
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue, alpha = pixels[x, y]
                if alpha <= 16:
                    continue
                label = _nearest_colour_label((red, green, blue), label_colours, threshold)
                if label is None:
                    continue
                label_masks.setdefault(label, np.zeros((size[1], size[0]), dtype=bool))[y, x] = True
    return {
        "label_masks": {label: mask for label, mask in label_masks.items() if bool(np.any(mask))},
        "method": "nearest_front_part_colour",
    }


def _label_colour_signatures(parts: list[dict[str, Any]]) -> dict[str, list[tuple[int, int, int]]]:
    signatures: dict[str, list[tuple[int, int, int]]] = {}
    for part in parts:
        label = _canonical_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        colour = part.get("dominant_colour")
        if not isinstance(colour, (list, tuple)) or len(colour) < 3:
            continue
        red, green, blue = int(colour[0]), int(colour[1]), int(colour[2])
        signatures.setdefault(label, []).append((red, green, blue))
    return signatures


def _nearest_colour_label(
    colour: tuple[int, int, int],
    signatures: dict[str, list[tuple[int, int, int]]],
    threshold: float,
) -> str | None:
    if max(colour) <= 48 and "outline" in signatures:
        return "outline"
    best_label = None
    best_distance = float("inf")
    for label, colours in signatures.items():
        for candidate in colours:
            distance = sum((float(a) - float(b)) ** 2 for a, b in zip(colour, candidate)) ** 0.5
            if distance < best_distance:
                best_distance = distance
                best_label = label
    return best_label if best_label is not None and best_distance <= threshold else None


def _merge_label_masks(*groups: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    merged: dict[str, np.ndarray] = {}
    for group in groups:
        for label, mask in group.items():
            canonical = _canonical_label(label)
            merged[canonical] = np.asarray(mask, dtype=bool) if canonical not in merged else (merged[canonical] | np.asarray(mask, dtype=bool))
    return {label: mask for label, mask in merged.items() if bool(np.any(mask))}


def _side_depth_extents(label_masks: dict[str, np.ndarray]) -> dict[str, Any]:
    extents: dict[str, Any] = {}
    for label, mask in sorted(label_masks.items()):
        coords = np.argwhere(mask)
        if len(coords) == 0:
            continue
        ys = coords[:, 0]
        xs = coords[:, 1]
        extents[label] = {
            "pixel_count": int(len(coords)),
            "min_side_x": int(xs.min()),
            "max_side_x": int(xs.max()),
            "min_y": int(ys.min()),
            "max_y": int(ys.max()),
        }
    return extents


def _side_correspondence(
    parts: list[dict[str, Any]],
    side_alpha: np.ndarray | None,
    side_paths: list[Path],
    side_authority: str,
    side_semantic_authority: str,
    side_label_masks: dict[str, np.ndarray],
) -> dict[str, Any]:
    labels = _semantic_pixels(parts)
    labels_present_front = sorted(label for label, pixels in labels.items() if pixels)
    labels_present_side = sorted(label for label, mask in side_label_masks.items() if bool(np.any(mask)))
    labels_missing_side = []
    label_overlap: dict[str, Any] = {}
    for label, pixels in sorted(labels.items()):
        if not pixels:
            continue
        if label in side_label_masks:
            mask = side_label_masks[label]
            hits = int(np.count_nonzero(mask))
            ratio = min(1.0, hits / float(max(len(pixels), 1)))
        elif side_alpha is not None:
            hits = 0
            for x, y in pixels:
                if 0 <= y < side_alpha.shape[0] and 0 <= x < side_alpha.shape[1] and bool(side_alpha[y, x]):
                    hits += 1
            ratio = hits / float(max(len(pixels), 1))
        else:
            hits = 0
            ratio = 0.0
        label_overlap[label] = {
            "front_pixel_count": len(pixels),
            "side_overlap_or_mask_pixels": hits,
            "overlap_ratio": ratio,
        }
        if ratio <= 0.02:
            labels_missing_side.append(label)
    critical_missing = [
        label
        for label in labels_missing_side
        if label in {"head", "torso", "left_leg", "right_leg"} and side_authority in {"authored_side", "authored_side_fixture"}
    ]
    return {
        "schema": "spritespatial_side_view_correspondence_v1",
        "side_sprite_paths": [str(path) for path in side_paths],
        "side_geometry_authority": side_authority,
        "side_semantic_authority": side_semantic_authority,
        "labels_present_front": labels_present_front,
        "labels_present_side": labels_present_side,
        "labels_missing_from_side": labels_missing_side,
        "label_overlap": label_overlap,
        "passed": side_authority not in {"authored_side", "authored_side_fixture"} or not critical_missing,
    }


def _front_back_correspondence(
    parts: list[dict[str, Any]],
    back_alpha: np.ndarray | None,
    back_sprite_path: Path | None,
    back_authority: str,
) -> dict[str, Any]:
    labels = _semantic_pixels(parts)
    label_overlap: dict[str, Any] = {}
    labels_present_front = sorted(label for label, pixels in labels.items() if pixels)
    labels_present_back: list[str] = []
    labels_missing_back: list[str] = []
    poor: list[str] = []
    for label, pixels in sorted(labels.items()):
        if not pixels:
            continue
        hits = 0
        if back_alpha is not None:
            for x, y in pixels:
                if 0 <= y < back_alpha.shape[0] and 0 <= x < back_alpha.shape[1] and bool(back_alpha[y, x]):
                    hits += 1
        ratio = hits / float(max(len(pixels), 1))
        label_overlap[label] = {
            "front_pixel_count": len(pixels),
            "back_alpha_overlap": hits,
            "overlap_ratio": ratio,
        }
        if ratio > 0.0:
            labels_present_back.append(label)
        if ratio <= 0.02:
            labels_missing_back.append(label)
        elif ratio < 0.35:
            poor.append(label)
    critical_missing = [label for label in labels_missing_back if label in {"head", "torso", "left_leg", "right_leg"}]
    return {
        "schema": "spritespatial_front_back_view_correspondence_v1",
        "back_sprite_path": str(back_sprite_path) if back_sprite_path else "",
        "back_geometry_authority": back_authority,
        "labels_present_front": labels_present_front,
        "labels_present_back": sorted(set(labels_present_back)),
        "labels_missing_from_back": labels_missing_back,
        "labels_with_poor_correspondence": poor,
        "labels_only_inferred": labels_missing_back if back_authority != "authored_back" else [],
        "label_overlap": label_overlap,
        "passed": back_authority != "authored_back" or not critical_missing,
    }


def _semantic_pixels(parts: list[dict[str, Any]]) -> dict[str, set[Pixel]]:
    result: dict[str, set[Pixel]] = {}
    for part in parts:
        label = _canonical_label(str(part.get("semantic_label", part.get("name", "unknown"))))
        result.setdefault(label, set()).update({(int(x), int(y)) for x, y in part.get("pixels", [])})
    return result


def _canonical_label(label: str) -> str:
    aliases = {
        "hat_hair": "hair/hat",
        "boots_feet": "boots/feet",
        "equipment": "equipment/shield/sword",
        "shield": "equipment/shield/sword",
        "sword": "equipment/shield/sword",
    }
    return aliases.get(label, label)


def _mask_iou(a: np.ndarray, b: np.ndarray | None) -> float:
    if b is None:
        return 0.0
    intersection = int(np.count_nonzero(a & b))
    union = int(np.count_nonzero(a | b))
    return float(intersection) / float(max(union, 1))


def _warnings(back_authority: str, side_authority: str, side_used: bool) -> list[str]:
    warnings = []
    if back_authority != "authored_back":
        warnings.append("Authored back geometry is unavailable; semantic_rules remains the fallback.")
    if not side_used:
        warnings.append(f"Side geometry authority is not used because side status is {side_authority}.")
    return warnings


def _write_side_conflict(side: np.ndarray | None, front: np.ndarray, back: np.ndarray | None, path: Path) -> None:
    if side is None:
        _write_mask(np.zeros_like(front), path)
        return
    image = Image.new("RGBA", (front.shape[1], front.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    support = front | (back if back is not None else front)
    for y in range(front.shape[0]):
        for x in range(front.shape[1]):
            if side[y, x] and support[y, x]:
                pixels[x, y] = (80, 220, 120, 255)
            elif side[y, x]:
                pixels[x, y] = (255, 180, 40, 255)
            elif support[y, x]:
                pixels[x, y] = (70, 120, 255, 140)
    image.save(path, format="PNG")


def _write_front_back_side_conflict(front: np.ndarray, back: np.ndarray | None, side: np.ndarray | None, path: Path) -> None:
    image = Image.new("RGBA", (front.shape[1], front.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    back_mask = back if back is not None else np.zeros_like(front)
    side_mask = side if side is not None else np.zeros_like(front)
    for y in range(front.shape[0]):
        for x in range(front.shape[1]):
            count = int(front[y, x]) + int(back_mask[y, x]) + int(side_mask[y, x])
            if count == 3:
                pixels[x, y] = (80, 220, 120, 255)
            elif count == 2:
                pixels[x, y] = (255, 220, 80, 255)
            elif count == 1:
                pixels[x, y] = (255, 80, 80, 220)
    image.save(path, format="PNG")


def _write_mask(mask: np.ndarray, path: Path) -> None:
    image = Image.new("RGBA", (mask.shape[1], mask.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y, x in np.argwhere(mask):
        pixels[int(x), int(y)] = (255, 255, 255, 255)
    image.save(path, format="PNG")


def _write_conflict(front: np.ndarray, back: np.ndarray | None, path: Path) -> None:
    if back is None:
        _write_mask(np.zeros_like(front), path)
        return
    image = Image.new("RGBA", (front.shape[1], front.shape[0]), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(front.shape[0]):
        for x in range(front.shape[1]):
            if front[y, x] and back[y, x]:
                pixels[x, y] = (80, 220, 120, 255)
            elif front[y, x]:
                pixels[x, y] = (255, 80, 70, 255)
            elif back[y, x]:
                pixels[x, y] = (70, 120, 255, 255)
    image.save(path, format="PNG")


def _write_correspondence_overlay(
    size: tuple[int, int],
    parts: list[dict[str, Any]],
    back_alpha: np.ndarray | None,
    path: Path,
) -> None:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for label, coords in _semantic_pixels(parts).items():
        color = _label_color(label)
        for x, y in coords:
            if 0 <= x < width and 0 <= y < height:
                if back_alpha is not None and not bool(back_alpha[y, x]):
                    pixels[x, y] = (255, 70, 70, 255)
                else:
                    pixels[x, y] = color
    ImageDraw.Draw(image).text((1, 1), "green/colour=covered red=front label missing in back alpha", fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _write_side_correspondence_overlay(
    size: tuple[int, int],
    side_alpha: np.ndarray | None,
    side_label_masks: dict[str, np.ndarray],
    path: Path,
) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    if side_alpha is not None:
        for y, x in np.argwhere(side_alpha):
            pixels[int(x), int(y)] = (255, 255, 255, 180)
    for label, mask in side_label_masks.items():
        color = _label_color(label)
        for y, x in np.argwhere(mask):
            pixels[int(x), int(y)] = color
    ImageDraw.Draw(image).text((1, 1), "side semantic masks if present; white=silhouette only", fill=(255, 255, 255, 255))
    image.save(path, format="PNG")


def _label_color(label: str) -> tuple[int, int, int, int]:
    return {
        "outline": (20, 20, 20, 255),
        "head": (245, 180, 120, 255),
        "face": (255, 220, 160, 255),
        "hair/hat": (90, 180, 60, 255),
        "torso": (60, 200, 120, 255),
        "left_arm": (210, 140, 80, 255),
        "right_arm": (210, 140, 80, 255),
        "left_leg": (80, 150, 220, 255),
        "right_leg": (80, 150, 220, 255),
        "boots/feet": (190, 60, 50, 255),
        "equipment/shield/sword": (230, 220, 80, 255),
    }.get(label, (220, 80, 220, 255))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
