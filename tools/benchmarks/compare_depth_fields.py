from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two serialised depth fields.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    baseline = np.load(args.baseline)
    candidate = np.load(args.candidate)
    same_shape = baseline.shape == candidate.shape
    delta = np.abs(baseline - candidate) if same_shape else np.array([np.inf])
    report = {
        "same_shape": same_shape,
        "max_absolute_delta": float(delta.max()),
        "mean_absolute_delta": float(delta.mean()),
        "passed": same_shape and float(delta.max()) <= args.tolerance,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
