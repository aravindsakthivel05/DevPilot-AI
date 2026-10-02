# DevPilot AI

DevPilot indexes Python and Java repositories, extracts source symbols and dependency links, then searches
that snapshot to answer repository questions with file and line references. If configured, it can
add semantic embeddings and a local or hosted language model. Source files are not sent to a provider unless
you configure one.

The **Coverage** tab lists indexed paths and skipped paths with reasons. Ignored directories are
reported as directories; DevPilot does not inspect their contents. Existing reference snapshots
have coverage reports from their pinned commits in
[`reference-coverage.json`](docs/reference-coverage.json).
The code explorer also suggests related tests using static call/import references and file-name
matches. These are leads for review, not proof that a test executes a given line.
The question toolbar offers **AI explanation** and **Evidence only**. Evidence only returns source
locations without asking the model to synthesize an answer.
When `DEVPILOT_LANGGRAPH_ENABLED=1`, **Deep investigation** uses a bounded LangGraph workflow
for focused follow-up retrieval. **Quick answer** keeps the original one-pass path. The
Verification screen also offers a guided repair that pauses for review before running the saved
draft in Docker. [`docs/langgraph.md`](docs/langgraph.md) explains the workflow and measured costs.

This is a local research prototype. It uses SQLite, Python's standard-library AST parser, and
Tree-sitter for Java. The graph contains definitions, containment, imports, inheritance, and
conservatively resolved calls. Dynamic dispatch and some imports can remain unresolved.

## Repository map

| Path | What is here |
| --- | --- |
| `backend/` | HTTP API, ingestion, static analysis, retrieval, providers, and test execution |
| `frontend/` | React interface, styles, Vite setup, and browser build |
| `examples/parcel_service/` | Small, readable, cross-file Python project used by the demo |
| `tests/` | API workflows, analysis contracts, and provider/container checks |
| `infra/` | Docker image definitions for isolated Python and Maven test runners |
| `docs/` | Architecture, data flow, and file-by-file reading guide |
| `scripts/` | Reproducible real-repository, model, and container validation commands |
| `pyproject.toml` | Python dependencies, development tools, and test/format settings |
| `.env.example` | Provider configuration variable names; no real credentials |

See [the file guide](docs/file-guide.md) for a reading order and
[the architecture note](docs/architecture.md) for the main workflows. The
[improvement status](docs/progress.md) separates live-validated features from the remaining
data-collection and optional fine-tuning work.

DevPilot can save an investigation into a local review queue, validate human-provided expected
symbols and source ranges, then export reviewed cases into repository-separated development and
holdout datasets. This improves retrieval evaluation; it does not automatically fine-tune the
configured model. See the [reviewed learning loop](docs/learning-loop.md) for the workflow and
snapshot deletion controls.

## Run locally

Requirements: Python 3.11+, Node.js, and npm. Docker is needed only to run indexed repositories'
tests inside the isolation container. A model provider is optional.

From the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

In `frontend/`, install and build the UI:

```sh
npm install
npm run build
```

Start the backend from the project root:

