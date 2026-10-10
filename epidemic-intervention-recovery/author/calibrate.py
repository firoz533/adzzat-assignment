"""Calibration runner: measure oracle and naive-baseline error across noise seeds.

For each secret set and seed it generates a dataset, runs the given fitter,
and reports absolute/relative errors, interval containment and widths, and
runtime. Output feeds the tolerances in the fixtures and author/calibration.md.

Usage:
  python calibrate.py --fitter ../solution/fit.py --seeds 11 12 13 14 15
  python calibrate.py --fitter baseline_naive.py --seeds 11
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent / "tests"
NAMES = ["beta1", "beta2", "gamma", "t_switch", "rho", "I0"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fitter", type=Path, required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--secrets", nargs="+", default=["secrets_visible.json", "secrets_hidden.json"])
    args = ap.parse_args()

    summary = {}
    for secret in args.secrets:
        spec = json.loads((HERE / secret).read_text())
        truth = spec["params"]
        rows = []
        for seed in args.seeds:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                subprocess.run([sys.executable, str(TESTS / "generate.py"), "--secrets", str(HERE / secret),
                                "--seed", str(seed), "--csv", str(tmp / "cases.csv"),
                                "--fixture", str(tmp / "fx.json")], check=True, capture_output=True)
                fx = json.loads((tmp / "fx.json").read_text())
                t0 = time.perf_counter()
                proc = subprocess.run([sys.executable, str(args.fitter), "--input", str(tmp / "cases.csv"),
                                       "--output", str(tmp / "out.json"), "--population", str(spec["population"]),
                                       "--sigma", str(spec["sigma"])], capture_output=True, text=True)
                dt = time.perf_counter() - t0
                if proc.returncode:
                    print(f"[{secret} seed {seed}] fitter failed:\n{proc.stderr[-2000:]}")
                    continue
                out = json.loads((tmp / "out.json").read_text())
                est, iv = out["estimates"], out["intervals"]
                mu_true = np.array(fx["expected_reported"])
                mu_hat = np.array(out["expected_reported"])
                row = {"seed": seed, "runtime_s": round(dt, 1),
                       "fit_max_abs": float(np.max(np.abs(mu_hat - mu_true))),
                       "fit_max_rel": float(np.max(np.abs(mu_hat - mu_true) / (np.abs(mu_true) + 5.0)))}
                for k in NAMES:
                    err = est[k] - truth[k]
                    rel = abs(err) / abs(truth[k])
                    lo, hi = iv[k]
                    row[k] = {"est": round(est[k], 5), "abs_err": round(err, 5), "rel_err": round(rel, 5),
                              "contains": bool(lo <= truth[k] <= hi), "width": round(hi - lo, 5),
                              "width_rel": round((hi - lo) / abs(truth[k]), 5)}
                rows.append(row)
                print(f"[{secret} seed {seed}] {dt:5.1f}s  " + "  ".join(
                    f"{k}={row[k]['est']:.4g}({'ok' if row[k]['contains'] else 'MISS'})" for k in NAMES))
        if rows:
            worst = {k: {"max_rel_err": max(r[k]["rel_err"] for r in rows),
                         "max_abs_err": max(abs(r[k]["abs_err"]) for r in rows),
                         "max_width_rel": max(r[k]["width_rel"] for r in rows),
                         "max_width_abs": max(r[k]["width"] for r in rows),
                         "all_contain": all(r[k]["contains"] for r in rows)} for k in NAMES}
            worst["fit_max_rel"] = max(r["fit_max_rel"] for r in rows)
            worst["fit_max_abs"] = max(r["fit_max_abs"] for r in rows)
            worst["max_runtime_s"] = max(r["runtime_s"] for r in rows)
            summary[secret] = {"rows": rows, "worst": worst}
            print(f"== {secret} worst-case ==")
            for k in NAMES:
                w = worst[k]
                print(f"  {k:9s} max_rel_err={w['max_rel_err']:.4f} max_abs_err={w['max_abs_err']:.4f} "
                      f"max_width_rel={w['max_width_rel']:.4f} contain_all={w['all_contain']}")
            print(f"  fit max_rel={worst['fit_max_rel']:.4f} max_abs={worst['fit_max_abs']:.2f} runtime<={worst['max_runtime_s']}s")
    out = HERE / f"calibration_{args.fitter.stem}.json"
    out.write_text(json.dumps(summary, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
