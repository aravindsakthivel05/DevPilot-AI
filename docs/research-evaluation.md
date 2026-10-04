# Research evaluation

Keep source retrieval, factual answer support, error detection and fix quality separate. Passing API/syntax tests is not evidence of general repository understanding.

`POST /api/repositories/{id}/research-evaluate` accepts questions with reviewed expected **indexed symbol IDs**. It checks that IDs exist in the snapshot and compares lexical, semantic, graph, hybrid, no graph/semantic/lexical/structure/reranking, 1/3 hops, and alternative graph weights. The lexical baseline disables structural reranking, with `lexical_structured` reported separately. Actual ranks yield Recall, Precision, MRR, NDCG and all-required-evidence at 5/10. Semantic-only and no-lexical runs report unavailability when a complete embedding corpus cannot seed retrieval. Graph mode uses lexical seeds; hybrid can use lexical and semantic seeds; its results must be described accordingly.

`detection_metrics` measures exact type/file/line precision/recall/F1 with explicit false positives and negatives. True negatives remain unavailable without a labelled negative population; unflagged source lines are not automatically correct cases. It requires complete reviewed expected candidates; confidence is not a truth label. Static errors remain candidates even when a fixture is correctly localized. `scripts/validate_research_prototype.py` records the two intentionally labelled fixture candidates, real provider outputs, abstention, drafts and source snapshots in an isolated data directory.

Answer correctness and citation support need separate source review of each accepted claim, including owners, conditions, arguments, return expressions and call order. Do not count citation syntax as entailment. Draft quality likewise needs review of patch relevance, framework imports, expected behavior, source compatibility and useful regression assertions. Existing `learning_cases` stores pending/reviewed labels, repository development/holdout splits and reviewed targets; raw model answers are not training truth.

## Reproducible datasets

The small checked-in nine-language repository and `evaluation/implementation-2026-10-04/research-cases.json` are authored **development** fixtures. They cover parsing, a Python guard, TypeScript delegation, C++/Go lookup, static localisation and unsupported deployment state. They do not prove generalization or balanced language coverage. Prior public-repository datasets/reports remain under `evaluation/`; the Pydantic index smoke check is not a new held-out answer benchmark.

For defensible research, freeze commits and source-backed questions across languages and frameworks. Include definitions, call/dependency traces, inheritance, exceptions, configuration, tests, architectural questions and unanswerable requests. Keep entire repositories in development or holdout; tune only development examples. Use independent reviewers for held-out answers and candidate fixes. Record confidence, omissions and wrong answers, not only successful generations. No new local model fine-tuning was performed during this implementation.

## Timing

Ingestion records read/snapshot, analysis+graph, chunk/storage, embedding and total time. Retrieval records lexical, semantic, fusion/seed reranking, graph, reranking, context-record and total timings. Answer diagnostics record provider request/generation/audit durations and usage where returned, plus total response time. Token planning estimates are distinct from provider-reported usage. Small fixture gains and warm model timings should not be extrapolated to huge repositories.
