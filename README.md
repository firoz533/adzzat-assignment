# Terminal-Bench style tasks for Adzzat

Two self-designed, Harbor-compatible agent benchmark tasks, built against the
Adzzat author brief: a single genuinely hard problem per task, verification
against final container state with independent ground truth, several
independent weighted criteria so partial solutions separate cleanly, no
network, deterministic images, and an instruction under 600 words that says
what is verified and nothing about how.

| Task | Domain | The hard idea |
|------|--------|---------------|
| [epidemic-intervention-recovery](epidemic-intervention-recovery/) | Scientific computing | Parameter identifiability under a discontinuity: recover six SEIR parameters and an unknown intervention day from under-reported Poisson counts, with calibrated intervals, as a fitter that must also work on a hidden dataset whose switch sits after the peak |
| [crash-safe-job-pipeline](crash-safe-job-pipeline/) | Software engineering | Exactly-once semantics across a crash boundary: leased claims with fencing, stable idempotency keys for an external effect, one transaction for the bookkeeping, and a liveness rule, verified by deterministic fault injection at seven instrumentation points |

Each task directory follows the Harbor 0.7.1 layout (`task.toml`,
`instruction.md`, `environment/`, `tests/`, `solution/`) and adds `author/`
with the design note, calibration scripts and evidence. Secrets and reference
values live only under `tests/`, which never enters the agent image.

## Design principles shared by both tasks

- Ground truth is independent of the oracle. Task 1 compares against the
  secret parameters that generated the data. Task 2 checks invariants that
  any correct pipeline must satisfy under any interleaving.
- Difficulty is calibrated before any model rollout: a deliberately naive
  first attempt is written for each task and must fail several criteria while
  the oracle passes all. Task 1's naive fit scores 0.35, Task 2's naive
  pipeline scores 0.15.
- The verifier runs submitted code as an unprivileged user in a separate
  container, bounds what it reads, kills stray processes, and never exposes
  reference values to the submitted process.
- Criteria are mechanisms, not restatements of the same requirement, so a
  partial solution lands on a partial score rather than on zero or one.

## Running

Requires Docker and Harbor 0.7.1 (`pip install harbor==0.7.1`).

```sh
harbor run -p /absolute/path/to/<task> -a oracle     # must give reward 1
harbor run -p /absolute/path/to/<task> -a nop        # must give reward 0
harbor run -p /absolute/path/to/<task> -a claude-code -m anthropic/claude-opus-5-5 -k 5
```

## Validation status

See each task's `author/calibration.md` for oracle, nop and rollout results
and for where models failed.
