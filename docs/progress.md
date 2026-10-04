# DevPilot improvement status

**Latest checkpoint: October 3, 2026.** See [the accuracy report](accuracy-2026-10-03.md)
for current behavior, test results and remaining gates. The chronological notes below retain earlier
experiments; their model settings, validation claims and test counts describe those earlier runs.

The application indexes the eight reference repositories at commits recorded in
[`indexed-reference-repositories.json`](indexed-reference-repositories.json). Python and Java
symbols, source locations, and graph relationships are searchable. The frontend builds, the
backend suite passes, and the three Java runner modes have live offline-container validation in
[`java-runner-validation.json`](java-runner-validation.json).
The [indexed-file audit](index-audit.md) records what the versioned scanner now includes and
which source relationships remain unanalyzed.
The versioned scanner update is now applied to the same eight commits: selected type stubs,
UI/build text, and Mockito plugin configuration are indexed. Seven reference snapshots gained
files, while Commons Lang was unchanged
([coverage comparison](indexing-v2-comparison.json)). Mockito gained 22 explicit configuration
links. On the 48-case expanded set, retrieval scores were unchanged after reindexing; the
12-question Click/JUnit4 clean checkpoint also remained at 83% hybrid recall@8 and 0.38 MRR
([result](../evaluation/clean-holdout-indexing-v2.json)). These checks do not show a search gain
yet; the added text supports new question types that still need labels.

The local model setup uses Ollama `llama3.2:latest` for repository answers,
`qwen2.5-coder:7b` for Python test/patch proposals, and `nomic-embed-text` for embeddings.
One generated demo change has a test that fails before its patch and passes afterward in Docker;
[`model-validation.json`](model-validation.json) records that run. Proposals remain drafts until
the selected tests execute. Citation checks validate marker ranges, not factual support.

The fixed retrieval set has 24 reviewed symbol questions, three per reference repository. Its
current 18-question development recall@8 is 61% in hybrid mode. The six-question nominal holdout
scores 83%, but those repositories were inspected during earlier development and do not form a
clean holdout. Exact case-level results are in [`evaluation/baseline.json`](../evaluation/baseline.json).

The improvement pass now records per-path indexing decisions through the repository coverage API
and UI, and the code explorer shows candidate related tests with static-reference versus filename
heuristic labels. Java model drafts can add new JUnit tests and source edits, which remain subject
to syntax, patch, and container checks. A hand-authored Commons Lang Java regression failed before
its patch and passed afterward in an offline Maven container
([`java-generated-test-validation.json`](java-generated-test-validation.json)). The local Qwen
Java smoke tests have been rejected for source-edit mismatches, a timeout, and finally an invented
test-file path absent from the index
([`java-model-validation.json`](java-model-validation.json)). Draft edits are now limited to
paths actually retrieved as evidence, and a unique Java line can tolerate omitted indentation.
Model-authored Java repair is not yet validated end to end.
Earlier path-only diagnostics show one empty draft followed by an attempted edit to
`IterableStringTokenizerTest.java`, which is not in the pinned snapshot. No patch from that run
was applied or executed.
Another Qwen attempt on `BitField.clear` reached offline execution, but its generated test
expected `clear(0)` to return `-1`. It failed both before and after the proposed patch
([run record](java-model-validation-bitfield.json)); this is a failed repair.

A fresh Click/JUnit4 holdout was pinned before this retrieval pass. Its first 12 source-reviewed
symbol questions yielded 75% hybrid recall@8, with 0.34 mean reciprocal rank. The sample is small
and does not include answerability or answer-support judgments; the case-level record is
[`clean-holdout-result.json`](../evaluation/clean-holdout-result.json). No weights or prompts were
tuned against this result.

The answer workflow now rejects generated text with uncited paragraphs and retries once with
specific citation feedback. The new [answer review runner](../scripts/review_answers.py) stores
pinned snapshot/model information and requires human judgments for correctness, factual support,
and abstention. In a two-question Flask development smoke check, the local model produced two
answers with valid citation syntax. One answer was correct but cited the wrong excerpt for some
claims; the other confused Flask and View dispatch. Neither had all claims supported
([review records](../evaluation/answer-review-smoke-v3.jsonl)). This is direct evidence that
valid markers alone do not establish a trustworthy answer. The
[repair evaluator](../scripts/evaluate_repairs.py) now defines a repeatable task contract with
patch provenance and a distinctive failure before/passing result after a patch. No real-repository
repair set has been curated yet. Its synthetic Commons Lang fixture passed a live offline Maven
run (1/1); the [fixture record](../evaluation/repairs/fixture-commons/result.json) is explicitly
excluded from the real-task target.

