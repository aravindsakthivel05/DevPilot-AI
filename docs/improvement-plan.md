# Reliability improvement plan

This is the working checklist for the approved eight-stage plan. A stage is complete only when
its exit criterion is met; a passing smoke test does not close a broader stage.

| Stage | Current state | Exit criterion |
| --- | --- | --- |
| 1. Freeze baseline | Complete | Eight pinned snapshots, original 24-case result, and pre-improvement copy retained. |
| 2. Evaluation labels | In progress | 20–30 realistic source-reviewed questions per reference repo, including answerable and unanswerable cases; larger independent Python/Java holdout. |
| 3. Repository structure | In progress | Coverage audit and validated Python/Java relationships, test links, configuration and documentation links on representative repos. |
| 4. Retrieval | In progress | Development gains without regression, then a fixed clean-holdout checkpoint with case-level results. |
| 5. Answers | In progress | Reviewed correctness, citation support, and abstention metrics on a broad question set; false claims measurably reduced. |
| 6. Change workflow | In progress | Model-authored Python and Java regression test plus applicable patch each fail before and pass after in offline containers. |
| 7. Real repairs | Not yet complete | 30–50 reviewed real issues at pinned commits with provenance, distinctive failure, patch, and repeatable before/after result. |
| 8. Local training decision | Deferred | Compare local models and prompts on verified tasks; train locally only if an adapter has enough data and improves the untouched holdout. |

The source of truth for measured results and known failures is [progress.md](progress.md).
Dataset protocols live in [evaluation/README.md](../evaluation/README.md) and the
[repair task guide](../evaluation/repairs/README.md). Do not use synthetic fixtures as real
repair successes or citation syntax as an answer-support score.
