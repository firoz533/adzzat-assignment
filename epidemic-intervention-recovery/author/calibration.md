# Calibration record

All numbers from `author/calibrate.py` on the author's machine (single core,
Python 3.14, scipy 1.18). Docker timings are recorded separately below.

## Population sweep

At a population of one million (10 percent attack fraction) a correct Poisson
maximum-likelihood fit could not recover rho or I0 at all (errors above 100
percent, interval widths above 20 times the value). At 150 thousand (37
percent attack) both are recovered within a few percent. The visible dataset
uses 150 thousand; the hidden dataset uses 100 thousand with the switch after
the natural peak (80 percent attack).

## Oracle on the fixture seeds

Visible, seed 117:

| parameter | rel. error | interval contains truth | rel. width |
|-----------|-----------:|:-----------------------:|-----------:|
| beta1 | 0.006 | yes | 0.09 |
| beta2 | 0.013 | yes | 0.21 |
| gamma | 0.010 | yes | 0.22 |
| t_switch | 0.018 day | yes | 0.47 day |
| rho | 0.011 | yes | 0.65 |
| I0 | 0.019 | yes | 0.49 |

Hidden, seed 121:

| parameter | rel. error | interval contains truth | rel. width |
|-----------|-----------:|:-----------------------:|-----------:|
| beta1 | 0.006 | yes | 0.11 |
| beta2 | 0.012 | yes | 0.21 |
| gamma | 0.008 | yes | 0.22 |
| t_switch | 0.010 day | yes | 0.89 day |
| rho | 0.003 | yes | 0.07 |
| I0 | 0.002 | yes | 0.17 |

Runtime 28 to 40 seconds per dataset. Extra hidden seeds 212 and 43 also pass
every criterion.

## Naive baseline (least squares, generic start, Gaussian intervals)

Visible, seed 117: gamma 11 percent off (fails criterion 1), t_switch
interval excludes the truth (fails 4), rho 31 percent off (fails 3). Passes 2
and 5. Weighted score 0.35.

Hidden, seed 121: beta2 54 percent off, gamma 67 percent off, t_switch found
at day 22 instead of 66, rho 21 percent off. Fails 1, 2, 3, 4.

## Traps observed while authoring

- The first oracle, warm-started along the switch grid, fell into a basin with
  gamma at its lower bound and beta1 at half the truth on the hidden set. The
  negative log-likelihood there is 20 units above the truth, so it is a genuine
  local optimum. Starting from several points on the growth-rate ridge fixed it.
- Pinning the switch at the smoothed peak of reported cases, then fitting the
  rest by maximum likelihood, gives beta1 off by 250 percent on the hidden set.
- Unbounded fits drift to rho above one and I0 near zero; the reporting
  fraction bound is essential.

## Docker results (Harbor 0.7.1, Docker Desktop, linux/amd64, 2 cores)

| run | reward | criteria | probe seconds (visible x2, hidden x2) | total |
|-----|-------:|----------|----------------------------------------|------:|
| oracle, 9 Oct 2026 | 1 | 1 1 1 1 1 | 36.5, 30.5, 25.8, 25.2 | 4 m 15 s |

| nop, 9 Oct 2026 | 0 | 0 0 0 0 0 | submitted script missing, every criterion fails as intended | 42 s |

Probe time is well inside the 240-second efficiency bound and the 300-second
hard limit. Rollout results are appended below as they are produced. The
verifier's criteria.json for each run is kept under author/evidence/.
