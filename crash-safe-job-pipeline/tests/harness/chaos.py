"""Runtime-provided crash injection.

Workers call chaos.point(name) at fixed places. The harness sets CRASH_AT to a
comma-separated list of "worker-id:point:n" entries; when the named worker
reaches its n-th hit of that point, the process exits immediately with code
137, exactly as a SIGKILL would: no exception, no finally blocks, no commits.

Every hit is also recorded in the SQLite file named by CHAOS_DB so the harness
can confirm the instrumentation points are still being executed.
"""
from __future__ import annotations

import os
import sqlite3
import time

_counts: dict[str, int] = {}
_conn = None


def _parse(spec):
    out = {}
    for item in filter(None, (s.strip() for s in spec.split(","))):
        worker, point, n = item.rsplit(":", 2)
        out[(worker, point)] = int(n)
    return out


def _record(worker, point, n):
    global _conn
    path = os.environ.get("CHAOS_DB")
    if not path:
        return
    if _conn is None:
        _conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
        _conn.execute("PRAGMA busy_timeout = 10000")
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.execute("CREATE TABLE IF NOT EXISTS hits(worker TEXT, point TEXT, n INTEGER, at REAL)")
    _conn.execute("INSERT INTO hits VALUES (?, ?, ?, ?)", (worker, point, n, time.time()))


def point(name: str) -> None:
    worker = os.environ.get("WORKER_ID", "worker-0")
    _counts[name] = _counts.get(name, 0) + 1
    n = _counts[name]
    _record(worker, name, n)
    target = _parse(os.environ.get("CRASH_AT", "")).get((worker, name))
    if target is not None and n == target:
        _record(worker, f"crash:{name}", n)
        os._exit(137)
