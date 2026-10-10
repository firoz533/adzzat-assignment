# Design note: crash-safe-job-pipeline

Author-side record. Not shipped to the agent.

## Problem

The container holds a small, working job pipeline: a SQLite queue, workers
that claim jobs, compute a result, call an external effect service, write an
output file, update per-customer totals and mark the job done. It is correct
when nothing crashes. The agent must make it correct when workers are killed
at arbitrary points and restarted, without losing jobs, duplicating effects,
or drifting the totals, and must recover orphaned work promptly.

## The one hard idea

Exactly-once semantics across a crash boundary, when one of the effects lives
outside the database. The pieces interact: a crash after the external effect
but before the commit means the retry must not repeat the effect, which needs
a stable idempotency key; a crash after claim means the lease must expire so
another worker can take over; a crash between the output row and the totals
update means the two must be one transaction; and the effect service only
deduplicates when the client sends the same key both times. Fixing any one of
these without the others still fails a scenario.

## Fault injection that is reproducible

Workers call `chaos.point(name)` at fixed semantic places. The grader owns the
chaos module (its copy shadows the agent's via PYTHONPATH) and the effect
service. An environment variable such as `CRASH_AT=worker-1:after_effect:2`
makes worker 1 exit with code 137 at its second hit of that point. Counters are
per worker, so the crash position is deterministic for that worker. The
invariants checked afterwards are interleaving-independent, so a correct
solution passes under any schedule.

The grader also verifies each named point was hit at least once per scenario,
so deleting the hooks fails the task.

## Criteria

| # | Criterion | Weight |
|---|-----------|-------:|
| 1 | Completeness: every job done exactly once, none stuck, under crashes | 20 |
| 2 | Exactly-once effects: effect service log has one entry per job | 25 |
| 3 | Consistency: totals equal the sum over outputs, output files match rows | 20 |
| 4 | Recovery: orphaned jobs re-run within the lease bound; scenario time bound | 20 |
| 5 | Clean run: no crashes, all jobs done with the throughput floor | 15 |

Scenarios: for each of six crash points, a worker is killed at its 1st and
3rd hit, and restarted by the supervisor. Twelve crash scenarios plus one clean
scenario, around 10 seconds each.

## What the naive pipeline gets wrong

- Claim has no lease: a crash after claim strands the job in `running`.
- The effect call carries a fresh random idempotency key on each attempt, so
  the service cannot deduplicate a retry.
- Output row, totals update and done-mark are three separate autocommits.
- The output file is written before the row, and overwritten blindly.
