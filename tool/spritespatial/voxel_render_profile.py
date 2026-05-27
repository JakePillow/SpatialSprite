from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


LABEL_COLORS = {
    1: (8, 8, 8, 255),
    2: (235, 87, 66, 255),
    3: (255, 189, 107, 255),
    4: (89, 46, 184, 255),
    5: (46, 138, 230, 255),
    6: (56, 184, 117, 255),
    7: (66, 163, 107, 255),
    8: (189, 133, 51, 255),
    9: (133, 179, 51, 255),
    10: (107, 61, 31, 255),
    11: (235, 209, 51, 255),
    12: (163, 163, 163, 255),
}


def load_render_profile(profile_ref: str | Path | None, workspace_root: Path) -> dict[str, Any]:
    name = str(profile_ref or "voxel_sprite")
    path = Path(name)
    if not path.suffix:
        path = workspace_root / "profiles" / "render_profiles" / f"{name}.json"
    elif not path.is_absolute():
        path = workspace_root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["path"] = str(path)
    return data


def apply_voxel_render_profile(
    mesh: dict[str, Any],
    front: Image.Image,
    output_dir: Path,
    profile: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(mesh.get("vertices", []), dtype=np.float32)
    faces = [list(map(int, face)) for face in mesh.get("faces", [])]
    metadata = list(mesh.get("face_metadata", []))
    while len(metadata) < len(faces):
        metadata.append({})
    front_rgba = front.convert("RGBA")
    alpha = np.asarray(front_rgba.getchannel("A")) > 16
    seam = _silhouette_seam(alpha)
    pixels = front_rgba.load()
    counts = {
        "front_faces": 0,
        "back_faces": 0,
        "side_faces": 0,
        "top_faces": 0,
        "bottom_faces": 0,
        "outer_outline_faces": 0,
        "internal_black_faces": 0,
        "internal_black_faces_suppressed": 0,
    }
    source_distance = []
    side_shaded = 0
    side_total = 0
    for index, face in enumerate(faces):
        face_meta = dict(metadata[index]) if isinstance(metadata[index], dict) else {}
        label = int(face_meta.get("semantic_label", 12))
        normal = _face_normal(vertices, face)
        face_type = _face_type(normal)
        counts[f"{face_type}_faces"] = counts.get(f"{face_type}_faces", 0) + 1
        source_scale = float(mesh.get("config", {}).get("sdf_resolution_scale", 1.0))
        source_color = _source_color(face_meta, pixels, front.size, label, source_scale)
        outer_outline = label == 1 and _is_outer_outline(face_meta, seam, source_scale)
        internal_outline = label == 1 and not outer_outline
        if outer_outline:
            counts["outer_outline_faces"] += 1
        if internal_outline:
            counts["internal_black_faces"] += 1
        color = _shade_color(source_color, face_type, profile)
        if label == 1:
            if outer_outline:
                strength = float(profile.get("outline_strength", 0.92))
                color = tuple(max(0, min(255, int(channel * (1.0 - strength)))) for channel in source_color[:3]) + (source_color[3],)
            elif bool(profile.get("black_seam_suppression", True)):
                counts["internal_black_faces_suppressed"] += 1
                color = _shade_color(source_color, "side", {**profile, "side_darkening": profile.get("internal_outline_darkening", 0.58)})
        if face_type in {"side", "top", "bottom"}:
            side_total += 1
            if _luma(color) < _luma(source_color) or face_type == "top":
                side_shaded += 1
        source_distance.append(_rgb_distance(color, source_color))
        face_meta.update(
            {
                "render_profile": profile.get("name", "voxel_sprite"),
                "render_face_type": face_type,
                "render_color": [round(color[0] / 255.0, 6), round(color[1] / 255.0, 6), round(color[2] / 255.0, 6), round(color[3] / 255.0, 6)],
                "source_color": [source_color[0], source_color[1], source_color[2], source_color[3]],
                "outer_outline": outer_outline,
                "black_seam_suppressed": internal_outline and bool(profile.get("black_seam_suppression", True)),
            }
        )
        metadata[index] = face_meta

    total_faces = max(len(faces), 1)
    outline_faces = max(counts["outer_outline_faces"] + counts["internal_black_faces"], 1)
    report = {
        "schema": "spritespatial_voxel_render_profile_report_v1",
        "render_profile": profile.get("name", "voxel_sprite"),
        "profile_path": profile.get("path", ""),
        "face_counts": counts,
        "internal_black_face_ratio": float(counts["internal_black_faces"]) / float(total_faces),
        "outer_outline_preservation_score": float(counts["outer_outline_faces"]) / float(outline_faces),
        "source_colour_match_score": max(0.0, 1.0 - (float(np.mean(source_distance)) / 220.0 if source_distance else 0.0)),
        "side_face_shading_score": float(side_shaded) / float(side_total or 1),
        "voxel_face_readability_score": 0.0,
    }
    report["voxel_face_readability_score"] = float(
        0.30 * (1.0 - report["internal_black_face_ratio"])
        + 0.25 * report["outer_outline_preservation_score"]
        + 0.25 * report["source_colour_match_score"]
        + 0.20 * report["side_face_shading_score"]
    )
    mesh["face_metadata"] = metadata
    mesh["render_profile"] = {
        "name": profile.get("name", "voxel_sprite"),
        "semantic_colour_mode": profile.get("semantic_colour_mode", "source_then_semantic_fallback"),
        "material_flatness": profile.get("material_flatness", 1.0),
        "face_snap_to_pixel_grid": bool(profile.get("face_snap_to_pixel_grid", True)),
    }
    mesh["voxel_render_report"] = report
    paths = _write_debug_outputs(output_dir, metadata, report, profile)
    report["paths"] = {key: str(path) for key, path in paths.items()}
    (output_dir.parent / "voxel_render_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"mesh": mesh, "report": report, "paths": paths}


def _write_debug_outputs(
    output_dir: Path,
    metadata: list[dict[str, Any]],
    report: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Path]:
    paths = {
        "face_type_counts": output_dir / "face_type_counts.json",
        "render_profile": output_dir / "render_profile.json",
        "render_colour_swatches": output_dir / "render_colour_swatches.png",
    }
    paths["face_type_counts"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["render_profile"].write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    swatches = Image.new("RGBA", (240, 96), (24, 24, 24, 255))
    draw = ImageDraw.Draw(swatches)
    for index, face_meta in enumerate(metadata[:24]):
        color = face_meta.get("render_color", [0.5, 0.5, 0.5, 1.0])
        rgba = tuple(int(float(channel) * 255) for channel in color)
        x = (index % 12) * 20
        y = (index // 12) * 36
        draw.rectangle((x + 2, y + 16, x + 18, y + 32), fill=rgba)
        draw.text((x + 2, y + 2), str(index), fill=(240, 240, 240, 255))
    swatches.save(paths["render_colour_swatches"], format="PNG")
    return paths


def _source_color(
    face_meta: dict[str, Any],
    pixels: Any,
    size: tuple[int, int],
    label: int,
    source_scale: float = 1.0,
) -> tuple[int, int, int, int]:
    cells = face_meta.get("source_cells", [])
    samples = []
    scale = max(1.0, float(source_scale))
    for cell in cells:
        if not isinstance(cell, list) or len(cell) < 2:
            continue
        y = int(round(float(cell[0]) / scale))
        x = int(round(float(cell[1]) / scale))
        if 0 <= x < size[0] and 0 <= y < size[1]:
            pixel = pixels[x, y]
            if pixel[3] > 16:
                samples.append(pixel)
    if samples:
        return tuple(int(round(sum(pixel[channel] for pixel in samples) / len(samples))) for channel in range(4))  # type: ignore[return-value]
    return LABEL_COLORS.get(label, LABEL_COLORS[12])


def _shade_color(color: tuple[int, int, int, int], face_type: str, profile: dict[str, Any]) -> tuple[int, int, int, int]:
    if face_type == "front":
        factor = 1.0
    elif face_type == "back":
        factor = float(profile.get("back_darkening", 0.82))
    elif face_type == "top":
        factor = float(profile.get("top_light_boost", 1.16))
    elif face_type == "bottom":
        factor = float(profile.get("bottom_darkening", 0.52))
    else:
        factor = float(profile.get("side_darkening", 0.62))
    ambient = float(profile.get("ambient_occlusion_fake", 0.0))
    if face_type in {"side", "bottom", "back"}:
        factor *= max(0.0, 1.0 - ambient * 0.35)
    return (
        max(0, min(255, int(round(color[0] * factor)))),
        max(0, min(255, int(round(color[1] * factor)))),
        max(0, min(255, int(round(color[2] * factor)))),
        color[3],
    )


def _face_normal(vertices: np.ndarray, face: list[int]) -> np.ndarray:
    if len(face) < 3:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)
    a = vertices[face[0]]
    b = vertices[face[1]]
    c = vertices[face[2]]
    normal = np.cross(b - a, c - a)
    length = float(np.linalg.norm(normal))
    if length <= 1e-8:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)
    return normal / length


def _face_type(normal: np.ndarray) -> str:
    ax, ay, az = abs(float(normal[0])), abs(float(normal[1])), abs(float(normal[2]))
    if az >= ax and az >= ay:
        return "front" if float(normal[2]) >= 0.0 else "back"
    if ay >= ax and ay >= az:
        return "top" if float(normal[1]) < 0.0 else "bottom"
    return "side"


def _is_outer_outline(face_meta: dict[str, Any], seam: np.ndarray, source_scale: float = 1.0) -> bool:
    if bool(face_meta.get("is_silhouette", False)):
        return True
    scale = max(1.0, float(source_scale))
    for cell in face_meta.get("source_cells", []):
        if not isinstance(cell, list) or len(cell) < 2:
            continue
        y = int(round(float(cell[0]) / scale))
        x = int(round(float(cell[1]) / scale))
        if 0 <= y < seam.shape[0] and 0 <= x < seam.shape[1] and bool(seam[y, x]):
            return True
    return False


def _silhouette_seam(alpha: np.ndarray) -> np.ndarray:
    seam = np.zeros_like(alpha, dtype=bool)
    height, width = alpha.shape
    for y in range(height):
        for x in range(width):
            if not alpha[y, x]:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height or not alpha[ny, nx]:
                    seam[y, x] = True
                    break
    return seam


def _luma(color: tuple[int, int, int, int]) -> float:
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def _rgb_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    return math.sqrt(float((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))
