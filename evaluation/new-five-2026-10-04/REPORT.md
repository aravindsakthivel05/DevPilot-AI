# Five fresh repositories — DevPilot evaluation

Date: 2026-10-04. Model: `qwen2.5-coder:14b`; embeddings: `nomic-embed-text:latest`.

Three of five repositories indexed. Of nine answerable questions attempted, six produced accepted model answers and three produced no validated explanation. Source comparison found no complete, fully accurate and supported answer among these nine; some answers contain useful correct parts. Six more answerable questions were blocked by indexing. The three live-state abstention checks executed passed; two were blocked. These findings do not establish production readiness.

## Scope and method

This evaluates DevPilot indexing, embeddings, retrieval, bounded graph traversal, source-grounded answers and live-state abstention. It does not execute upstream project tests, apply patches, or train model weights. Repositories were shallow-cloned at the commits below into ignored local directories; the evaluation used an isolated database. Backend hashes remained unchanged throughout the run. Questions and expected source anchors were authored from source before model generation and not supplied as answer hints. Codex reviewed answers against pinned source and cited excerpts; this is not an independent human-labelled benchmark. Each question ran once, without tuning against the results.

## Indexing

| Repository | Pinned commit | Status | Files | Symbols | Edges | Index + embeddings (s) |
|---|---|---|---:|---:|---:|---:|
| [axios](https://github.com/axios/axios) | `c4303eeb601d` | ready | 449 | 12142 | 15883 | 189.821 |
| [gin](https://github.com/gin-gonic/gin) | `43fe48e8a0f4` | ready | 123 | 4180 | 5361 | 66.688 |
| [clap](https://github.com/clap-rs/clap) | `4be56132cf7a` | failed | — | — | — | 4.342 |
| [fmt](https://github.com/fmtlib/fmt) | `9197f51593da` | failed | — | — | — | 17.943 |
| [fluentvalidation](https://github.com/FluentValidation/FluentValidation) | `fa3c160b1779` | ready | 275 | 6274 | 6112 | 132.356 |

Both clap and fmt failed with `UNIQUE constraint failed: symbols.id`. A read-only reproduction found one duplicate parameter ID in clap and ten in fmt. Parameters sharing a name and line (two `_` Rust parameters, for example) collide because parameter IDs omit their position. See `indexing-failure-diagnostics.json`. Separately, `.h` files currently default to the C adapter, limiting C++ header analysis. These defects were recorded without changing the tested backend.

## Answer results

| Case | Source review | Accepted generation | Time (s) |
|---|---|---|---:|
| axios-easy | inadequate_answer | True | 103.121 |
| axios-medium | incorrect | True | 85.925 |
| axios-hard | no_validated_answer | False | 95.932 |
| gin-easy | no_validated_answer | False | 119.559 |
| gin-medium | incorrect | True | 89.788 |
| gin-hard | incomplete_with_type_inaccuracy | True | 119.477 |
| clap-easy | blocked_by_indexing | not attempted | 0.000 |
| clap-medium | blocked_by_indexing | not attempted | 0.000 |
| clap-hard | blocked_by_indexing | not attempted | 0.000 |
| fmt-easy | blocked_by_indexing | not attempted | 0.000 |
| fmt-medium | blocked_by_indexing | not attempted | 0.000 |
| fmt-hard | blocked_by_indexing | not attempted | 0.000 |
| fluentvalidation-easy | no_validated_answer | False | 105.605 |
| fluentvalidation-medium | incorrect | True | 80.982 |
| fluentvalidation-hard | incorrect | True | 88.345 |

Median elapsed time for the nine attempted answerable questions: **95.932 seconds**. This includes retrieval, model generation and validation, not just model decoding. Accepted generation means the pipeline accepted an answer; it does not mean source review found it correct.

### What failed

- **axios-easy**: Misses all settle status/validateStatus conditions and the 4xx-versus-other rejection classification. Cites dispatch/catch and transport/body-size/timeout errors instead of lib/core/settle.js:14-27. Generation acceptance is not a pass.
- **axios-medium**: Claims there is no explicit temporary-response cleanup and substitutes garbage collection. This contradicts dispatchRequest.js:59-66, which sets config.response and deletes it in finally. Also substitutes interceptor processing for transformData handling. Cited request/_request excerpts do not establish those claims.
- **axios-hard**: Source contains interceptor-ordering and synchronous-path logic, but no validated explanation was produced. Warning: Conflicting aspect statuses. Not an answer pass; the rejection avoids exposing the rejected draft as correct.
- **gin-easy**: Only one of the three source anchors was in the final model context. Generation validation rejected the ShouldBindJSON source identity. Source exists; failure is a retrieval/generation coverage miss, not an unanswerable question.
- **gin-medium**: Wrongly attributes oversized-body classification to plainBinding io.ReadAll and invents exceeding-memory-limit detection. Actual MustBindWith (context.go:832-850) uses errors.As for *http.MaxBytesError and aborts with 413; other errors use 400, returning the original error. The cited plain binder does not prove the memory-limit or HTTP-classification claims.
- **gin-hard**: Correctly describes decode-error return, validate invocation and unknown-field rejection. UseNumber explanation drops Number: source json.go:16-18 says a number stored in any becomes Number rather than float64, not any rather than float64. Omits Validator==nil / ValidateStruct branching (binding.go:122-127). Thus useful partial content but not a complete accurate answer.
- **fluentvalidation-easy**: Required ValidateInternalAsync source was retrieved and supplied, but the identity validator rejected AbstractValidator.cs as a named symbol. No validated explanation of PreValidate before null checking was produced.
- **fluentvalidation-medium**: Conflates validators within a single rule with all separate rules for the same property. Class stop exits Rules iteration after new failures (AbstractValidator.cs:166); rule stop exits Components iteration (PropertyRule.cs:132). Citations show test setup assignments, not assertions or implementation establishing these scopes.
- **fluentvalidation-hard**: Conflates a nullable-struct validator null check with arbitrary rule/component conditions controlling lazy property evaluation. Omits PropertyFunc running once only after the first eligible component (PropertyRule.cs:112-120). Says dependent rules need no failures, but actual condition is no new failures relative to totalFailures (137-142); previous failures may exist. Cancellation description is supported.

## Retrieval comparison

Mean symbol Recall@5 over nine answerable questions on the three indexed repositories. All expected symbol labels mapped to the index. This measures labelled entity retrieval, not statement truth or exact context completeness.

| Retrieval mode | Mean Recall@5 |
|---|---:|
| lexical | 0.685 |
| semantic | 0.204 |
| graph | 0.444 |
| hybrid | 0.333 |

Lexical retrieval outperformed the current hybrid configuration on this small set. Graph mode uses lexical seeds and two hops; hybrid uses its configured fusion and reranking with two hops. This comparison does not establish optimal weights or a general ranking across repositories. Actual source anchors supplied in model context are recorded separately in `results.json`; retrieving a broad module range alone does not guarantee all required source was supplied.

## Other checks

- Three live-production questions correctly abstained before model generation (Axios, Gin, FluentValidation). Clap and fmt guard checks were blocked, not passed.
- Static issue detection returned zero candidates in each of the three indexed repositories. Without reviewed error labels this is not evidence of bug absence or detector accuracy.
- Project automated tests: **186 passed, 1 skipped** (Docker-dependent). Python lint/format and frontend formatting/build passed. Passing these project checks does not remove the observed real-repository failures.

## Recommended next changes

1. Make parameter IDs position-aware and infer C++ grammar for C++ headers; add regressions for the observed collisions.
2. Preserve exact implementation definitions through fusion and context selection; compare against the frozen lexical baseline.
3. Tighten claim support for negative statements, type semantics and branch conditions while correcting filename-versus-symbol false rejections.
4. Re-run this frozen set after fixes, then evaluate new held-out repositories with independent reviewed labels.

## Evidence and reproduction

- `snapshots.json`: repository commits, index counts and embedding status.
- `questions.json`: frozen questions, expected answer descriptions and source anchors.
- `results.json`: unchanged backend hashes, actual full responses, citations, context coverage, graph checks and four retrieval modes.
- `source-review.json`: every case reviewed separately from pipeline acceptance.
- `summary.json`, `index.log`, `run.log`, `indexing-failure-diagnostics.json`: counts and run evidence.

Runner: `python -m scripts.test_new_repositories --help`. The stage commands are `index` then `run`; use the isolated checkout/data paths documented by the runner. Local checkouts and the model/database caches are intentionally ignored by Git.
