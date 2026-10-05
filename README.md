# DevPilot AI

**Structure-Aware Repository Intelligence for Autonomous Software Engineering**

DevPilot indexes a public GitHub repository or local folder, extracts source structure, and combines lexical, semantic and graph retrieval to answer repository questions with source evidence. It can detect conservative static issue candidates, localise them, investigate their causes, and draft fixes and regression tests for manual review.

**The core generates candidate fixes and tests for manual review.** The optional behavior-check CLI runs explicitly supplied scenarios in Docker; passing those scenarios does not automatically verify generated answers or drafts. Indexed repositories are immutable snapshots. The core needs neither Docker nor LangGraph. Answers and suggestions can still be wrong; citations establish provenance, not proof of meaning.

See [source reasoning and quality evaluation](docs/behavior-quality.md) for behavior tables, focused reading, generator/reviewer comparisons, isolated checks and the gated local training workflow.

## Start on this Mac

```sh
./setup_and_run.sh
```

Prerequisites: Python 3.11+, Git, Node.js 18+ and npm. The script installs Python/frontend dependencies, builds the UI, and serves it at **http://127.0.0.1:8000**. It recognizes an installed, running Ollama, preferring installed `qwen2.5-coder:14b` over `qwen2.5-coder:7b`, plus `nomic-embed-text:latest`. Explicit provider/model settings take precedence. It does not download large models or install system tools automatically.

For the more capable model already tested on this Mac:

```sh
DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
DEVPILOT_LLM_MODEL=qwen2.5-coder:14b \
DEVPILOT_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1 \
DEVPILOT_EMBEDDING_MODEL=nomic-embed-text:latest \
./setup_and_run.sh
```

If installing Ollama models yourself, run `ollama pull qwen2.5-coder:14b` and `ollama pull nomic-embed-text`. Model memory and response time depend on the Mac. A configured OpenAI-compatible provider is also supported. Export settings from [.env.example](.env.example); the backend does not automatically load `.env` files. Credentials remain on the backend.

Without a chat model, lexical/graph investigation and static analysis work, and issue-based suggestions provide static guidance. Without embeddings, hybrid retrieval falls back to lexical/graph; semantic-only mode reports unavailability.

## Use it

1. Add a public `https://github.com/owner/repository` URL or local directory. Wait for indexing to finish.
2. Inspect **Coverage** for exclusions and **Code explorer** for the immutable stored source.
3. Ask a question in **Investigate**. Click numbered citations to open their source location. Review aspect status and the actual excerpts supplied to the model.
4. Explore **Dependencies** using file/symbol, relationship filters, direction and 0–3 hops. This is the Repository Structural Graph.
5. Run **Error analysis**. Each candidate includes its location, confidence, evidence, candidate cause and suggested action. Unresolved calls alone are not reported as errors.
6. Request a fix/test draft there, or use **Suggestions** for a specific request. Test-only requests reject implementation edits. Review the diff, imports and test assumptions manually.
7. Use **Retrieval diagnostics** for candidate scores and timings; **Research experiments** compares modes and ablations using reviewed expected symbol IDs. **Evaluation** retains the earlier question-review/learning workflow.

For a small nine-language integration example, index `examples/research-repository`. It contains intentional static candidates and is source data, not a runnable application.

## Languages and scope

Tree-sitter adapters support **Python, Java, JavaScript, TypeScript, C, C++, Go, Rust and C#**. Python reuses AST scope resolution; Java reuses declared receiver/import resolution. The other adapters establish selected literal imports, same-file/static calls and limited cross-file relationships. All use normalized symbol metadata.

Support is unequal. Dynamic dispatch, overload/type resolution, macro expansion, generated code, framework wiring, JavaScript CommonJS/default/namespace import resolution, Go module imports, and Rust traits are incomplete. Conditional C/C++ macro definitions are indexed with nearby guards. `.h` uses C++ when its content contains clear C++ constructs and otherwise uses C. Kotlin and Python `.pyi` are searchable text rather than fully analyzed adapters. Grammar recovery can flag valid dialects; see [language capabilities and limitations](docs/language-support.md).

