# October 3 accuracy checkpoint

Read [the report](../../docs/accuracy-2026-10-03.md) first. `manifest.json` records implementation hashes, runtime versions, checks and open limits.

- `expanded-retrieval-final.json`, `workflow-final.json`: fixed retrieval measurements; not factual-answer scores.
- `public-three-final.json` and its source review: repeated FastAPI/Django/PyTorch checkpoint before the final returned-call fix.
- `new-holdout-model-comparison-final.json`, `model-source-review.json`: frozen Jinja/Gson model comparison before final Pydantic development fixes.
- `pydantic-serialization-final.json`, `serialization-source-review.json`, `ui-serialization-final.json`: final affected-question validation, including actual API/browser output.
- `runtime-final.json`: disposable local provider/embedding smoke test.
- `guided-python-fixture.json`: positive four-stage synthetic repair; the Java regression rejection is in diagnostics.
- `training-gate.json`, `grounded-training-review-pack.jsonl`: export remains closed; targets are unreviewed.
- `pytest-final.txt`, `lint-final.txt`, `format-final.txt`, `frontend-build-final.txt`: checks.
- `diagnostics/`: prior failures and intermediate checkpoints retained for provenance.

Source judgments are Codex reviews, not independent human grades. No new model weights were trained. Models still make errors.
