# DevPilot: five complex repository tests

Date: 2026-10-04. Qwen 2.5 Coder 7B, context 8,192, source budget 4,096, local Ollama, claim audit enabled. Existing Quick answer pipeline and LangGraph Deep pipeline; no embedding corpus or fine-tuning. All repositories were newly pinned for evaluation only. The production backend was unchanged throughout the run.

## Measured outcome

- **Correct and complete answers: 2/20** answerable runs (15 Quick questions plus five hard-question Deep runs).
- **Correct, complete and fully supported by exact cited lines: 1/20**.
- Expected-symbol retrieval recall@8: **87.3%** averaged per run. This measures labeled methods retrieved, not all relevant code or answer accuracy.
- Median full answer latency: **37.41 s**; range 16.73–72.95 s. Includes retrieval, generation, retries and audit.
- Generated explanations accepted: 13/20, of which 2 were marked partial. Acceptance is not a correctness score.
- Source review categories: 2 correct and complete, 9 correct but incomplete, 2 incorrect, and 7 no validated answer.
- Private-runtime abstention checks: **10/10**. These use the same explicit private-state prompt across the five repositories and both modes; they are not ten distinct adversarial prompts.
- Unhandled run errors: 0.

## Results by repository

| Repository | Indexed files / symbols | Quick correct & complete | Quick strict citation-supported | Recall@8 | Quick median | Hard Deep correct & complete |
|---|---:|---:|---:|---:|---:|---:|
| [sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) | 700 / 41,447 | 0/3 | 0/3 | 100.0% | 36.95 s | Fail |
| [celery](https://github.com/celery/celery) | 790 / 11,459 | 1/3 | 0/3 | 100.0% | 50.3 s | Fail |
| [scrapy](https://github.com/scrapy/scrapy) | 639 / 9,029 | 0/3 | 0/3 | 100.0% | 39.7 s | Fail |
| [mybatis](https://github.com/mybatis/mybatis-3) | 2,048 / 12,569 | 1/3 | 1/3 | 77.8% | 32.92 s | Fail |
| [resilience4j](https://github.com/resilience4j/resilience4j) | 1,368 / 10,872 | 0/3 | 0/3 | 80.0% | 32.49 s | Fail |

## What the results show

Retrieval often finds the named entry points, but the complete explanation frequently fails. MyBatis caching and Resilience4j transitions also miss crucial helper methods. Deep mode completed zero of the five hard answers, as did Quick on those same questions; this small single-run sample does not establish general equivalence or a universal latency advantage.

The most useful next changes would be to preserve every requested obligation when splitting questions; retrieve helper methods under the exact requested class/overload; include operative branch/call lines in claim citations; and distinguish valid exception/owner references from wrong-owner citations without rejecting the entire useful answer unnecessarily. These are findings and suggested follow-up work, not changes made during this evaluation. The same-model audit both catches some wrong claims and accepts some unsupported ones, so it cannot replace source review.

## Source-reviewed findings

### sqlalchemy-easy — quick

**Question:** In Session.flush, what happens if a flush is already in progress, and how is the _flushing flag reset after _flush runs?

**Verdict:** correct but incomplete. Correct exception and flag reset, but the answer does not say finally or False, so it does not explain how the flag is reset. Both cited ranges support the limited claims.

Time: 16.73 s; expected-symbol recall@8: 100.0%.

### sqlalchemy-medium — quick

**Question:** Under which conditions does Session._autoflush call flush, and how does it handle a StatementError?

**Verdict:** no validated answer. Both drafts were rejected because StatementError identity was not established by the identity validator. The pinned implementation catches sa_exc.StatementError. No substantive answer was delivered; safe fallback is not answer accuracy.

Time: 36.95 s; expected-symbol recall@8: 100.0%.

### sqlalchemy-hard — quick

**Question:** Trace SessionTransaction.commit and _prepare_impl: how is pending work flushed before commit, what prevents endless flushing, and which connection transactions are committed?

**Verdict:** correct but incomplete. The outline is broadly accurate but omits the should_commit condition and root-or-nested guard when asked which transactions commit. Its first citation (1327-1329) ends before the actual _prepare_impl call at 1330, so that claim lacks exact cited-line support. The 100-flush bound is correct.

Time: 47.03 s; expected-symbol recall@8: 100.0%.

### sqlalchemy-hard — deep

**Question:** Trace SessionTransaction.commit and _prepare_impl: how is pending work flushed before commit, what prevents endless flushing, and which connection transactions are committed?

**Verdict:** incorrect and incomplete. The 100-iteration loop raises on exhaustion (after 100 attempted iterations without a clean check), not after executing more than 100 flushes. It also omits should_commit and the root-or-nested guard and substitutes vague current-connection wording. The message text says Over 100 but that is not the actual loop condition. The audit accepted these claims.

Time: 48.38 s; expected-symbol recall@8: 100.0%.

### celery-easy — quick

**Question:** How does Task.delay forward positional and keyword arguments to asynchronous task submission?

**Verdict:** correct and complete but citations insufficient. Correctly explains forwarding to apply_async. However its citations are only the delay declaration at 534 and apply_async signature at 547-548. Neither includes the actual forwarding call at 545; the explanation is true but not established by its cited lines.

Time: 24.92 s; expected-symbol recall@8: 100.0%.

### celery-medium — quick

**Question:** In Task.signature_from_request, how are arguments, execution options, priority and an explicit queue carried into the new signature?

**Verdict:** correct but incomplete. The limited statements are true, but the requested explicit queue behavior is entirely omitted, as are None-only argument defaults. The claim that arguments reach the new signature cites 742-745 (declaration/default selection), excluding self.signature at 762-764. Options merge and priority claims have relevant citations.

Time: 50.30 s; expected-symbol recall@8: 100.0%.

### celery-hard — quick

**Question:** In Task.retry, explain the retry counter and maximum-limit check, then distinguish eager execution from publishing a normal retry and the effect of throw=False.

**Verdict:** no validated answer. Both attempts were rejected: first lexical claim support, then Task.retry source-identity validation. The expected retry method was retrieved, but no substantive validated answer reached the user. This is safe fallback, not a successful answer.

Time: 58.96 s; expected-symbol recall@8: 100.0%.

### celery-hard — deep

**Question:** In Task.retry, explain the retry counter and maximum-limit check, then distinguish eager execution from publishing a normal retry and the effect of throw=False.

**Verdict:** no validated answer. Both attempts were rejected: first lexical claim support, then Task.retry source-identity validation. The expected retry method was retrieved, but no substantive validated answer reached the user. This is safe fallback, not a successful answer.

Time: 41.94 s; expected-symbol recall@8: 100.0%.

### scrapy-easy — quick

**Question:** In Scheduler.next_request, which queue is checked first, when is the disk queue checked, and what is returned when both are empty?

**Verdict:** no validated answer. The expected Scheduler.next_request method was retrieved. Both attempts were rejected by lexical claim support validation and a source-location fallback was delivered. Drafts describe the actual memory-first behavior but their short citations omit some of the surrounding branch conditions; delivered fallback is not a complete answer.

Time: 39.70 s; expected-symbol recall@8: 100.0%.

### scrapy-medium — quick

**Question:** How does RFPDupeFilter.request_seen identify and record a new request, and what does it return for a duplicate?

**Verdict:** correct but incomplete. Fingerprint generation, membership check and duplicate True are correct and supported by source 1. However the requested recording of a new request is not explained: it omits adding the fingerprint to _fingerprints, optional length-prefixed file persistence, and the new-request False result.

Time: 28.64 s; expected-symbol recall@8: 100.0%.

### scrapy-hard — quick

**Question:** Trace Scheduler.enqueue_request and next_request: how are duplicates rejected, how does enqueue fall back between disk and memory, and in what order are requests dequeued?

**Verdict:** no validated answer. Both expected scheduler methods were retrieved. The first draft failed aspect relevance and the retry failed Scheduler.enqueue_request source-identity validation. The delivered source-location fallback does not explain duplicate filtering and disk-enqueue/memory-dequeue ordering.

Time: 72.95 s; expected-symbol recall@8: 100.0%.

### scrapy-hard — deep

**Question:** Trace Scheduler.enqueue_request and next_request: how are duplicates rejected, how does enqueue fall back between disk and memory, and in what order are requests dequeued?

**Verdict:** no validated answer. As in Quick, both expected scheduler methods were retrieved but the drafts failed aspect relevance and source-identity validation. Deep did not yield a validated explanation.

Time: 54.45 s; expected-symbol recall@8: 100.0%.

### mybatis-easy — quick

**Question:** What does ParamNameResolver.getNamedParams return when args is null or there are no named parameters?

**Verdict:** correct complete and supported. Directly answers both null/no-parameter conditions and the null return. Lines 159-160 explicitly contain the combined condition and return null.

Time: 21.79 s; expected-symbol recall@8: 100.0%.

### mybatis-medium — quick

**Question:** In MapperMethod.executeForMany, how are RowBounds applied, and when is the selected list converted to an array or a declared collection?

**Verdict:** incorrect and incomplete. RowBounds behavior is correct. But collection conversion is not performed merely because the return type is not an array: the outer isAssignableFrom check must first fail; an assignable list is returned unchanged. The claimed conversion condition is too broad, and its 151-153 citation shows the array branch rather than the collection branch at 154.

Time: 37.87 s; expected-symbol recall@8: 100.0%.

### mybatis-hard — quick

**Question:** For CachingExecutor.query with CacheKey and BoundSql, which conditions enable cache lookup, what happens on a cache miss, and how do commit and rollback affect transactional cache changes?

**Verdict:** correct but incomplete. Cache lookup and delegate-on-miss outline are broadly correct, but non-null cache and transactional staging/required rollback distinctions are not explained. Neither CachingExecutor.commit nor rollback was retrieved in the top eight; the commit/rollback claim cites TransactionalCacheManager.getObject and putObject (34-36 and 38-40), which establish neither operation. The lookup claim citation 98-99 omits the outer non-null guard at 97.

Time: 32.92 s; expected-symbol recall@8: 33.3%.

### mybatis-hard — deep

**Question:** For CachingExecutor.query with CacheKey and BoundSql, which conditions enable cache lookup, what happens on a cache miss, and how do commit and rollback affect transactional cache changes?

**Verdict:** correct but incomplete. Deep correctly states all three lookup conditions and the delegate/tcm write on miss. It still omits the critical commit-versus-required-only-rollback behavior. Its commit/rollback claim cites TransactionalCacheManager.rollback and getObject, not CachingExecutor.commit/rollback or manager.commit. Exact cited support is incomplete even though the broad delegation claim is true.

Time: 35.54 s; expected-symbol recall@8: 33.3%.

### resilience4j-easy — quick

**Question:** What does CircuitBreakerStateMachine.ClosedState.tryAcquirePermission actually return?

**Verdict:** no validated answer. The exact ClosedState.tryAcquirePermission method was retrieved and drafts included the correct isClosed.get() return. Both attempts nevertheless failed named-symbol source-identity validation, so the delivered output was a fallback rather than the requested answer.

Time: 26.62 s; expected-symbol recall@8: 100.0%.

### resilience4j-medium — quick

**Question:** How do CircuitBreakerStateMachine.onError and handleThrowable distinguish wrapped, ignored, recorded and non-recorded exceptions?

**Verdict:** correct but incomplete. Wrapped, ignored and recorded exception explanations are correct and supported by their cited lines. The explicitly requested non-recorded exception path is entirely missing: it publishes success and calls state.onSuccess. Ignored-event publication/early return and the subsequent transition check are also omitted.

Time: 32.49 s; expected-symbol recall@8: 100.0%.

### resilience4j-hard — quick

**Question:** In CircuitBreakerStateMachine.HalfOpenState, how does tryAcquirePermission limit probe calls, how does releasePermission restore a permit, and how do onError and onSuccess lead to OPEN or CLOSED?

**Verdict:** honest partial answer. Correctly describes the counter and permit restoration, then explicitly marks the state-transition aspect insufficient. Only two of the five expected methods were retrieved, with no supplemental improvement. However the zero-counter false-return claim cites 1117-1120, ending before onCallNotPermitted and return false at 1122-1123. The transition abstention is honest; the full question is unanswered.

Time: 42.66 s; expected-symbol recall@8: 40.0%.

### resilience4j-hard — deep

**Question:** In CircuitBreakerStateMachine.HalfOpenState, how does tryAcquirePermission limit probe calls, how does releasePermission restore a permit, and how do onError and onSuccess lead to OPEN or CLOSED?

**Verdict:** honest partial answer. Deep again retrieves only the permit-acquire and release methods among five expected methods. The draft incorrectly used OpenState.onSuccess for the HalfOpenState transition claim; the audit rejected that claim, producing an honest missing-evidence message. The remaining zero-counter false-return claim still cites only the positive branch and an unrelated OpenState delegation, so exact citation support is incomplete.

Time: 35.56 s; expected-symbol recall@8: 40.0%.

## Scope and reproducibility

These are Codex source reviews, not independent human grading. Completeness is judged against explicit question obligations; exact citation support uses each claim’s actual cited line ranges. A safe fallback is recorded as no validated answer, rather than a factual hallucination or a successful substantive answer. A correct but incomplete explanation fails the complete-answer metric.

One repeat per mode on this Mac is a small sample, not a general model accuracy estimate or a controlled before/after comparison. Repository complexity is a qualitative architecture label. Full roots were scanned, but only supported file types were indexed; coverage exclusions are recorded. No parser errors occurred, which does not prove complete call-graph resolution. Dynamic dispatch, external/native code and many references remain unresolved.

This tests DevPilot indexing, retrieval and repository question answering. Upstream project test suites, service deployment, patch generation and repair success were not tested. No new training ran and these repositories were not added to training data.

Artifacts in `evaluation/complex-five-2026-10-04/`: frozen questions and expected source; pinned snapshots; raw results and all draft/audit/context diagnostics; separate source reviews; reviewed results and summary. Backend SHA-256 hashes and model digest are in results.json. The interrupted pre-finalization checkpoint is retained separately and excluded from scores.

The evaluation runner refuses to overwrite existing results and checks every expected symbol range and snapshot fingerprint before answering. Reproduction requires the recorded commits, frozen questions, model digest, settings and a separate output directory; re-cloning a moving branch alone is not the same benchmark.
