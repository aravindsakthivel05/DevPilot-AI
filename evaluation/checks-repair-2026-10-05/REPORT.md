# DevPilot: repair-aware validation changes and regression results

**The changes preserve several correct explanations that the previous checks removed. Overall answer accuracy remains limited.**

Main source-reviewed rerun: **1/6 fully adequate**, versus **0/6** before; **3/6 incomplete**, **2/6 incorrect or unsupported**. Both live-state guards passed. All six answerable cases received their frozen source anchors, versus five before.

Median answer time increased from **104.3s** to **114.1s**. This run does not demonstrate a speed improvement.

## Implemented behavior

- Citation expansion uses available original-source coordinates, enclosing Python conditions, exception/finally headers and return sites. It cannot invent omitted lines or prove the resulting claim correct.
- Implicit Python returns and assigned return values can survive the provenance checks; incomplete declarations and unsupported non-None implicit-return claims still fail.
- Executable completeness is tracked separately from omitted docstrings/comments. Terminology casing such as WebSocket/websocket is accepted; missing full configuration identifiers still fail.
- Claim review reports requested-behavior coverage separately. An unsupported verdict must identify bounded, available source coordinates or becomes uncertainty. The reviewer remains fallible.
- Unverified model prose is kept in diagnostics and replaced by neutral uncertainty in the displayed answer. Multiple missing-detail notes within an aspect are deduplicated.
- One bounded correction can read additional candidate sources after concrete rejection/coverage feedback. It must retain previously accepted claim text; timeout, lower reviewed coverage or lost details preserves the initial answer and its citation context.
- The targeted follow-up reserves context space for repair feedback before selecting source excerpts.

Configuration: claim review and bounded repair are enabled by default; `DEVPILOT_REPAIR_REJECTED_CLAIMS=0` disables the extra pass. Explicit environment values override setup defaults. The model weights are unchanged.

## Method and limitations

Local `qwen2.5-coder:14b` with `nomic-embed-text:latest`, hybrid retrieval, limit 8, graph depth 2 and 8192-token context. LangGraph/legacy execution were disabled for this CLI run. The same source-authored questions, labels, reference answers and essential-behavior rubric were reused from the baseline. Labels/reference answers were withheld from generation. These are development regression cases because they informed the implementation, not an unseen accuracy benchmark. Grading is by Codex against source, not an independent human evaluator.

The implementation remained unchanged within each recorded live phase. The main run preceded the small repair-feedback-budget change; that change has a separate targeted routing recheck and an automated budget test. No target repository test suites, patches or training jobs were executed.

## Main run comparison

| Case | Before | After | Before time | After time |
|---|---|---|---:|---:|
| aiohttp-easy | Incomplete | Incomplete | 94.0s | 105.3s |
| aiohttp-medium | Incomplete | Incomplete | 114.5s | 122.9s |
| aiohttp-hard | Incorrect / unsupported | Incorrect / unsupported | 149.3s | 198.4s |
| werkzeug-easy | Incomplete | Correct and adequate | 50.3s | 50.9s |
| werkzeug-medium | Incomplete | Incomplete | 82.6s | 97.0s |
| werkzeug-hard | Incorrect / unsupported | Incorrect / unsupported | 144.5s | 176.4s |
| aiohttp-unanswerable | Appropriate abstention | Appropriate abstention | 0.0s | 0.0s |
| werkzeug-unanswerable | Appropriate abstention | Appropriate abstention | 0.0s | 0.0s |

## Actual answers and source review

### aiohttp-easy

**Question:** How does ClientSession.close handle an owned versus a shared connector, and what happens if the session is already closed?

**Source grade:** Incomplete

**Actual main-run answer:**

> ClientSession.close handles an owned connector by closing it if the session is not already closed [1].
>
> ClientSession.close sets the connector to None after handling it [1].
>
> ClientSession.close checks if the session is already closed before proceeding [1].
>
> If the session is already closed, ClientSession.close does nothing and returns immediately [1].

**Review:** The valid already-closed no-op/implicit return explanation now survives. Shared-connector behavior still is not explicitly contrasted; retained explanations are correct. The same-model coverage reviewer incorrectly labels the aspect complete.

**Change observed:** Previously rejected implicit-return claim retained with expanded original-source citations.

