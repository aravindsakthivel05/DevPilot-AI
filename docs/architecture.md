# Architecture and data flow

DevPilot is a local prototype with a small FastAPI backend, React client, and SQLite database. The
browser talks to the local backend. The backend owns repository paths, storage, provider
configuration, and Docker calls.

## Indexing flow

```text
POST /api/repositories or POST /api/demo
  → background job in backend/ingestion.py
  → collect bounded Python, Java, and text files
  → calculate commit and content fingerprint
  → parse Python with backend/analysis.py and Java with backend/java_analysis.py
  → store files, symbols, and edges through backend/db.py
  → optionally request provider embeddings
  → publish indexing state and extraction counts
```

Files in `.git`, virtual environments, build output, dependency locks, environment secret files,
and oversized files are skipped. A snapshot fingerprint represents included file contents, even
when a local source directory has no Git commit. This graph is a structural index, not a complete
compiler-grade Code Property Graph. Calls that cannot be resolved remain unresolved instead of
being presented as proven edges.

## Question flow

```text
POST /api/repositories/{id}/ask
  → backend/retrieval.py ranks text matches
  → optional vector search adds semantic matches
  → graph expansion follows selected relationships
  → bounded source excerpts are returned with locations and reasons
  → optional backend/providers.py request synthesises an answer
  → result and evidence are stored in SQLite history
```

Text, graph, and hybrid modes work without a model. Semantic mode requires indexed vectors and a
configured embedding provider. Without a chat model, the result is a retrieval report. Range checks
can detect a citation number with no matching source entry; they do not validate factual support.
With LangGraph enabled, `deep=true` selects the bounded investigation graph. It reuses retrieval
and the same citation policy, preserves distinct primary matches, and may run focused searches.
The standard route remains one-pass. See [the LangGraph design](langgraph.md).

## Storage map

`repositories` tracks index state and snapshot fingerprints. `files` stores included file text.
`symbols` stores modules, documents, functions, classes, and methods with source ranges. `edges`
stores typed relationships. `embeddings` stores optional provider vectors. `investigations` and
`executions` hold question and run history. SQLite and indexed snapshot files live under
`.devpilot/`, which Git ignores. `learning_cases` stores pending or human-reviewed questions
against immutable repository snapshots; `learning_repository_splits` keeps each repository
entirely in either development or holdout. A saved investigation can be queued only once.
`agent_runs` records review and completion state for guided repairs. LangGraph checkpoints live in
a separate local `.devpilot/agent-checkpoints.sqlite3` file so a review can resume.

## Test execution boundary

Indexing reads files without running them. The execution route copies an indexed snapshot into a
temporary directory, disables network access, drops Linux capabilities, makes the container root
read-only, and applies CPU, memory, process, and time limits. A writable mount lets Python,
Maven, or Gradle create temporary test artifacts; the indexed snapshot itself remains unchanged.
Java runner images cache project dependencies during a separate image build, then use Maven's or
Gradle's offline mode for verification. Mockito's Gradle test task bypasses cached test results
while reusing compilation artifacts. A passed result covers only the selected command and snapshot.

`POST /api/repositories/{id}/propose` retrieves source evidence and asks the configured chat model
for a JSON draft containing tests and an optional unified diff. The backend checks the draft's
paths, size, syntax, and indexed-file scope. The UI presents it for review; only the separate
execution request runs tests. Patch application is confined to the disposable copy by preventing
Git from finding the parent project repository.
The guided LangGraph repair route uses the same proposal validation and Docker runner. It saves
the draft at a review interrupt, resumes only on an explicit approve/decline request, and reports
the before/after result. A before/after transition verifies the selected generated test, not a
general repair claim.

Mocks test command construction and failure handling without claiming Docker ran. The Python
smoke test runs only when Docker and `devpilot-runner:local` exist. The repeatable Java validation
command runs selected tests from Petclinic, Commons Lang, and Mockito; its results are in
[`java-runner-validation.json`](java-runner-validation.json).

## Current scope

Python analysis uses AST, and Java analysis uses Tree-sitter. Neither fully resolves reflection,
dynamic dispatch, or runtime dependency injection. Java method overloads can share a qualified
name; those references stay unresolved when ambiguous. SQLite serves one local workspace.
Citation entailment checks, production hosting, and multi-user access remain outside this prototype.
