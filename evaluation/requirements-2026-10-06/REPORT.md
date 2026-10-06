# Requirement-aware answers: implementation and measured results

The pending fixes and validation runs are complete. Answer quality is still
limited: **only 1/11 answerable questions was fully adequate** against the frozen
detail rubric. Passing software checks does not establish correct answers.

## Implemented changes

- Derive bounded question requirements, bind coverage to stable draft claim
  indices, and display actual missing-detail descriptions in the UI.
- Permit explicit same-aspect, cited corrections of previously accepted mistakes
  with separate review; preserve the original answer on failure or dropped facts.
- Fix conditional caller subjects, including plural `MultiDiGraphs`.
- Shorten the generator prompt and emphasize yielded values, exception predicates,
  argument forwarding, caller state updates and separate valid algorithm cases.
- Deduplicate cited review source and exclude generator completeness flags.
  Oversized reviews omit duplicate syntax tables and adapt the output reserve,
  retaining every actual cited and enclosing source line. Unfit source remains
  unverified; budget decisions are recorded.
- Add deterministic reading for unambiguous named implementations, bounded
  snapshot-aware lexical caching, actual serialized prompt estimates and stage
  timings. Generated answers are not cached.
- Require every scheduled comparison variant/repeat in scoring, preserve failures,
  and report unavailable audits separately from provider exceptions.
- Extend pending local-training packs with the requirement-aware target contract.
  No automatic target approval, adapter training or model promotion occurred.

See [implementation details](../../docs/requirement-answers.md) and the
[manual file guide](../../docs/file-guide.md).

## Final software and execution checks

- **264 automated tests passed, zero skipped**, including the real-container smoke
  test after starting the existing Colima VM. [Actual log](automated-tests.log).
- Ruff checks/formatting, frontend formatting/production build, setup shell syntax
  and Git whitespace checks passed.
- **18 supplied Docker scenarios passed**: AnyIO 11, Pluggy 7.
  [Final evidence](holdout/execution-final.json).
- Final runs preserved backend hashes, frozen question hashes and pinned snapshot
  fingerprints. Installed model digests still match the recorded settings.
  [Validation record](validation-checks.json).

The scenarios execute extracted pinned functions with controlled fixtures in
isolated containers. They are not complete repository suites or proof that model
explanations are correct. The [offline budget replay](review-budget-replay.json)
uses the exact formerly oversized Qwen draft with a stub transport: it now fits
8,192 tokens while retaining all cited/enclosing source. This proves budgeting
and source retention only, not factual accuracy.

## Final end-to-end answer results

Generator/reviewer: `qwen2.5-coder:14b`; embeddings: `nomic-embed-text:latest`.
These runs use the custom pipeline, optional LangGraph disabled, local providers,
one scheduled run per question and up to two bounded generation attempts.
[Exact settings and backend hashes](final-run-settings.json).

| Dataset | Split | Correct | Fully adequate | Covered details | Median time |
| --- | --- | --- | --- | --- | --- |
| NetworkX | Development regression | 2/3 | 0/3 | 10/17 | 269.143 s |
| Tenacity + Boltons | Development regression | 3/4 | 1/4 | 17/26 | 153.955 s |
| AnyIO + Pluggy | Fresh repository holdout | 3/4 | 0/4 | 10/28 | 174.053 s |

All **five private-runtime guards passed** without model calls. Combined results:
8/11 factually correct, 1/11 fully adequate, 37/71 details, five unsupported claims,
median 160.617 seconds. This aggregate mixes development and holdout data and is
**not an unseen generalization score**. [Combined review](final-summary.json).

Every frozen source anchor reached context in 10/11 answerable cases; LRU received
2/3 anchors. Anchor recall does not prove every needed helper or detail was supplied.

- [NetworkX outputs](networkx-final/results.json), [explicit review](networkx-final/source-review.json), [summary](networkx-final/summary.json).
- [Development outputs](behavior-final/results.json), [explicit review](behavior-final/source-review.json), [summary](behavior-final/summary.json).
- [Holdout outputs](holdout/results.json), [explicit review](holdout/source-review.json), [summary](holdout/summary.json).

NetworkX improved from **8/17 to 10/17 details**: exact BFS arguments and valid
weight=None normalization were added. Global seen updates, reverse-view semantics
and mapping keys remain omitted. Broad mutation/error statements remain wrong.
Correctness stayed 2/3 and fully adequate answers stayed 0/3. Median latency rose
from 128.185 to 269.143 seconds because easy/hard questions used two attempts;
this does **not** demonstrate an overall speed gain. [Earlier run](networkx/summary.json).

The held-out answers omit warning metadata, complete result/filtering behavior,
error chaining and callback replay details. AnyIO substitutes generic cancellation
for the exact `cancelled_caught` predicate. The Boltons path answer confuses initial
TypeError recovery with unconditional wrapping. Model coverage flags often call
these answers complete anyway. The Tenacity cause answer covers the frozen details,
although neutral uncertainty text remains. Its direct raised-exception statement is
interpreted as a direct type match alone: a root appearing again as an explicit
cause in a cycle may still match. Independent reviewers can reassess these judgments.

## Controlled local model comparison

All twelve scheduled outputs completed on three identical frozen contexts, one
attempt each, **before the final budget/prompt fixes**. Cold loading and review are
included. This differs from the final end-to-end repair runs.

| Generator | Reviewer | Correct | Fully adequate | Details | Median time | Unavailable audits |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen 14B | Qwen 14B | 1/3 | 0/3 | 3/17 | 146.506 s | 1 |
| Qwen 14B | Gemma 12B | 1/3 | 0/3 | 3/17 | 139.462 s | 1 |
| Gemma 12B | Qwen 14B | 0/3 | 0/3 | 8/17 | 188.943 s | 0 |
| Gemma 12B | Gemma 12B | 0/3 | 0/3 | 8/17 | 161.493 s | 0 |

Qwen hard drafts were withheld by the former preflight overflow. Gemma supplied
more details but incorrect collection/size/reversal statements. Changing only the
reviewer did not correct those answers. This sample does not justify a general
model ranking or automatic model promotion; the default remains unchanged.

[Raw comparison](model-comparison.json), [source review](model-comparison-source-review.json),
[scored summary](model-comparison-summary.json). Reconstruct its frozen backend
from `980c6e8` using [this patch](comparison-backend-from-980c6e8.patch): reconstruction
matched all 103 backend hashes. [Reproducibility check](comparison-reproducibility.json).

## Limits, training and reproduction

The current local model/prompt combination has not achieved reliable, fully
adequate answers. Source provenance and fallible model review are not semantic
proof. Do not present these measurements as production accuracy.

Seven new structured targets remain pending: three development and four holdout.
No training dataset was exported and no weights changed. The operational gate
requires at least 100 reviewed development examples, five development repositories,
and repository-separated validation/holdout data. That threshold alone does not
guarantee improvement. Holdouts are evaluation-only.
[Development gate](networkx-final/training-gate.json), [holdout gate](holdout/training-gate-final.json).

References and correctness labels are Codex source reviews, **not independent human
assessment**. Composite frozen details require their mechanism, not only the broad
outcome. Expected answers were excluded from generation. No tuning followed observed
holdout answers. These Python repositories do not establish equal QA quality across
all nine supported languages.

Initial harness failures and interrupted development outputs are retained for audit
and excluded from completed-run scores. Upstream notices accompany source excerpts
in [licenses/](licenses/README.md). To reproduce, restore/recreate the isolated
indexes at recorded commits, then run `run-final-validation.py` from the project
root with the recorded models. Databases, weights and runtime worktrees stay outside Git.
