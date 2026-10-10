"""Reference SEIR forward model with a single transmission switch.

Grader-side only. The agent never sees this file; it writes its own model from
the equations stated in instruction.md.

State: S, E, I, R, C where C is cumulative infections (C' = sigma * E).
Daily incidence on day d is C(d+1) - C(d). Reported counts are Poisson with
mean rho * incidence.
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

PARAM_NAMES = ["beta1", "beta2", "gamma", "t_switch", "rho", "I0"]


def _rhs(beta, sigma, gamma, N):
    def f(_t, y):
        S, E, I, _R, _C = y
        inf = beta * S * I / N
        return [-inf, inf - sigma * E, sigma * E - gamma * I, gamma * I, sigma * E]
    return f


def cumulative_infections(params, N, sigma, days, rtol=1e-10, atol=1e-8):
    """Return C(t) at t = 0, 1, ..., days (length days + 1).

    The switch at t_switch is handled by integrating in two pieces so the
    discontinuity in beta is exact rather than smeared by the step controller.
    """
    beta1, beta2, gamma, t_switch, _rho, I0 = (params[k] for k in PARAM_NAMES)
    y0 = [N - I0, 0.0, I0, 0.0, 0.0]
    grid = np.arange(days + 1, dtype=float)
    out = np.empty(days + 1)
    t_switch = float(np.clip(t_switch, 0.0, days))

    left = grid[grid <= t_switch]
    right = grid[grid > t_switch]
    y_switch = y0
    if t_switch > 0.0:
        t_eval = np.unique(np.concatenate([left, [t_switch]]))
        sol = solve_ivp(_rhs(beta1, sigma, gamma, N), (0.0, t_switch), y0,
                        t_eval=t_eval, rtol=rtol, atol=atol, method="DOP853")
        if not sol.success:
            raise RuntimeError(sol.message)
        out[: len(left)] = sol.y[4, : len(left)]
        y_switch = sol.y[:, -1]
    if len(right):
        sol = solve_ivp(_rhs(beta2, sigma, gamma, N), (t_switch, float(days)), y_switch,
                        t_eval=right, rtol=rtol, atol=atol, method="DOP853")
        if not sol.success:
            raise RuntimeError(sol.message)
        out[len(left):] = sol.y[4]
    if t_switch == 0.0:
        out[0] = 0.0
    return out


def expected_reported(params, N, sigma, days):
    C = cumulative_infections(params, N, sigma, days)
    incidence = np.diff(C)
    return params["rho"] * incidence, incidence
