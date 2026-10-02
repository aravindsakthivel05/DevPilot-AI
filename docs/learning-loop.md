# Cross-repository reviewed learning loop

DevPilot now keeps reviewed examples separately from repository source indexes. This is a
repeatable data and evaluation loop; it does **not** update a chat model's weights or treat model
outputs as labels.

## Repository memory

Each ready repository has a persistent SQLite record, an immutable content fingerprint, an index,
and a local source snapshot under `.devpilot/snapshots/<repository-id>`. Select that repository
again in the app to reuse its index. A new repository still needs its own ingest and index before
DevPilot can cite its source. The question retrieval APIs always scope evidence to the selected
repository snapshot.

Use `DELETE /api/repositories/{repository_id}` only when you want that repository removed. The
endpoint removes its SQLite data (including investigations and learning cases) and its local
source snapshot. It refuses to run while indexing is in progress. This is a local application;
it does not upload reviewed cases to a shared service.

## Review a question

1. Ask a repository question in the app.
2. From its answer or evidence report, choose **Queue for review**. This stores the question,
   snapshot ID, and a compact record of the DevPilot response and evidence as a pending case.
3. Open **Evaluation → Review queue**. Check the full indexed file before entering expected
   qualified symbols, the expected answer, source ranges, and review notes. Mark a case
   unanswerable when the pinned snapshot cannot support an answer.
4. For generated model answers, explicitly label answer correctness and whether each claim is
   supported. The UI requires a Yes/No decision; an unmarked field is not treated as reviewed.
5. Choose the repository's split on its first reviewed case. Every later case from that same
   repository must use that split, so a repository cannot leak between development and holdout.

The API is also available directly:

- `POST /api/repositories/{id}/learning-cases` with `question` and optional saved `investigation_id`
- `GET /api/repositories/{id}/learning-cases?status=pending`
- `POST /api/repositories/{id}/learning-cases/{case_id}/review`

The review endpoint validates that each expected symbol and line range exists inside the pinned
repository index. It keeps prior review versions in `review_history` if labels are corrected.
For generated answers, use the indexed files to assess claim support; matching quote text alone
does not prove that a citation entails a claim.

## Export and evaluate

Export only reviewed cases; pending cases are ignored. The command creates separate development
and holdout JSONL files plus the exact repository-ID/fingerprint manifest needed by the evaluator.
It refuses to overwrite existing files.

```sh
python -m scripts.export_learning_cases \
  --development evaluation/learning-development.jsonl \
  --holdout evaluation/learning-holdout.jsonl \
  --manifest evaluation/learning-manifest.json
```

Evaluate development cases while changing retrieval logic:

```sh
python -m scripts.evaluate_dataset \
  --dataset evaluation/learning-development.jsonl \
  --manifest evaluation/learning-manifest.json
```

Run the holdout evaluation only after choosing the change to keep. Once a holdout result has
guided tuning, those repositories are no longer an untouched holdout; reserve new repositories
for the next final check. The split is assigned per repository, not per question.

Review data can improve query decomposition, symbol ranking, language analysis, and regression
coverage when it is used to compare changes on the development set. DevPilot does not presently
train or fine-tune a model from this data. Any later local fine-tuning should use only reviewed
expected answers and source labels, run offline, and be evaluated against untouched repositories.
Do not promote generated answers without human verification.

## Additional repository corpus

The 15 repositories listed in `testreposlink.docx` are recorded in
[`training-repository-catalog.json`](../evaluation/training-repository-catalog.json), with pinned
commit IDs and source fingerprints in
[`training-repository-snapshots.json`](../evaluation/training-repository-snapshots.json). Eight
were already indexed. Seven additional repositories are now indexed in the local workspace.
Django, PyTorch, and Elasticsearch Java use explicit primary-source scopes because full checkouts
exceed the default index limits; their exact scopes and the elevated indexing limits for the two
larger snapshots are recorded in the catalog and manifest. Their indexed files are pinned to the
upstream commits shown in the manifest.

The seven additional snapshots each have 25 source-linked candidate cards under
[`review-queue-testrepos/`](../evaluation/review-queue-testrepos/). All 175 cards remain pending:
they are source excerpts for a reviewer to turn into realistic questions and verified answers,
not training or evaluation labels. The eight earlier repositories retain their existing review
queues and reviewed examples. No model weights were updated. Exported learning data must still
come only from cases reviewed against the full pinned source; preserve the existing repository
split rules and keep the clean holdout snapshots out of tuning.

To restore the seven added snapshots from the pinned public repositories, run:

```sh
DEVPILOT_MAX_INDEX_FILES=10000 DEVPILOT_MAX_INDEX_BYTES=100000000 \
  .venv/bin/python -m scripts.load_reference_repositories \
  fastapi spring-data-elasticsearch django numpy scikit-learn pytorch elasticsearch-java
```

The scoped Django, PyTorch, and Elasticsearch Java checkouts are sparse clones kept under
`.devpilot/reference-checkouts/`. Their database source paths point to the selected code roots;
the catalog preserves the canonical GitHub URL and selected root for review.
