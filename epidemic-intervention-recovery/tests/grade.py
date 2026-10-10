"""Grade the submitted fitter against private fixtures without importing it as root.

The submitted script is executed as UID 65534 in a scratch directory with a
timeout, on the visible dataset and on a hidden dataset with different secrets.
Reference answers never leave this process. Writes /logs/verifier/reward.txt
(binary) and criteria.json (per-criterion outcomes and residuals).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
LOGS = Path("/logs/verifier")
SUBMISSION = Path("/app/submission/fit.py")
NAMES = ["beta1", "beta2", "gamma", "t_switch", "rho", "I0"]
WEIGHTS = {"1": 20, "2": 25, "3": 25, "4": 20, "5": 10}
DATASETS = {"visible": "visible_cases.csv", "hidden": "hidden_cases.csv"}
PROBE_LIMIT = 300


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4_000_000:
            raise ValueError("Expected bounded regular JSON file")
        return json.loads(stream.read(4_000_001))


def kill_children():
    for _ in range(10):
        found = False
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                line = next(s for s in (entry / "status").read_text().splitlines() if s.startswith("Uid:"))
                if 65534 in map(int, line.split()[1:]):
                    os.kill(int(entry.name), signal.SIGKILL)
                    found = True
            except (FileNotFoundError, ProcessLookupError):
                pass
        if not found:
            return
        time.sleep(0.01)


def finite_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def validate_schema(result, days):
    if not isinstance(result, dict):
        raise ValueError("Result is not a JSON object")
    for key in ("estimates", "intervals", "expected_reported"):
        if key not in result:
            raise ValueError(f"Missing key {key}")
    est, iv, mu = result["estimates"], result["intervals"], result["expected_reported"]
    for k in NAMES:
        if k not in est or not finite_number(est[k]):
            raise ValueError(f"estimates.{k} missing or non-finite")
        if k not in iv or not (isinstance(iv[k], list) and len(iv[k]) == 2
                               and all(finite_number(v) for v in iv[k])):
            raise ValueError(f"intervals.{k} must be two finite numbers")
        if iv[k][0] > iv[k][1]:
            raise ValueError(f"intervals.{k} lower bound exceeds upper bound")
    if not (isinstance(mu, list) and len(mu) == days and all(finite_number(v) for v in mu)):
        raise ValueError(f"expected_reported must hold {days} finite numbers")
    if any(v < 0 for v in mu):
        raise ValueError("expected_reported must be non-negative")


class Runner:
    def __init__(self):
        LOGS.mkdir(exist_ok=True, parents=True)
        self.base = Path(tempfile.mkdtemp(prefix="epi-eval-"))
        os.chmod(self.base, 0o755)
        self.counter = 0
        self.timings = {}

    def invoke(self, name, csv_path, population, sigma):
        if not SUBMISSION.is_file():
            raise ValueError("Submitted /app/submission/fit.py is missing")
        self.counter += 1
        directory = self.base / f"run-{self.counter}"
        directory.mkdir(mode=0o700)
        shutil.copyfile(csv_path, directory / "cases.csv")
        os.chmod(directory / "cases.csv", 0o644)
        script = self.base / f"fit-{self.counter}.py"
        shutil.copyfile(SUBMISSION, script)
        os.chmod(script, 0o644)
        os.chown(directory, 65534, 65534)
        output = directory / "result.json"
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(directory),
            "PYTHONPATH": str(SUBMISSION.parent), "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
            "MPLCONFIGDIR": str(directory / "mpl"), "MPLBACKEND": "Agg",
        }
        started = time.monotonic()
        with (LOGS / f"invocation-{self.counter}.log").open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, str(script), "--input", str(directory / "cases.csv"),
                 "--output", str(output), "--population", repr(population), "--sigma", repr(sigma)],
                cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT,
                user=65534, group=65534, extra_groups=[], start_new_session=True)
            try:
                code = process.wait(timeout=PROBE_LIMIT)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ValueError(f"{name}: exceeded the {PROBE_LIMIT}-second probe limit")
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                kill_children()
        elapsed = time.monotonic() - started
        self.timings[f"{name}-{self.counter}"] = elapsed
        if code:
            raise ValueError(f"{name}: fitter exited {code}; see invocation-{self.counter}.log")
        return read_json(output), elapsed


def within(actual, truth, tol):
    return abs(actual - truth) <= tol


def main():
    runner = Runner()
    results = {}
    errors = {}
    for name, csv in DATASETS.items():
        fixture = read_json(HERE / "fixtures" / f"{name}.json")
        try:
            first, t1 = runner.invoke(name, HERE / "fixtures" / csv, fixture["input"]["population"],
                                      fixture["input"]["sigma"])
            validate_schema(first, fixture["input"]["days"])
            second, t2 = runner.invoke(name, HERE / "fixtures" / csv, fixture["input"]["population"],
                                       fixture["input"]["sigma"])
            validate_schema(second, fixture["input"]["days"])
            results[name] = {"fixture": fixture, "first": first, "second": second, "times": [t1, t2]}
        except (ValueError, KeyError, TypeError, OSError) as error:
            errors[name] = str(error)

    def every_dataset(check):
        """Run a check on each dataset; any failure or missing run fails the criterion."""
        detail = {}
        for name in DATASETS:
            if name in errors:
                raise ValueError(f"{name}: {errors[name]}")
            detail[name] = check(results[name])
        return detail

    def strong(run):
        fx, est = run["fixture"], run["first"]["estimates"]
        truth, tol = fx["secrets"], fx["tolerances"]
        out = {}
        for k in ("beta1", "gamma"):
            err = abs(est[k] - truth[k]) / abs(truth[k])
            out[k] = err
            if err > tol["relative"][k]:
                raise ValueError(f"{k} relative error {err:.4f} exceeds {tol['relative'][k]}")
        mu = np.asarray(run["first"]["expected_reported"], dtype=float)
        ref = np.asarray(fx["expected_reported"], dtype=float)
        excess = np.abs(mu - ref) - (tol["fit_abs"] + tol["fit_rel"] * np.abs(ref))
        out["fit_max_abs"] = float(np.max(np.abs(mu - ref)))
        if np.any(excess > 0):
            raise ValueError(f"expected_reported deviates by {out['fit_max_abs']:.3f} beyond tolerance")
        return out

    def switch(run):
        fx, est = run["fixture"], run["first"]["estimates"]
        truth, tol = fx["secrets"], fx["tolerances"]
        out = {"t_switch": abs(est["t_switch"] - truth["t_switch"]),
               "beta2": abs(est["beta2"] - truth["beta2"]) / abs(truth["beta2"])}
        if out["t_switch"] > tol["absolute"]["t_switch"]:
            raise ValueError(f"t_switch error {out['t_switch']:.3f} days exceeds {tol['absolute']['t_switch']}")
        if out["beta2"] > tol["relative"]["beta2"]:
            raise ValueError(f"beta2 relative error {out['beta2']:.4f} exceeds {tol['relative']['beta2']}")
        return out

    def weak(run):
        fx, est = run["fixture"], run["first"]["estimates"]
        truth, tol = fx["secrets"], fx["tolerances"]
        out = {}
        for k in ("rho", "I0"):
            out[k] = abs(est[k] - truth[k]) / abs(truth[k])
            if out[k] > tol["relative"][k]:
                raise ValueError(f"{k} relative error {out[k]:.4f} exceeds {tol['relative'][k]}")
        return out

    def calibrated(run):
        fx, est, iv = run["fixture"], run["first"]["estimates"], run["first"]["intervals"]
        truth, tol = fx["secrets"], fx["tolerances"]
        out = {}
        for k in NAMES:
            lo, hi = iv[k]
            width = hi - lo
            bound = tol["width_absolute"][k] if k in tol["width_absolute"] else tol["width_relative"][k] * abs(truth[k])
            out[k] = {"contains": bool(lo <= truth[k] <= hi), "width": width, "bound": bound}
            if not (lo <= truth[k] <= hi):
                raise ValueError(f"{k} interval [{lo:.4g}, {hi:.4g}] excludes the true value")
            if not (lo <= est[k] <= hi):
                raise ValueError(f"{k} interval excludes its own point estimate")
            if width > bound:
                raise ValueError(f"{k} interval width {width:.4g} exceeds bound {bound:.4g}")
        return out

    def efficient(run):
        tol = run["fixture"]["tolerances"]
        out = {"runtime_s": run["times"]}
        if max(run["times"]) > tol["runtime_s"]:
            raise ValueError(f"runtime {max(run['times']):.1f}s exceeds {tol['runtime_s']}s")
        a = np.array([run["first"]["estimates"][k] for k in NAMES])
        b = np.array([run["second"]["estimates"][k] for k in NAMES])
        drift = float(np.max(np.abs(a - b) / np.maximum(np.abs(a), 1e-12)))
        out["repeat_drift"] = drift
        if drift > tol["repeat_rel"]:
            raise ValueError(f"repeated run changed estimates by relative {drift:.3g}")
        return out

    groups = {"1": strong, "2": switch, "3": weak, "4": calibrated, "5": efficient}
    outcomes, diagnostics = {}, {}
    for number, check in groups.items():
        try:
            diagnostics[number] = every_dataset(check)
            outcomes[number] = 1
        except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
            outcomes[number] = 0
            diagnostics[number] = {"error": str(error)}
    reward = int(all(outcomes.values()))
    report = {"task_id": "epidemic-intervention-recovery", "reward": reward,
              "weighted_score": sum(WEIGHTS[k] * outcomes[k] for k in outcomes) / 100,
              "per_criterion": outcomes, "full_pass": bool(reward), "weights": WEIGHTS,
              "diagnostics": diagnostics, "probe_seconds": runner.timings}
    (LOGS / "criteria.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    (LOGS / "reward.txt").write_text(str(reward))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
