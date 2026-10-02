# Eight-repository evaluation

Run on 25 September 2026 using shallow public checkouts of the five Python and three Java
repositories from `RepositoriesLinks.docx`. Exact commits, snapshot fingerprints, all 24 questions,
retrieved symbols, and per-question scores are in [evaluation-results.json](evaluation-results.json).
The repeatable runner is [`scripts/evaluate_repositories.py`](../scripts/evaluate_repositories.py).
The eight repositories are also loaded into DevPilot's persistent local workspace; their snapshot
IDs are in [indexed-reference-repositories.json](indexed-reference-repositories.json).

The newer [case dataset](../evaluation/cases.jsonl) and
[baseline report](../evaluation/baseline.json) run against those persistent snapshots. The three
Java snapshots were refreshed to include Maven/Gradle manifests and resources, so their IDs and
file counts differ from the original shallow-checkout report below. Re-run the current baseline
with `.venv/bin/python -m scripts.evaluate_dataset > evaluation/baseline.json`.

The current 24-case baseline has 18 development questions and six nominal holdout questions.
Hybrid recall@8 is 61% on development and 83% on holdout. The holdout repositories were inspected
during earlier retrieval work; this split is useful for repeatable regression checks but cannot
support an unbiased generalization claim. A fresh, independently labelled set is still needed.

Three manually labelled symbol questions were used per repository. Recall@8 is the fraction of
questions whose expected symbol appears among the top eight results. Every expected symbol was
confirmed present in its index before scoring.

| Repository | Indexed files | Symbols | Edges | Lexical recall@8 | Graph recall@8 | Hybrid recall@8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Flask | 183 | 1,805 | 2,294 | 67% | 67% | 67% |
| Requests | 64 | 871 | 1,601 | 100% | 100% | 100% |
| HTTPX | 90 | 1,331 | 2,029 | 33% | 67% | 33% |
| pytest | 647 | 7,975 | 12,844 | 33% | 33% | 33% |
| Rich | 504 | 2,600 | 7,398 | 100% | 33% | 100% |
| Spring Petclinic | 59 | 299 | 309 | 67% | 67% | 67% |
| Commons Lang | 659 | 12,985 | 21,179 | 67% | 67% | 67% |
| Mockito | 1,017 | 9,985 | 14,222 | 67% | 67% | 67% |
| **All 24 questions** | | | | **67%** | **63%** | **67%** |

The first run revealed that Commons Lang's 403 KB `StringUtils.java` exceeded the old 300 KB
per-file limit. The limit is now 1 MB while the repository-wide 40 MB bound remains. The rerun
indexed all expected labels. Hybrid retrieval now preserves its eight strongest direct matches,
so graph expansion cannot displace a stronger direct result when the result list is full.

Misses remain on descriptive questions that omit method names, especially in pytest and HTTPX.
One Petclinic example asks which method displays an owner; its expected `showOwner` method is
indexed but falls outside the top eight. This is a retrieval ranking issue, not a parser failure.
The Java graph also cannot resolve every runtime relationship, including Spring dependency
injection and overloaded method calls.

These 24 questions are a small, hand-labelled evaluation set. They do not measure generated answer
correctness, patch quality, or broad repository coverage. The comparison used no embeddings.
The [local model smoke test](model-validation.json) separately confirmed semantic indexing and a
cited answer. The [container run](container-validation.json) confirmed a regression test failing on
the baseline snapshot and passing with a temporary patch.

To repeat the run, clone the eight public repositories and pass their local paths:

```sh
.venv/bin/python -m scripts.evaluate_repositories \
  flask=/path/to/flask requests=/path/to/requests httpx=/path/to/httpx \
  pytest=/path/to/pytest rich=/path/to/rich petclinic=/path/to/spring-petclinic \
  commons-lang=/path/to/commons-lang mockito=/path/to/mockito
```
