from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.asset_schema import AssetSchema  # noqa: E402


VIEWS = ("front", "back", "left", "right", "unknown")
POSES = ("idle", "walk", "run", "jump", "duck", "other")


@dataclass(frozen=True)
class Candidate:
    candidate_id: int
    image: Image.Image
    bbox: tuple[int, int, int, int]
    alpha_coverage: float
    complete_score: float
    deterministic_pose_hint: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract and optionally rank sprite-sheet view candidates.")
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ai-rank", action="store_true")
    parser.add_argument("--api-provider", choices=("openai",), default="openai")
    parser.add_argument("--confirm-copy", action="store_true")
    parser.add_argument("--model", default=os.environ.get("OPENAI_VIEW_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-candidates", type=int, default=320)
    parser.add_argument("--ai-batch-size", type=int, default=80)
    parser.add_argument("--no-ai-sheet-context", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asset = AssetSchema.load_from_file(_resolve(args.asset))
    sheet_path = _resolve(args.sheet)
    out_dir = _resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = out_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    sheet = Image.open(sheet_path).convert("RGBA")
    candidates = extract_candidates(sheet, args.max_candidates)
    candidate_records = write_candidates(candidates, candidates_dir)
    contact_sheet = out_dir / "candidate_contact_sheet.png"
    write_contact_sheet(candidates, contact_sheet)
    report = {
        "schema": "spritespatial_view_candidates_v2",
        "asset": str(_resolve(args.asset)),
        "sheet": str(sheet_path),
        "candidate_count": len(candidates),
        "candidate_dir": str(candidates_dir),
        "candidate_contact_sheet": str(contact_sheet),
        "ai_rank_requested": bool(args.ai_rank),
        "ai_rank_completed": False,
        "copy_performed": False,
        "validation": {
            "candidate_files_exist": all(Path(record["path"]).exists() for record in candidate_records),
            "candidate_files_have_alpha": all(record["has_alpha"] for record in candidate_records),
            "no_source_overwrite_without_confirm_copy": not args.confirm_copy,
        },
        "ai_sheet_context_enabled": bool(args.ai_rank and not args.no_ai_sheet_context),
        "candidates": candidate_records,
    }

    rankings: list[dict[str, Any]] = []
    if args.ai_rank:
        rankings = rank_candidates_with_ai(candidates, candidate_records, contact_sheet, args)
        rankings = add_deterministic_view_suggestions(rankings, candidates)
        report["ai_rank_completed"] = bool(rankings)
        report["ai_ranking_warning"] = "" if rankings else "AI ranking unavailable; deterministic candidates remain valid."
        write_rank_outputs(rankings, candidates, out_dir)
    else:
        write_rank_outputs([], candidates, out_dir)

    if args.confirm_copy:
        if not rankings:
            raise ValueError("--confirm-copy requires --ai-rank rankings or a future manual-selection file.")
        copy_report = copy_ranked_candidates(asset, rankings, candidates, args)
        report["copy_performed"] = True
        report["copy_report"] = copy_report
    else:
        report["copy_note"] = "No asset source images were overwritten because --confirm-copy was not provided."

    (out_dir / "candidate_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(candidates)} candidates to {out_dir}")
    if args.ai_rank:
        print(f"AI ranked candidates: {len(rankings)}")
    if not args.confirm_copy:
        print("No source sprites copied; pass --confirm-copy to apply selected candidates.")
    return 0


def extract_candidates(sheet: Image.Image, limit: int) -> list[Candidate]:
    rgba = sheet.convert("RGBA")
    mask = _foreground_mask(rgba)
    components = _components(mask)
    candidates: list[Candidate] = []
    for component in sorted(components, key=lambda item: (min(y for _x, y in item), min(x for x, _y in item))):
        if len(component) < 18:
            continue
        xs = [x for x, _y in component]
        ys = [y for _x, y in component]
        x0, x1 = max(0, min(xs) - 3), min(rgba.width, max(xs) + 4)
        y0, y1 = max(0, min(ys) - 3), min(rgba.height, max(ys) + 4)
        width, height = x1 - x0, y1 - y0
        if not (6 <= width <= 90 and 8 <= height <= 96):
            continue
        crop = remove_background(rgba.crop((x0, y0, x1, y1)))
        if not crop.getbbox() or not _looks_like_sprite_crop(crop):
            continue
        crop = pad_candidate(crop)
        alpha = crop.getchannel("A")
        opaque = sum(1 for value in alpha.tobytes() if value > 16)
        coverage = opaque / max(crop.width * crop.height, 1)
        complete = _complete_score(crop)
        candidates.append(
            Candidate(
                candidate_id=len(candidates),
                image=crop,
                bbox=(x0, y0, x1, y1),
                alpha_coverage=coverage,
                complete_score=complete,
                deterministic_pose_hint=_pose_hint(width, height),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def write_candidates(candidates: list[Candidate], output_dir: Path) -> list[dict[str, Any]]:
    records = []
    for candidate in candidates:
        path = output_dir / f"candidate_{candidate.candidate_id:03d}.png"
        candidate.image.save(path, format="PNG")
        records.append(
            {
                "candidate_id": candidate.candidate_id,
                "path": str(path),
                "bbox": list(candidate.bbox),
                "size": list(candidate.image.size),
                "has_alpha": "A" in candidate.image.getbands(),
                "alpha_coverage": candidate.alpha_coverage,
                "complete_score": candidate.complete_score,
                "deterministic_pose_hint": candidate.deterministic_pose_hint,
            }
        )
    return records


def write_contact_sheet(candidates: list[Candidate], path: Path, title: str = "candidates") -> None:
    cell = 72
    cols = 8
    rows = max(1, (len(candidates) + cols - 1) // cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell + 18), (0, 120, 120, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 3), title, fill=(255, 255, 255, 255))
    for index, candidate in enumerate(candidates):
        x = (index % cols) * cell
        y = (index // cols) * cell + 18
        draw.rectangle((x, y, x + cell - 1, y + cell - 1), outline=(0, 70, 70, 255))
        image = candidate.image
        sheet.alpha_composite(image, (x + (cell - image.width) // 2, y + (cell - image.height) // 2))
        draw.text((x + 3, y + 3), str(candidate.candidate_id), fill=(255, 255, 255, 255))
    sheet.save(path, format="PNG")


def rank_candidates_with_ai(
    candidates: list[Candidate],
    candidate_records: list[dict[str, Any]],
    contact_sheet: Path,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    if args.api_provider != "openai":
        return []
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        warning = {
            "warning": "OPENAI_API_KEY is not set. AI ranking skipped.",
            "rankings": [],
        }
        (_resolve(args.out) / "ai_ranked_candidates.json").write_text(json.dumps(warning, indent=2) + "\n", encoding="utf-8")
        return []
    out_dir = _resolve(args.out)
    debug_dir = out_dir / "ai_batches"
    debug_dir.mkdir(parents=True, exist_ok=True)
    all_rankings: list[dict[str, Any]] = []
    batch_size = max(12, int(args.ai_batch_size))
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    for batch_index, start in enumerate(range(0, len(candidate_records), batch_size)):
        records = candidate_records[start : start + batch_size]
        batch_candidates = [by_id[int(record["candidate_id"])] for record in records if int(record["candidate_id"]) in by_id]
        batch_sheet = debug_dir / f"ai_rank_batch_{batch_index:03d}.png"
        write_contact_sheet(batch_candidates, batch_sheet, title=f"ai rank batch {batch_index}")
        all_rankings.extend(
            _rank_candidate_batch(api_key, records, batch_sheet, args, len(candidates), debug_dir, batch_index)
        )
    return _dedupe_rankings(all_rankings)


def _rank_candidate_batch(
    api_key: str,
    candidate_records: list[dict[str, Any]],
    contact_sheet: Path,
    args: argparse.Namespace,
    candidate_count: int,
    debug_dir: Path,
    batch_index: int,
) -> list[dict[str, Any]]:
    prompt = _ranking_prompt(candidate_records)
    content = [{"type": "input_text", "text": prompt}]
    if not args.no_ai_sheet_context:
        source_context = debug_dir / "source_sheet_context.png"
        if not source_context.exists():
            _write_source_sheet_context(_resolve(args.sheet), source_context)
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{_b64(source_context)}",
            }
        )
    content.append(
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{_b64(contact_sheet)}",
        }
    )
    payload = {
        "model": args.model,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "text": {"format": {"type": "json_object"}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        warning = {
            "warning": f"AI ranking batch {batch_index} failed: HTTP {exc.code} {exc.reason}",
            "response_body": body[:4000],
            "rankings": [],
        }
        (debug_dir / f"ai_rank_batch_{batch_index:03d}_error.json").write_text(json.dumps(warning, indent=2) + "\n", encoding="utf-8")
        return []
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        warning = {
            "warning": f"AI ranking batch {batch_index} failed: {exc}",
            "rankings": [],
        }
        (debug_dir / f"ai_rank_batch_{batch_index:03d}_error.json").write_text(json.dumps(warning, indent=2) + "\n", encoding="utf-8")
        return []
    (debug_dir / f"ai_rank_batch_{batch_index:03d}_response.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    text = _extract_response_text(data)
    (debug_dir / f"ai_rank_batch_{batch_index:03d}_text.txt").write_text(text, encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"rankings": []}
    rankings = parsed.get("rankings", parsed if isinstance(parsed, list) else [])
    return [_normalise_ranking(item, candidate_count) for item in rankings if isinstance(item, dict)]


def _dedupe_rankings(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_id: dict[int, dict[str, Any]] = {}
    for ranking in rankings:
        candidate_id = int(ranking.get("candidate_id", -1))
        if candidate_id < 0:
            continue
        previous = best_by_id.get(candidate_id)
        if previous is None or float(ranking.get("confidence", 0.0)) > float(previous.get("confidence", 0.0)):
            best_by_id[candidate_id] = ranking
    return sorted(best_by_id.values(), key=lambda item: int(item["candidate_id"]))


def add_deterministic_view_suggestions(
    rankings: list[dict[str, Any]],
    candidates: list[Candidate],
) -> list[dict[str, Any]]:
    suggestions = []
    suggestion_ids = set()
    has_ai_back = any(item.get("view") == "back" for item in rankings)
    for candidate in candidates:
        back_score = _rear_facing_score(candidate.image)
        if not has_ai_back and back_score >= 0.74:
            suggestion_ids.add(candidate.candidate_id)
            suggestions.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "view": "back",
                    "pose": "idle" if candidate.deterministic_pose_hint == "standing_or_unknown" else "other",
                    "confidence": min(0.93, round(back_score, 3)),
                    "reason": "Deterministic rear-facing fallback: strong back-of-head/cap colors with reduced visible face cues.",
                    "source": "deterministic_back_fallback",
                }
            )
            continue
        side = _side_facing_view(candidate.image)
        if side is None:
            continue
        view, score = side
        suggestion_ids.add(candidate.candidate_id)
        suggestions.append(
            {
                "candidate_id": candidate.candidate_id,
                "view": view,
                "pose": "idle" if candidate.deterministic_pose_hint == "standing_or_unknown" else "other",
                "confidence": min(0.92, round(score, 3)),
                "reason": "Deterministic side-facing fallback: profile face/nose is offset to one side, matching Mario sheet side-view frames.",
                "source": "deterministic_side_fallback",
            }
        )
    filtered_rankings = [item for item in rankings if int(item.get("candidate_id", -1)) not in suggestion_ids]
    return _dedupe_rankings(filtered_rankings + suggestions)


def write_rank_outputs(rankings: list[dict[str, Any]], candidates: list[Candidate], output_dir: Path) -> None:
    ranked_path = output_dir / "ai_ranked_candidates.json"
    ranked_path.write_text(
        json.dumps(
            {
                "rankings": rankings,
                "deterministic_suggestion_count": sum(
                    1
                    for item in rankings
                    if item.get("source") in {"deterministic_back_fallback", "deterministic_side_fallback"}
                ),
                "deterministic_back_suggestion_count": sum(
                    1 for item in rankings if item.get("source") == "deterministic_back_fallback"
                ),
                "deterministic_side_suggestion_count": sum(
                    1 for item in rankings if item.get("source") == "deterministic_side_fallback"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    by_view: dict[str, list[Candidate]] = {view: [] for view in VIEWS}
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if rankings:
        for item in sorted(rankings, key=lambda record: record.get("confidence", 0.0), reverse=True):
            candidate = by_id.get(int(item.get("candidate_id", -1)))
            view = item.get("view", "unknown")
            if candidate and view in by_view:
                by_view[view].append(candidate)
    else:
        by_view["unknown"] = candidates
    for view, items in by_view.items():
        write_contact_sheet(items, output_dir / f"{view}_candidates.png", title=f"{view} candidates")


def copy_ranked_candidates(
    asset: AssetSchema,
    rankings: list[dict[str, Any]],
    candidates: list[Candidate],
    args: argparse.Namespace,
) -> dict[str, Any]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    copied = {}
    for view in ("front", "back", "left", "right"):
        best = _best_for_view(rankings, view)
        if not best:
            continue
        candidate = by_id.get(int(best["candidate_id"]))
        if not candidate:
            continue
        output_name = f"{view}.png"
        output_path = asset.source_dir / output_name
        normalised = _fit_to_reference_canvas(candidate.image, asset.sprite_path("front"))
        if best.get("mirrored_from"):
            normalised = ImageOps.mirror(normalised)
        normalised.save(output_path, format="PNG")
        asset.source_sprites[view] = output_name
        copied[view] = {
            "candidate_id": best["candidate_id"],
            "confidence": best["confidence"],
            "path": str(output_path),
            "mirrored_from": best.get("mirrored_from"),
        }
    _update_asset_json(_resolve(args.asset), asset, copied, "ai_ranked")
    return {"copied": copied, "candidate_selection_method": "ai_ranked"}


def remove_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16 or _is_sheet_background(red, green, blue):
                pixels[x, y] = (0, 0, 0, 0)
    bbox = rgba.getbbox()
    return rgba.crop(bbox) if bbox else rgba


def pad_candidate(image: Image.Image, size: tuple[int, int] = (40, 48)) -> Image.Image:
    if image.width > size[0] or image.height > size[1]:
        return image
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size[0] - image.width) // 2, size[1] - image.height - 2))
    return canvas


def _foreground_mask(image: Image.Image) -> np.ndarray:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    mask = np.zeros((rgba.height, rgba.width), dtype=bool)
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 16 and not _is_sheet_background(red, green, blue):
                mask[y, x] = True
    return mask


def _components(mask: np.ndarray) -> list[set[tuple[int, int]]]:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    component.add((nx, ny))
                    stack.append((nx, ny))
        components.append(component)
    return components


def _is_sheet_background(red: int, green: int, blue: int) -> bool:
    is_teal_sheet_color = red <= 12 and 45 <= green <= 170 and 45 <= blue <= 170 and abs(green - blue) <= 50
    is_blue_page_color = 70 <= red <= 110 and 145 <= green <= 190 and 215 <= blue <= 255
    return is_teal_sheet_color or is_blue_page_color


def _looks_like_sprite_crop(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return False
    x0, y0, x1, y1 = bbox
    width = x1 - x0
    height = y1 - y0
    if width < 8 or height < 14:
        return False
    opaque_pixels = 0
    colorful_pixels = 0
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            red, green, blue, alpha_value = pixels[x, y]
            if alpha_value <= 16:
                continue
            opaque_pixels += 1
            channel_span = max(red, green, blue) - min(red, green, blue)
            bright_enough = max(red, green, blue) >= 80
            not_grayscale_text = channel_span >= 35 and not (red >= 220 and green >= 220 and blue >= 220)
            if bright_enough and not_grayscale_text:
                colorful_pixels += 1
    if opaque_pixels < 45:
        return False
    component_count, largest_component = _alpha_component_stats(image)
    if component_count > 4 or largest_component / max(opaque_pixels, 1) < 0.5:
        return False
    return colorful_pixels / max(opaque_pixels, 1) >= 0.18


def _alpha_component_stats(image: Image.Image) -> tuple[int, int]:
    alpha = image.getchannel("A")
    mask = np.array(alpha) > 16
    components = _components(mask)
    if not components:
        return 0, 0
    return len(components), max(len(component) for component in components)


def _complete_score(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return 0.0
    x0, y0, x1, y1 = bbox
    margin_penalty = 0
    if x0 <= 1 or y0 <= 1 or x1 >= image.width - 1 or y1 >= image.height - 1:
        margin_penalty = 0.25
    aspect = (y1 - y0) / max(x1 - x0, 1)
    aspect_score = 1.0 if 1.1 <= aspect <= 3.5 else 0.65
    return max(0.0, min(1.0, aspect_score - margin_penalty))


def _pose_hint(width: int, height: int) -> str:
    if height < 18:
        return "duck"
    if width > height * 1.25:
        return "jump_or_special"
    return "standing_or_unknown"


def _ranking_prompt(candidate_records: list[dict[str, Any]]) -> str:
    records = [
        {
            "candidate_id": item["candidate_id"],
            "bbox": item["bbox"],
            "size": item["size"],
            "complete_score": round(float(item["complete_score"]), 3),
            "deterministic_pose_hint": item["deterministic_pose_hint"],
        }
        for item in candidate_records
    ]
    return (
        "Classify each numbered sprite crop in the contact sheet. Return only JSON with a 'rankings' array. "
        "Each ranking must have candidate_id, view front|back|left|right|unknown, pose idle|walk|run|jump|duck|other, "
        "confidence 0.0-1.0, and a short reason. Prefer idle/neutral full-body standing frames. Penalise attack, jump, "
        "duck, special poses, cropped/incomplete sprites, and mirrored duplicates. This is a Super Mario World sprite sheet: "
        "you are given the original labeled source sheet plus a numbered candidate crop sheet. Use the source-sheet labels "
        "near each candidate bbox when judging pose/view. "
        "most walk/run/idle gameplay sprites are side-facing profiles, not front views. Classify profile sprites with visible "
        "side nose/face as left or right. Reserve front for true front-facing sprites such as pipe/victory/castle-facing frames "
        "where the face/body are square-on. For rear-facing sprites with no visible "
        "face/nose and visible back-of-head, classify as back even if the sprite is small. Flag if a supposed back candidate "
        "appears front-facing by using view unknown and a low confidence. Do not propose new art. "
        f"Candidate metadata: {json.dumps(records)}"
    )


def _rear_facing_score(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return 0.0
    x0, y0, x1, y1 = bbox
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    opaque = 0
    rear_pink = 0
    blue_overalls = 0
    face_light = 0
    white_eye = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            red, green, blue, alpha_value = pixels[x, y]
            if alpha_value <= 16:
                continue
            opaque += 1
            if red >= 160 and green <= 125 and 70 <= blue <= 150:
                rear_pink += 1
            if blue >= 115 and green >= 70 and red <= 150:
                blue_overalls += 1
            if red >= 190 and green >= 120 and 45 <= blue <= 145:
                face_light += 1
            if red >= 220 and green >= 220 and blue >= 220:
                white_eye += 1
    if opaque == 0:
        return 0.0
    rear_ratio = rear_pink / opaque
    blue_ratio = blue_overalls / opaque
    face_ratio = (face_light + white_eye) / opaque
    score = 0.25 + rear_ratio * 1.6 + min(blue_ratio, 0.22) * 0.7 - min(face_ratio, 0.2) * 0.55
    return max(0.0, min(1.0, score))


def _side_facing_view(image: Image.Image) -> tuple[str, float] | None:
    if _rear_facing_score(image) >= 0.74:
        return None
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    width = max(x1 - x0, 1)
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    opaque = 0
    face_weight = 0
    face_x_total = 0.0
    white_weight = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            red, green, blue, alpha_value = pixels[x, y]
            if alpha_value <= 16:
                continue
            opaque += 1
            is_skin = red >= 175 and green >= 80 and 35 <= blue <= 155
            is_eye_or_glove = red >= 220 and green >= 220 and blue >= 220
            if is_skin or is_eye_or_glove:
                weight = 2 if is_skin else 1
                face_weight += weight
                face_x_total += (x - x0) * weight
                if is_eye_or_glove:
                    white_weight += 1
    if opaque == 0 or face_weight == 0:
        return None
    face_ratio = face_weight / opaque
    face_center = face_x_total / face_weight
    offset = (face_center / width) - 0.5
    if face_ratio < 0.22 or abs(offset) < 0.08:
        return None
    confidence = 0.58 + min(abs(offset), 0.34) * 0.75 + min(face_ratio, 0.5) * 0.25
    if white_weight / opaque > 0.18 and abs(offset) < 0.13:
        return None
    return ("left" if offset < 0 else "right", max(0.0, min(1.0, confidence)))


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def _normalise_ranking(item: dict[str, Any], candidate_count: int) -> dict[str, Any]:
    candidate_id = int(item.get("candidate_id", -1))
    view = str(item.get("view", "unknown"))
    pose = str(item.get("pose", "other"))
    if candidate_id < 0 or candidate_id >= candidate_count:
        candidate_id = -1
    if view not in VIEWS:
        view = "unknown"
    if pose not in POSES:
        pose = "other"
    confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
    return {
        "candidate_id": candidate_id,
        "view": view,
        "pose": pose,
        "confidence": confidence,
        "reason": str(item.get("reason", ""))[:240],
    }


def _best_for_view(rankings: list[dict[str, Any]], view: str) -> dict[str, Any] | None:
    items = [item for item in rankings if item.get("view") == view and int(item.get("candidate_id", -1)) >= 0]
    if not items and view in {"left", "right"}:
        opposite = "right" if view == "left" else "left"
        mirrored_items = [
            dict(item, view=view, mirrored_from=opposite)
            for item in rankings
            if item.get("view") == opposite and int(item.get("candidate_id", -1)) >= 0
        ]
        items = mirrored_items
    if not items:
        return None
    pose_bonus = {"idle": 0.2, "walk": 0.08, "run": 0.04, "other": 0.0, "jump": -0.15, "duck": -0.2}
    return max(items, key=lambda item: float(item.get("confidence", 0.0)) + pose_bonus.get(item.get("pose", "other"), 0.0))


def _fit_to_reference_canvas(image: Image.Image, reference_path: Path) -> Image.Image:
    reference = Image.open(reference_path).convert("RGBA")
    crop = remove_background(image)
    bbox = crop.getbbox()
    crop = crop.crop(bbox) if bbox else crop
    canvas = Image.new("RGBA", reference.size, (0, 0, 0, 0))
    if crop.width > canvas.width or crop.height > canvas.height:
        crop.thumbnail(canvas.size, Image.Resampling.NEAREST)
    canvas.alpha_composite(crop, ((canvas.width - crop.width) // 2, canvas.height - crop.height - 1))
    return canvas


def _update_asset_json(path: Path, asset: AssetSchema, copied: dict[str, Any], method: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("source_sprites", {})
    for view, record in copied.items():
        data["source_sprites"][view] = Path(record["path"]).name
    data["source_coverage"] = {
        "front": "authored" if "front" in copied else "authored",
        "back": "authored" if "back" in copied else "inferred",
        "left": "authored" if "left" in copied else "inferred",
        "right": "authored" if "right" in copied else "inferred",
        "candidate_selection_method": method,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _write_source_sheet_context(source_path: Path, output_path: Path) -> None:
    image = Image.open(source_path).convert("RGBA")
    max_height = 1800
    if image.height > max_height:
        ratio = max_height / image.height
        image = image.resize((max(1, int(image.width * ratio)), max_height), Image.Resampling.NEAREST)
    image.save(output_path, format="PNG")


def _resolve(path: Path) -> Path:
    return (WORKSPACE_ROOT / path if not path.is_absolute() else path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