```sh
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The backend serves the built UI from
`frontend/dist/`. Choose **Try the example** to index `examples/parcel_service`, or add a local
directory or public GitHub repository. For frontend development with hot reload, keep Vite running
in another terminal:

```sh
cd frontend
npm run dev
```

## Optional model provider

DevPilot uses the OpenAI-compatible chat-completions and embeddings API shape. Set these variables
in the backend environment before starting it. Do not put real credentials in `.env.example` or
commit them to the repository.

```sh
export DEVPILOT_LLM_BASE_URL="https://provider.example/v1"
export DEVPILOT_LLM_MODEL="your-chat-model"
export DEVPILOT_PROPOSAL_MODEL="your-code-model" # optional; defaults to chat model
export DEVPILOT_EMBEDDING_MODEL="your-embedding-model"
export DEVPILOT_API_KEY="your-key"
```

Leave the embedding model empty for text and graph retrieval only. After enabling embeddings, create
a fresh repository snapshot so it builds the vector index. A configured provider receives question
text and retrieved source excerpts when those features are used. Health reports whether a provider
is configured, but does not check the credentials.

For the local Ollama models validated on this Mac, start Ollama and run `make api-local` after
installing `llama3.2:latest`, `qwen2.5-coder:7b`, and `nomic-embed-text`. This uses Llama for
repository answers and Qwen for Python or Java test/patch drafts, both through the local endpoint. The
`api-local` target also enables the opt-in LangGraph controls. Plain `make api` leaves them off
unless `DEVPILOT_LANGGRAPH_ENABLED=1` is set.

When the chat base URL points to local Ollama on port `11434`, DevPilot automatically uses
Ollama's native chat endpoint for schema-constrained answer output and keeps the model loaded for
10 minutes. Set `DEVPILOT_OLLAMA_NATIVE_API=0` to use the OpenAI-compatible endpoint, or adjust
`DEVPILOT_OLLAMA_KEEP_ALIVE` to change the local model's keep-alive period.
The Verification screen can generate a review draft of tests and
an optional patch. The draft is not an execution result; use **Run verification** to compare tests
before and after the patch in Docker.
For source changes, the proposal model supplies exact old/new snippets; DevPilot constructs and
preflights the unified diff before showing it. A demo generated test and patch have passed
fail-before/pass-after verification in the isolated runner; see
[model validation](docs/model-validation.json). The Java runner has also passed a hand-authored
fail-before/pass-after regression; a local model-authored Java draft has not yet passed that check.
See [the progress report](docs/progress.md) for the exact validation status.

## Checks

```sh
python -m pytest -q
ruff format --check backend tests examples
cd frontend && npm run format:check && npm run build
```

Container execution requires a running Docker engine and a built runner image. On this Mac, Docker
CLI with Colima is installed; start the engine with `colima start` if it is stopped:

```sh
docker build -f infra/Dockerfile.runner -t devpilot-runner:local .
```

Build repository-specific Java images with `.venv/bin/python -m scripts.build_java_runner`
followed by `petclinic`, `commons-lang`, or `mockito`. The two Maven images and the Gradle image
cache dependencies during the build so their selected tests can run offline in disposable,
network-disabled containers. The Mockito runner disables Gradle's build cache at execution time
so a passing result reflects tests run for that snapshot, rather than a cached test result.

Then use **Verification** for the selected repository. The image must provide its dependencies.

The repeatable evaluation dataset is in `evaluation/cases.jsonl`. Run
`.venv/bin/python -m scripts.evaluate_dataset > evaluation/baseline.json` to score retrieval on
the pinned local snapshots. To compare installed Ollama models on identical evidence, run
`.venv/bin/python -m scripts.compare_local_models llama3.2:latest qwen2.5-coder:7b --cases 8`.
Model comparison records answers, citation syntax, and time for manual review; it does not grade
factual correctness. See the [local comparison notes](docs/model-comparison.md).

For source-backed answer evaluation, use
`.venv/bin/python -m scripts.review_answers prepare --output evaluation/answer-review.jsonl`
with a local model configured, review the resulting correctness/support/abstention fields against
the pinned source, then run
`.venv/bin/python -m scripts.review_answers score evaluation/answer-review.jsonl`. Valid citation
markers alone do not
prove the answer is correct. Reviewed regression tasks use
[`scripts/evaluate_repairs.py`](scripts/evaluate_repairs.py); see the
[`evaluation/repairs/` guide](evaluation/repairs/README.md). The included Commons Lang repair
fixture is synthetic and is not a real-issue success count.

## Current boundaries

- Indexing reads source files. It does not run them.
- Python and Java source plus common text/documentation formats are indexed. Large, binary,
  secret, and generated files are excluded; limits live in `backend/config.py`.
- This structural graph is not a compiler-grade Code Property Graph. Runtime Python relationships
  can remain unresolved.
- Citation-number range checks do not prove that the cited code supports a claim.
- Retrieval evaluation measures whether labelled symbols are returned. It does not grade answer
  correctness.
- An experimental local QLoRA run used repository-tree metadata to teach transferable structure
  analysis. It failed its four-repository held-out check and is not enabled in DevPilot. See the
  [training setup and measured result](docs/local-training.md) before considering another run.
- [Real-repository evaluation](docs/evaluation.md) records retrieval results on all eight
  repositories from the reference document. [Model validation](docs/model-validation.json) and
  [container validation](docs/container-validation.json) record the local smoke tests.
- All eight reference repositories are loaded as persistent local snapshots. Their exact commits
  and IDs are in [indexed-reference-repositories.json](docs/indexed-reference-repositories.json).
  Run `make load-references` to restore any missing snapshots from the public GitHub URLs.
- The 15 repositories in the test repository document are also indexed locally. Seven were added
  in this corpus update; 175 source-linked review candidates are pending verification. Indexing
  makes source available for retrieval, while the separate tree-only experiment described above
  trains an adapter; see [their snapshot manifest](evaluation/training-repository-snapshots.json)
  and the [learning-loop guide](docs/learning-loop.md).
- A passing test covers only the tests that actually ran.
- SQLite keeps local setup simple. Multi-user service and production deployment are outside the
  current prototype.
