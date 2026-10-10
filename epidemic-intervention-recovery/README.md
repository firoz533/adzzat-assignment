# Epidemic intervention recovery

The agent recovers the parameters of an SEIR epidemic whose transmission rate
dropped once at an unknown day, from 120 days of noisy, under-reported case
counts, and delivers the method as a reusable command-line fitter. See
[instruction.md](instruction.md) for the agent request and
[environment/CONTRACT.md](environment/CONTRACT.md) for the equations,
interface and acceptance criteria.

## The hard idea

Identifiability under a discontinuity. Early exponential growth fixes only one
combination of the transmission and recovery rates, the reporting fraction and
the initial infected are confounded until susceptibles deplete, the switch is
a discontinuity that stalls gradient fitters, and the likelihood has a
competing basin with a near-zero recovery rate that reproduces the growth rate
and the peak. The hidden dataset places the switch four days after the natural
peak, so the shortcut of reading the switch off the peak is four days wrong.
A plain least-squares fit from a generic start, which is what a first attempt
looks like, scores 0.35.

## Environment

Digest-pinned Python 3.12.11 on Debian Bookworm with pinned numpy, scipy,
pandas and matplotlib. The agent gets the visible dataset, its known constants
and the contract. No network. Two CPU cores and 2 GiB for both agent and
verifier. Only `/app/submission` reaches the verifier, which copies the single
submitted script out and runs it as UID 65534 with a 300-second limit per
invocation, twice on the visible dataset and twice on a hidden one generated
from the same model with different population, incubation rate, parameters
and noise. Reference values never enter the probe process.

## Verification

| # | Criterion | Weight | What it measures |
|---|-----------|-------:|------------------|
| 1 | Strong parameters | 20 | beta1, gamma and the fitted daily means |
| 2 | Switch | 25 | t_switch within 0.75 day, beta2 within 15 percent |
| 3 | Weak parameters | 25 | rho and I0 within 25 percent |
| 4 | Interval calibration | 20 | every 95 percent interval contains the truth and its estimate, and is narrower than a stated bound |
| 5 | Efficiency | 10 | under 240 seconds per run and bit-reproducible estimates |

Every criterion is evaluated on both datasets. The reward is binary; the
weighted score and residuals are written to `/logs/verifier/criteria.json`.

Ground truth is independent of the oracle: the data are generated from secret
parameters, so grading compares against those parameters and the noiseless
expected counts. Tolerances were set from the Fisher information and checked
against the oracle across several noise seeds; fixture seeds were chosen so
the maximum-likelihood estimate sits within a quarter standard error of the
truth on every parameter, which means any correct method passes with margin.
Details are in [author/calibration.md](author/calibration.md).

## Layout

- `instruction.md`: agent request, under 600 words.
- `task.toml`: Harbor resources, artifacts and separate verifier.
- `environment/`: agent image, visible data, known constants, contract.
- `tests/`: grader, private fixtures with secrets, reference model, generator.
- `solution/`: oracle fitter and install script.
- `author/`: design note, secrets, calibration scripts and results. Not part of the task images.

## Running

```sh
harbor run -p /absolute/path/to/epidemic-intervention-recovery -a oracle
harbor run -p /absolute/path/to/epidemic-intervention-recovery -a nop
harbor run -p /absolute/path/to/epidemic-intervention-recovery -a claude-code -m anthropic/claude-opus-5-5 -k 5
```

## Validation status

Oracle and nop results, rollout outcomes and step counts are recorded in
[author/calibration.md](author/calibration.md) as they are produced.