**Frozen reference:** An already-closed session skips the guarded close body. Otherwise, it awaits closing a non-null connector only if connector_owner is true, then clears the session connector reference even for a shared connector. The closed property is true when the connector is None or itself closed; if already closed the guarded body does not clear a retained reference.

Reference source:
- [aiohttp/client.py:1415](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1415)
- [aiohttp/client.py:1425](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L1425)

### aiohttp-medium

**Question:** In BaseConnector.connect and _wait_for_available_connection, how are connection placeholders and queued waiters cleaned up when an awaited operation fails or is cancelled?

**Source grade:** Incomplete

**Actual main-run answer:**

> In _wait_for_available_connection, when an awaited operation fails or is cancelled, the future (fut) is removed from keyed_waiters in the finally block [1].
>
> If keyed_waiters becomes empty after removing fut, the key is deleted from self._waiters [1].
>
> In connect, if an exception occurs during the creation of a connection (in the try-except block), _release_acquired is called to clean up the placeholder [2].
>
> _release_acquired removes the placeholder from _acquired and, if applicable, from _acquired_per_host [4].
>
> It also calls _release_waiter to potentially release a waiter [4].

**Review:** Main cleanup behaviors remain correct. Citation expansion now includes finally at 753 and BaseException at 701. Explicit connection-creation cancellation and re-raising explanations remain absent; semantic completeness does not improve.

**Change observed:** Citation provenance now includes surrounding control-flow conditions.

**Frozen reference:** connect adds an acquired placeholder before traced connection creation; BaseException catches failures including cancellation, calls _release_acquired(key, placeholder), then re-raises. _release_acquired discards it globally, removes it from per-host acquisition if configured, deletes an empty per-host bucket, and releases a waiting slot; it returns early if the connector already closed. The waiter method has a finally block that removes its future and deletes an empty per-key waiter queue, including cancellation or trace exceptions inside the try.

