#!/usr/bin/env python3
"""Portable RL data quality audit helper — stdlib only, no external services.

Reconstructed verbatim from Appendix D of the supplied "Task QA Runbook v2"
PDF (the runbook ships the script only as printed text).

Subcommands:
  merge --batch-dir DIR --output results.jsonl --html report.html
      Join verdict_*.json to batch_*.json, compute weights + flags, write JSONL + HTML.
  report --input results.jsonl --output report.html
      Re-render the HTML report from an existing results JSONL.
  recompute --input results.jsonl [--output out.jsonl]
      Recompute weight aggregates + flags in place (use after editing verdicts).

The batch files (batch_NNN.json) are written by Claude Code following the skill
(one JSON array with one task object). This helper never talks to any network
service — reports are local HTML files you open in a browser.
"""
from __future__ import annotations
import argparse, glob, html as html_lib, json, os, re
from pathlib import Path

# ---- fields we track per task ----
STR_FIELDS = ["task_id", "task_name", "source", "is_agentic", "prompt_quality_rationale",
              "problematic_rubrics", "rubric_quality_rationale", "problematic_tests", "test_quality_rationale",
              "uncovered_requirements", "has_redundancies", "score_distribution_reasonable",
              "coverage_and_balance_rationale", "is_self_contained", "missing_data", "missing_tools",
              "task_adequacy_rationale", "task_dir", "prompt_text", "rubrics_json", "test_weights_json",
              "flagged_dimensions", "error"]
INT_FIELDS = ["prompt_clarity", "criteria_completeness", "input_adequacy", "environment_adequacy",
              "num_problematic_rubrics", "num_total_rubrics", "num_problematic_tests", "num_total_tests", "num_flags"]
FLOAT_FIELDS = ["problematic_weight", "total_positive_weight", "total_absolute_weight",
                "rubric_problematic_weight", "rubric_absolute_weight"]

def _blank_row():
    r = {k: "" for k in STR_FIELDS}
    r.update({k: 0 for k in INT_FIELDS})
    r.update({k: 0.0 for k in FLOAT_FIELDS})
    return r

