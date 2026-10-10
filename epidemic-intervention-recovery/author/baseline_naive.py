"""Deliberately naive baseline used only to calibrate difficulty.

Plain least squares on raw counts with all six parameters free from a generic
start, Gaussian intervals from the curve_fit covariance. This is roughly what
a first attempt looks like. It is expected to fail several criteria.

Same CLI as the oracle so the calibration runner can swap them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "solution"))
from fit import NAMES, expected_counts  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--population", type=float, required=True)
    ap.add_argument("--sigma", type=float, required=True)
    args = ap.parse_args()

    rows = np.loadtxt(args.input, delimiter=",", skiprows=1)
    y = rows[:, 1].astype(float)
    days = len(y)
    N, sigma = args.population, args.sigma

    def model(_x, beta1, beta2, gamma, t_switch, rho, I0):
        return expected_counts([beta1, beta2, gamma, t_switch, rho, I0], N, sigma, days)

    p0 = [0.3, 0.3, 0.1, 60.0, 0.5, 1.0]
    bounds = ([1e-4, 1e-4, 1e-4, 1.0, 1e-4, 1e-3], [5.0, 5.0, 5.0, days - 1.0, 1.0, 1e5])
    popt, pcov = curve_fit(model, np.arange(days), y, p0=p0, bounds=bounds, maxfev=20000)
    se = np.sqrt(np.maximum(np.diag(pcov), 0.0))
    result = {
        "estimates": {k: float(v) for k, v in zip(NAMES, popt)},
        "intervals": {k: [float(v - 1.96 * s), float(v + 1.96 * s)] for k, v, s in zip(NAMES, popt, se)},
        "expected_reported": [float(v) for v in model(None, *popt)],
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
