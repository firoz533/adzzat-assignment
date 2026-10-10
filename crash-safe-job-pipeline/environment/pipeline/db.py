"""Database helpers shared by the seeder and the workers."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def db_path():
    return os.environ.get("PIPELINE_DB", "/app/work/pipeline.db")


def connect(path=None, autocommit=True):
    """Open the pipeline database.

    autocommit=True (the default) means every statement commits on its own.
    Pass autocommit=False to manage transactions yourself with BEGIN/COMMIT.
    """
    conn = sqlite3.connect(path or db_path(), timeout=10.0,
                           isolation_level=None if autocommit else "DEFERRED")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path=None):
    conn = connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.close()
