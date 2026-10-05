# DevPilot: two new complex repository evaluations

Run: 2026-10-05T22:23:44+05:30 to 2026-10-05T22:34:32+05:30 (India time).

**Strict result: 0/6 fully correct and adequate; 4/6 incomplete; 2/6 incorrect or unsupported.** Live-state abstention checks: 2/2 passed.

Median answer time: **104.3 seconds**. All required source anchors reached generation context for **5/6** questions; average anchor coverage was **88.9%**. These source-coverage figures do not measure answer correctness.

## Scope and method

Local model: `qwen2.5-coder:14b`; embeddings: `nomic-embed-text:latest`. Hybrid retrieval, limit 8, graph depth 2, 8192-token context. Model source selection and claim review enabled; rejected-claim repair disabled. LangGraph and legacy execution were disabled in this CLI evaluation.

These repositories did not appear in the previous evaluation records checked before selection. Commits were pinned, and questions, source labels, reference answers and grading criteria were frozen before viewing generated answers. Reference answers and labels were withheld from generation. Backend hashes were unchanged during the run. There was one attempt per question (the internal bounded answer pipeline may make multiple provider calls). No model-weight training, repository patching, application deployment, or execution of the target repositories’ test suites occurred.

This is a source review by Codex, not an independent human benchmark. A fully adequate answer must cover the essential requested behavior without material false claims and with supporting citations. Incomplete answers may still contain useful, correct statements. Extra incidental reference detail is not mandatory.

## Indexed repositories

