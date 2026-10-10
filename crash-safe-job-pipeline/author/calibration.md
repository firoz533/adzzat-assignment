# Calibration record

Local runs on the author's machine with `author/run_matrix.py` (Python 3.14,
Windows). Docker results are appended below as they are produced.

## Oracle (solution/worker.py)

| scenario | elapsed | done | complete | effects | consistent | recovered | orphan recovery |
|---|---:|---:|:-:|:-:|:-:|:-:|---:|
| clean | 1.5 s | 40/40 | yes | yes | yes | n/a | n/a |
| after_claim 1, 3 | 4.6 s | 40/40 | yes | yes | yes | yes | 4.1 s |
| after_compute 1, 3 | 4.6 s | 40/40 | yes | yes | yes | yes | 4.0 s |
| after_effect 1, 3 | 4.5 s | 40/40 | yes | yes | yes | yes | 3.9 s |
| after_output_file 1, 3 | 4.6 s | 40/40 | yes | yes | yes | yes | 4.0 s |
| after_output_row 1, 3 | 4.6 s | 40/40 | yes | yes | yes | yes | 4.0 s |
| after_totals 1, 3 | 4.5 s | 40/40 | yes | yes | yes | yes | 4.0 s |
| after_done 1, 3 | 1.5 s | 40/40 | yes | yes | yes | yes | no orphan |

All five criteria pass. Recovery time is the 4-second lease plus polling.

## Naive pipeline (environment/pipeline/worker.py)

| scenario | done | complete | effects | consistent | recovered |
|---|---:|:-:|:-:|:-:|:-:|
| clean | 40/40 | yes | yes | yes | n/a |
| after_claim 1, 3 | 39/40 | no | no (missing) | yes | no |
| after_compute 1, 3 | 39/40 | no | no (missing) | yes | no |
| after_effect 1, 3 | 39/40 | no | yes | yes | no |
| after_output_file 1, 3 | 39/40 | no | yes | no | no |
| after_output_row 1, 3 | 39/40 | no | yes | no | no |
| after_totals 1, 3 | 39/40 | no | yes | yes | no |
| after_done 1, 3 | 40/40 | yes | yes | yes | yes |

Criteria 1 to 4 fail, criterion 5 passes. Weighted score 0.15.

## Partial fixes and what they score

Reasoned from the scenario table; each mechanism maps to different criteria:

- Lease reclaim only: completeness and recovery pass; a retry after
  `after_effect` delivers a second effect under a fresh key (criterion 2
  fails); a retry after `after_output_row` hits the primary key or double
  counts totals (criterion 3 fails).
- Lease reclaim plus stable keys: criterion 2 passes; criterion 3 still fails
  until the three writes share one transaction.
- Transaction without a fencing token: a slow worker whose lease expired can
  commit a second time; the clean and short scenarios rarely expose this, so
  it shows up as an intermittent failure rather than a systematic one.

## Docker results (Harbor 0.7.1, Docker Desktop, linux/amd64, 2 cores)

| run | reward | criteria | notes | total |
|-----|-------:|----------|-------|------:|
| oracle, 9 Oct 2026 | 1 | 1 1 1 1 1 | all 15 scenarios pass; orphan recovery 3.9 to 4.1 s; clean 1.6 s | 2 m 12 s |
| nop, 9 Oct 2026 | 0 | 0 0 0 0 0 | submitted package missing, every criterion fails as intended | 30 s |

Nop and rollout results are appended below as they are produced. The
verifier's criteria.json for each run is kept under author/evidence/.
