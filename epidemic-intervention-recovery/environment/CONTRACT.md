# Contract: epidemic intervention recovery

## Model

Compartments S, E, I, R with a cumulative-infection counter C, population N,
incubation rate sigma, recovery rate gamma, and a transmission rate that
changes once at an unknown time:

```
S' = -beta(t) S I / N
E' =  beta(t) S I / N - sigma E
I' =  sigma E - gamma I
R' =  gamma I
C' =  sigma E
beta(t) = beta1  if t <  t_switch
          beta2  if t >= t_switch
```

Initial state at t = 0: S = N - I0, E = 0, I = I0, R = 0, C = 0.
N and sigma are known and supplied on the command line. The unknowns are
beta1, beta2, gamma, t_switch, rho and I0. All are positive; rho is a
reporting fraction in (0, 1]; t_switch lies strictly inside the observation
window.

## Observation model

Day d covers the interval [d, d+1). True incidence on day d is
C(d+1) - C(d). The reported count for day d is a Poisson draw with mean
rho times that incidence. Days are independent given the trajectory. The
dataset holds days 0 to 119 as a CSV with header `day,reported`.

## Interface

```
python /app/submission/fit.py --input cases.csv --output result.json \
    --population N --sigma SIGMA
```

The script must be a single self-contained file that imports only numpy,
scipy, pandas and the standard library. It is copied out of `/app/submission`
and executed on its own, so it must not read any other file, and must write:

```json
{
  "estimates": {"beta1": f, "beta2": f, "gamma": f, "t_switch": f, "rho": f, "I0": f},
  "intervals": {"beta1": [lo, hi], "beta2": [lo, hi], "gamma": [lo, hi],
                "t_switch": [lo, hi], "rho": [lo, hi], "I0": [lo, hi]},
  "expected_reported": [120 floats]
}
```

`intervals` are 95 percent confidence intervals. `expected_reported` is the
fitted mean reported count for each day, which equals rho times the fitted
incidence. All numbers must be finite.

## Verification

The script is run twice on the supplied dataset and twice on a hidden dataset
generated from the same model with different N, sigma, parameters and noise.
Every criterion must hold on both datasets.

| # | Criterion | Weight | Tolerance |
|---|-----------|-------:|-----------|
| 1 | beta1, gamma, fitted mean | 20 | beta1, gamma within 8 percent; each day's fitted mean within 5 + 10 percent of the true mean |
| 2 | Switch | 25 | t_switch within 0.75 day; beta2 within 15 percent |
| 3 | rho, I0 | 25 | each within 25 percent |
| 4 | Intervals | 20 | every interval contains the true value and its own estimate; widths at most 25 percent (beta1), 60 percent (beta2), 50 percent (gamma), 1.5 days (t_switch), 90 percent (rho), 90 percent (I0) of the true value |
| 5 | Efficiency | 10 | each run finishes within 240 seconds on 2 cores; the second run reproduces the first estimates to a relative 1e-6 |

Percent tolerances are relative to the true value. A run that exceeds 300
seconds, exits non-zero, or writes a malformed file fails every criterion.
The reward is 1 only when all five criteria pass; the weighted score is kept
for diagnosis.

## Guidance on identifiability

The hidden dataset is drawn from the same model family, so a method that
works only for the supplied numbers will not pass. The supplied data are
consistent with the stated model; no reporting delay, weekday effect or
over-dispersion is present.
