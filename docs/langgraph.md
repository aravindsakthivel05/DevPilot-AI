# LangGraph integration

DevPilot has two question paths. **Quick answer** calls the existing retrieval and answer code.
**Deep investigation** runs a bounded LangGraph state machine. The switch is explicit in the UI
and requires `DEVPILOT_LANGGRAPH_ENABLED=1`; `make api-local` sets it. Evidence-only deep runs
still avoid an LLM call. Both paths use the same answer and citation policy.

The investigation graph checks for explicit live/private/future-state questions, runs primary
retrieval, assesses candidate coverage for up to six aspects, and performs at most two focused
rounds. The first round considers every aspect of a compound question; later searches consider
missing candidate evidence. No new candidates stops further work. Outgoing calls, inheritance,
decorator, alias and selected configuration relationships can supply helpers. Candidate coverage
is a lexical heuristic, never factual completion. The original ranked primary matches are retained
and bounded supplemental evidence is appended, with at most fifteen evidence entries. Source
IDs, ranks, and relationship reasons flow through graph state; source excerpts are loaded from
the pinned snapshot only when composing the final answer. No extra model call plans a query.

The guided repair graph is separate: draft → review interrupt → existing baseline → generated
baseline → generated patched → existing patched → outcome. The draft must include a test and
applicable patch. Approval runs the **saved** draft;
decline performs no Docker work. The UI also retains its manual proposal and verification path.
Each run has a repository fingerprint, so a changed snapshot cannot silently resume. LangGraph
checkpoints use `.devpilot/agent-checkpoints.sqlite3`; `agent_runs` in the application database
stores API status. On restart, an interrupted running verification is marked failed, while a
draft paused for review can still resume. A reported test transition is limited to the selected
generated regression and selected existing tests. Complete structured reports must show the same
testcase failing before and passing after, plus no regression in previously passing selected
existing testcases. Missing reports, zero tests and a success exit code alone do not establish it.

## Measured retrieval cost and coverage

The current October 3 checkpoint is [workflow-final.json](../evaluation/accuracy-2026-10-03/workflow-final.json):
54.2% Quick and 54.2% Deep recall@8 on four development questions, with 558 ms and 1022 ms
mean response respectively. The bounded supplement did not add labelled hits on this set.
Deep is optional; this result does not establish a benefit over the improved Quick path.
The table below retains the earlier implementation's measurements for comparison.

The final comparison used the same pinned snapshots and no model calls. Both timed paths now
produce a complete evidence-only answer; earlier development files timed quick retrieval alone:

| Reviewed set | Quick recall@8 | Deep recall@8 | Mean quick response | Mean deep response |
| --- | ---: | ---: | ---: | ---: |
| 4 multi-stage workflow questions | 37.5% | 54.2% | 269 ms | 611 ms |
| 64 mostly symbol-seeded questions | 84.4% | 84.4% | 267 ms | 313 ms |
| 12 Click/JUnit4 checkpoint questions | 83.3% | 83.3% | 175 ms | 211 ms |

The [workflow](../evaluation/langgraph-workflow-response-checkpoint.json),
[symbol](../evaluation/langgraph-symbol-response-checkpoint.json), and
[Click/JUnit4](../evaluation/langgraph-clean-holdout-response-checkpoint.json) reports contain case-level
results. These are retrieval measurements, not answer correctness. Four workflow questions are
far too few to predict broad accuracy; the new urllib3/Commons Collections final holdout remains
unscored. Deep retrieval can be slower, especially on large repos; quick requests do not enter
LangGraph. No parallel Ollama calls were added because local model contention could increase
latency. No node cache was added before profiling repeat queries and invalidation by fingerprint.

Run `python -m scripts.evaluate_agent_investigation --dataset evaluation/workflow-cases.jsonl
--output /tmp/devpilot-agent-check.json` to repeat a development comparison. The guided graph
has unit tests for pause, approval, decline, and response shape. The controlled
`scripts.validate_langgraph_repair` fixture checks checkpoint/resume and live offline Docker;
it does not claim a model-authored or real-issue repair. A live Qwen2.5-Coder draft for the
parcel demo reached the review interrupt but was [declined](langgraph-guided-model-smoke.json):
it proposed accepting zero weight even though the existing validation rejects it, and its
change came after that validation call. The graph made no Docker call for that declined draft.

## Current default

LangGraph is now an optional dependency (`pip install '.[orchestration]'`) and defaults to disabled in `setup_and_run.sh`. The core custom RAG engine works without it. Optional Deep investigation retains per-pass traces. Guided execution also requires the separate legacy execution flag; it is outside the recommendation-based research workflow. See [current architecture](architecture.md).
