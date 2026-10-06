# Fresh Marshmallow holdout

This directory records an evaluation of public `marshmallow-code/marshmallow`, pinned to `d08471b17880c62b789971ada638707a11d3f8d4`, using DevPilot commit `a329ed0f2f3c8d4ee9e6ba22387f25197ace90b2`.

Three source-authored questions (easy, medium, hard) request 20 explicit details. A fourth question checks abstention for unknowable private production credentials. The questions and labels were frozen before model output. The expected answers and labels are withheld from generation. There is one attempt through the normal pipeline per question, including its existing bounded repair flow; this is not a repeated-run estimate.

- `questions.json`: frozen questions, required details, and pinned source anchors.
- `provenance.json`, `run-settings.json`: project/repository commits, question and backend hashes, local model identities and settings.
- `snapshots.json`: repository indexing coverage, limitations, embedding readiness and timings.
- `results.json`: actual final answers, retrieval evaluations, evidence, claim audits, repairs and timings.
- `source-review.json`, `summary.json`, `REPORT.md`: explicit source review and final results, added after completion.
- `marshmallow-issues.json`: static-analysis candidates; not confirmed defects.
- `upstream-LICENSE.txt`: unmodified upstream MIT license notice.
- `index.log`, `run.log`: stage logs.

To rerun, install the existing project dependencies and local models, clone the pinned repository to `.devpilot/marshmallow-2026-10-06-checkouts/marshmallow`, and run `.venv/bin/python evaluation/marshmallow-2026-10-06/run-evaluation.py`. The driver uses an isolated database. To obtain a fresh repeat rather than resume, move the old output JSON and evaluation database out of the way while retaining the frozen questions. A source review must be performed for each fresh run; old review labels must not be reused as new output labels.

This is a source-reviewed answer-quality test, not a run of Marshmallow's upstream suite. Target code was not executed, model weights were not changed, examples were not approved for training, and no project implementation was tuned on this holdout. Codex authored the labels and review; this is not independent human evaluation. One Python repository and three questions cannot establish general correctness.
