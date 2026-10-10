"""Crash-safe pipeline worker (oracle).

Exactly-once semantics across worker crashes, built from four pieces that
only work together:

1. Leased claims. A claim records the time; a job whose lease has expired can
   be re-claimed by any worker. The attempt counter acts as a fencing token.
2. Stable idempotency keys. The external effect is keyed by the job id, so a
   retry after a crash is acknowledged as a duplicate and not delivered again.
3. One transaction for the durable effects: the fenced done-mark, the output
   row and the totals update commit together or not at all.
4. Workers only exit once every job is done, so an orphaned job is always
   picked up once its lease expires.

The chaos.point(...) calls keep their original positions and meanings.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import chaos
import effects

from pipeline.db import connect

WORKER_ID = os.environ.get("WORKER_ID", "worker-0")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/work/outputs"))
LEASE_SECONDS = 4.0
IDLE_POLL_SECONDS = 0.2


def compute(payload: str) -> float:
    digest = hashlib.sha256(payload.encode()).hexdigest()
    time.sleep(0.03)
    return int(digest[:6], 16) % 10000 / 100


def claim(conn):
    """Claim the oldest queued job or the oldest job whose lease has expired."""
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "UPDATE jobs SET status = 'running', claimed_by = ?, claimed_at = ?, attempts = attempts + 1 "
            "WHERE id = (SELECT id FROM jobs WHERE status = 'queued' "
            "            OR (status = 'running' AND claimed_at < ?) ORDER BY id LIMIT 1) "
            "RETURNING id, customer_id, payload, attempts",
            (WORKER_ID, now, now - LEASE_SECONDS),
        ).fetchone()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return row


def write_output_atomically(job_id, amount):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final = OUTPUT_DIR / f"{job_id}.json"
    tmp = OUTPUT_DIR / f".{job_id}.{WORKER_ID}.tmp"
    tmp.write_text(json.dumps({"job_id": job_id, "amount": amount, "worker": WORKER_ID}))
    os.replace(tmp, final)


def process(conn, job):
    job_id, customer, payload, attempt = job["id"], job["customer_id"], job["payload"], job["attempts"]
    chaos.point("after_claim")

    amount = compute(payload)
    chaos.point("after_compute")

    # Stable key: a retry of the same job reuses it and the service deduplicates.
    effects.send(job_id, idempotency_key=f"job-{job_id}", body={"customer": customer, "amount": amount})
    chaos.point("after_effect")

    write_output_atomically(job_id, amount)
    chaos.point("after_output_file")

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Fence on our own attempt number: if another worker re-claimed the job
        # after our lease expired, this updates nothing and we abandon the attempt.
        fenced = conn.execute(
            "UPDATE jobs SET status = 'done', finished_at = ? "
            "WHERE id = ? AND status = 'running' AND claimed_by = ? AND attempts = ?",
            (time.time(), job_id, WORKER_ID, attempt))
        if fenced.rowcount != 1:
            conn.execute("ROLLBACK")
            return
        conn.execute("INSERT INTO outputs(job_id, amount, worker, attempt, created_at) VALUES (?, ?, ?, ?, ?)",
                     (job_id, amount, WORKER_ID, attempt, time.time()))
        chaos.point("after_output_row")
        conn.execute("INSERT INTO customer_totals(customer_id, total_amount, n_done) VALUES (?, ?, 1) "
                     "ON CONFLICT(customer_id) DO UPDATE SET total_amount = total_amount + excluded.total_amount, "
                     "n_done = n_done + 1", (customer, amount))
        chaos.point("after_totals")
        conn.execute("COMMIT")
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        raise
    chaos.point("after_done")


def all_done(conn):
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE status != 'done'").fetchone()[0] == 0


def main():
    conn = connect()
    while True:
        job = claim(conn)
        if job is not None:
            process(conn, job)
            continue
        if all_done(conn):
            break
        time.sleep(IDLE_POLL_SECONDS)   # others hold leases; wait for them to finish or expire
    conn.close()


if __name__ == "__main__":
    main()
