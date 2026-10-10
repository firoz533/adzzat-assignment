"""Scenario runner and invariant checks for the job pipeline.

A scenario seeds the queue, starts workers, optionally kills one of them at a
named instrumentation point via CRASH_AT, restarts crashed workers, waits for
every worker to exit, and then checks the final state. The checks are
interleaving-independent: a correct pipeline passes them under any schedule.

Usage (development):
  python harness.py --package /app --crash worker-1:after_effect:2
  python harness.py --package /app --clean
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

POINTS = ["after_claim", "after_compute", "after_effect", "after_output_file",
          "after_output_row", "after_totals", "after_done"]
N_JOBS, N_CUSTOMERS, N_WORKERS = 40, 4, 3
SCENARIO_TIMEOUT = 90.0        # hard stop for a scenario
RECOVERY_BOUND = 15.0          # orphaned job must finish within this many seconds of the crash
CLEAN_BOUND = 30.0             # no-crash scenario must finish within this
CRASH_BOUND = 60.0             # crash scenario must finish within this


def kill_user_processes(uid):
    """Kill every process owned by uid (Linux only). Used by the grader between scenarios."""
    proc = Path("/proc")
    if not proc.exists():
        return
    for _ in range(10):
        found = False
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                line = next(s for s in (entry / "status").read_text().splitlines() if s.startswith("Uid:"))
                if uid in map(int, line.split()[1:]):
                    os.kill(int(entry.name), signal.SIGKILL)
                    found = True
            except (FileNotFoundError, ProcessLookupError, StopIteration):
                pass
        if not found:
            return
        time.sleep(0.01)


def q(path, sql, args=()):
    conn = sqlite3.connect(path, timeout=10.0)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


class Scenario:
    def __init__(self, package_root, harness_dir, crash_at="", workdir=None, user=None):
        self.package_root = Path(package_root).resolve()
        self.harness_dir = Path(harness_dir).resolve()
        self.crash_at = crash_at
        self.work = Path(workdir or tempfile.mkdtemp(prefix="pipeline-"))
        self.user = user
        self.db = self.work / "pipeline.db"
        self.out = self.work / "outputs"
        self.effects = self.work / "effects.db"
        self.chaos = self.work / "chaos.db"
        self.logs = self.work / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.crash_time = None
        self.orphan = None
        self.restarts = 0
        self.exit_codes = []

    def env(self, worker_id, crash_at):
        base = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
        if os.name == "nt":  # local development on Windows only; the task runs on Linux
            base = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if k in os.environ}
        return {
            **base, "HOME": str(self.work),
            "PYTHONPATH": f"{self.harness_dir}{os.pathsep}{self.package_root}",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "WORKER_ID": worker_id, "PIPELINE_DB": str(self.db), "OUTPUT_DIR": str(self.out),
            "EFFECTS_DB": str(self.effects), "CHAOS_DB": str(self.chaos), "CRASH_AT": crash_at,
        }

    def spawn(self, worker_id, crash_at):
        log = (self.logs / f"{worker_id}.log").open("ab")
        kwargs = {}
        if self.user is not None:
            kwargs = {"user": self.user, "group": self.user, "extra_groups": []}
        return subprocess.Popen([sys.executable, "-m", "pipeline.worker"], cwd=self.work,
                                env=self.env(worker_id, crash_at), stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, **kwargs)

    def seed(self):
        proc = subprocess.run([sys.executable, "-m", "pipeline.seed", "--db", str(self.db), "--jobs", str(N_JOBS),
                               "--customers", str(N_CUSTOMERS)], cwd=self.work, env=self.env("seed", ""),
                              capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError("seeding failed: " + proc.stdout + proc.stderr)
        if self.user is not None:
            for p in [self.work, self.db, *self.work.glob("pipeline.db*")]:
                os.chown(p, self.user, self.user)

    def run(self):
        self.seed()
        started = time.monotonic()
        procs = {f"worker-{i}": self.spawn(f"worker-{i}", self.crash_at) for i in range(N_WORKERS)}
        live = dict(procs)
        while live and time.monotonic() - started < SCENARIO_TIMEOUT:
            for wid, p in list(live.items()):
                code = p.poll()
                if code is None:
                    continue
                self.exit_codes.append((wid, code))
                del live[wid]
                if code == 137:
                    if self.crash_time is None:
                        self.crash_time = time.time()
                        rows = q(self.db, "SELECT id FROM jobs WHERE status = 'running' AND claimed_by = ?", (wid,))
                        self.orphan = rows[0][0] if rows else None
                    self.restarts += 1
                    time.sleep(0.5)
                    live[wid] = self.spawn(wid, "")   # replacement never crashes again
            time.sleep(0.05)
        timed_out = bool(live)
        for p in live.values():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            p.wait()
        self.elapsed = time.monotonic() - started
        self.timed_out = timed_out
        return self.check()

    # ------------------------------------------------------------------
    def check(self):
        r = {"elapsed_s": round(self.elapsed, 2), "timed_out": self.timed_out,
             "restarts": self.restarts, "exit_codes": self.exit_codes, "crash_at": self.crash_at}
        jobs = q(self.db, "SELECT id, customer_id, status, attempts, finished_at FROM jobs ORDER BY id")
        outputs = q(self.db, "SELECT job_id, amount, worker, attempt FROM outputs ORDER BY job_id")
        totals = q(self.db, "SELECT customer_id, total_amount, n_done FROM customer_totals")
        deliveries = q(self.effects, "SELECT job_id, key FROM deliveries") if self.effects.exists() else []
        calls = q(self.effects, "SELECT job_id FROM calls") if self.effects.exists() else []
        hits = q(self.chaos, "SELECT point, COUNT(*) FROM hits GROUP BY point") if self.chaos.exists() else []

        status = {row[2] for row in jobs}
        r["n_jobs"] = len(jobs)
        r["n_done"] = sum(1 for row in jobs if row[2] == "done")
        r["n_outputs"] = len(outputs)
        r["complete"] = (len(jobs) == N_JOBS and status == {"done"} and len(outputs) == N_JOBS
                         and {row[0] for row in outputs} == {row[0] for row in jobs} and not self.timed_out
                         and all(code in (0, 137) for _, code in self.exit_codes))

        per_job = {}
        for job_id, _key in deliveries:
            per_job[job_id] = per_job.get(job_id, 0) + 1
        r["n_deliveries"] = len(deliveries)
        r["n_calls"] = len(calls)
        r["duplicate_effects"] = sorted(j for j, c in per_job.items() if c > 1)
        r["missing_effects"] = sorted(row[0] for row in jobs if row[0] not in per_job)
        r["effects_exactly_once"] = len(jobs) == N_JOBS and not r["duplicate_effects"] and not r["missing_effects"]

        expected = {}
        for job_id, amount, _w, _a in outputs:
            cust = next(row[1] for row in jobs if row[0] == job_id)
            t = expected.setdefault(cust, [0.0, 0])
            t[0] += amount
            t[1] += 1
        got = {row[0]: (row[1], row[2]) for row in totals}
        totals_ok = set(got) == set(expected) and all(
            abs(got[c][0] - expected[c][0]) < 1e-6 and got[c][1] == expected[c][1] for c in expected)
        files = sorted(p.name for p in self.out.glob("*.json")) if self.out.exists() else []
        files_ok = files == sorted(f"{row[0]}.json" for row in outputs)
        if files_ok:
            for job_id, amount, _w, _a in outputs:
                try:
                    data = json.loads((self.out / f"{job_id}.json").read_text())
                except (OSError, ValueError):
                    files_ok = False
                    break
                if data.get("job_id") != job_id or abs(float(data.get("amount", -1)) - amount) > 1e-9:
                    files_ok = False
                    break
        r["totals_consistent"] = totals_ok
        r["files_consistent"] = files_ok
        r["consistent"] = totals_ok and files_ok

        r["orphan"] = self.orphan
        if self.crash_at:
            finished = {row[0]: row[4] for row in jobs}
            if self.orphan is not None and self.crash_time is not None and finished.get(self.orphan):
                r["orphan_recovery_s"] = round(finished[self.orphan] - self.crash_time, 2)
            else:
                r["orphan_recovery_s"] = None
            recovered = self.orphan is None or (r["orphan_recovery_s"] is not None
                                                and r["orphan_recovery_s"] <= RECOVERY_BOUND)
            r["recovered"] = bool(recovered and r["complete"] and self.elapsed <= CRASH_BOUND)
            r["crashed"] = self.restarts >= 1
        else:
            r["recovered"] = None
            r["crashed"] = False
        r["clean_fast"] = (not self.crash_at) and r["complete"] and self.elapsed <= CLEAN_BOUND

        hit = {row[0]: row[1] for row in hits}
        r["points_hit"] = {p: hit.get(p, 0) for p in POINTS}
        r["instrumented"] = all(hit.get(p, 0) >= 1 for p in POINTS)
        return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default="/app", help="directory containing the pipeline package")
    ap.add_argument("--crash", default="", help="CRASH_AT spec, e.g. worker-1:after_effect:2")
    ap.add_argument("--clean", action="store_true", help="run without crashes")
    ap.add_argument("--keep", action="store_true", help="keep the scratch directory")
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    # In the verifier the runtime modules sit next to this file; in the agent
    # image this file lives in /app/tools and the modules in /app/runtime.
    runtime = here if (here / "chaos.py").exists() else here.parent / "runtime"
    sc = Scenario(a.package, runtime, "" if a.clean else a.crash)
    result = sc.run()
    print(json.dumps(result, indent=2))
    print("scratch:", sc.work)
    if not a.keep:
        shutil.rmtree(sc.work, ignore_errors=True)


if __name__ == "__main__":
    main()
