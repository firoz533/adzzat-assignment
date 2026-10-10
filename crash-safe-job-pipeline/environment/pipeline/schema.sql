PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY,
    customer_id   TEXT    NOT NULL,
    payload       TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'queued',   -- queued | running | done
    attempts      INTEGER NOT NULL DEFAULT 0,
    claimed_by    TEXT,
    claimed_at    REAL,
    finished_at   REAL
);

CREATE TABLE IF NOT EXISTS outputs (
    job_id        INTEGER PRIMARY KEY REFERENCES jobs(id),
    amount        REAL    NOT NULL,
    worker        TEXT    NOT NULL,
    attempt       INTEGER NOT NULL,
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_totals (
    customer_id   TEXT    PRIMARY KEY,
    total_amount  REAL    NOT NULL DEFAULT 0,
    n_done        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, id);
