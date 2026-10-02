# Public repository tier test

**Run date:** 2026-10-02  
**Model:** local Ollama `qwen2.5-coder:7b`  
**Test:** one repository-analysis question per tier, run through DevPilot's standard Quick path
and its LangGraph Deep path. Both used the same pinned local snapshot and model. The cases and
full outputs are in [`public-repository-tier-questions.jsonl`](public-repository-tier-questions.jsonl)
and [`public-repository-tier-test.json`](public-repository-tier-test.json).

These are representative public projects, not a statistically designed benchmark. Django and
PyTorch's codebases and question scope are tested locally using pinned snapshots; no repository
test suites or application code were executed.

| Tier | Repository and pinned scope | Indexed files / symbols | Expected symbols found in top 8 | Result |
| --- | --- | ---: | ---: | --- |
| Medium | [FastAPI](https://github.com/fastapi/fastapi), full indexed repository | 2,879 / 8,871 | 1/2 (50%) | Found `FastAPI.openapi`, missed `get_openapi`. The answer described delegation, but did not establish where route schemas are actually assembled. |
| Complex | [Django](https://github.com/django/django), `django/` package only | 1,114 / 12,728 | 3/3 (100%) | Found the expected QuerySet and SQL compiler methods. The answer's `[4]` citation points to `RawQuerySet._fetch_all`, not the `QuerySet._fetch_all` it names, so the claim is not properly supported by that citation. |
| Very complex | [PyTorch](https://github.com/pytorch/pytorch), `torch/` scope only | 2,597 / 60,945 | 2/4 (50%) | Found `_call_impl` and forward pre-hook registration, but missed `_wrapped_call_impl` and forward-hook registration. The answer stopped after describing pre-hooks; it did not answer how `forward()` and post-hooks are handled. |
| **Overall** | **3 questions** | | **6/9 (66.7%)** | **No complete, fully supported answer across all requested details.** |

Quick and Deep returned the same retrieved symbols and the same generated answer for all three
questions. Each Deep run used one retrieval pass, so LangGraph did not add evidence for these
cases. The per-run timings in the JSON are single measurements and should not be treated as a
latency benchmark.

All six generated responses passed the current citation-format checks. That check only verifies
citation structure and allowed citation numbers; it does not establish that a citation entails
the attached claim. The Django mismatch and the incomplete PyTorch response show why manual
source review remains necessary. Semantic embeddings were not active for this run, so retrieval
used the available lexical/graph paths.

The repeatable runner is [`scripts/test_public_repository_tiers.py`](../scripts/test_public_repository_tiers.py).
With Ollama running and DevPilot configured for the local Qwen model, rerun it from the project
root:

```sh
env DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
  DEVPILOT_LLM_MODEL=qwen2.5-coder:7b \
  .venv/bin/python -m scripts.test_public_repository_tiers \
  --output evaluation/public-repository-tier-rerun.json
```
