"""Oracle: recover SEIR parameters and a transmission switch from reported cases.

Method (not disclosed to the agent):
  * Poisson maximum likelihood with smooth parameters in log space.
  * t_switch searched on a coarse grid with warm starts, refined twice, then
    polished jointly with Nelder-Mead.
  * 95 percent intervals from the observed-information (Hessian) matrix of the
    negative log-likelihood in the working parametrisation, mapped back.

Usage: python fit.py --input cases.csv --output result.json --population N --sigma S
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
from scipy.integrate import odeint
from scipy.optimize import minimize

NAMES = ["beta1", "beta2", "gamma", "t_switch", "rho", "I0"]
LOG_IDX = [0, 1, 2, 4, 5]  # everything except t_switch is fitted in log space

# Physical box in natural units for (beta1, beta2, gamma, rho, I0). rho is a
# reporting fraction so it cannot exceed one; I0 is bounded by the population.
LOWER = np.array([1e-3, 1e-3, 0.02, 0.005, 0.1])
UPPER = np.array([5.0, 5.0, 2.0, 1.0, 1e5])


# ----------------------------------------------------------------------------
# Forward model
# ----------------------------------------------------------------------------
def _rhs(y, _t, beta, sigma, gamma, N):
    S, E, I, _R, _C = y
    inf = beta * S * I / N
    return [-inf, inf - sigma * E, sigma * E - gamma * I, gamma * I, sigma * E]


def expected_counts(theta, N, sigma, days, rtol=1e-9, atol=1e-7):
    """Daily expected reported counts for a parameter vector in natural units."""
    beta1, beta2, gamma, t_switch, rho, I0 = theta
    t_switch = float(np.clip(t_switch, 0.0, days))
    y0 = np.array([N - I0, 0.0, I0, 0.0, 0.0])
    grid = np.arange(days + 1, dtype=float)
    C = np.empty(days + 1)
    left = grid[grid <= t_switch]
    right = grid[grid > t_switch]
    y_sw = y0
    if t_switch > 0.0:
        t_eval = np.concatenate([left, [t_switch]]) if left[-1] < t_switch else left
        ys = odeint(_rhs, y0, t_eval, args=(beta1, sigma, gamma, N), rtol=rtol, atol=atol)
        C[: len(left)] = ys[: len(left), 4]
        y_sw = ys[-1]
    if len(right):
        t_eval = np.concatenate([[t_switch], right])
        ys = odeint(_rhs, y_sw, t_eval, args=(beta2, sigma, gamma, N), rtol=rtol, atol=atol)
        C[len(left):] = ys[1:, 4]
    if t_switch == 0.0:
        C[0] = 0.0
    return rho * np.diff(C)


# ----------------------------------------------------------------------------
# Likelihood in working coordinates
# ----------------------------------------------------------------------------
def to_natural(w):
    theta = np.array(w, dtype=float)
    theta[LOG_IDX] = np.exp(theta[LOG_IDX])
    return theta


def to_working(theta):
    w = np.array(theta, dtype=float)
    w[LOG_IDX] = np.log(w[LOG_IDX])
    return w


def nll(w, y, N, sigma, days, rtol=1e-7, atol=1e-5):
    theta = to_natural(w)
    if not np.all(np.isfinite(theta)) or theta[3] < 0.5 or theta[3] > days - 0.5:
        return 1e30
    smooth = theta[LOG_IDX]
    if np.any(smooth < LOWER) or np.any(smooth > UPPER) or theta[5] > 0.5 * N:
        return 1e30
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mu = expected_counts(theta, N, sigma, days, rtol=rtol, atol=atol)
    if not np.all(np.isfinite(mu)):
        return 1e30
    mu = np.maximum(mu, 1e-9)
    return float(np.sum(mu - y * np.log(mu)))


def _smooth_bounds(N):
    upper = UPPER.copy()
    upper[4] = min(upper[4], 0.5 * N)
    return list(zip(np.log(LOWER), np.log(upper)))


def fit_smooth(w0, t_switch, y, N, sigma, days, maxiter=60):
    """Optimise the five smooth parameters with t_switch held fixed."""
    def f(v):
        w = np.array([v[0], v[1], v[2], t_switch, v[3], v[4]])
        return nll(w, y, N, sigma, days)
    v0 = np.array([w0[0], w0[1], w0[2], w0[4], w0[5]])
    bounds = _smooth_bounds(N)
    v0 = np.clip(v0, [b[0] + 1e-6 for b in bounds], [b[1] - 1e-6 for b in bounds])
    res = minimize(f, v0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": maxiter, "ftol": 1e-10, "gtol": 1e-6})
    w = np.array([res.x[0], res.x[1], res.x[2], t_switch, res.x[3], res.x[4]])
    return w, float(res.fun)


# ----------------------------------------------------------------------------
# Full procedure
# ----------------------------------------------------------------------------
def growth_rate(y, peak):
    """Exponential growth rate of the early counts, clipped to a sane range."""
    early = y[: max(peak, 8)]
    d = np.arange(len(early))
    mask = early > 0
    slope = 0.15
    if mask.sum() >= 4:
        slope = float(np.polyfit(d[mask], np.log(early[mask]), 1)[0])
    return float(np.clip(slope, 0.03, 0.6)), early, mask


def initial_guesses(y, days, sigma):
    """Several starts spread along the growth-rate ridge.

    Early exponential growth fixes only one combination of beta1 and gamma:
    (r + gamma)(r + sigma) = beta1 * sigma. Starting from several gamma values
    on that ridge is what lets the search escape the slow-recovery basin.
    """
    peak = int(np.argmax(np.convolve(y, np.ones(5) / 5, mode="same")))
    r, early, mask = growth_rate(y, peak)
    starts = []
    for gamma in (0.08, 0.2, 0.4):
        beta1 = (r + gamma) * (r + sigma) / sigma
        rho = 0.5
        I0 = max(float(early[mask][0]) / rho, 1.0) if mask.any() else 5.0
        guess = np.array([beta1, gamma * 0.7, gamma, float(peak), rho, I0])
        guess[LOG_IDX] = np.clip(guess[LOG_IDX], LOWER * 1.01, UPPER * 0.99)
        starts.append(guess)
    return starts


def initial_guess(y, days, sigma=0.33):
    return initial_guesses(y, days, sigma)[1]


def run(y, N, sigma, days, seed=0):
    fresh = [to_working(g) for g in initial_guesses(y, days, sigma)]
    guess_ts = fresh[0][3]

    # Stage 1: coarse grid over t_switch. At every grid point the search
    # starts both from the previous best (warm) and from each fresh guess on
    # the growth-rate ridge, so a bad basin found early cannot capture the walk.
    coarse = np.unique(np.concatenate([np.arange(8.0, days - 5.0, 8.0), [guess_ts]]))
    best = (None, np.inf)
    warm = None
    for ts in coarse:
        starts = list(fresh) + ([warm] if warm is not None else [])
        local = (None, np.inf)
        for s in starts:
            cand, val = fit_smooth(s, ts, y, N, sigma, days, maxiter=40)
            if val < local[1]:
                local = (cand, val)
        warm = local[0]
        if local[1] < best[1]:
            best = local

    # Stages 2 to 4: refine around the best point at increasing resolution.
    for span, step in ((8.0, 2.0), (1.5, 0.5), (0.5, 0.125)):
        centre = best[0][3]
        for ts in np.arange(centre - span, centre + span + 1e-9, step):
            if ts < 0.5 or ts > days - 0.5 or abs(ts - centre) < 1e-9:
                continue
            cand, val = fit_smooth(best[0], ts, y, N, sigma, days, maxiter=80)
            if val < best[1]:
                best = (cand, val)

    # Stage 5: joint polish including t_switch at tight ODE tolerance.
    tight = lambda v: nll(v, y, N, sigma, days, rtol=1e-9, atol=1e-7)
    res = minimize(tight, best[0], method="Nelder-Mead",
                   options={"xatol": 1e-5, "fatol": 1e-8, "maxiter": 800})
    w_hat = res.x if res.fun <= tight(best[0]) else best[0]
    return w_hat


def hessian(f, x, h):
    n = len(x)
    H = np.zeros((n, n))
    f0 = f(x)
    for i in range(n):
        ei = np.zeros(n); ei[i] = h[i]
        fpp = f(x + ei); fmm = f(x - ei)
        H[i, i] = (fpp - 2 * f0 + fmm) / h[i] ** 2
        for j in range(i + 1, n):
            ej = np.zeros(n); ej[j] = h[j]
            fpq = f(x + ei + ej); fpn = f(x + ei - ej)
            fnp = f(x - ei + ej); fnn = f(x - ei - ej)
            H[i, j] = H[j, i] = (fpq - fpn - fnp + fnn) / (4 * h[i] * h[j])
    return H


def intervals(w_hat, y, N, sigma, days):
    f = lambda v: nll(v, y, N, sigma, days, rtol=1e-9, atol=1e-7)
    h = np.array([2e-3, 2e-3, 2e-3, 0.05, 2e-3, 2e-3])
    H = hessian(f, w_hat, h)
    H = 0.5 * (H + H.T)
    try:
        cov = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(H)
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    lo = to_natural(w_hat - 1.96 * se)
    hi = to_natural(w_hat + 1.96 * se)
    # Respect the physical box: a reporting fraction cannot exceed one.
    lo[LOG_IDX] = np.maximum(lo[LOG_IDX], LOWER)
    hi[LOG_IDX] = np.minimum(hi[LOG_IDX], UPPER)
    return lo, hi


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

    w_hat = run(y, N, sigma, days)
    theta = to_natural(w_hat)
    lo, hi = intervals(w_hat, y, N, sigma, days)
    mu = expected_counts(theta, N, sigma, days)

    result = {
        "estimates": {k: float(v) for k, v in zip(NAMES, theta)},
        "intervals": {k: [float(a), float(b)] for k, a, b in zip(NAMES, lo, hi)},
        "expected_reported": [float(v) for v in mu],
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
