# Contract: crash-safe job pipeline

## The system

`/app/pipeline` is a small job pipeline on SQLite:

- `jobs` holds queued work. A worker claims a job, computes a result from its
  payload, calls the external effect service once for the job, writes an
  output file, records an `outputs` row, adds the amount to the customer's
  `customer_totals`, and marks the job done.
- Workers are started with `python -m pipeline.worker` and read `WORKER_ID`,
  `PIPELINE_DB` and `OUTPUT_DIR` from the environment. Several run at once.
- `/app/runtime/effects.py` is the external effect service. It is outside the
  database and cannot join its transactions. It deduplicates on the
  idempotency key only: the same key is delivered once; a new key for the same
  job is delivered again.
- `/app/runtime/chaos.py` provides `chaos.point(name)`. The worker calls it at
  seven fixed places in this order: `after_claim`, `after_compute`,
  `after_effect`, `after_output_file`, `after_output_row`, `after_totals`,
  `after_done`. When `CRASH_AT` names a worker, a point and a hit count, that
  worker exits with code 137 at that moment, exactly like SIGKILL.

The pipeline is correct when nothing crashes. It is not correct when a worker
is killed and a replacement worker is started.

## Required behaviour

Under any sequence of worker kills and restarts, once every worker has
exited, all of the following must hold:

1. **Complete.** Every job is `done`, each has exactly one `outputs` row, and
   no job is left `queued` or `running`. A worker exits with code 0 only when
   every job is done; while other workers hold jobs it must wait for them to
   finish or for their claims to become reclaimable.
2. **Exactly-once effects.** The effect service has delivered exactly one
   effect per job. Repeated calls that the service acknowledges as duplicates
   are fine; a second delivery for the same job is not, and a job with no
   delivery is not.
3. **Consistent bookkeeping.** For every customer, `total_amount` equals the
   sum of that customer's `outputs.amount` and `n_done` equals their count.
   `OUTPUT_DIR` holds exactly one `<job_id>.json` per output row, and its
   `amount` equals the row's.
4. **Prompt recovery.** A job held by a worker that is killed must be done
   within 15 seconds of the kill, and a crash scenario must finish within 60
   seconds.
5. **Clean throughput.** With no crashes, the batch of 40 jobs on three
   workers finishes within 30 seconds.

The seven instrumentation points must remain in the worker, in the same
order, with the same meanings, and must still be executed for every job.
Removing or moving them fails every criterion. You may change anything else:
schema, claim logic, transactions, file handling, module layout. You may not
modify the runtime modules; the verifier uses its own copies.

## Development tools

`python /app/tools/run_scenario.py --package /app --clean` runs a scenario
without crashes. `--crash worker-1:after_effect:2` kills worker-1 at its
second hit of that point and restarts it. The output lists every invariant
above. The verifier uses the same harness with its own scenario list.

## Delivery

Copy the complete modified package to `/app/submission/pipeline`, including
`__init__.py`, `schema.sql`, `db.py`, `seed.py` and `worker.py`. Only that
directory reaches the verifier. The verifier runs workers as an unprivileged
user with the runtime modules ahead of your package on `PYTHONPATH`.

## Verification

Fourteen crash scenarios (each instrumentation point, first and third hit of
worker-1, with the killed worker restarted) plus one clean scenario.

| # | Criterion | Weight | Scenarios |
|---|-----------|-------:|-----------|
| 1 | Complete | 20 | all |
| 2 | Exactly-once effects | 25 | all |
| 3 | Consistent bookkeeping | 20 | all |
| 4 | Prompt recovery | 20 | crash scenarios |
| 5 | Clean throughput | 15 | clean scenario |

A criterion passes only if it holds in every scenario listed. The reward is 1
only when all five pass. Per-scenario results are kept for diagnosis.
