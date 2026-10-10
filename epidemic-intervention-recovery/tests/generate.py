"""Generate a dataset and its private fixture from secret parameters.

Usage:
  python generate.py --secrets secrets.json --seed 11 --days 120 \
      --csv ../environment/data/cases.csv --fixture fixtures/visible.json

The CSV holds only (day, reported). The fixture holds the secrets, the
noiseless expected counts and the tolerances, and never leaves tests/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from seir_model import PARAM_NAMES, expected_reported


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secrets", type=Path, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    args = ap.parse_args()

    spec = json.loads(args.secrets.read_text())
    params = {k: float(spec["params"][k]) for k in PARAM_NAMES}
    N, sigma = float(spec["population"]), float(spec["sigma"])

    mean, incidence = expected_reported(params, N, sigma, args.days)
    rng = np.random.default_rng(args.seed)
    reported = rng.poisson(mean)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as f:
        f.write("day,reported\n")
        for d, r in enumerate(reported):
            f.write(f"{d},{int(r)}\n")

    fixture = {
        "input": {"population": N, "sigma": sigma, "days": args.days, "seed": args.seed},
        "secrets": params,
        "expected_reported": mean.tolist(),
        "incidence": incidence.tolist(),
        "tolerances": spec.get("tolerances", {}),
    }
    args.fixture.parent.mkdir(parents=True, exist_ok=True)
    args.fixture.write_text(json.dumps(fixture, indent=2))
    peak = int(np.argmax(mean))
    print(f"wrote {args.csv} and {args.fixture}")
    print(f"  total reported={int(reported.sum())}  peak day={peak}  peak mean={mean[peak]:.1f}")
    print(f"  attack fraction={incidence.sum() / N:.3f}  reported at switch~{mean[int(params['t_switch'])]:.1f}")


if __name__ == "__main__":
    main()