def _parse_rubric_scores(rubrics_json):
    scores = {}
    try:
        for i, rb in enumerate(json.loads(rubrics_json), start=1):
            rn = str(rb.get("number", rb.get("rubric_number", "")))
            if rn.startswith("R"):
                rn = rn[1:]
            if not rn:
                rn = str(i)
            scores[rn] = float(rb.get("points", rb.get("score", rb.get("weight", 0))) or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return scores

def _parse_test_weights(tw_json):
    try:
        return {k: float(v) for k, v in json.loads(tw_json).items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}

def _compute_weights(r):
    rubric_scores = _parse_rubric_scores(r["rubrics_json"]) if r["rubrics_json"] else {}
    tw = _parse_test_weights(r["test_weights_json"]) if r["test_weights_json"] else {}
    test_weights = list(tw.values()) if tw else ([3.0] * r["num_total_tests"] if r["num_total_tests"] else [])
    r["rubric_absolute_weight"] = sum(abs(w) for w in rubric_scores.values())
    r["total_positive_weight"] = sum(w for w in rubric_scores.values() if w > 0) + sum(w for w in test_weights if w > 0)
    r["total_absolute_weight"] = r["rubric_absolute_weight"] + sum(abs(w) for w in test_weights)
    prob = 0.0
    if r["problematic_rubrics"]:
        try:
            for p in json.loads(r["problematic_rubrics"]):
                prob += abs(rubric_scores.get(str(p.get("rubric_number", "")), 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    r["rubric_problematic_weight"] = prob
    tprob = 0.0
    if r["problematic_tests"]:
        try:
            for p in json.loads(r["problematic_tests"]):
                tprob += abs(tw.get(str(p.get("test_name", "")), 3.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    r["problematic_weight"] = prob + tprob

def _compute_flags(r):
    flags = []
    if r["prompt_clarity"] and r["prompt_clarity"] <= 3:
        flags.append("prompt_clarity")
    if r["total_absolute_weight"] > 0 and r["problematic_weight"] / r["total_absolute_weight"] >= 0.10:
        flags.append("problematic_rubrics_tests")
    if r["criteria_completeness"] and r["criteria_completeness"] <= 3:
        flags.append("criteria_completeness")
    if str(r["score_distribution_reasonable"]).lower() == "no":
        flags.append("score_distribution")
    if r["input_adequacy"] and r["input_adequacy"] <= 3:
        flags.append("input_adequacy")
    if r["environment_adequacy"] and r["environment_adequacy"] <= 3:
        flags.append("environment_adequacy")
    if str(r["is_self_contained"]).lower() == "no":
        flags.append("not_self_contained")
    r["num_flags"] = len(flags)
    r["flagged_dimensions"] = ", ".join(flags)

# ---- merge ----
def _norm_list_field(v):
    if isinstance(v, list):
        return json.dumps(v) if v else ""
    return v or ""

def merge(batch_dir, out_jsonl, out_html):
    verdicts = sorted(glob.glob(os.path.join(batch_dir, "verdict_*.json")))
    if not verdicts:
        raise SystemExit(f"No verdict_*.json in {batch_dir}")
    rows = []
    eval_fields = ["prompt_clarity", "is_agentic", "prompt_quality_rationale", "problematic_rubrics",
                   "rubric_quality_rationale", "criteria_completeness", "uncovered_requirements", "has_redundancies",
                   "score_distribution_reasonable", "coverage_and_balance_rationale", "is_self_contained",
                   "input_adequacy", "environment_adequacy", "missing_data", "missing_tools", "task_adequacy_rationale",
                   "problematic_tests", "test_quality_rationale", "error"]
    for vf in verdicts:
        idx = os.path.basename(vf).split("verdict_")[1].split(".")[0]
        bp = os.path.join(batch_dir, f"batch_{idx}.json")
        bmeta = {}
        if os.path.isfile(bp):
            bt = json.load(open(bp))
            bt = bt if isinstance(bt, list) else [bt]
            for bd in bt:
                rubrics = bd.get("rubrics", [])
                tc = bd.get("test_code", "") or ""
                bmeta[bd.get("task_name", "")] = {
                    "task_id": bd.get("task_id", ""), "task_name": bd.get("task_name", ""),
                    "source": bd.get("source", ""), "task_dir": bd.get("task_dir", ""),
                    "prompt_text": bd.get("prompt_text", ""),
                    "rubrics_json": json.dumps(rubrics) if isinstance(rubrics, list) else (rubrics or ""),
                    "num_total_rubrics": len(rubrics) if isinstance(rubrics, list) else 0,
                    "num_total_tests": len(re.findall(r"def test_", tc)) if tc else 0,
                    "test_weights_json": json.dumps(bd.get("test_weights", {})),
                }
        raw = json.load(open(vf))
        for v in (raw if isinstance(raw, list) else [raw]):
            if not isinstance(v, dict):
                continue
            r = _blank_row()
            name = v.get("task_name", "")
            meta = bmeta.get(name) or (next(iter(bmeta.values())) if len(bmeta) == 1 else {})
            r.update({k: meta.get(k, r[k]) for k in meta})
            for k in eval_fields:
                if k in v and v[k] is not None:
                    r[k] = v[k]
            r["problematic_rubrics"] = _norm_list_field(r["problematic_rubrics"])
            r["problematic_tests"] = _norm_list_field(r["problematic_tests"])
            for lf, cf in [("problematic_rubrics", "num_problematic_rubrics"),
                           ("problematic_tests", "num_problematic_tests")]:
                r[cf] = len(json.loads(r[lf])) if isinstance(r[lf], str) and r[lf].startswith("[") else 0
            for k in INT_FIELDS:
                try:
                    r[k] = int(r[k]) if r[k] not in ("", None) else 0
                except (TypeError, ValueError):
                    r[k] = 0
            _compute_weights(r)
            _compute_flags(r)
            rows.append(r)
    _write_jsonl(rows, out_jsonl)
    generate_html(rows, out_html)
    ok = [r for r in rows if not r["error"]]
    n = max(len(ok), 1)
    flagged = sum(1 for r in ok if r["num_flags"] > 0)
    print(f"Merged {len(rows)} results, {len(rows)-len(ok)} errors")
    print(f"Flagged: {flagged}/{len(rows)}")
    print(f"Avg clarity={sum(r['prompt_clarity'] for r in ok)/n:.1f} "
          f"completeness={sum(r['criteria_completeness'] for r in ok)/n:.1f} "
          f"input_adeq={sum(r['input_adequacy'] for r in ok)/n:.1f} "
          f"env_adeq={sum(r['environment_adequacy'] for r in ok)/n:.1f}")
    print(f"Problematic rubrics={sum(r['num_problematic_rubrics'] for r in ok)}")
    print(f"JSONL: {out_jsonl}\nHTML: {out_html}")

def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def _load_jsonl(path):
    rows = []
    for line in open(path):
        if not line.strip():
            continue
        d = _blank_row()
        raw = json.loads(line)
        d.update({k: raw.get(k, d[k]) for k in d})
        for k in INT_FIELDS:
            try:
                d[k] = int(d[k]) if d[k] not in ("", None) else 0
            except (TypeError, ValueError):
                d[k] = 0
        rows.append(d)
    return rows

# ---- HTML ----
_STYLE = """
:root{--bg:#f0f2f5;--card:#fff;--border:#e4e6eb;--text:#1c1e21;--muted:#65676b;--accent:#1877f2;--green:#31a24c;--red:#e4405f}
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;margin:0;padding:24px;background:var(--bg);color:var(--text);line-height:1.5}
.wrap{max-width:1300px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin-bottom:16px}
.card{background:var(--card);border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,.1);margin-bottom:16px;padding:16px 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.tile{background:var(--bg);padding:14px;border-radius:8px;text-align:center}.tile .n{font-size:22px;font-weight:700}.tile .l{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}
table{border-collapse:collapse;width:100%;font-size:13px}thead th{background:#f8f9fa;border-bottom:2px solid var(--border);padding:9px 11px;text-align:left;font-size:11px;text-transform:uppercase;color:var(--muted)}
tbody td{padding:9px 11px;border-bottom:1px solid var(--border);vertical-align:middle}tr[data-i]{cursor:pointer}tr[data-i]:hover{background:#f5f7fa}tr.flag{background:#fff5f5}tr.flag:hover{background:#fee}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:100;justify-content:center;align-items:flex-start;padding:40px 20px;overflow-y:auto}.modal.open{display:flex}
.box{background:#fff;border-radius:12px;max-width:900px;width:100%;padding:0 0 16px}.mh{display:flex;justify-content:space-between;padding:16px 22px;border-bottom:1px solid var(--border)}.mh h2{margin:0;font-size:16px}.x{cursor:pointer;font-size:22px;color:var(--muted);border:none;background:none}
.mc{padding:16px 22px;max-height:75vh;overflow-y:auto}.sec{margin-bottom:12px}.st{font-size:12px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:5px}
.rat{background:#fafbfc;border:1px solid var(--border);border-radius:6px;padding:9px 11px;font-size:12px;color:#444;white-space:pre-wrap}pre{white-space:pre-wrap;background:#fafbfc;border:1px solid var(--border);border-radius:6px;padding:10px;font-size:12px;max-height:300px;overflow:auto}
.issue{border:1px solid var(--border);border-radius:6px;margin-bottom:7px}.ih{padding:7px 11px;background:#fafbfc;border-bottom:1px solid var(--border);font-size:12px}.tag{background:#fce8e6;color:#c5221f;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:600;text-transform:uppercase;margin-right:7px}.ir{padding:7px 11px;font-size:12px;color:#555}
.f{display:flex;gap:8px;margin-bottom:12px}.fb{padding:6px 14px;border-radius:16px;border:1px solid var(--border);background:#fff;font-size:12px;cursor:pointer}.fb.on{background:var(--accent);color:#fff}
"""

def _color(s):
    return "#27ae60" if s >= 4 else ("#f39c12" if s >= 3 else "#e74c3c")

def _cards(pr_json, kind):
    out = []
    try:
        items = json.loads(pr_json) if pr_json else []
    except json.JSONDecodeError:
        items = []
    for p in items:
        tag = html_lib.escape(str(p.get("issue", p.get("issue_type", ""))))
        ident = f"R{p.get('rubric_number','?')}" if kind == "rubric" else html_lib.escape(str(p.get("test_name", "?")))
        crit = html_lib.escape(str(p.get("criterion", "")))
        rat = html_lib.escape(str(p.get("rationale", "")))
        out.append(f'<div class="issue"><div class="ih"><span class="tag">{tag}</span><b>{ident}</b> {crit}</div>'
                   f'<div class="ir">{rat}</div></div>')
    return "".join(out)

def generate_html(rows, out_html):
    total = len(rows)
    ok = [r for r in rows if not r["error"]]
    n = max(len(ok), 1)
    flagged = sum(1 for r in ok if r["num_flags"] > 0)
    avg_c = sum(r["prompt_clarity"] for r in ok) / n
    avg_k = sum(r["criteria_completeness"] for r in ok) / n
    tpr = sum(r["num_problematic_rubrics"] for r in ok)
    p = ['<!doctype html><html><head><meta charset="utf-8"><title>RL Data Quality Audit</title>',
         f"<style>{_STYLE}</style></head><body><div class='wrap'>"]
    p.append(f"<div class='card'><h1>RL Data Quality Audit</h1><div class='sub'>{flagged} flagged / {total} tasks "
             f"&bull; click a row for details</div>"
             f"<div class='tiles'>"
             f"<div class='tile'><div class='n'>{total}</div><div class='l'>Tasks</div></div>"
             f"<div class='tile'><div class='n' style='color:{'#e4405f' if flagged else '#31a24c'}'>{flagged}</div>"
             f"<div class='l'>Flagged</div></div>"
             f"<div class='tile'><div class='n' style='color:{_color(avg_c)}'>{avg_c:.1f}</div><div class='l'>Avg Clarity</div></div>"
             f"<div class='tile'><div class='n' style='color:{'#e4405f' if tpr else '#31a24c'}'>{tpr}</div>"
             f"<div class='l'>Prob. Rubrics</div></div>"
             f"<div class='tile'><div class='n' style='color:{_color(avg_k)}'>{avg_k:.1f}</div><div class='l'>Avg Completeness</div></div>"
             f"</div></div>")
    p.append(f"<div class='card'><div class='f'><button class='fb' data-f='all'>All ({total})</button>"
             f"<button class='fb' data-f='flag'>Flagged ({flagged})</button>"
             f"<button class='fb' data-f='clean'>Clean ({total-flagged})</button></div>"
             "<table><thead><tr><th>Task</th><th>Source</th><th>Clarity</th><th>Prob. Rubrics</th>"
             "<th>Completeness</th><th>Score Dist</th><th>Self-Contained</th><th>Input</th><th>Env</th></tr></thead><tbody>")
    details = []
    for i, r in enumerate(rows):
        fl = r["num_flags"] > 0
        p.append(f"<tr data-i='{i}' class='{'flag' if fl else ''}'>"
                 f"<td><b>{html_lib.escape(r['task_name'])}</b></td><td>{html_lib.escape(r['source'])}</td>"
                 f"<td style='color:{_color(r['prompt_clarity'])}'><b>{r['prompt_clarity']}</b></td>"
                 f"<td style='color:{'#e4405f' if r['num_problematic_rubrics'] else '#31a24c'}'>"
                 f"{r['num_problematic_rubrics']}/{r['num_total_rubrics']}</td>"
                 f"<td style='color:{_color(r['criteria_completeness'])}'><b>{r['criteria_completeness']}</b></td>"
                 f"<td>{r['score_distribution_reasonable']}</td><td>{r['is_self_contained']}</td>"
                 f"<td style='color:{_color(r['input_adequacy'])}'>{r['input_adequacy']}</td>"
                 f"<td style='color:{_color(r['environment_adequacy'])}'>{r['environment_adequacy']}</td></tr>")
        d = [f"<div class='sec'><div class='st'>Prompt</div><pre>{html_lib.escape(r['prompt_text'][:6000])}</pre></div>",
             f"<div class='sec'><div class='st'>Prompt Quality</div><div class='rat'>"
             f"{html_lib.escape(r['prompt_quality_rationale'])}</div></div>",
             "<div class='sec'><div class='st'>Rubric Accuracy</div>" + _cards(r["problematic_rubrics"], "rubric")
             + f"<div class='rat'>{html_lib.escape(r['rubric_quality_rationale'])}</div></div>",
             "<div class='sec'><div class='st'>Test Correctness</div>" + _cards(r["problematic_tests"], "test")
             + f"<div class='rat'>{html_lib.escape(r['test_quality_rationale'])}</div></div>",
             f"<div class='sec'><div class='st'>Coverage &amp; Balance</div><div class='rat'>"
             f"{html_lib.escape(r['coverage_and_balance_rationale'])}</div></div>",
             f"<div class='sec'><div class='st'>Task Adequacy</div><div class='rat'>"
             f"{html_lib.escape(r['task_adequacy_rationale'])}</div></div>"]
        details.append(f"<div id='d{i}' style='display:none'>{''.join(d)}</div>")
    p.append("</tbody></table></div>")
    p.append("<div class='modal' id='m'><div class='box'><div class='mh'><h2 id='mt'></h2>"
             "<button class='x' onclick=\"document.getElementById('m').classList.remove('open')\">&times;</button></div>"
             "<div class='mc' id='mb'></div></div></div>")
    p.append("<div style='display:none'>" + "".join(details) + "</div>")
    p.append("""<script>
document.querySelectorAll('tr[data-i]').forEach(function(t){t.onclick=function(){var i=this.dataset.i;document.getElementById('mt').textContent=this.cells[0].innerText;document.getElementById('mb').innerHTML=document.getElementById('d'+i).innerHTML;document.getElementById('m').classList.add('open')}});
document.getElementById('m').onclick=function(e){if(e.target===this)this.classList.remove('open')};
document.querySelectorAll('.fb').forEach(function(b){b.onclick=function(){document.querySelectorAll('.fb').forEach(x=>x.classList.remove('on'));this.classList.add('on');var f=this.dataset.f;document.querySelectorAll('tr[data-i]').forEach(function(r){r.style.display=(f==='all'||(f==='flag')===r.classList.contains('flag'))?'':'none'})}});
</script></div></body></html>""")
    Path(out_html).write_text("".join(p))

def recompute(inp, out):
    rows = _load_jsonl(inp)
    for r in rows:
        _compute_weights(r)
        _compute_flags(r)
    _write_jsonl(rows, out or inp)
    print(f"Recomputed {len(rows)} rows -> {out or inp}")

def main():
    ap = argparse.ArgumentParser(description="Portable RL data quality audit helper (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--batch-dir", required=True)
    m.add_argument("--output", required=True)
    m.add_argument("--html", required=True)
    r = sub.add_parser("report")
    r.add_argument("--input", required=True)
    r.add_argument("--output", required=True)
    rc = sub.add_parser("recompute")
    rc.add_argument("--input", required=True)
    rc.add_argument("--output", default=None)
    a = ap.parse_args()
    if a.cmd == "merge":
        merge(a.batch_dir, a.output, a.html)
    elif a.cmd == "report":
        generate_html(_load_jsonl(a.input), a.output)
        print(f"HTML: {a.output}")
    elif a.cmd == "recompute":
        recompute(a.input, a.output)

if __name__ == "__main__":
    main()