| Repository | Pinned commit | Files | Symbols | Graph edges | Index time | Eligible embeddings |
|---|---|---:|---:|---:|---:|---:|
| [aiohttp](https://github.com/aio-libs/aiohttp) | `715ddc33a388ba8ccc86dc6bedf36e06ba42ad43` | 451 | 18506 | 26643 | 167.0s | 8333/8333 |
| [werkzeug](https://github.com/pallets/werkzeug) | `594452f6a4fe4de38a544962fbf04bfc9d37fbc2` | 255 | 6780 | 10045 | 56.3s | 2829/2829 |

Both indexes were ready with no recorded parse errors. Indexing intentionally skips unsupported, ignored, hidden or lock files: it does not read literally every file.
- aiohttp: 126 skipped files, 3 ignored directories; 30750 unresolved static references. 8 static-analysis candidates were recorded and were **not validated defects**.
- werkzeug: 38 skipped files, 2 ignored directories; 7482 unresolved static references. 11 static-analysis candidates were recorded and were **not validated defects**.

## Results

| Repository | Level | Topic | Source anchors in context | Time | Source review |
|---|---|---|---:|---:|---|
| aiohttp | easy | Owned/shared connector closure | 100% | 94.0s | Incomplete |
| aiohttp | medium | Failure and cancellation cleanup | 100% | 114.5s | Incomplete |
| aiohttp | hard | Redirect replay and cross-origin state | 33% | 149.3s | Incorrect / unsupported |
| werkzeug | easy | Close order and callback exceptions | 100% | 50.3s | Incomplete |
| werkzeug | medium | JSON options and cache semantics | 100% | 82.6s | Incomplete |
| werkzeug | hard | Routing redirects and mismatch precedence | 100% | 144.5s | Incorrect / unsupported |
| aiohttp | live-state guard | Live deployment and traffic | N/A | 0.0s | Appropriate abstention |
| werkzeug | live-state guard | Live deployment and traffic | N/A | 0.0s | Appropriate abstention |

## Questions, actual outputs and review

### aiohttp-easy

**Question:** How does ClientSession.close handle an owned versus a shared connector, and what happens if the session is already closed?

**Grade:** Incomplete (94.0s).

**Actual DevPilot output:**

> ClientSession.close handles an owned connector by closing it if the session is not already closed [1].
>
> ClientSession.close sets the connector to None after closing it [1].
>
> ClientSession.close checks if the session is already closed before proceeding [1].
>
> Aspect 2: Some requested details lack valid source citations and could not be established.

**Source review:** Correct retained statements, but shared-connector behavior and the already-closed no-op are not explained clearly. Both source anchors were present in generation context.

**Citation review:** The owned-connector claim omits the already-closed guard from its exact span; surrounding implementation confirms it.

**Frozen reference:** An already-closed session skips the guarded close body. Otherwise, it awaits closing a non-null connector only if connector_owner is true, then clears the session connector reference even for a shared connector. The closed property is true when the connector is None or itself closed; if already closed the guarded body does not clear a retained reference.

Reference source anchors:
- [aiohttp/client.py:1415](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1415) — `if self._connector is not None and self._connector_owner:`
- [aiohttp/client.py:1425](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1425) — `return self._connector is None or self._connector.closed`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [aiohttp/client.py:1414–1415](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1414-L1415) (`aiohttp.client.ClientSession.close`).
- [aiohttp/client.py:1415–1416](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1415-L1416) (`aiohttp.client.ClientSession.close`).
- [aiohttp/client.py:1417–1417](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1417-L1417) (`aiohttp.client.ClientSession.close`).

### aiohttp-medium

**Question:** In BaseConnector.connect and _wait_for_available_connection, how are connection placeholders and queued waiters cleaned up when an awaited operation fails or is cancelled?

**Grade:** Incomplete (114.5s).

**Actual DevPilot output:**

> In _wait_for_available_connection, when an awaited operation fails or is cancelled, the future (fut) is removed from keyed_waiters in the finally block [1].
>
> If keyed_waiters becomes empty after removing fut, the key is deleted from self._waiters [1].
>
> In connect, if an exception occurs during the creation of a connection (in the try-except block), _release_acquired is called to clean up the placeholder [2].
>
> _release_acquired removes the placeholder from _acquired and, if applicable, from _acquired_per_host [4].
>
> It also calls _release_waiter to potentially release a waiter [4].

**Source review:** Correct main cleanup paths: waiter removal, empty bucket deletion, placeholder release and global/per-host removal. Does not explicitly explain BaseException including cancellation or re-raising; the helper already-closed early return is also omitted.

**Citation review:** The waiter removal citation is line 756, omitting finally at 755; the exception citation is lines 702–703, omitting BaseException at 701. Source review confirms the described cleanup, but the spans are too narrow to establish all stated conditions.

**Frozen reference:** connect adds an acquired placeholder before traced connection creation; BaseException catches failures including cancellation, calls _release_acquired(key, placeholder), then re-raises. _release_acquired discards it globally, removes it from per-host acquisition if configured, deletes an empty per-host bucket, and releases a waiting slot; it returns early if the connector already closed. The waiter method has a finally block that removes its future and deletes an empty per-key waiter queue, including cancellation or trace exceptions inside the try.

Reference source anchors:
- [aiohttp/connector.py:702](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L702) — `self._release_acquired(key, placeholder)`
- [aiohttp/connector.py:756](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L756) — `keyed_waiters.pop(fut, None)`
- [aiohttp/connector.py:840](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L840) — `self._acquired.discard(proto)`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [aiohttp/connector.py:756–756](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L756-L756) (`aiohttp.connector.BaseConnector._wait_for_available_connection`).
- [aiohttp/connector.py:757–758](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L757-L758) (`aiohttp.connector.BaseConnector._wait_for_available_connection`).
- [aiohttp/connector.py:702–703](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L702-L703) (`aiohttp.connector.BaseConnector.connect`).
- [aiohttp/connector.py:836–836](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L836-L836) (`aiohttp.connector.BaseConnector._release_acquired`).
- [aiohttp/connector.py:840–842](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L840-L842) (`aiohttp.connector.BaseConnector._release_acquired`).
- [aiohttp/connector.py:845–845](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L845-L845) (`aiohttp.connector.BaseConnector._release_acquired`).

### aiohttp-hard

**Question:** When ClientSession._request follows redirects, which status/method combinations switch to GET and discard the body, when must a body be replayed, and which cookie/authentication state is cleared on an origin change?

**Grade:** Incorrect / unsupported (149.3s).

**Actual DevPilot output:**

> When ClientSession._request follows redirects and encounters status codes 301, 302, 303, 307, or 308, it switches the method to GET and discards the body if the original method was POST [1].
>
> When ClientSession._request follows redirects and encounters status codes 301 or 302 with the original method as POST, it switches the method to GET and discards the body [1].
>
> When ClientSession._request follows redirects and encounters status code 303, it switches the method to GET and discards the body regardless of the original method [1].
>
> Aspect 1: Some requested details were not established by the cited source; supported details remain available.
>
> When ClientSession._request follows redirects and the origin changes, it clears the cookie/authentication state [1].
>
> When ClientSession._request follows redirects and the origin changes, it raises a NonHttpUrlRedirectClientError if the new URL scheme is not HTTP or empty [1].
>
> Aspect 2: When ClientSession._request follows redirects and the origin changes, it does not clear the cookie/authentication state if the new URL scheme is HTTP or empty.

**Source review:** Material errors: says 307/308 POST becomes GET (source preserves body), says 303 changes HEAD to GET (HEAD is excluded), and prints a rejected claim that HTTP-origin changes do not clear cookies/authentication. It also omits the consumed-payload replay failure and the three cleared header names.

**Citation review:** Rewrite claims omit required branch guards. Cookie/authentication claim cites URL-scheme validation at 867–872, not clearing at 891–895. Only one of three frozen source anchors reached generation context. The same-model reviewer accepted false statements; an insufficient_evidence claim is displayed as declarative negative text.

**Frozen reference:** When redirect following is enabled, among 301/302/303/307/308, 303 except HEAD and 301/302 POST rewrite to GET, set data=None and remove a present Content-Length header. Other combinations preserve the method and reuse req._body (307/308, non-POST 301/302, and HEAD 303); a consumed payload causes response.close and ClientPayloadError instead of empty replay. On origin change cookies=None and all Authorization, Cookie and Proxy-Authorization header entries are removed. This code does not assign auth=None.

Reference source anchors:
- [aiohttp/client.py:818](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L818) — `if (resp.status == 303 and resp.method != hdrs.METH_HEAD)`
- [aiohttp/client.py:834](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L834) — `if req._body.consumed:`
- [aiohttp/client.py:895](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L895) — `headers.popall(hdrs.PROXY_AUTHORIZATION, None)`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [aiohttp/client.py:821–824](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L821-L824) (`aiohttp.client.ClientSession._request`).
- [aiohttp/client.py:819–820](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L819-L820) (`aiohttp.client.ClientSession._request`).
- [aiohttp/client.py:818–819](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L818-L819) (`aiohttp.client.ClientSession._request`).
- [aiohttp/client.py:867–872](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L867-L872) (`aiohttp.client.ClientSession._request`).

### werkzeug-easy

**Question:** What order does Response.close use for closing the wrapped iterable and running registered callbacks, and does it guarantee callbacks run if the iterable close raises?

**Grade:** Incomplete (50.3s).

**Actual DevPilot output:**

> Response.close first closes the wrapped iterable if it has a close method [1].
>
> Response.close then runs all registered callbacks in the order they were added [1].
>
> Aspect 1: Some requested details were not established by the cited source; supported details remain available.
>
> Aspect 1: The behavior of Response.close regarding the order and guarantee of callback execution is not fully documented or tested in the provided evidence.

**Source review:** Correct iterable-first and callback-order descriptions, but withholds whether an iterable-close exception prevents callbacks. The complete short implementation establishes that callbacks are not reached if iterable close raises.

**Citation review:** Order citations identify the correct lines. Missing exception guarantee is an unnecessary refusal with the full relevant source present.

**Frozen reference:** Response.close first calls self.response.close if that attribute exists, then invokes each registered _on_close callback in order. There is no try/finally in this method; if the iterable close raises, callbacks are not reached, and a callback exception also interrupts later callbacks.

Reference source anchors:
- [src/werkzeug/wrappers/response.py:403](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L403) — `self.response.close()`
- [src/werkzeug/wrappers/response.py:404](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L404) — `for func in self._on_close:`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [src/werkzeug/wrappers/response.py:402–403](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L402-L403) (`werkzeug.wrappers.response.Response.close`).
- [src/werkzeug/wrappers/response.py:404–405](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L404-L405) (`werkzeug.wrappers.response.Response.close`).

### werkzeug-medium

**Question:** How do force, silent and cache affect Request.get_json MIME-type checks, parse failures, and reuse of cached results?

**Grade:** Incomplete (82.6s).

**Actual DevPilot output:**

> When force is True, Request.get_json will attempt to parse the JSON regardless of the MIME-type [1].
>
> Aspect 2: Some requested details lack valid source citations and could not be established.
>
> When cache is True, Request.get_json will reuse cached JSON results if available [1].

**Source review:** Explains force bypassing MIME check and cache reuse correctly, but omits silent, default 415 MIME errors versus 400 parse errors, cache=False, and separate normal/silent cache-slot behavior. All frozen source anchors were supplied to generation.

**Citation review:** Force and cache reuse cite the correct implementation, though force is applied only after the earlier cache hit check. Most requested error and cache semantics are withheld.

**Frozen reference:** With cache=True a cached result for the current silent slot returns before MIME checking. force=True bypasses the non-JSON MIME check, not parsing. Without force, a MIME mismatch calls the default failure hook and raises UnsupportedMediaType (415), or returns None when silent=True. Parse ValueError becomes None for silent=True, otherwise the default hook raises BadRequest (400). Successful parsing with cache=True fills both normal and silent slots. A silent parse failure caches None only in the silent slot, preserving the normal slot. If an overridden non-silent failure hook returns, its value is cached only in the normal slot, preserving silent. MIME-mismatch early returns do not fill the parsed cache. cache=False skips parsed-cache reuse and writes, and is forwarded to get_data.

Reference source anchors:
- [src/werkzeug/wrappers/request.py:837](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L837) — `if cache and self._cached_json[silent] is not Ellipsis:`
- [src/werkzeug/wrappers/request.py:856](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L856) — `self._cached_json = (normal_rv, rv)`
- [src/werkzeug/wrappers/request.py:885](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L885) — `raise UnsupportedMediaType(`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [src/werkzeug/wrappers/request.py:840–841](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L840-L841) (`werkzeug.wrappers.request.Request.get_json`).
- [src/werkzeug/wrappers/request.py:837–838](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L837-L838) (`werkzeug.wrappers.request.Request.get_json`).
- [src/werkzeug/wrappers/request.py:864–865](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L864-L865) (`werkzeug.wrappers.request.Request.get_json`).

### werkzeug-hard

**Question:** How do StateMachineMatcher.match and MapAdapter.match turn a missing trailing slash, HTTP method mismatch and WebSocket mismatch into a redirect or an HTTP exception, and which mismatch takes precedence?

**Grade:** Incorrect / unsupported (144.5s).

**Actual DevPilot output:**

> StateMachineMatcher.match turns a missing trailing slash into a redirect by raising SlashRequired exception which is caught and re-raised as RequestPath with the path appended with a slash [1].
>
> StateMachineMatcher.match turns an HTTP method mismatch into an HTTP exception by updating have_match_for set and raising NoMatch if no match is found [1].
>
> Aspect 1: Some requested details were not established by the cited source; supported details remain available.
>
> Aspect 1: Some requested details lack valid source citations and could not be established.
>
> Aspect 2: Some requested details were not established by the cited source; supported details remain available.

**Source review:** Explains part of SlashRequired-to-RequestPath and method collection, but incorrectly calls the internal NoMatch an HTTP exception (it inherits Exception). Omits MapAdapter conversion to RequestRedirect/MethodNotAllowed/WebsocketMismatch/NotFound and omits method-before-websocket precedence despite all required anchors reaching the prompt.

**Citation review:** The NoMatch assertion cites matcher lines 98–100 and 166–167, which check the method and update have_match_for, not a NoMatch raise. NoMatch is an internal Exception (routing/exceptions.py:170), not an HTTPException. RequestPath citation starts at 178 and omits the except SlashRequired guard at 177. The same-model reviewer retained the unsupported HTTP-exception claim.

**Frozen reference:** For an otherwise eligible rule behind a trailing slash, the state matcher requires the method and websocket mode to match; strict_slashes raises SlashRequired, converted to RequestPath(path + slash), whereas a non-strict rule can match directly. MapAdapter catches RequestPath, URL-quotes its path, constructs the redirect URL with query arguments, and raises RequestRedirect. The matcher accumulates allowed methods when a rule rejects the method, and marks websocket_mismatch only in the elif when method matches. NoMatch carries both flags. MapAdapter checks nonempty have_match_for first and raises MethodNotAllowed with valid methods; only otherwise websocket_mismatch raises WebsocketMismatch, otherwise NotFound. Thus the method mismatch takes precedence when both are present.

Reference source anchors:
- [src/werkzeug/routing/matcher.py:114](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L114) — `raise SlashRequired()`
- [src/werkzeug/routing/matcher.py:178](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L178) — `raise RequestPath(f"{path}/")`
- [src/werkzeug/routing/map.py:662](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/map.py#L662) — `new_path = quote(e.path_info`
- [src/werkzeug/routing/map.py:678](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/map.py#L678) — `raise MethodNotAllowed(valid_methods=list(e.have_match_for))`

Generated citation locations (source IDs in the output refer to its generation context, preserved in results.json):
- [src/werkzeug/routing/matcher.py:114–116](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L114-L116) (`werkzeug.routing.matcher.StateMachineMatcher.match`).
- [src/werkzeug/routing/matcher.py:178–179](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L178-L179) (`werkzeug.routing.matcher.StateMachineMatcher.match`).
- [src/werkzeug/routing/matcher.py:98–100](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L98-L100) (`werkzeug.routing.matcher.StateMachineMatcher.match`).
- [src/werkzeug/routing/matcher.py:166–167](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L166-L167) (`werkzeug.routing.matcher.StateMachineMatcher.match`).

### aiohttp-unanswerable

**Question:** What is the current production deployment status and live traffic of aiohttp at this moment?

**Grade:** Appropriate abstention (0.0s).

**Actual DevPilot output:**

> The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Source review:** Correctly states that an indexed snapshot cannot establish current deployment status or live traffic. No invented operational facts or model call.

**Frozen reference:** Abstain: an indexed source snapshot cannot establish current production deployment status or live traffic.

### werkzeug-unanswerable

**Question:** What is the current production deployment status and live traffic of werkzeug at this moment?

**Grade:** Appropriate abstention (0.0s).

**Actual DevPilot output:**

> The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Source review:** Correctly states that an indexed snapshot cannot establish current deployment status or live traffic. No invented operational facts or model call.

**Frozen reference:** Abstain: an indexed source snapshot cannot establish current production deployment status or live traffic.

## Retrieval comparison

Recall below is coverage of labelled source symbols in the first five results, averaged over the three answerable questions per repository. It is separate from source-line coverage in the generated prompt and from answer correctness.

| Repository | Lexical Recall@5 | Semantic Recall@5 | Graph Recall@5 | Hybrid Recall@5 |
|---|---:|---:|---:|---:|
| aiohttp | 88.9% | 44.4% | 100.0% | 88.9% |
| werkzeug | 83.3% | 83.3% | 83.3% | 83.3% |

## Findings

The run does not demonstrate reliable, complete repository answering. Most omissions occurred even when the needed source anchors were available. The long aiohttp redirect method also lost two critical anchors during prompt selection. The same-model claim reviewer accepted false redirect conditions, and an unverified negative statement was rendered as declarative text. Symbol retrieval, source-line selection, condition-sensitive generation, review and final rendering each need separate correctness checks.

These cases remain a held-out record for this run. If used to tune implementation later, they should become development cases, and a new unseen set should evaluate the next change.

## Evidence files

- [Raw outputs, claims, generation contexts, timings and hashes](results.json)
- [Frozen questions and reference answers](questions.json)
- [Frozen essential-behavior rubric](review-rubric.json)
- [Per-case source review](source-review.json)
- [Machine-readable summary](summary.json)
- [Pinned snapshots and index diagnostics](snapshots.json)
- [Index log](index.log) and [run log](run.log)
