Recover the parameters of an epidemic that was interrupted by an intervention on an unknown day, and deliver the method as a reusable fitter.

`/app/data/cases.csv` holds 120 days of reported cases from a single outbreak. The counts are an under-reported, noisy view of the true daily infections. The outbreak follows an SEIR model whose transmission rate dropped once, from `beta1` to `beta2`, at an unknown time `t_switch`. The population `N` and incubation rate `sigma` are known and given in `/app/data/meta.json`. The recovery rate `gamma`, the reporting fraction `rho`, the initial number infected `I0`, both transmission rates and the switch time are unknown. The exact equations, the observation model and the output schema are specified in `/app/CONTRACT.md`.

Write `/app/submission/fit.py`. It must accept `--input`, `--output`, `--population` and `--sigma`, read the CSV, and write a JSON file containing point estimates for all six unknowns, a 95 percent confidence interval for each, and the fitted expected reported count for each of the 120 days. The script may import only numpy, scipy, pandas and the standard library. It must be deterministic: two runs on the same input must give the same estimates.

Verification runs your script on the supplied dataset and on a hidden dataset generated from the same model with a different population, incubation rate, parameter values and noise draw. Five criteria are checked on both datasets, each with the tolerances stated in the contract:

1. Pre-switch transmission rate, recovery rate and the fitted daily means.
2. The switch day and the post-switch transmission rate.
3. The reporting fraction and the initial number infected.
4. Interval calibration: every interval must contain the true value and must not exceed a stated width.
5. Efficiency: each run completes within 240 seconds on two CPU cores with 2 GiB of memory, and repeated runs agree.

The reward is 1 only when all five criteria pass on both datasets. Individual outcomes are recorded for diagnosis. No network access is available or needed. Only `/app/submission` is transferred to the verifier, which runs the script as an unprivileged user with a 300-second limit per invocation.
