# Crash-safe job pipeline

The agent makes a small SQLite-backed job pipeline correct under worker
crashes: no job lost or stranded, exactly one delivery per job to an external
effect service that only deduplicates on idempotency keys, bookkeeping that
never drifts, and prompt recovery of orphaned work. See
[instruction.md](instruction.md) for the agent request and
[environment/CONTRACT.md](environment/CONTRACT.md) for the system, required
behaviour and criteria.

## The hard idea

Exactly-once semantics across a crash boundary when one effect lives outside
the database. Four mechanisms are needed and they only work together: leased
claims with a fencing token so a dead worker's job can be re-claimed without
double-processing, a stable idempotency key so a retried effect is suppressed
by the service, one transaction for the done-mark, output row and totals so a
crash between them leaves nothing half-applied, and an exit rule that keeps
workers alive until every job is done. Fixing any subset still fails at least
one scenario, which is what spreads the scores.

## Fault injection that is reproducible

Workers call `chaos.point(name)` at seven fixed places. The verifier owns the
chaos and effects modules, which shadow the agent's copies on `PYTHONPATH`.
`CRASH_AT=worker-1:after_effect:3` makes worker-1 exit with code 137 at its
third hit of that point; counters are per worker, so the crash position is
deterministic. The invariants are interleaving-independent, so a correct
pipeline passes under any schedule. Every scenario also verifies that all
seven points were executed, so deleting or moving the hooks fails the task.

## Environment

Digest-pinned Python 3.12.11 on Debian Bookworm, standard library only. The
agent gets the pipeline package, the runtime modules, the contract and the
same scenario harness the verifier uses. No network. Two CPU cores and 2 GiB.
Only `/app/submission/pipeline` reaches the verifier, which runs workers as
UID 65534.

## Verification

| # | Criterion | Weight | Scenarios |
|---|-----------|-------:|-----------|
| 1 | Complete: every job done exactly once, none stranded | 20 | all 15 |
| 2 | Exactly-once effects | 25 | all 15 |
| 3 | Consistent totals and output files | 20 | all 15 |
| 4 | Orphan recovered within 15 s, scenario within 60 s | 20 | 14 crash |
| 5 | Clean batch within 30 s | 15 | 1 clean |

Reward is binary; per-scenario results are written to
`/logs/verifier/criteria.json`.

## Calibration

Oracle: all 15 scenarios pass; orphans recover in about 4 seconds; clean run
1.5 seconds. Naive pipeline: clean run passes, every crash scenario except
`after_done` fails completeness and recovery, `after_claim` and
`after_compute` crashes lose the effect, `after_output_file` and
`after_output_row` crashes leave inconsistent bookkeeping. Weighted score
0.15. Details in [author/calibration.md](author/calibration.md).

## Layout

- `instruction.md`, `task.toml`
- `environment/`: agent image, `pipeline/` package, `runtime/` modules, `tools/run_scenario.py`, contract
- `tests/`: grader, `harness/` with the verifier's copies of the runtime modules and scenario runner
- `solution/`: oracle worker and install script
- `author/`: design note, calibration script and record

## Running

```sh
harbor run -p /absolute/path/to/crash-safe-job-pipeline -a oracle
harbor run -p /absolute/path/to/crash-safe-job-pipeline -a nop
harbor run -p /absolute/path/to/crash-safe-job-pipeline -a claude-code -m anthropic/claude-opus-5-5 -k 5
```
