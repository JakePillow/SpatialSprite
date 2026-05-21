from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gpt-4o-mini"


def run_api_visual_judge(
    output_dir: Path,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    model = model or os.environ.get("OPENAI_VIEW_MODEL", DEFAULT_MODEL)
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    report_path = output_dir / "visual_mapping_report.json"
    image_paths = [
        output_dir / "comparison_contact_sheet.png",
        output_dir / "compare_0.png",
        output_dir / "compare_45.png",
        output_dir / "compare_90.png",
        output_dir / "compare_135.png",
        output_dir / "compare_180.png",
    ]
    if not api_key:
        return _write_error(output_dir, "OPENAI_API_KEY is not set. API visual judge skipped.")
    missing = [str(path) for path in [report_path, *image_paths] if not path.exists()]
    if missing:
        return _write_error(output_dir, f"API visual judge inputs are missing: {missing}")
    visual_report = json.loads(report_path.read_text(encoding="utf-8"))
    prompt = _prompt(visual_report)
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for image_path in image_paths:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{_b64(image_path)}",
            }
        )
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {"format": {"type": "json_object"}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return _write_error(output_dir, f"API visual judge HTTP {exc.code}: {body[:1200]}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return _write_error(output_dir, f"API visual judge request failed: {exc}")
    text = _extract_response_text(data)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _write_error(output_dir, "API visual judge returned non-JSON text.", {"response_text": text[:4000]})
    judgement = _normalise_judgement(parsed)
    judgement["schema"] = "spritespatial_api_visual_judgement_v1"
    judgement["advisory_only"] = True
    judgement["model"] = model
    (output_dir / "api_visual_judgement.json").write_text(json.dumps(judgement, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(output_dir / "api_visual_judgement.json"), "judgement": judgement}


def _prompt(visual_report: dict[str, Any]) -> str:
    compact = {
        "front_visual_mapping_iou": visual_report.get("front_visual_mapping_iou"),
        "worst_visual_mapping_view": visual_report.get("worst_visual_mapping_view"),
        "worst_visual_mapping_score": visual_report.get("worst_visual_mapping_score"),
        "views": {
            view: {
                "target_authority": item.get("target_authority"),
                "silhouette_iou": item.get("silhouette_iou"),
                "overfill_ratio": item.get("overfill_ratio"),
                "underfill_ratio": item.get("underfill_ratio"),
                "semantic_match_ratio": item.get("semantic_match_ratio"),
                "recommended_next_action": item.get("recommended_next_action"),
            }
            for view, item in visual_report.get("views", {}).items()
        },
    }
    return (
        "You are judging whether flattened 3D renders preserve authored sprite identity. "
        "Do not suggest generating art. Do not suggest replacing source sprites. "
        "Do not mutate geometry or imply validation truth; this judgement is advisory only. "
        "Judge shape, silhouette, semantic consistency, and readability. Distinguish authored views from inferred views. "
        "Return only JSON with fields: overall_readability_score, front_readability_score, side_readability_score, "
        "back_readability_score, does_front_read_like_source_sprite, does_side_read_like_valid_constructed_view, "
        "does_back_read_like_authored_or_inferred_view, main_shape_failures, semantic_failures, silhouette_failures, "
        "likely_cause, recommended_next_engineering_step, confidence. Scores must be 0.0-1.0. "
        f"Deterministic report summary: {json.dumps(compact)}"
    )


def _normalise_judgement(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_readability_score": _score(data.get("overall_readability_score")),
        "front_readability_score": _score(data.get("front_readability_score")),
        "side_readability_score": _score(data.get("side_readability_score")),
        "back_readability_score": _score(data.get("back_readability_score")),
        "does_front_read_like_source_sprite": bool(data.get("does_front_read_like_source_sprite", False)),
        "does_side_read_like_valid_constructed_view": bool(data.get("does_side_read_like_valid_constructed_view", False)),
        "does_back_read_like_authored_or_inferred_view": bool(data.get("does_back_read_like_authored_or_inferred_view", False)),
        "main_shape_failures": _string_list(data.get("main_shape_failures", [])),
        "semantic_failures": _string_list(data.get("semantic_failures", [])),
        "silhouette_failures": _string_list(data.get("silhouette_failures", [])),
        "likely_cause": str(data.get("likely_cause", ""))[:1000],
        "recommended_next_engineering_step": str(data.get("recommended_next_engineering_step", ""))[:1000],
        "confidence": _score(data.get("confidence")),
    }


def _score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:300] for item in value]


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def _write_error(output_dir: Path, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema": "spritespatial_api_visual_judgement_error_v1",
        "ok": False,
        "advisory_only": True,
        "error": message,
    }
    if extra:
        payload.update(extra)
    path = output_dir / "api_visual_judgement_error.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"ok": False, "path": str(path), "error": message}


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")