Reference source:
- [aiohttp/connector.py:702](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L702)
- [aiohttp/connector.py:756](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L756)
- [aiohttp/connector.py:840](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/connector.py#L840)

### aiohttp-hard

**Question:** When ClientSession._request follows redirects, which status/method combinations switch to GET and discard the body, when must a body be replayed, and which cookie/authentication state is cleared on an origin change?

**Source grade:** Incorrect / unsupported

**Actual main-run answer:**

> When ClientSession._request follows redirects and encounters status codes 301, 302, 303, 307, or 308, it switches the method to GET and discards the body if the original method was POST [1].
>
> Aspect 1: Some requested details could not be established from the supplied source evidence.
>
> When ClientSession._request follows redirects and the origin changes, it clears the cookie and authentication state [1].
>
> Aspect 2: Some requested details could not be established from the supplied source evidence.

**Review:** Still incorrectly says 307/308 POST switches to GET. Body replay and consumed-payload errors remain unexplained; the three cleared header names are absent. Authentication clearing now cites the actual clearing code. A formerly displayed unverified negative assertion is replaced by neutral uncertainty.

**Change observed:** All three source anchors reach context; cross-origin clearing citation is corrected; unverified declarative text is removed. A duplicate-heavy correction fails formatting and preserves the initial accepted answer.

**Frozen reference:** When redirect following is enabled, among 301/302/303/307/308, 303 except HEAD and 301/302 POST rewrite to GET, set data=None and remove a present Content-Length header. Other combinations preserve the method and reuse req._body (307/308, non-POST 301/302, and HEAD 303); a consumed payload causes response.close and ClientPayloadError instead of empty replay. On origin change cookies=None and all Authorization, Cookie and Proxy-Authorization header entries are removed. This code does not assign auth=None.

Reference source:
- [aiohttp/client.py:818](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L818)
- [aiohttp/client.py:834](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L834)
- [aiohttp/client.py:895](https://github.com/aio-libs/aiohttp/blob/715ddc33a388ba8ccc86dc6bedf36e06ba42ad43/aiohttp/client.py#L895)

### werkzeug-easy

**Question:** What order does Response.close use for closing the wrapped iterable and running registered callbacks, and does it guarantee callbacks run if the iterable close raises?

**Source grade:** Correct and adequate

**Actual main-run answer:**

> Response.close first closes the wrapped iterable if it has a close method [1].
>
> Response.close then runs all registered callbacks in the order they were added [1].
>
> Response.close does not guarantee that callbacks will run if the iterable's close method raises an exception [1].
>
> Aspect 1: Some requested details could not be established from the supplied source evidence.

**Review:** Covers iterable-first order, callback registration order and lack of a callback guarantee if iterable close raises. This answers the essential question correctly. A neutral, unnecessary missing-details note remains from the model draft.

**Change observed:** Executable completeness allows the correct exception-behavior claim to survive.

**Frozen reference:** Response.close first calls self.response.close if that attribute exists, then invokes each registered _on_close callback in order. There is no try/finally in this method; if the iterable close raises, callbacks are not reached, and a callback exception also interrupts later callbacks.

Reference source:
- [src/werkzeug/wrappers/response.py:403](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L403)
- [src/werkzeug/wrappers/response.py:404](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/response.py#L404)

### werkzeug-medium

**Question:** How do force, silent and cache affect Request.get_json MIME-type checks, parse failures, and reuse of cached results?

**Source grade:** Incomplete

**Actual main-run answer:**

> When force is True, Request.get_json will attempt to parse the JSON regardless of the MIME-type [1].
>
> When silent is True, Request.get_json will suppress exceptions and return None on parse failures [1].
>
> When cache is True, Request.get_json will reuse cached JSON results if available [1].

**Review:** Correctly covers force bypassing MIME checks, silent returning None on parse failure, and cache reuse. Missing default MIME/parse error types, cache=False and separate cache-slot behavior leave the answer incomplete. The same-model coverage reviewer still incorrectly labels every aspect complete.

**Change observed:** The formerly rejected assigned-return-value explanation survives with expanded citations.

**Frozen reference:** With cache=True a cached result for the current silent slot returns before MIME checking. force=True bypasses the non-JSON MIME check, not parsing. Without force, a MIME mismatch calls the default failure hook and raises UnsupportedMediaType (415), or returns None when silent=True. Parse ValueError becomes None for silent=True, otherwise the default hook raises BadRequest (400). Successful parsing with cache=True fills both normal and silent slots. A silent parse failure caches None only in the silent slot, preserving the normal slot. If an overridden non-silent failure hook returns, its value is cached only in the normal slot, preserving silent. MIME-mismatch early returns do not fill the parsed cache. cache=False skips parsed-cache reuse and writes, and is forwarded to get_data.

Reference source:
- [src/werkzeug/wrappers/request.py:837](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L837)
- [src/werkzeug/wrappers/request.py:856](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L856)
- [src/werkzeug/wrappers/request.py:885](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/wrappers/request.py#L885)

### werkzeug-hard

**Question:** How do StateMachineMatcher.match and MapAdapter.match turn a missing trailing slash, HTTP method mismatch and WebSocket mismatch into a redirect or an HTTP exception, and which mismatch takes precedence?

**Source grade:** Incorrect / unsupported

**Actual main-run answer:**

> StateMachineMatcher.match turns a missing trailing slash into a redirect by raising SlashRequired exception which is caught and re-raised as RequestPath with the path appended with a slash [1].
>
> Aspect 1: Some requested details could not be established from the supplied source evidence.
>
> MapAdapter.match handles the exceptions raised by StateMachineMatcher.match and converts them into appropriate HTTP exceptions: RequestPath becomes RequestRedirect, NoMatch with have_match_for set raises MethodNotAllowed, NoMatch with websocket_mismatch set raises WebsocketMismatch, and any other NoMatch raises NotFound [2] [1].
>
> The precedence of mismatches is determined by the order in which they are checked: missing trailing slash takes precedence over HTTP method mismatch and WebSocket mismatch [1].

**Review:** Caller-to-adapter HTTP exception conversion now survives source-identity checks with both source identities cited. However, the answer wrongly asserts missing-slash precedence and omits method-before-websocket precedence. Unsupported claims that the matcher itself raises MethodNotAllowed/WebsocketMismatch are appropriately withheld. A correction exceeds the context budget, retaining the original answer.

**Change observed:** The correctly attributed MapAdapter workflow survives; terminology casing no longer removes the precedence claim, but the retained claim is itself incorrect.

**Frozen reference:** For an otherwise eligible rule behind a trailing slash, the state matcher requires the method and websocket mode to match; strict_slashes raises SlashRequired, converted to RequestPath(path + slash), whereas a non-strict rule can match directly. MapAdapter catches RequestPath, URL-quotes its path, constructs the redirect URL with query arguments, and raises RequestRedirect. The matcher accumulates allowed methods when a rule rejects the method, and marks websocket_mismatch only in the elif when method matches. NoMatch carries both flags. MapAdapter checks nonempty have_match_for first and raises MethodNotAllowed with valid methods; only otherwise websocket_mismatch raises WebsocketMismatch, otherwise NotFound. Thus the method mismatch takes precedence when both are present.

Reference source:
- [src/werkzeug/routing/matcher.py:114](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L114)
- [src/werkzeug/routing/matcher.py:178](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/matcher.py#L178)
- [src/werkzeug/routing/map.py:662](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/map.py#L662)
- [src/werkzeug/routing/map.py:678](https://github.com/pallets/werkzeug/blob/594452f6a4fe4de38a544962fbf04bfc9d37fbc2/src/werkzeug/routing/map.py#L678)

### aiohttp-unanswerable

**Question:** What is the current production deployment status and live traffic of aiohttp at this moment?

**Source grade:** Appropriate abstention

**Actual main-run answer:**

> The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Review:** Appropriately abstains from inventing live deployment or traffic information.

**Frozen reference:** Abstain: an indexed source snapshot cannot establish current production deployment status or live traffic.

### werkzeug-unanswerable

**Question:** What is the current production deployment status and live traffic of werkzeug at this moment?

**Source grade:** Appropriate abstention

**Actual main-run answer:**

> The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Review:** Appropriately abstains from inventing live deployment or traffic information.

**Frozen reference:** Abstain: an indexed source snapshot cannot establish current production deployment status or live traffic.

## Targeted feedback-budget recheck

**werkzeug-hard**, 215.8s. Prompt-budget rejection: False. Selected generation attempt: 1.

> StateMachineMatcher.match turns a missing trailing slash into a redirect by raising SlashRequired exception which is caught and re-raised as RequestPath with the path appended with a slash [1].
>
> Aspect 1: Some requested details could not be established from the supplied source evidence.
>
> MapAdapter.match handles the exceptions raised by StateMachineMatcher.match and converts them into appropriate HTTP exceptions: RequestPath becomes RequestRedirect, NoMatch with have_match_for set raises MethodNotAllowed, NoMatch with websocket_mismatch set raises WebsocketMismatch, and any other NoMatch raises NotFound [2] [1].
>
> The precedence of mismatches is determined by the order in which they are checked: missing trailing slash takes precedence over HTTP method mismatch and WebSocket mismatch [1].

**werkzeug-unanswerable**, 0.0s. Prompt-budget rejection: False. Selected generation attempt: N/A.

> The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Targeted review (werkzeug-hard):** The correction now fits the 8192-token prompt budget and completes generation/review. It retains the original three accepted claims but does not improve reviewed coverage, so the first answer is selected. The source-based routing-precedence error remains; the model reviewer still incorrectly approves it. This validates feedback-budget handling and fallback, not answer correctness.

**Targeted review (werkzeug-unanswerable):** Still appropriately abstains from inventing live deployment and traffic.

## Remaining limitations

The model still misreads redirect conditions and routing precedence, and the same-model reviewer can approve these mistakes or incorrectly mark incomplete coverage as complete. A neutral missing-details note can remain even when the essential question is answered. Literal retained-text preservation protects against lost details but may reject a useful paraphrase. Citation validity, executable coverage, model acceptance and passing application tests do not prove general answer correctness.

## Verification and evidence

Automated suite: **233 passed, 1 skipped**. Ruff lint/format, frontend Prettier/build and bootstrap shell syntax checks passed.

- [Raw main-run outputs and diagnostics](results.json)
- [Per-case source review](source-review.json)
- [Frozen questions](questions.json) and [grading rubric](review-rubric.json)
- [Main-run settings](run-settings.json) and [final project checks](project-checks.json)
- [Targeted budget-check raw outputs](budget-recheck/results.json)
- [Implementation guide](../../docs/repair-aware-validation.md)
