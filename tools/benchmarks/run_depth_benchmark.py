from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = WORKSPACE_ROOT / "tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from spritespatial.depthfields import DepthConfig, generate_depth_field  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic depth-field regressions.")
    parser.add_argument("--corpus", type=Path, default=WORKSPACE_ROOT / "benchmarks/depth/corpus.json")
    parser.add_argument("--baseline", type=Path, default=WORKSPACE_ROOT / "benchmarks/depth/baselines/metrics.json")
    parser.add_argument("--report", type=Path, default=WORKSPACE_ROOT / "benchmarks/depth/reports/latest.json")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    return parser.parse_args()


def run_case(case: dict[str, Any], report_root: Path) -> dict[str, Any]:
    width, height = (int(value) for value in case["size"])
    alpha = np.zeros((height, width), dtype=bool)
    regions: list[dict[str, Any]] = []
    for region in case["regions"]:
        x0, y0, x1, y1 = (int(value) for value in region["rect"])
        mask = np.zeros_like(alpha)
        mask[y0:y1, x0:x1] = True
        alpha |= mask
        regions.append(
            {
                "region_id": str(region["id"]),
                "semantic_class": str(region["class"]),
                "mask": mask,
            }
        )
    output_dir = report_root / str(case["id"])
    result = generate_depth_field(
        {"asset_id": str(case["id"]), "alpha_mask": alpha},
        regions,
        DepthConfig(output_dir=output_dir),
    )
    opaque_values = result.pinned_depth_field[alpha]
    return {
        "z_max": round(float(opaque_values.max()), 8) if opaque_values.size else 0.0,
        "z_mean": round(float(opaque_values.mean()), 8) if opaque_values.size else 0.0,
        "silhouette_pinned": result.diagnostics.silhouette_pin_passed,
        "isolated_spikes": result.diagnostics.isolated_spike_count,
        "join_discontinuity_max": round(result.diagnostics.join_discontinuity_max, 8),
        "region_count": len(result.diagnostics.regions),
        "validation_passed": result.validation.passed,
        "depth_version": result.depth_version,
    }


def compare(
    actual: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]], tolerance: float
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for case_id, metrics in actual.items():
        expected = baseline.get(case_id)
        if expected is None:
            failures.append({"case": case_id, "metric": "case", "reason": "missing baseline"})
            continue
        for key, value in metrics.items():
            target = expected.get(key)
            matches = (
                abs(float(value) - float(target)) <= tolerance
                if isinstance(value, float) and isinstance(target, (float, int))
                else value == target
            )
            if not matches:
                failures.append({"case": case_id, "metric": key, "expected": target, "actual": value})
    return failures


def main() -> int:
    args = parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    report_root = args.report.parent / "artifacts"
    metrics = {case["id"]: run_case(case, report_root) for case in corpus["cases"]}
    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        failures: list[dict[str, Any]] = []
    elif args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        failures = compare(metrics, baseline, args.tolerance)
    else:
        failures = [{"metric": "baseline", "reason": f"missing {args.baseline}"}]
    report = {
        "schema": "spritespatial_depth_benchmark_report_v1",
        "case_count": len(metrics),
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": not failures, "case_count": len(metrics), "failure_count": len(failures)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
