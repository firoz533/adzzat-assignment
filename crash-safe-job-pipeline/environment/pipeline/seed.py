"""Seed a deterministic batch of jobs."""
from __future__ import annotations

import argparse
import random

from pipeline.db import connect, init_db


def seed(path, n_jobs=40, n_customers=4, seed=1):
    init_db(path)
    rng = random.Random(seed)
    conn = connect(path)
    conn.execute("DELETE FROM jobs")
    conn.execute("DELETE FROM outputs")
    conn.execute("DELETE FROM customer_totals")
    for i in range(1, n_jobs + 1):
        customer = f"cust-{rng.randrange(n_customers):02d}"
        payload = f"order-{i:04d}-{rng.randrange(10**6):06d}"
        conn.execute("INSERT INTO jobs(id, customer_id, payload) VALUES (?, ?, ?)", (i, customer, payload))
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--jobs", type=int, default=40)
    ap.add_argument("--customers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    seed(a.db, a.jobs, a.customers, a.seed)
    print(f"seeded {a.jobs} jobs")
