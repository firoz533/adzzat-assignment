"""Pipeline worker.

Claims queued jobs one at a time, computes a result, notifies the external
effect service, writes an output file, records the output row, updates the
customer's running totals and marks the job done. Exits when no queued jobs
remain.

Run with:  python -m pipeline.worker
Environment: WORKER_ID, PIPELINE_DB, OUTPUT_DIR (see CONTRACT.md).

The calls to chaos.point(...) are fixed instrumentation points used by the
test harness to kill the worker at precise moments. They must stay in place
and keep their meaning.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import chaos
import effects

from pipeline.db import connect

WORKER_ID = os.environ.get("WORKER_ID", "worker-0")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/work/outputs"))


def compute(payload: str) -> float:
    """Deterministic, slightly slow result for a payload."""
    digest = hashlib.sha256(payload.encode()).hexdigest()
    time.sleep(0.03)
    return int(digest[:6], 16) % 10000 / 100


def claim(conn):
    row = conn.execute(
        "UPDATE jobs SET status = 'running', claimed_by = ?, claimed_at = ?, attempts = attempts + 1 "
        "WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1) "
        "RETURNING id, customer_id, payload, attempts",
        (WORKER_ID, time.time()),
    ).fetchone()
    return row


def process(conn, job):
    job_id, customer, payload, attempt = job["id"], job["customer_id"], job["payload"], job["attempts"]
    chaos.point("after_claim")

    amount = compute(payload)
    chaos.point("after_compute")

    effects.send(job_id, idempotency_key=str(uuid.uuid4()), body={"customer": customer, "amount": amount})
    chaos.point("after_effect")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{job_id}.json").write_text(json.dumps({"job_id": job_id, "amount": amount, "worker": WORKER_ID}))
    chaos.point("after_output_file")

    conn.execute("INSERT INTO outputs(job_id, amount, worker, attempt, created_at) VALUES (?, ?, ?, ?, ?)",
                 (job_id, amount, WORKER_ID, attempt, time.time()))
    chaos.point("after_output_row")

    conn.execute("INSERT INTO customer_totals(customer_id, total_amount, n_done) VALUES (?, ?, 1) "
                 "ON CONFLICT(customer_id) DO UPDATE SET total_amount = total_amount + excluded.total_amount, "
                 "n_done = n_done + 1", (customer, amount))
    chaos.point("after_totals")

    conn.execute("UPDATE jobs SET status = 'done', finished_at = ? WHERE id = ?", (time.time(), job_id))
    chaos.point("after_done")


def main():
    conn = connect()
    while True:
        job = claim(conn)
        if job is None:
            break
        process(conn, job)
    conn.close()


if __name__ == "__main__":
    main()
