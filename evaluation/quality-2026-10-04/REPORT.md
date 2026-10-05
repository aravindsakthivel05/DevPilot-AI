# DevPilot answer-quality evaluation — October 4, 2026

Indexing and source recovery improved. **The answer-accuracy target has not been met.** Source citations and a same-model claim reviewer still admit incorrect or incomplete explanations. No model weights were trained from these outputs.

## Frozen development run

Pinned repositories: Axios, Gin, Clap, fmt and FluentValidation. Question wording is unchanged from the preceding evaluation. Expected answers and source labels never enter retrieval, source selection or generation. This five-repository set guided development; it is not an untouched holdout.

| Measure | Previous rerun | This 20-case run |
| --- | ---: | ---: |
| Repositories successfully indexed | 3/5 | 5/5 |
| Fully correct, complete and grounded answers, strict source review | 0/9 attempted (6 blocked) | 1/15 attempted |
| Incomplete answers without identified false claims | — | 7/15 |
| Partial answers with identified unsupported/overbroad claims | — | 7/15 |
| Appropriate live-state refusals | 3/3 attempted (2 blocked) | 5/5 |
| Hybrid entity Recall@5 | 0.333 | 0.756 |
| Complete required source-anchor context | — | 14/15 |
| Mean required source-anchor context recall | — | 0.978 |
| Median answerable-case latency | 95.011 s (9 cases) | 94.869 s (15 cases) |

The timing medians have different case coverage and do not establish a speedup. Entity recall measures exact frozen symbol IDs; source-anchor coverage measures supplied executable ranges. A module label can penalize entity recall even when a smaller implementation supplies its source range. Neither metric is answer accuracy.

## Source review by question

| Case | Review category | Findings |
| --- | --- | --- |
| axios-easy | partial with unsupported claims | Omitted falsy-status resolution branch; extra content-limit claim omits the disabled-limit guard. |
| axios-medium | partial with unsupported claims | Core transform/finally order is correct, but omits transform callback arguments and cancellation/header steps; error cleanup omits reason.response guard. |
| axios-hard | partial with unsupported claims | Incorrectly says synchronous request interceptors run before asynchronous ones; code selects exclusive execution branches. |
| gin-easy | incomplete | Correct caller/binder/decode flow; frozen reference additionally requires exact nil-request/body check and its invalid-request error, summarized vaguely as valid. |
| gin-medium | incomplete | Correct MaxBytesError distinction; requested response status and original error return are withheld. |
| gin-hard | incomplete | Correct decode/validate flow and optional Validator; global decoder defaults and precise number behavior withheld. |
| clap-easy | partial with unsupported claims | Supplied-argument APIs are described, but adds unrelated environment/derive APIs and an incorrect get_matches call target. |
| clap-medium | incomplete | Missing-value Ok(None) is correct; requested type-mismatch behavior withheld; adds unrelated removal API. |
| clap-hard | incomplete | Build/parser/global propagation and IgnoreErrors stderr guard correct; validation and mutable entry stages absent. |
| fmt-easy | incomplete | Correct nan/inf case, sign and zero-fill summary; omits numeric-alignment, signed width and single-zero fill conditions. |
| fmt-medium | fully correct complete | Capacity branches and allocate/copy/publish/deallocate order match pinned source, including inline-store exclusion. |
| fmt-hard | partial with unsupported claims | Confuses #if macro value with definedness; no-exception assertion print/abort behavior missing. |
| fluentvalidation-easy | partial with unsupported claims | Null/pre-validation ordering correct, but no-further-checks claim omits ThrowOnFailures exception branch. |
| fluentvalidation-medium | partial with unsupported claims | Failure increase and Stop distinction mostly correct; wrongly assigns ClassLevelCascadeMode via rule Cascade extension. |
| fluentvalidation-hard | incomplete | Condition/cancellation/baseline outline present; lazy first property access, caching, accessor exception wrapper and exact order missing. |
| axios-unanswerable | appropriate abstention | Correctly refuses live deployment/traffic facts from a source snapshot. |
| gin-unanswerable | appropriate abstention | Correctly refuses live deployment/traffic facts from a source snapshot. |
| clap-unanswerable | appropriate abstention | Correctly refuses live deployment/traffic facts from a source snapshot. |
| fmt-unanswerable | appropriate abstention | Correctly refuses live deployment/traffic facts from a source snapshot. |
| fluentvalidation-unanswerable | appropriate abstention | Correctly refuses live deployment/traffic facts from a source snapshot. |

## Subsequent final checks

`final-rechecks/` retains separate outputs and backend hashes for five targeted questions after general fixes to aspect scoping, coordinated obligations and support checks. Those outputs do not overwrite the preceding run. Targeted rechecks removed the false interceptor sequencing claim but remained incomplete. Recognizing `#elif` and enabling one bounded correction removed the fmt definedness confusion and added stderr/abort behavior. Gin’s missing decoder details were not recovered; its accepted partial draft was preserved. Property-validation answers still omitted lazy property access and related details.

The additional ItsDangerous/Zod run indexed 2/2 repositories and found all required source anchors for 4/4 answerable questions. Strict source review rated 3 incomplete and 1 partially incorrect, including Zod’s false cache-reuse claim; 2/2 live-state guards refused appropriately. See [its separate report](../quality-holdout-2026-10-04/REPORT.md). The original run is preserved, and Zod became a development repository once that failure informed a general guard. Subsequent checks do not count as untouched holdout accuracy.

## Artifacts and reproduction

- `questions.json`, `snapshots.json`: frozen questions, references, pinned commits and fingerprints.
- `results.json`, `run.log`: complete raw outputs and the backend hashes used for the 20-case run.
- `source-review.json`, `summary.json`: Codex source judgments and computed metrics, not independent human labels.
- `indexing/`: structural and compact embedding rebuild evidence.
- `diagnostics/`: preflights, source coverage, unsuccessful reranker/model experiments and interrupted early runs. These are not counted as held-out accuracy.
- `static/`: conservative static candidates from source, not executed test failures.
- `project-checks.json`, `runtime-check.json`: regression/build/API checks.

Use the commands in [the quality implementation notes](../../docs/quality-2026-10-04.md). The runner refuses to resume a result after backend/question changes. Repository code is never executed during these evaluations. Larger or independent benchmarks are needed before generalizing results.
