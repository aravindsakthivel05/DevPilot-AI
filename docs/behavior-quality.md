# Source reasoning and local quality evaluation

DevPilot now attaches a bounded Python syntax table to selected source definitions
before asking the model for prose. Each row retains the original statement lines,
scope and enclosing conditions, including negated branches, loops, exception
handlers and finally blocks. Rows whose required source lines are missing are
omitted. Other languages still use their source excerpts and existing parsers;
Python syntax extraction does not imply full multilingual control-flow analysis.

The table is a reading aid. It does not evaluate expressions, resolve dynamic
dispatch, prove reachability or establish runtime values. Statement order is
textual order, not a claim that every statement executes. Early return, exceptions
and nested scopes still matter. The same answer/citation policy remains in place.

Question obligations identify requested conditions, ordering, returns, errors,
cleanup and state changes. Missing named definitions get priority in bounded
follow-up reads. `semantic_coverage: unverified` is intentional: finding a symbol
does not establish an adequate answer. The fallible reviewer still assesses
completeness separately from whether individual claims have supporting source.

## Files

| File | Purpose |
|---|---|
| `backend/rag/behavior.py` | Deterministic Python syntax tables |
| `backend/rag/obligations.py` | Per-question reading checklist |
| `backend/rag/investigation.py` | Focused reads for missing named definitions |
| `scripts/compare_local_models.py` | Frozen-context generator/reviewer comparisons |
| `scripts/run_behavior_checks.py` | Supplied checks in network-disabled Docker containers |
| `scripts/prepare_grounded_training.py` | Review packs, correction pairs and repository-separated export |
| `scripts/train_grounded_adapter.py` | Gated local MLX QLoRA candidate training |
| `scripts/evaluate_grounded_adapter.py` | Held-out base/adapter generations; scores await source review |

## Reproduce the evaluation

Use the same `DEVPILOT_DATA` for indexing, answer runs, comparisons and execution.
The evaluation database is separate from the app database. Source-authored frozen
questions and references are in `evaluation/behavior-2026-10-05/questions.json`.
They are Codex-authored, not independent human labels. Tenacity and Boltons remain
holdout repositories for training. Actual run results and review are in that
directory; do not infer answer quality from citation acceptance or test pass counts.

```sh
export PYTHONPATH=.
export DEVPILOT_DATA=.devpilot/behavior-2026-10-05
export DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1
export DEVPILOT_LLM_MODEL=qwen2.5-coder:14b
export DEVPILOT_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
export DEVPILOT_EMBEDDING_MODEL=nomic-embed-text:latest

# A new output path is required to preserve recorded evidence.
.venv/bin/python -m scripts.run_behavior_checks \
  --manifest evaluation/behavior-2026-10-05/snapshots.json \
  --tests evaluation/behavior-2026-10-05/behavior-tests \
  --output /tmp/devpilot-behavior-run.json

# Both models must already be installed. KEEP_ALIVE=0 prevents simultaneous
# generator/reviewer residency on a memory-constrained Mac; reload time is included.
DEVPILOT_OLLAMA_KEEP_ALIVE=0 .venv/bin/python -m scripts.compare_local_models \
  qwen2.5-coder:14b gemma3:12b \
  --reviewers qwen2.5-coder:14b gemma3:12b --cases 3 --repeats 1 --investigate \
  --dataset evaluation/behavior-2026-10-05/comparison-cases.jsonl \
  --manifest evaluation/behavior-2026-10-05/snapshots.json \
  --output /tmp/devpilot-model-comparison.json
```

Comparisons save after every case and can resume with `--resume`. Resume rejects
changes to code, source contexts, model digests, questions or recorded settings.
This is a one-attempt generation comparison, separate from the end-to-end retry
policy. Cross-model review is still fallible. Expected answers are withheld from
generation. Judge correctness, required-detail coverage, unsupported claims,
abstention and latency separately; keep all failed attempts in the denominator.

## Local training gate

Fresh test outputs do not update model weights. Review packs retain source,
snapshot and reviewer provenance. Structured targets remain pending until reviewed.
Correction pairs require an explicitly reviewed correction reason in addition to
target review. An incorrect answer can be a correction input; it is never the
supervised target. Duplicate IDs/questions cannot inflate the readiness gate.

The default export gate is 100 reviewed development examples from at least five
repositories, plus reviewed holdouts from at least two different repositories.
An entire development repository becomes validation data. Holdouts never enter
training. The training launcher checks hashes, actual counts and repository
separation and rejects examples that would be silently truncated. It uses only an
existing local checkpoint and writes an experimental adapter; no upload, fusion,
default-model change or automatic promotion occurs.

```sh
.venv/bin/python -m scripts.prepare_grounded_training export \
  path/to/reviewed-pack.jsonl --output .devpilot/grounded-export

# Run only after export reports training_ready=true. Unload Ollama before MLX.
.venv/bin/python -m scripts.train_grounded_adapter \
  --data .devpilot/grounded-export \
  --model .devpilot/models/Qwen2.5-Coder-7B-Instruct-4bit \
  --adapter .devpilot/adapters/grounded-candidate

# Run base and candidate separately with different output paths.
.devpilot/mlx-training-venv/bin/python -m scripts.evaluate_grounded_adapter \
  --data .devpilot/grounded-export \
  --model .devpilot/models/Qwen2.5-Coder-7B-Instruct-4bit \
  --output evaluation/grounded-base.json
```

For the candidate evaluation, add `--adapter .devpilot/adapters/grounded-candidate`.
Both runs must have the same dataset and prompt hashes. Source-review outputs
before considering a model change; lower training loss is insufficient. The prior
tree-only adapter regressed and remains unpromoted. See [local training](local-training.md).

The local training implementation follows the official
[MLX-LM LoRA documentation](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md).
The alternative-model download uses the official
[Ollama Gemma 3 12B package](https://ollama.com/library/gemma3:12b).