One owner-name retrieval boost was tried on the development data and reverted. It improved
development mean reciprocal rank from 0.38 to 0.45 but left development recall@8 at 61% and
reduced the older regression split's mean reciprocal rank from 0.38 to 0.34. The result is kept
in [`retrieval-candidate.json`](../evaluation/retrieval-candidate.json); the clean Click/JUnit4
holdout was not run for this tuning decision.

A second, general ranking change modestly downweights class/interface/enum blocks so large class
sources do not crowd out methods. It raised development hybrid mean reciprocal rank from 0.38 to
0.42 without changing 61% recall@8; the older regression split improved from 0.38 to 0.57 MRR
with unchanged 83% recall. This change was kept. Exact cases are in
[`retrieval-kind-candidate.json`](../evaluation/retrieval-kind-candidate.json). The clean
Click/JUnit4 holdout remains outside tuning.

At the next fixed checkpoint, the 12-question clean holdout improved from 75% to 83% hybrid
recall@8 and from 0.34 to 0.38 MRR
([case-level result](../evaluation/clean-holdout-checkpoint-2.json)). This is encouraging but
still too small to claim broad generalization; no tuning used individual holdout misses.

On the same two Flask development questions after that retrieval change, one local answer fell
back to source locations and the other gave an incorrect View-versus-Flask dispatch explanation.
The [reviewed records](../evaluation/answer-review-smoke-v4.jsonl) show that higher symbol-ranking
MRR has not yet translated into reliable model answers. Do not present the revised prompt as a
verified answer-quality improvement.

Qwen 2.5 Coder 7B was also tried on those same two development answers
([reviewed records](../evaluation/answer-review-qwen-smoke.jsonl)). Its one generated answer was
correct on the pinned Flask version but did not cite adequate support for every claim; the
other fell back to locations. The two-case sample cannot justify a model switch.

Eight new cases ask for live, private, or future values that a pinned source snapshot cannot
establish. The local Llama model invented answers on the first two before a narrow external-state
guard was added ([pre-guard samples](../evaluation/unanswerable-smoke.jsonl)). The guard now
abstains on all eight reviewed cases
([post-guard reviews](../evaluation/unanswerable-postguard.jsonl)). It does not detect every
unanswerable question; general abstention still needs a broader evaluation set and model review.

The [review queue](../evaluation/review-queue/) now has 25 source-linked candidates per original
repository (200 total). These are starting points for writing realistic questions; 184 remain
pending in the first expansion and 160 remain after the second expansion. Pending cards are not
included in scored results.
Sixteen of those cards (two per repository) were completed against pinned source and promoted
alongside the original questions and eight abstention cases into
[`expanded-cases.jsonl`](../evaluation/expanded-cases.jsonl). The 48-case file has 40 answerable
symbol questions. Hybrid recall@8 is 73% on its 30 development questions and 90% on its 10 older,
contaminated holdout questions
([case-level results](../evaluation/expanded-retrieval.json)). Fifteen of the 16 new symbol
questions hit in the top eight. These added questions were seeded from known symbols and are
easier than independently written cross-file questions; their score must not be treated as a
general accuracy estimate.
Twenty-four more cards were source-reviewed, bringing the working dataset to 64 answerable
symbol questions and eight explicit abstention cases
([72-case file](../evaluation/expanded-cases-v3.jsonl)). On the reindexed snapshots, hybrid
recall@8 is 81% for 48 development questions and 94% for 16 older, contaminated holdout
questions ([case-level result](../evaluation/expanded-retrieval-v3.json)). Most new questions
were written with their target symbol in hand, so this score primarily checks symbol lookup;
independently written cross-file questions and a new untouched holdout are still needed.
The final untouched Python/Java repository pair has now been pinned as urllib3 and Apache
Commons Collections ([commits](../evaluation/final-holdout-snapshots.json)). No questions have
been labelled or scored on this pair, and its repositories must remain outside tuning.
Four separately reviewed development questions now ask about multi-stage request, test-run, and
mock-creation workflows across source files
([cases](../evaluation/workflow-cases.jsonl)). Hybrid retrieval found only 37.5% of the expected
symbols in the top eight ([case-level result](../evaluation/workflow-retrieval.json)); the pytest
workflow found none. This exposes a specific gap hidden by symbol-seeded questions. No ranking
change has been accepted on the strength of these four cases alone.

