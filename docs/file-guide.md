# Manual file guide

Read the files in this order to follow a question from the browser to repository evidence.

## 1. Start at the application boundary

1. [`frontend/src/main.jsx`](../frontend/src/main.jsx) mounts React.
2. [`frontend/src/App.jsx`](../frontend/src/App.jsx) holds page views, UI state, navigation, and
   API calls.
3. [`frontend/src/style.css`](../frontend/src/style.css) defines the responsive layout and visual
   styling.
4. [`frontend/vite.config.js`](../frontend/vite.config.js) proxies API calls to the backend during
   frontend development.

The backend entry point is [`backend/main.py`](../backend/main.py). It defines API request models,
local-origin checks, application routes, and server startup. Start here to see which module each
endpoint delegates to.

## 2. Follow an indexing job

1. [`backend/ingestion.py`](../backend/ingestion.py) reads a local directory or public GitHub URL,
   filters files, records path-level coverage and the commit/fingerprint, and orchestrates analysis.
2. [`backend/config.py`](../backend/config.py) defines supported file types, limits, ignored
   directories, storage location, and provider environment settings.
3. [`backend/analysis.py`](../backend/analysis.py) extracts modules, classes, functions, methods,
   containment, imports, inheritance, and resolvable calls.
   [`backend/java_analysis.py`](../backend/java_analysis.py) performs the corresponding Java
   extraction with Tree-sitter.
   [`backend/config_links.py`](../backend/config_links.py) adds conservative relationships from
   Python type stubs and Mockito plugin configuration text to indexed symbols.
4. [`backend/providers.py`](../backend/providers.py) optionally builds embeddings after structural
   extraction. The local-only path does not need it.
5. [`backend/db.py`](../backend/db.py) owns the SQLite schema and small connection/data helpers.
   The database and on-disk snapshots are under `.devpilot/`.

The `/coverage` route in `backend/main.py` pages through indexed and skipped paths. The Coverage
tab in `frontend/src/App.jsx` shows the same report. A skipped directory is a boundary: files
inside it were not scanned. `scripts/backfill_coverage.py` reconstructs reference reports at
their pinned commits and reindexes a snapshot only when scanner rules change its fingerprint.
`scripts/backfill_configuration_links.py` updates those selected configuration relationships
on already-pinned snapshots.
[`backend/test_links.py`](../backend/test_links.py) finds related-test candidates from static
references and file names; it does not measure runtime test coverage.

The example project is deliberately small. Start at
[`examples/parcel_service/parcel/api.py`](../examples/parcel_service/parcel/api.py), follow the
imports to `pricing.py` and `models.py`, and compare them with
[`examples/parcel_service/tests/test_pricing.py`](../examples/parcel_service/tests/test_pricing.py).

## 3. Follow a question

1. The `/ask` route in `backend/main.py` validates the question and calls `answer`.
   With Deep investigation selected, it calls [`backend/agent_investigation.py`](../backend/agent_investigation.py)
   to coordinate primary and focused retrieval through LangGraph.
2. [`backend/retrieval.py`](../backend/retrieval.py) ranks text matches, optionally adds embedding
   matches, expands candidates over stored relationships, and selects source evidence.
3. If a chat model is configured, `answer` calls `generate` in `backend/providers.py`; otherwise,
   it returns a retrieval report.
   Paragraph citation checks reject uncited model text and retry once. This is a syntax check,
   not proof that a citation supports a claim.
4. Evidence records include the snapshot path, qualified symbol, line range, retrieval reason, and
   source excerpt.
5. The file endpoint reads from the indexed snapshot in SQLite, even if the original directory has
   changed since indexing.

The dependency view reads `/graph`. Evaluation runs the same retrieval strategies against
user-supplied expected symbol labels.

## 4. Follow a verification job

1. [`backend/proposals.py`](../backend/proposals.py) asks the configured model for a JSON draft,
   validates test paths and source syntax, and returns the draft to the UI for review.
   [`backend/agent_repair.py`](../backend/agent_repair.py) adds a resumable review interrupt and
   before/after verification graph for the guided route.
2. `backend/main.py` checks that Docker is available before accepting an execution request.
3. [`backend/execution.py`](../backend/execution.py) copies the indexed snapshot into a temporary
   directory, validates optional test files or a patch, starts the container, and records results.
