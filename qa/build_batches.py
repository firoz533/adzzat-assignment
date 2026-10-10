"""Build batch_NNN.json review records for the pre-rollout QA skill (runbook section 1).

Each record carries the agent prompt, the grading criteria normalised to
{number, points, criterion}, the grader source, the test shell source and the
paths that are not visible to the agent at runtime.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "out"

TASKS = [
    {
        "dir": "epidemic-intervention-recovery",
        "rubrics": [
            (20, "Criterion 1, both datasets: beta1 and gamma within 8 percent relative error of the generating values; every day's fitted expected reported count within 5 + 10 percent of the noiseless true mean."),
            (25, "Criterion 2, both datasets: t_switch within 0.75 day of the generating value (41.3 visible, 66.4 hidden); beta2 within 15 percent relative error."),
            (25, "Criterion 3, both datasets: rho and I0 within 25 percent relative error of the generating values."),
            (20, "Criterion 4, both datasets: every reported 95 percent interval contains the generating value and the point estimate, and its width does not exceed 25 percent (beta1), 60 percent (beta2), 50 percent (gamma), 1.5 days (t_switch), 90 percent (rho), 90 percent (I0) of the generating value."),
            (10, "Criterion 5, both datasets: each of two runs finishes within 240 seconds on two cores; the second run reproduces the first estimates to relative 1e-6; output JSON is well formed and finite."),
        ],
        "ignore": ["tests", "solution", "author"],
    },
    {
        "dir": "crash-safe-job-pipeline",
        "rubrics": [
            (20, "Criterion 1, all 15 scenarios: every one of the 40 jobs is status done with exactly one outputs row, no job queued or running, every worker exited 0 or 137, scenario not timed out."),
            (25, "Criterion 2, all 15 scenarios: the effect service's deliveries table has exactly one row per job id, no job with zero or two deliveries."),
            (20, "Criterion 3, all 15 scenarios: customer_totals equals the per-customer sum and count over outputs; OUTPUT_DIR holds exactly one <job_id>.json per output row whose amount equals the row."),
            (20, "Criterion 4, 14 crash scenarios: the job held by the killed worker at the moment of the kill is done within 15 seconds of the kill; the scenario finishes within 60 seconds."),
            (15, "Criterion 5, clean scenario: all jobs done within 30 seconds with three workers and no crashes."),
        ],
        "ignore": ["tests", "solution", "author"],
    },
]


def main():
    OUT.mkdir(exist_ok=True)
    for i, t in enumerate(TASKS):
        d = ROOT / t["dir"]
        record = {
            "task_id": f"adzzat/{t['dir']}",
            "task_name": t["dir"],
            "task_dir": str(d),
            "prompt_text": (d / "instruction.md").read_text(encoding="utf-8"),
            "rubrics": [{"number": n + 1, "points": pts, "criterion": c} for n, (pts, c) in enumerate(t["rubrics"])],
            "test_code": (d / "tests" / "grade.py").read_text(encoding="utf-8"),
            "test_sh": (d / "tests" / "test.sh").read_text(encoding="utf-8"),
            "test_weights": {},
            "ignore_paths": [str(d / p) for p in t["ignore"]],
        }
        (OUT / f"batch_{i:03d}.json").write_text(json.dumps([record], indent=2), encoding="utf-8")
        print("wrote", OUT / f"batch_{i:03d}.json")


if __name__ == "__main__":
    main()
