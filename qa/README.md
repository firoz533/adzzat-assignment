# Pre-rollout QA

This folder applies the supplied "Task QA Runbook v2" to both tasks.

- `dq_audit.py` is Appendix D of the runbook, reconstructed from the PDF text
  because the script itself was not bundled. Logic and output schema are
  unchanged; only line wrapping introduced by the PDF was repaired.
- `build_batches.py` writes one `batch_NNN.json` review record per task in
  the schema of the runbook's SKILL.md section 1: prompt text, grading
  criteria normalised to number, points and criterion, grader source, test
  shell source, and the paths not visible to the agent at runtime.
- `out/verdict_NNN.json` are the reviews against the runbook's
  `eval_guide.md`, one per task, in its exact output schema.
- `out/results.jsonl` and `out/report.html` are produced by
  `python dq_audit.py merge --batch-dir out --output out/results.jsonl --html out/report.html`.

Result: 0 of 2 tasks flagged; clarity 5.0, completeness 4.5, input and
environment adequacy 5.0, no problematic rubrics or tests.

Caveat: the reviews were written by the task author, not by an independent
reviewer or subagent as the runbook prescribes, so they should be treated as
a self-audit. The two residual limitations found are recorded in the verdict
rationales and in each task's `author/calibration.md`: interval containment
in Task 1 is a probabilistic event mitigated by seed selection, and the
fencing-token race in Task 2 is not forced by the current scenario set.

Post-rollout QA (`dq_post.py`, Appendix E) runs on rollout results and has
not been executed yet because no model rollouts have been run.
