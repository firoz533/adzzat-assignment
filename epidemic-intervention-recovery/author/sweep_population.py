"""Sweep the population size to find where rho and I0 become identifiable.

Usage: python sweep_population.py secrets_visible.json 1000000 300000 150000 80000
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))
sys.path.insert(0, str(HERE.parent / "solution"))
from seir_model import PARAM_NAMES, expected_reported  # noqa: E402
import fit  # noqa: E402

warnings.simplefilter("ignore")
spec = json.loads((HERE / sys.argv[1]).read_text())
truth = {k: float(spec["params"][k]) for k in PARAM_NAMES}
sigma = float(spec["sigma"])
seed = 11

for N in map(float, sys.argv[2:]):
    mean, inc = expected_reported(truth, N, sigma, 120)
    y = np.random.default_rng(seed).poisson(mean).astype(float)
    t0 = time.perf_counter()
    w = fit.run(y, N, sigma, 120)
    theta = fit.to_natural(w)
    lo, hi = fit.intervals(w, y, N, sigma, 120)
    dt = time.perf_counter() - t0
    ts = int(truth["t_switch"])
    print(f"N={int(N):>8d} attack_at_switch={inc[:ts].sum()/N:.2f} attack_total={inc.sum()/N:.2f} "
          f"peak_mean={mean.max():.0f} runtime={dt:.0f}s")
    for k, v, a, b in zip(PARAM_NAMES, theta, lo, hi):
        print(f"    {k:9s} rel_err={abs(v-truth[k])/truth[k]:.3f} contains={a<=truth[k]<=b} "
              f"width_rel={(b-a)/truth[k]:.3f}")
