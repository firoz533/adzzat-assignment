"""Run the full scenario matrix against a worker implementation, for calibration.

Usage:
  python run_matrix.py --worker ../environment/pipeline/worker.py   # naive
  python run_matrix.py --worker ../solution/worker.py                # oracle
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(TASK / "tests" / "harness"))
import harness  # noqa: E402

KEYS = ["complete", "effects_exactly_once", "consistent", "recovered", "clean_fast", "instrumented", "crashed"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--points", nargs="*", default=harness.POINTS)
    ap.add_argument("--hits", nargs="*", type=int, default=[1, 3])
    a = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="matrix-pkg-"))
    shutil.copytree(TASK / "environment" / "pipeline", root / "pipeline")
    shutil.copyfile(a.worker, root / "pipeline" / "worker.py")

    scenarios = [("clean", "")] + [(f"{p}-{k}", f"worker-1:{p}:{k}") for p in a.points for k in a.hits]
    rows = {}
    for name, crash in scenarios:
        sc = harness.Scenario(root, TASK / "tests" / "harness", crash)
        r = sc.run()
        rows[name] = r
        flags = " ".join(f"{k}={'Y' if r.get(k) else ('-' if r.get(k) is None else 'n')}" for k in KEYS)
        extra = f" orphan={r.get('orphan')} rec={r.get('orphan_recovery_s')} dup={r.get('duplicate_effects')} miss={len(r.get('missing_effects', []))}"
        print(f"{name:22s} {r['elapsed_s']:6.2f}s done={r['n_done']:2d}/{r['n_jobs']} {flags}{extra}")
        shutil.rmtree(sc.work, ignore_errors=True)
    crit = {
        "1 complete": all(rows[n]["complete"] for n in rows),
        "2 effects": all(rows[n]["effects_exactly_once"] for n in rows),
        "3 consistent": all(rows[n]["consistent"] for n in rows),
        "4 recovered": all(rows[n]["recovered"] for n in rows if n != "clean"),
        "5 clean_fast": rows["clean"]["clean_fast"],
        "gate instrumented": all(rows[n]["instrumented"] for n in rows),
    }
    print(json.dumps(crit, indent=2))
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