Still required before claiming the broader improvement plan complete:

1. Expand to 20–30 realistic questions per reference repository and a larger clean holdout,
   including unanswerable cases and supported answers.
2. Improve retrieval against that dataset and measure answer correctness and citation support,
   not just symbol recall. The generated Flask answers did not fully support their claims; a
   broader, independently reviewed answer set is needed before comparing models or prompts.
3. Curate and verify 30–50 real-repository repair tasks with pinned commits, failing-before and
   passing-after tests, and patch provenance. The demo change is not a substitute.
4. Reassess local adapter training only after those data exist and the untouched holdout shows
   a specific model limitation. At that checkpoint no fine-tuning had been run; the later tree-only
   adapter experiment in [local-training.md](local-training.md) failed its transfer check and remains unused.

The most useful commands are `make check`, `cd frontend && npm run build`, `make eval-dataset`,
`make validate-java`, and `DEVPILOT_PROPOSAL_MODEL=qwen2.5-coder:7b make validate-local` with
Ollama and Docker running. See the [file guide](file-guide.md) for manual inspection order.

At this checkpoint, `make api-local` served the built UI at `http://127.0.0.1:8000` (HTTP 200).
The health API reported local Llama, embeddings, and Docker available; an explicit live-secret
question returned `abstained=true` through the HTTP API. Browser automation was unavailable in
this environment, so the new toolbar has build and API validation but no visual UI inspection.

## LangGraph checkpoint

An opt-in LangGraph investigation path and a separate review-gated guided repair path are now
implemented. Quick questions still use the original one-pass route. The guided repair graph
persists its local checkpoint, pauses after the generated draft, and resumes only after an
approve/decline request; a declined draft never calls Docker. The existing manual verification
path remains available. See [the design and bounds](langgraph.md).

On four reviewed multi-stage development questions, deep retrieval improved expected-symbol
recall@8 from 37.5% to 54.2%. With equivalent evidence-only answer timing, mean response time
rose from 269 to 611 ms. On 64 mostly symbol-seeded questions, both paths scored 84.4%, with
267 vs 313 ms mean response time. A fixed 12-case Click/JUnit4 checkpoint scored 83.3% on both
paths, with 175 vs 211 ms. These small, no-model checks do not measure answer correctness, and the final untouched
holdout remains unscored. The first merge rule lost two correct symbol results; it was revised
before these final measurements, and the failed trial records remain in `evaluation/`.

The controlled synthetic Commons Lang fixture [passed](langgraph-guided-fixture-validation-live.json)
the complete review/checkpoint/offline-Docker route: its test failed before and passed after the
hand-authored patch. This validates orchestration only; no model-authored real-repository repair
has been demonstrated by LangGraph. A live Qwen2.5-Coder draft reached the guided review
interrupt, but review found its patch contradicted the demo's existing zero-weight validation.
The draft was declined before Docker execution; see
[the model smoke result](langgraph-guided-model-smoke.json). Model-authored repair quality is still
unproven.

## Cross-repository reviewed learning

The app now keeps pending learning cases and human-reviewed labels in the local SQLite database,
pinned to a repository fingerprint. Review requires expected symbols, source ranges within those
indexed symbols, a reviewed answer for answerable cases, and explicit answer-quality labels for a
generated response. All questions from one repository are assigned to the same development or
holdout split. The Evaluation screen can queue and review a saved investigation; the export script
emits only reviewed cases and separate split datasets with their snapshot manifest.

This adds a durable source-reviewed evaluation and retrieval-tuning loop; it does not train model
weights. The 15-repository test corpus now has pinned snapshots and 175 additional source-linked
candidate cards, all pending review. No labels from those cards have been exported, so the corpus
has not demonstrated a generalization gain. Optional local fine-tuning remains gated on collecting
enough reviewed examples and establishing a clean repository-level holdout. The suite passes 96
tests with one Docker-dependent skip; the frontend formatter and production build pass.

## October 4 recommendation-based research refactor

The current default architecture supersedes the execution-focused core described in older entries. Nine-language adapters, normalized entities, structural chunks, bounded graph queries, custom modular RAG, conservative static errors, unverified suggestions and research diagnostics are implemented. Docker/guided execution remains an explicit legacy experiment. See [the current implementation report](implementation-2026-10-04.md) for actual verification and remaining limits. Historical evaluation results are retained and are not evidence that new broad accuracy milestones have been completed.
