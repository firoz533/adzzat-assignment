"""Runtime-provided external effect service (simulated).

send(job_id, idempotency_key, body) represents a call to a third-party system
such as a payment or notification API. It is NOT part of the pipeline database
and cannot take part in its transactions.

The service deduplicates on the idempotency key only: a second call with the
same key is acknowledged as a duplicate and NOT delivered again; a call with a
different key for the same job is delivered again. Every call and every
delivery is logged in the SQLite file named by EFFECTS_DB.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

_conn = None


def _db():
    global _conn
    if _conn is None:
        path = os.environ.get("EFFECTS_DB", "/app/work/effects.db")
        _conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
        _conn.execute("PRAGMA busy_timeout = 10000")
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.execute("CREATE TABLE IF NOT EXISTS calls(seq INTEGER PRIMARY KEY, job_id INTEGER, key TEXT, "
                      "worker TEXT, at REAL)")
        _conn.execute("CREATE TABLE IF NOT EXISTS deliveries(key TEXT PRIMARY KEY, job_id INTEGER, body TEXT, "
                      "worker TEXT, at REAL)")
    return _conn


def send(job_id: int, idempotency_key: str, body: dict) -> dict:
    conn = _db()
    worker = os.environ.get("WORKER_ID", "worker-0")
    time.sleep(0.02)  # network latency
    conn.execute("INSERT INTO calls(job_id, key, worker, at) VALUES (?, ?, ?, ?)",
                 (job_id, idempotency_key, worker, time.time()))
    try:
        conn.execute("INSERT INTO deliveries(key, job_id, body, worker, at) VALUES (?, ?, ?, ?, ?)",
                     (idempotency_key, job_id, json.dumps(body, sort_keys=True), worker, time.time()))
    except sqlite3.IntegrityError:
        return {"status": "duplicate", "key": idempotency_key}
    return {"status": "delivered", "key": idempotency_key}