4. [`infra/Dockerfile.runner`](../infra/Dockerfile.runner) creates the basic Python/pytest image.
   [`infra/Dockerfile.maven-runner`](../infra/Dockerfile.maven-runner) and
   [`infra/Dockerfile.gradle-runner`](../infra/Dockerfile.gradle-runner) prepare Java dependencies;
   [`scripts/build_java_runner.py`](../scripts/build_java_runner.py) builds them from pinned
   snapshots without editing those snapshots.

The isolation settings and their limits are described in
[`architecture.md`](architecture.md#test-execution-boundary). Tests mock Docker for deterministic
command and timeout checks. A real-container test is skipped if Docker or its prepared runner image
is unavailable.

## 5. Understand the test files

- [`tests/conftest.py`](../tests/conftest.py) isolates each API workflow in a temporary database and
  snapshot directory.
- [`tests/test_api_workflows.py`](../tests/test_api_workflows.py) covers demo indexing, retrieval,
  citations, history, evaluation, and validation through FastAPI routes.
- [`tests/test_analysis_contract.py`](../tests/test_analysis_contract.py) checks source locations,
  imports, inheritance, async/self calls, and unresolved/shadowed references.
- [`tests/test_execution_and_provider_contracts.py`](../tests/test_execution_and_provider_contracts.py)
  checks provider request shapes and mocked container behaviours.
- [`tests/test_java_analysis.py`](../tests/test_java_analysis.py) checks Java extraction.
- [`tests/test_proposals.py`](../tests/test_proposals.py) checks model draft parsing and rejection
  of unsafe test paths.
- [`tests/test_agent_workflows.py`](../tests/test_agent_workflows.py) checks the opt-in deep answer
  and guided repair pause, approval, decline, and Docker boundaries.
- [`tests/test_learning_loop.py`](../tests/test_learning_loop.py) checks human review, source-range
  validation, repository-level splits, reviewed-only exports, and repository data deletion.
- [`tests/test_evaluation_splits.py`](../tests/test_evaluation_splits.py) prevents a repository
  from appearing in both development and holdout evaluation splits.

The `scripts/` directory contains repeatable checks against local Ollama, Docker, and real
repository checkouts. `load_reference_repositories.py` restores the public reference and test
repositories into the local workspace. [`evaluation/cases.jsonl`](../evaluation/cases.jsonl)
contains the reviewed retrieval labels, and
[`scripts/evaluate_dataset.py`](../scripts/evaluate_dataset.py) evaluates them against the pinned
snapshots. The larger [`expanded-cases-v3.jsonl`](../evaluation/expanded-cases-v3.jsonl) mainly
checks symbol lookup; [`workflow-cases.jsonl`](../evaluation/workflow-cases.jsonl) checks four
multi-stage code paths, while [`final-holdout-snapshots.json`](../evaluation/final-holdout-snapshots.json)
reserves a fresh Python/Java pair. [`scripts/review_answers.py`](../scripts/review_answers.py)
prepares pinned local-model
answers for human correctness, support, and abstention review. The
[`scripts/evaluate_agent_investigation.py`](../scripts/evaluate_agent_investigation.py) command
compares evidence-only quick and deep answers, and
[`scripts/validate_langgraph_repair.py`](../scripts/validate_langgraph_repair.py) runs the labelled
synthetic guided-repair fixture through Docker. The
[`evaluation/review-queue/`](../evaluation/review-queue/) cards link source to pending questions;
[`scripts/promote_reviewed_questions.py`](../scripts/promote_reviewed_questions.py) admits only
completed cards to a scored dataset. The
[`backend/learning.py`](../backend/learning.py) module stores pending and source-reviewed question
cases per immutable repository snapshot; the Evaluation screen provides the review form.
[`scripts/export_learning_cases.py`](../scripts/export_learning_cases.py) exports only reviewed
records and writes separate development/holdout corpora with their pinned repository manifest.
[`docs/learning-loop.md`](learning-loop.md) describes review, split isolation, evaluation, and
snapshot deletion. This pipeline improves retrieval evaluation and tuning data; it does not train
model weights.
The
[`evaluation/repairs/`](../evaluation/repairs/) directory documents the repair-task contract and
[`scripts/evaluate_repairs.py`](../scripts/evaluate_repairs.py) runs reviewed tasks in offline
containers. [`scripts/compare_local_models.py`](../scripts/compare_local_models.py) records local
model responses for manual review. See [`evaluation.md`](evaluation.md) and
[`model-comparison.md`](model-comparison.md) for results and limitations.

Run `python -m pytest -q` from the project root to see the complete current test result.
