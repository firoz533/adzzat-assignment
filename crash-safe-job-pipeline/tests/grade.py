"""Grade the submitted pipeline package under crash injection.

The submitted package is copied to a scratch location readable by UID 65534
and every worker process runs as that user with the grader's own chaos and
effects modules ahead of it on PYTHONPATH. Scenarios kill worker-1 at each
instrumentation point on its first and third hit and restart it; one scenario
has no crashes. Writes /logs/verifier/reward.txt and criteria.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "harness"))
import harness  # noqa: E402

LOGS = Path("/logs/verifier")
SUBMISSION = Path("/app/submission/pipeline")
WEIGHTS = {"1": 20, "2": 25, "3": 20, "4": 20, "5": 15}
UID = 65534


def stage_submission():
    if not (SUBMISSION / "__init__.py").is_file() or not (SUBMISSION / "worker.py").is_file():
        raise ValueError("Submitted package /app/submission/pipeline is missing or incomplete")
    root = Path(tempfile.mkdtemp(prefix="pkg-"))
    os.chmod(root, 0o755)
    shutil.copytree(SUBMISSION, root / "pipeline", symlinks=False)
    for p in (root / "pipeline").rglob("*"):
        if p.is_symlink():
            raise ValueError("Symbolic links are not allowed in the submission")
        os.chmod(p, 0o755 if p.is_dir() else 0o644)
    os.chmod(root / "pipeline", 0o755)
    size = sum(p.stat().st_size for p in (root / "pipeline").rglob("*") if p.is_file())
    if size > 5_000_000:
        raise ValueError("Submission exceeds 5 MB")
    # The verifier's own runtime modules, world-readable, ahead of the package on PYTHONPATH.
    runtime = root / "runtime"
    runtime.mkdir(mode=0o755)
    for name in ("chaos.py", "effects.py"):
        shutil.copyfile(Path(__file__).resolve().parent / "harness" / name, runtime / name)
        os.chmod(runtime / name, 0o644)
    return root


def main():
    LOGS.mkdir(exist_ok=True, parents=True)
    scenarios = [("clean", "")]
    for point in harness.POINTS:
        for k in (1, 3):
            scenarios.append((f"{point}-{k}", f"worker-1:{point}:{k}"))

    results, fatal = {}, None
    try:
        root = stage_submission()
        for name, crash in scenarios:
            work = Path(tempfile.mkdtemp(prefix=f"sc-{name}-"))
            os.chmod(work, 0o755)
            os.chown(work, UID, UID)
            sc = harness.Scenario(root, root / "runtime", crash, workdir=work, user=UID)
            try:
                results[name] = sc.run()
            except Exception as error:  # noqa: BLE001 - any harness failure is a scenario failure
                results[name] = {"error": f"{type(error).__name__}: {error}"}
            for log in sc.logs.glob("*.log"):
                shutil.copyfile(log, LOGS / f"{name}-{log.name}")
            harness.kill_user_processes(UID)
    except (ValueError, OSError) as error:
        fatal = str(error)

    crash_names = [n for n, c in scenarios if c]

    def every(names, key, expect=True):
        bad = [n for n in names if results.get(n, {}).get(key) is not expect]
        if bad:
            raise ValueError(f"{key} failed in: {', '.join(bad)}")

    def gate():
        if fatal:
            raise ValueError(fatal)
        missing = [n for n, _ in scenarios if "error" in results.get(n, {"error": "missing"})]
        if missing:
            raise ValueError("scenario errors: " + "; ".join(f"{n}: {results[n]['error']}" for n in missing))
        every([n for n, _ in scenarios], "instrumented")
        every(crash_names, "crashed")

    def c1():
        gate(); every([n for n, _ in scenarios], "complete")
    def c2():
        gate(); every([n for n, _ in scenarios], "effects_exactly_once")
    def c3():
        gate(); every([n for n, _ in scenarios], "consistent")
    def c4():
        gate(); every(crash_names, "recovered")
    def c5():
        gate(); every(["clean"], "clean_fast")

    outcomes, diagnostics = {}, {}
    for number, check in {"1": c1, "2": c2, "3": c3, "4": c4, "5": c5}.items():
        try:
            check()
            outcomes[number] = 1
            diagnostics[number] = "ok"
        except (ValueError, KeyError, TypeError) as error:
            outcomes[number] = 0
            diagnostics[number] = str(error)
    reward = int(all(outcomes.values()))
    report = {"task_id": "crash-safe-job-pipeline", "reward": reward,
              "weighted_score": sum(WEIGHTS[k] * outcomes[k] for k in outcomes) / 100,
              "per_criterion": outcomes, "full_pass": bool(reward), "weights": WEIGHTS,
              "diagnostics": diagnostics, "scenarios": results}
    (LOGS / "criteria.json").write_text(json.dumps(report, indent=2, allow_nan=False, default=str))
    (LOGS / "reward.txt").write_text(str(reward))
    print(json.dumps({k: v for k, v in report.items() if k != "scenarios"}, indent=2))


if __name__ == "__main__":
    main()
