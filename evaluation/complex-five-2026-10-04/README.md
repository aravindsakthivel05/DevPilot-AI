# Five complex repositories: 2026-10-04

Evaluation-only snapshots of SQLAlchemy, Celery, Scrapy, MyBatis and Resilience4j. Full repository roots were scanned with DevPilot’s existing supported-file limits. Unsupported files and ignored directories are recorded in `snapshots.json`; this is not whole-language semantic understanding.

- `questions.jsonl`: 15 source-backed questions (one easy, medium and hard per repo) plus five equivalent private live-state checks. Expected source ranges distinguish Java overloads and include indexed Python decorators. Rubrics are not provided to the model.
- `snapshots.json`: pinned commits, fingerprints, file/symbol counts, parser and coverage information, indexing timing, evaluation-only labels.
- `expected-source-evidence.json`: numbered expected source, original file hashes and commit-specific GitHub links.
- `results.json`: full Quick pipeline on all questions, LangGraph Deep on hard and private-state questions. One repeat, existing Qwen 7B, native 8192 context, audit enabled, no embeddings. Written incrementally.
- `source-review.json`: separate Codex source review; not independent human review. Assesses delivered answer correctness, completeness and support by exact cited lines. Citation-validator or model-audit acceptance alone is not factual accuracy.
- `diagnostics/`: the interrupted initial run retained but excluded from final scores.

No model weights, production backend source, training cases or existing repository database were changed. The isolated evaluation database is `.devpilot/complex-five-2026-10-04`; checkouts are `.devpilot/complex-five-checkouts`.

This evaluates DevPilot’s repository indexing, retrieval and question answering. It does not execute the upstream projects’ entire test suites, deploy their services, or evaluate generated patches. Complexity labels are qualitative descriptions of their architecture, not a standardized benchmark classification. Timings are single-run observations on this Mac.
