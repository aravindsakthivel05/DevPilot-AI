# Manual file guide

Start with the public workflow, then follow one layer at a time:

| Read | What to inspect |
| --- | --- |
| `backend/main.py` | Core ingestion/question/file/history/learning routes, rebuild jobs, optional router mounting |
| `backend/api/research.py` | Languages, neighborhood, error analysis, drafts, diagnostics and experiment endpoints |
| `backend/ingestion.py` | File limits/coverage, immutable snapshots, analysis, chunks, database publishing and timings |
| `backend/models.py`, `migrations.py`, `db.py`, `indexing.py` | Normalized metadata, additive schema, storage and explicit derived rebuild |
| `backend/languages/registry.py`, `base.py` | Adapter contract and extension dispatch |
| `backend/languages/<language>/parser.py`, `resolver.py` | Each language's grammar mapping / resolution boundary |
| `backend/languages/tree_parser.py`, `resolution.py` | Shared extraction and conservative import/call policies |
| `backend/analysis.py`, `java_analysis.py` | Preserved detailed Python/Java resolvers |
| `backend/structure.py`, `structural_metadata.py`, `config_links.py`, `graph.py` | Parameters/tests, declared types/manifests, explicit config links and bounded graph |
| `backend/rag/pipeline.py` | Complete custom query-to-answer flow |
| Other `backend/rag/*.py` | Inspectable chunk, BM25, vector, graph, fusion, reranking, context, citation and sufficiency logic |
| `backend/providers.py`, `model_providers.py`, `evidence.py`, `claim_audit.py` | Provider transport/contracts and fallible claim validation |
| `backend/errors/*.py`, `proposals.py` | Static rules, localisation, explanations and unverified drafts |
| `backend/evaluation.py`, `learning.py` | Retrieval/error scoring and reviewed cross-repo learning data |
| `frontend/src/App.jsx`, `api.js` | Workspace state, navigation and HTTP helper |
| `frontend/src/components/*Page.jsx`, `ResearchUI.jsx` | Individual preserved pages and new research workflows |
| `scripts/validate_research_prototype.py` | Repeatable local provider integration; target source is never executed |
| `tests/test_language_adapters.py`, `test_research_core.py`, `test_research_suggestions.py` | New parser, graph, migration, API and suggestion regression checks |
| `backend/legacy/`, `infra/` | Historical optional execution experiments, excluded from core |

`retrieval.py`, `execution.py` and `agent_repair.py` are thin compatibility aliases to the moved modules so existing imports and test monkeypatch targets keep working. They are not duplicate engines. No useful existing tests were intentionally removed.

`.devpilot/` contains local databases, snapshots, models, checkpoints and backups; do not push it. `evaluation/` and `docs/` contain shareable evidence and explanations. Frontend `dist/`, environments, dependency folders and local execution artifacts are generated rather than source files.
