# Design note: epidemic-intervention-recovery

Author-side record of the design decisions. Not shipped to the agent.

## Problem

An SEIR epidemic ran with a transmission rate that dropped at an unknown day.
The agent receives 120 days of reported cases, a noisy under-reported fraction
of true daily infections, and must recover six parameters with 95 percent
intervals. It delivers a script, not a number, so the grader can rerun it on a
hidden dataset with different secrets.

## Why ground truth is independent

The data are generated from secret parameters. The grader compares the agent's
output to those secrets and to the noiseless expected counts. No reference
solution is involved in grading.

## The one hard idea

Identifiability under a discontinuity. Four traps, each needing a different idea:

1. rho and I0 are confounded during exponential growth; only the nonlinear
   depletion of susceptibles separates them.
2. The switch is a discontinuity, so gradient fitters stall unless t_switch is
   searched separately from the smooth parameters.
3. beta and gamma trade off unless the full peak shape is used.
4. Intervals must both contain the truth and be narrower than a bound, so the
   noise model (Poisson, not Gaussian) has to be respected.
5. In the visible data the switch coincides with the peak of reported cases.
   In the hidden data the switch comes four days after the natural peak, so
   the bend is subtle and the "switch equals peak" shortcut is four days off.

## Population and seed choices

Attack fraction is the lever for rho/I0 identifiability: at a million people
(10 percent attack) rho was unrecoverable by any method; at 150 thousand
(37 percent) a correct fit pins it within a few percent. Fixture seeds were
chosen with author/pick_seeds.py so the maximum-likelihood estimate sits
within a quarter standard error of the truth on every parameter; any correct
method therefore passes with margin, and failures reflect method, not luck.

## Criteria

| # | Criterion | Weight |
|---|-----------|-------:|
| 1 | Strong parameters beta1, gamma and fitted expected counts | 20 |
| 2 | Switch day and post-switch beta2 | 25 |
| 3 | Weak parameters rho and I0 | 25 |
| 4 | Interval calibration (contain truth, width under bound) | 20 |
| 5 | Runtime under budget and reproducible output | 10 |

Every criterion is checked on both the visible and the hidden dataset.
Reward is 1 only when all pass; the weighted score is diagnostic.

## Calibration before rollouts

The oracle sets the tolerances: each tolerance is 2 to 3 times the oracle's
worst error over five noise seeds. A deliberately naive baseline (plain least
squares from a default start, t_switch free) must fail at least two criteria.
Both results are recorded in author/calibration.md.
