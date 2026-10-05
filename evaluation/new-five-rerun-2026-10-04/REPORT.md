# DevPilot five-repository repeat evaluation

Date: 2026-10-04. Same pinned repositories, byte-identical questions, unchanged backend and local Qwen2.5-Coder 14B / Nomic embeddings. Fresh isolated database, rebuilt indexes and new model requests. The previous report and outputs are preserved.

**The same substantive failures reproduced.** Three repositories indexed; clap and fmt failed. Six of nine attempted answerable questions produced pipeline-accepted answers, but none was complete, fully accurate and supported under the source review criteria. Some contain useful correct parts. Six further answerable questions were blocked by indexing. Three live-state guard checks passed; two were blocked.

## Project checks

- Pytest: **186 passed, 1 skipped**, 5.13 seconds; skipped test is Docker-dependent.
- Ruff: lint passed; 151 files formatted.
- Frontend: Prettier passed; Vite production build passed.

These automated checks verify the implementation contracts they cover; they do not establish real-repository answer correctness.

## Repository outcomes

| Repository | Index | Files | Symbols | Index + embeddings (s) | Easy | Medium | Hard |
|---|---|---:|---:|---:|---|---|---|
| [axios](https://github.com/axios/axios/tree/c4303eeb601d3d5914a0f425cc7539616fdc7ea7) | ready | 449 | 12142 | 189.593 | Inadequate | Incorrect | No validated answer |
| [gin](https://github.com/gin-gonic/gin/tree/43fe48e8a0f44af783116cdb010725e6bb50255f) | ready | 123 | 4180 | 66.643 | No validated answer | Incorrect | Partial; type inaccuracy |
| [clap](https://github.com/clap-rs/clap/tree/4be56132cf7a5ef6e237409a13225a5829cb24e4) | failed | — | — | 4.343 | Blocked | Blocked | Blocked |
| [fmt](https://github.com/fmtlib/fmt/tree/9197f51593dab5f637454a8889fb9638e737711a) | failed | — | — | 17.856 | Blocked | Blocked | Blocked |
| [fluentvalidation](https://github.com/FluentValidation/FluentValidation/tree/fa3c160b17796ff67d6aa5ae6c4b05b471f1a791) | ready | 275 | 6274 | 132.364 | No validated answer | Incorrect | Incorrect |

Both failed indexes again reported `UNIQUE constraint failed: symbols.id`. The earlier read-only diagnostic identified parameter IDs that collide when name and line match; see the [baseline diagnostic](../new-five-2026-10-04/indexing-failure-diagnostics.json). The backend was not patched during this repeat. Separately, current `.h` grammar defaults limit C++ header analysis.

## Comparison with the previous run

| Measure | Previous | Repeat |
|---|---:|---:|
| Successfully indexed repositories | 3/5 | 3/5 |
| Answerable questions attempted | 9/15 | 9/15 |
| Accepted generated answers | 6/9 | 6/9 |
| No validated explanation | 3/9 | 3/9 |
| Complete, accurate, supported answers under source review | 0/9 | 0/9 |
| Safe live-state abstention | 3/3 executed | 3/3 executed |
| Median answer elapsed time | 95.932 s | 95.011 s |

All 20 review outcomes agree with the previous run, including blocked cases. Eight of the nine answerable response texts are identical; the Axios medium response varies in wording but repeats the same incorrect cleanup claim. Timing differences from one repeat do not establish an efficiency improvement.

## Retrieval comparison

Mean symbol Recall@5 over nine answerable questions on the three usable indexes. Every expected entity label mapped; all 28 authored source anchors match the pinned checkouts.

| Mode | Previous | Repeat |
|---|---:|---:|
| lexical | 0.685 | 0.685 |
| semantic | 0.204 | 0.204 |
| graph | 0.444 | 0.444 |
| hybrid | 0.333 | 0.333 |

The current lexical configuration again outperformed hybrid on this small set. Graph uses lexical seeds and two hops; hybrid uses configured fusion and reranking with two hops. Entity recall is not answer accuracy or context completeness. Full source-anchor context diagnostics are retained in `results.json`.

## Source review and actual answer outputs

A complete answer must address the explicit question conditions without incorrect or unsupported claims. Codex compared fresh outputs to pinned source and cited excerpts; this is not an independent human-labelled benchmark. The expected answer descriptions were not passed to the answer pipeline.

### axios-easy

**Question:** Under what conditions does Axios resolve rather than reject an HTTP response, and how is the rejection error classified?

**Outcome:** Inadequate. Accepted generation: True. Elapsed: 103.905 s. Citation support: `unsupported_for_required_claims`.

Misses all settle status/validateStatus conditions and the 4xx-versus-other rejection classification. Cites dispatch/catch and transport/body-size/timeout errors instead of lib/core/settle.js:14-27. Generation acceptance is not a pass.

**Actual answer:**

> Axios resolves an HTTP response if the request is successful and no errors occur during the request lifecycle [3].
>
> Axios rejects an HTTP response if an error occurs during the request lifecycle [3].
>
> The rejection error is classified based on the type of error that occurred during the request [5] [6] [7].

**Source-backed expected behavior:** Resolves when response.status is falsy, validateStatus is absent/falsy or validateStatus(status) is true. Otherwise rejects AxiosError with ERR_BAD_REQUEST for 400<=status<500 and ERR_BAD_RESPONSE for every other rejected status.

### axios-medium

**Question:** How does Axios transform request and successful response data around adapter execution, and how is its temporary response reference cleaned up?

**Outcome:** Incorrect. Accepted generation: True. Elapsed: 88.241 s. Citation support: `unsupported`.

Rerun again claims no explicit temporary-response cleanup and attributes it to garbage collection. This contradicts dispatchRequest.js:59-66 (config.response assigned, transformed, then deleted in finally). Cites Axios request/_request and interceptor excerpts instead of the required transform/cleanup source.

**Actual answer:**

> Axios transforms request and successful response data around adapter execution by first merging the provided configuration with defaults, then applying request interceptors, executing the adapter to send the request, and finally processing the response through response interceptors [2] [6].
>
> Axios does not explicitly clean up its temporary response reference after adapter execution [2] [6].
>
> The response is managed within the promise chain and is cleaned up by JavaScript's garbage collector once it is no longer in use [2] [6].

**Source-backed expected behavior:** Dispatch flattens config, checks cancellation, constructs headers and transforms request data before calling adapter. On success rechecks cancellation, assigns config.response, transforms response.data within try, deletes config.response in finally, normalizes response headers and returns response. transformData iterates functions with config as this, data, normalized headers and optional response.status.

### axios-hard

**Question:** How do skipped interceptors, the legacy ordering option and synchronous versus asynchronous request interceptors change the request/response processing chain?

**Outcome:** No validated answer. Accepted generation: False. Elapsed: 95.011 s. Citation support: `not_applicable`.

Source contains interceptor-ordering and synchronous-path logic, but no validated explanation was produced. Warning: Conflicting aspect statuses. Not an answer pass; the rejection avoids exposing the rejected draft as correct.

**Actual output:** No validated explanation; retrieved locations were returned.

**Validation warning:** Conflicting aspect statuses.

**Source-backed expected behavior:** Functional runWhen returning false skips a request interceptor. ANDs synchronous flags of included interceptors. legacyInterceptorReqResOrdering true unshifts request pairs, otherwise pushes them; response pairs push. Any included nonsynchronous interceptor selects Promise.resolve(config) chained through request/dispatch/response pairs. Otherwise request callbacks run directly then dispatch, and response pairs use then. InterceptorManager.use defaults synchronous to false when options absent.

### gin-easy

**Question:** How does ShouldBindJSON pass an HTTP request to the JSON binding implementation?

**Outcome:** No validated answer. Accepted generation: False. Elapsed: 119.222 s. Citation support: `not_applicable`.

Only one of the three source anchors was in the final model context. Generation validation rejected the ShouldBindJSON source identity. Source exists; failure is a retrieval/generation coverage miss, not an unanswerable question.

**Actual output:** No validated explanation; retrieved locations were returned.

**Validation warning:** Named class ShouldBindJSON is not established by its cited source identity.

**Source-backed expected behavior:** ShouldBindJSON delegates obj and binding.JSON to ShouldBindWith, which returns b.Bind(c.Request,obj). jsonBinding.Bind rejects nil request/body with invalid request, otherwise calls decodeJSON(req.Body,obj).

### gin-medium

**Question:** When automatic binding fails, how does Gin distinguish oversized request bodies from other binding errors, and what does it return?

**Outcome:** Incorrect. Accepted generation: True. Elapsed: 87.277 s. Citation support: `unsupported`.

Wrongly attributes oversized-body classification to plainBinding io.ReadAll and invents exceeding-memory-limit detection. Actual MustBindWith (context.go:832-850) uses errors.As for *http.MaxBytesError and aborts with 413; other errors use 400, returning the original error. The cited plain binder does not prove the memory-limit or HTTP-classification claims.

**Actual answer:**

> Gin distinguishes oversized request bodies from other binding errors by reading the entire request body into memory using `io.ReadAll(req.Body)` and checking for an error [6].
>
> If the request body is oversized, `io.ReadAll(req.Body)` returns an error indicating that the read operation failed due to exceeding memory limits [6].
>
> When automatic binding fails due to an oversized request body, Gin returns the error returned by `io.ReadAll(req.Body)`, which typically indicates a read failure [6].

**Source-backed expected behavior:** MustBindWith obtains err from ShouldBindWith. Non-nil error matching *http.MaxBytesError via errors.As causes AbortWithError(413).SetType(ErrorTypeBind); other errors cause 400 with same bind-error type. Returns original error; success returns nil. ShouldBindWith returns binder.Bind.

### gin-hard

**Question:** How does JSON binding handle decoder errors and struct validation, and which global switches alter the decoder behavior?

**Outcome:** Partial; type inaccuracy. Accepted generation: True. Elapsed: 117.770 s. Citation support: `partial`.

Correctly describes decode-error return, validate invocation and unknown-field rejection. UseNumber explanation drops Number: source json.go:16-18 says a number stored in any becomes Number rather than float64, not any rather than float64. Omits Validator==nil / ValidateStruct branching (binding.go:122-127). Thus useful partial content but not a complete accurate answer.

**Actual answer:**

> JSON binding handles decoder errors by returning the error directly from the decoder's Decode method [1].
>
> JSON binding performs struct validation by calling the validate function after decoding [1].
>
> The global switch EnableDecoderUseNumber alters the decoder behavior to unmarshal numbers as any instead of float64 [1] [2].
>
> The global switch EnableDecoderDisallowUnknownFields alters the decoder behavior to return an error for unknown fields in structs [1] [2].

**Source-backed expected behavior:** decodeJSON constructs json.API decoder, calls UseNumber and DisallowUnknownFields conditionally according to EnableDecoderUseNumber and EnableDecoderDisallowUnknownFields (both false defaults). Decode error returns before validate. After successful decode, validate returns nil if Validator nil, else Validator.ValidateStruct(obj).

### fluentvalidation-easy

**Question:** Why can asynchronous validation reject a null root model, and can pre-validation stop processing before that check?

**Outcome:** No validated answer. Accepted generation: False. Elapsed: 103.654 s. Citation support: `not_applicable`.

Required ValidateInternalAsync source was retrieved and supplied, but the identity validator rejected AbstractValidator.cs as a named symbol. No validated explanation of PreValidate before null checking was produced.

**Actual output:** No validated explanation; retrieved locations were returned.

**Validation warning:** Named symbol AbstractValidator.cs is not established by its cited source identity.

**Source-backed expected behavior:** ValidateInternalAsync creates result from context.Failures and calls PreValidate first. If false, optionally raises for invalid+ThrowOnFailures and returns before null root check. If continuing and InstanceToValidate is null, throws InvalidOperationException with root-model non-null message.

### fluentvalidation-medium

**Question:** What is the difference between stopping at class level and stopping within a property rule during validation?

**Outcome:** Incorrect. Accepted generation: True. Elapsed: 81.304 s. Citation support: `unsupported_for_required_claims`.

Conflates validators within a single rule with all separate rules for the same property. Class stop exits Rules iteration after new failures (AbstractValidator.cs:166); rule stop exits Components iteration (PropertyRule.cs:132). Citations show test setup assignments, not assertions or implementation establishing these scopes.

**Actual answer:**

> Stopping at class level during validation means that if a rule fails, no further rules in the same class are executed [6] [1].
>
> Stopping within a property rule during validation means that if a rule fails, no further rules for the same property are executed [4] [7].
>
> The difference between stopping at class level and stopping within a property rule is that class-level stopping affects all rules in the class, while property-level stopping only affects rules for the specific property [6] [1] [4] [7].

**Source-backed expected behavior:** ClassLevelCascadeMode Stop breaks AbstractValidator rules loop when a rule adds failures. PropertyRule CascadeMode Stop breaks components loop when failures increase relative to snapshot before components. Different scopes. Dependent rules run only when that property rule did not add failures.

### fluentvalidation-hard

**Question:** In asynchronous property validation, how do rule conditions and component conditions control property access, cancellation and dependent rules?

**Outcome:** Incorrect. Accepted generation: True. Elapsed: 87.127 s. Citation support: `partial`.

Conflates a nullable-struct validator null check with arbitrary rule/component conditions controlling lazy property evaluation. Omits PropertyFunc running once only after the first eligible component (PropertyRule.cs:112-120). Says dependent rules need no failures, but actual condition is no new failures relative to totalFailures (137-142); previous failures may exist. Cancellation description is supported.

**Actual answer:**

> Rule conditions and component conditions control property access by checking if the value is null or if asynchronous conditions are met before invoking validators [3] [2].
>
> Cancellation is handled by throwing a cancellation exception if requested during validation [2] [7].
>
> Dependent rules are validated after the main rule if there are no failures and dependent rules exist [2] [7].

**Source-backed expected behavior:** Return when selector or rule Condition/AsyncCondition vetoes. Per component check cancellation, reset message formatter, skip false sync/async conditions. Evaluate PropertyFunc lazily only at first eligible component; wrap NullReferenceException with When guidance. Failure adds error; Stop can break. Nonnull dependent rules run only with no new failures and each checks cancellation.

## Abstention, static analysis and citations

- The three usable repositories correctly abstained on current production deployment and live traffic. These checks run before model generation. Clap/fmt guards were blocked, not passed.
- Static issue analysis returned zero candidates on all three usable indexes. Without independently reviewed bug labels this cannot establish bug absence or detector accuracy.
- All 34 citation provenance entries matched their source coordinates and quoted text. This does not establish that claims follow from those excerpts; support failures are recorded above.

## Evidence and reproduction

- `rerun-manifest.json`: tested code commit, model digests and same pinned source commits.
- `questions.json`, `source-anchor-checks.json`: frozen questions and checked source anchors.
- `snapshots.json`, `index.log`: fresh index counts, timings and failures.
- `results.json`, `run.log`: all fresh outputs, four retrieval modes, source context and graph diagnostics.
- `source-review.json`, `citation-source-checks.json`, `comparison.json`, `summary.json`: review and comparison evidence.
- `project-checks.json`: automated check results.

Use `reproduce.py index` then `reproduce.py run` from the repository root with the project Python environment. It requires the pinned checkouts under `.devpilot/new-five-2026-10-04-checkouts` and local Ollama models. Existing completed outputs resume; a further independent repeat needs separate output/data paths. No upstream repository code was executed, no patches applied and no model weight training performed.

Priority fixes remain collision-free parameter IDs, C++ header grammar inference, preserving implementation definitions in hybrid/context selection, and stronger claim support with fewer source-identity false rejections. These were not implemented as part of the repeat evaluation.
