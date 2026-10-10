"""Choose noise seeds whose maximum-likelihood estimate sits close to the truth.

Uses the first-order expansion  theta_hat - theta ~ I^-1 * score  with the
Fisher information evaluated at the true parameters, so scanning hundreds of
seeds costs only a handful of ODE solves. The chosen seed is then confirmed
with the real oracle by calibrate.py.

Usage: python pick_seeds.py secrets_visible.json 1 200
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))
from seir_model import PARAM_NAMES, expected_reported  # noqa: E402

spec = json.loads((HERE / sys.argv[1]).read_text())
lo, hi = int(sys.argv[2]), int(sys.argv[3])
truth = {k: float(spec["params"][k]) for k in PARAM_NAMES}
N, sigma, days = float(spec["population"]), float(spec["sigma"]), 120

# Working coordinates: log for all but t_switch, matching a sensible fitter.
def mu_of(w):
    p = {k: (np.exp(v) if k != "t_switch" else v) for k, v in zip(PARAM_NAMES, w)}
    return expected_reported(p, N, sigma, days)[0]

w0 = np.array([np.log(truth[k]) if k != "t_switch" else truth[k] for k in PARAM_NAMES])
mu = mu_of(w0)
J = np.empty((days, len(w0)))
for i in range(len(w0)):
    h = 1e-4 if PARAM_NAMES[i] != "t_switch" else 1e-3
    e = np.zeros(len(w0)); e[i] = h
    J[:, i] = (mu_of(w0 + e) - mu_of(w0 - e)) / (2 * h)
safe = np.maximum(mu, 1e-9)
info = J.T @ (J / safe[:, None])
cov = np.linalg.inv(info)
se = np.sqrt(np.diag(cov))
print("asymptotic relative half-widths (1.96 se):",
      {k: round(1.96 * s * (1 if k != "t_switch" else 1 / truth[k]), 3) for k, s in zip(PARAM_NAMES, se)})

rows = []
for seed in range(lo, hi + 1):
    y = np.random.default_rng(seed).poisson(mu)
    score = J.T @ ((y - mu) / safe)
    delta = cov @ score
    z = delta / se
    rows.append((float(np.max(np.abs(z))), seed, z))
rows.sort()
print("best seeds by max |z| (smaller is safer):")
for m, seed, z in rows[:10]:
    print(f"  seed {seed:4d}  max|z|={m:.2f}  z=" + " ".join(f"{k}={v:+.2f}" for k, v in zip(PARAM_NAMES, z)))