## Architecture and files

| Area | Purpose |
| --- | --- |
| `backend/languages/` | Registry and nine parser/resolver adapters |
| `backend/models.py`, `structure.py`, `structural_metadata.py`, `graph.py` | Normalized entities, declared metadata and bounded structural graph |
| `backend/rag/` | Our custom chunking, BM25, cosine vectors, graph retrieval, weighted RRF, deterministic reranking, context, citations and abstention |
| `backend/errors/` | Static detection, localisation, optional RAG explanation and draft suggestions |
| `backend/api/`, `main.py` | Research APIs and preserved existing HTTP routes |
| `backend/db.py`, `migrations.py` | SQLite storage and additive schema migration |
| `frontend/src/components/` | Separate investigation, explorer, graph/error/suggestion/research, coverage and review pages |
| `backend/legacy/`, `infra/` | Optional historical execution/repair experiments, disabled by default |
| `tests/`, `scripts/`, `evaluation/` | Regression checks, reproducible evaluation and actual result artifacts |

Read [architecture](docs/architecture.md), [file guide](docs/file-guide.md), [custom RAG](docs/custom-rag.md), [error analysis](docs/error-analysis.md), [evaluation](docs/research-evaluation.md), the [implementation report](docs/implementation-2026-10-04.md), and [answer-quality changes and measured limits](docs/quality-2026-10-04.md).

## Existing data and rebuilding

Migration adds normalized metadata and tables for chunks, issues, drafts, retrieval traces and evaluations. Stored snapshot files, fingerprints, existing history and training/review data are retained. Older snapshots display a rebuild action. Rebuilding updates derived indexes from **stored files**; it cannot recover files excluded by an older ingestion policy. Create a new snapshot from the original repository to include those files.

You can also rebuild from the CLI, preferably while the server is stopped:

```sh
.venv/bin/python -m scripts.rebuild_indexes REPOSITORY_ID --embeddings
```

Rebuilding retains vectors only for unchanged identity, signature, source and documentation under the same embedding policy/model revision. Dense embeddings use compact source entities; parameters and type references remain available through full-text and graph retrieval. Historical investigations keep their original source references; refresh reviewed labels before comparing a rebuilt index.

## Development checks

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check backend scripts tests
.venv/bin/python -m ruff format --check backend scripts tests
cd frontend
npm run format:check
npm run build
```

Core installation: `python -m pip install .`. Development tools: `python -m pip install '.[dev]'`. Optional LangGraph: `python -m pip install '.[orchestration]'` and `DEVPILOT_LANGGRAPH_ENABLED=1`; the custom RAG implementation remains independent. Historical execution requires an explicit `DEVPILOT_LEGACY_EXECUTION=1`, Docker and runner setup; it is outside the normal research workflow.

## Evaluation and honest claims

The checked-in research integration fixture tests all nine parsers, cross-file retrieval, static candidates, provider-backed answers and unverified drafts. It is an authored development fixture, **not an independent held-out benchmark**. Existing complex-repository reports are retained; their prior answer failures are not erased by passing new smoke tests. No new fine-tuning was performed in this refactor. Indexing repositories does not change model weights.

The [five fresh repositories evaluation](evaluation/new-five-2026-10-04/REPORT.md) records two indexing failures and incomplete or inaccurate answers on the three successfully indexed repositories. It includes frozen questions, pinned commits, full outputs and source review; passing project tests does not establish real-repository answer accuracy.

Reproduce the local integration in an isolated data directory:

```sh
DEVPILOT_DATA=.devpilot/research-validation \
DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
DEVPILOT_LLM_MODEL=qwen2.5-coder:14b \
DEVPILOT_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1 \
DEVPILOT_EMBEDDING_MODEL=nomic-embed-text:latest \
.venv/bin/python -m scripts.validate_research_prototype --live
```

This command never executes target repository code. It records actual output, unavailable modes and draft failures instead of inventing scores.
