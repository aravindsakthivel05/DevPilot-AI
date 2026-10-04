import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db
from .config import ROOT, SNAPSHOTS, agent_enabled, legacy_execution_enabled, provider_settings
from .execution import docker_status
from .ingestion import ingest
from .proposals import propose
from .readiness import index_status, provider_status
from .retrieval import answer, retrieve
from .test_links import related_tests

pool = ThreadPoolExecutor(max_workers=2)


def now():
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app):
    db.init()
    with db.connection() as c:
        c.execute(
            "UPDATE repositories SET status='failed',error='Indexing interrupted by server restart. Create a new snapshot.' WHERE status IN ('queued','indexing')"
        )
        c.execute(
            "UPDATE executions SET status='failed',result=? WHERE status='running'",
            (json.dumps({"error": "Execution interrupted by server restart."}),),
        )
        c.execute(
            "UPDATE agent_runs SET status='failed',result=? WHERE status='running'",
            (json.dumps({"error": "Guided verification interrupted by server restart."}),),
        )
    yield


app = FastAPI(title="DevPilot AI", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    # This app can inspect local paths. Reject cross-origin browser writes and DNS rebinding.
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("localhost", "127.0.0.1", "testserver"):
        return JSONResponse({"detail": "DevPilot is a local-only service."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ):
        return JSONResponse({"detail": "Origin not allowed."}, status_code=403)
    return await call_next(request)


def require_repo(repo_id, ready=True):
    repo = db.repository(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found.")
    if ready and repo["status"] != "ready":
        raise HTTPException(409, "Repository is not ready.")
    return repo


class IngestInput(BaseModel):
    source: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=100)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=6000)
    mode: Literal["hybrid", "lexical", "semantic", "graph"] = "hybrid"
    limit: int = Field(default=8, ge=1, le=15)
    hops: int = Field(default=2, ge=0, le=3)
    use_model: bool = True
    deep: bool = False


class ExecutionInput(BaseModel):
    image: str = "devpilot-runner:local"
    target: str = Field(default="tests", max_length=300)
    timeout: int = Field(default=60, ge=5, le=300)
    patch: str | None = Field(default=None, max_length=100000)
    extra_tests: dict[str, str] | None = None
    runner: Literal["python", "maven", "gradle"] = "python"


class ProposalInput(BaseModel):
    request: str = Field(min_length=5, max_length=6000)


class GuidedRepairInput(ProposalInput):
    image: str = "devpilot-runner:local"
    runner: Literal["python", "maven", "gradle"] = "python"
    target: str = Field(default="tests", max_length=300)
    timeout: int = Field(default=120, ge=5, le=300)


class ReviewDecision(BaseModel):
    approved: bool


class LearningCaseInput(BaseModel):
    question: str = Field(min_length=2, max_length=6000)
    investigation_id: str | None = Field(default=None, min_length=8, max_length=64)


class SourceReference(BaseModel):
    qualified: str = Field(min_length=1, max_length=500)
    path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered_lines(self):
        if self.end_line < self.start_line:
            raise ValueError("Source range end_line must be at least start_line.")
        return self


class LearningCaseReview(BaseModel):
    answerable: bool
    expected_symbols: list[str] = Field(default_factory=list, max_length=50)
    expected_answer: str | None = Field(default=None, max_length=12000)
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=50)
    answer_correct: bool | None = None
    all_claims_supported: bool | None = None
    appropriate_abstention: bool | None = None
    split: Literal["development", "holdout"]
    notes: str = Field(min_length=3, max_length=3000)

    @field_validator("expected_symbols")
    @classmethod
    def normalize_symbols(cls, symbols):
        cleaned = [symbol.strip() for symbol in symbols]
        if any(not symbol or len(symbol) > 500 for symbol in cleaned):
            raise ValueError("Expected symbols must be nonempty names up to 500 characters.")
        return cleaned


@app.get("/api/health")
def health():
    cfg = provider_settings()
    return {
        "status": "ok",
        "model_configured": bool(cfg["model"] and cfg["base_url"]),
        "embedding_configured": bool(
            cfg["embedding_model"] and (cfg["embedding_base_url"] or cfg["base_url"])
        ),
        "model": cfg["model"] or None,
        "docker": docker_status()
        if legacy_execution_enabled()
        else {"available": False, "reason": "Optional legacy execution is disabled"},
        "legacy_execution_enabled": legacy_execution_enabled(),
        "core_workflow": "evidence_grounded_suggestions",
        "langgraph_enabled": agent_enabled(),
    }


@app.get("/api/provider-status")
def provider_readiness(probe: bool = False):
    return provider_status(probe)


@app.get("/api/repositories/{repo_id}/index-status")
def repository_index_status(repo_id: str):
    require_repo(repo_id)
    return index_status(repo_id)


@app.get("/api/repositories")
def repositories():
    with db.connection() as c:
        rows = c.execute("SELECT id FROM repositories ORDER BY created_at DESC").fetchall()
    return [db.repository(r["id"]) for r in rows]


@app.delete("/api/repositories/{repo_id}")
def delete_repository(repo_id: str):
    repo = require_repo(repo_id, False)
    if repo["status"] in ("queued", "indexing"):
        raise HTTPException(409, "Wait for indexing to finish before deleting this snapshot.")
    snapshot = SNAPSHOTS / repo_id
    if snapshot.is_symlink() or snapshot.parent.resolve() != SNAPSHOTS.resolve():
        raise HTTPException(409, "Snapshot path is not a safe repository directory.")
    staging = SNAPSHOTS / f".deleting-{repo_id}"
    if staging.exists():
        raise HTTPException(409, "A previous snapshot deletion needs cleanup.")
    if snapshot.exists():
        snapshot.rename(staging)
    try:
        with db.connection() as connection:
            connection.execute("DELETE FROM repositories WHERE id=?", (repo_id,))
    except Exception:
        if staging.exists():
            staging.rename(snapshot)
        raise
    if staging.exists():
        shutil.rmtree(staging)
    return {"deleted": True, "id": repo_id}


@app.post("/api/repositories", status_code=202)
def create_repository(body: IngestInput):
    repo_id = uuid.uuid4().hex
    name = body.name or body.source.rstrip("/").split("/")[-1].removesuffix(".git")
    with db.connection() as c:
        c.execute(
            "INSERT INTO repositories(id,name,source,status,progress,created_at) VALUES (?,?,?,?,?,?)",
            (repo_id, name, body.source, "queued", "Waiting to index", now()),
        )
    pool.submit(ingest, repo_id, body.source)
    return db.repository(repo_id)


@app.post("/api/demo", status_code=202)
def demo():
    return create_repository(
        IngestInput(source=str(ROOT / "examples" / "parcel_service"), name="parcel-service")
    )


@app.get("/api/repositories/{repo_id}")
def get_repository(repo_id: str):
    return require_repo(repo_id, False)


@app.get("/api/repositories/{repo_id}/files")
def files(repo_id: str):
    require_repo(repo_id)
    with db.connection() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT path,language,length(content) AS size FROM files WHERE repo_id=? ORDER BY path",
                (repo_id,),
            )
        ]


@app.get("/api/repositories/{repo_id}/coverage")
def coverage(
    repo_id: str,
    status: Literal["all", "indexed", "skipped"] = "all",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    repo = require_repo(repo_id)
    summary = repo["stats"].get("coverage")
    if summary is None:
        return {
            "available": False,
            "reason": "Coverage was not recorded for this snapshot. Reindex to create a report.",
            "summary": None,
            "total": 0,
            "entries": [],
        }
    where = "repo_id=?" + (" AND status=?" if status != "all" else "")
    values = (repo_id, status) if status != "all" else (repo_id,)
    with db.connection() as c:
        total = c.execute(f"SELECT count(*) FROM coverage WHERE {where}", values).fetchone()[0]
        entries = [
            dict(row)
            for row in c.execute(
                f"SELECT path,kind,status,reason,size,extension FROM coverage WHERE {where} "
                "ORDER BY path LIMIT ? OFFSET ?",
                (*values, limit, offset),
            )
        ]
    return {"available": True, "summary": summary, "total": total, "entries": entries}


@app.get("/api/repositories/{repo_id}/related-tests")
def get_related_tests(repo_id: str, path: str):
    require_repo(repo_id)
    try:
        links = related_tests(repo_id, path)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "source_path": path,
        "links": links[:100],
        "truncated": len(links) > 100,
        "notice": "Static references and file names suggest related tests; they do not prove execution coverage.",
    }


@app.get("/api/repositories/{repo_id}/file")
def file(repo_id: str, path: str):
    require_repo(repo_id)
    with db.connection() as c:
        row = c.execute(
            "SELECT * FROM files WHERE repo_id=? AND path=?", (repo_id, path)
        ).fetchone()
    if not row:
        raise HTTPException(404, "File not found in this snapshot.")
    return dict(row)


class RebuildInput(BaseModel):
    embeddings: bool = True


@app.post("/api/repositories/{repo_id}/rebuild-index", status_code=202)
def rebuild_index(repo_id: str, body: RebuildInput):
    require_repo(repo_id)
    from .indexing import rebuild

    with db.connection() as connection:
        changed = connection.execute(
            "UPDATE repositories SET status='indexing',progress='Rebuilding derived indexes',error=NULL WHERE id=? AND status='ready'",
            (repo_id,),
        ).rowcount
    if changed != 1:
        raise HTTPException(409, "An indexing job is already active")

    def job():
        try:
            rebuild(repo_id, body.embeddings)
            db.update_repository(
                repo_id, status="ready", progress="Ready for investigation", error=None
            )
        except Exception as exc:
            db.update_repository(
                repo_id, status="failed", progress="Rebuild failed", error=str(exc)[:2000]
            )

    pool.submit(job)
    return {
        "id": repo_id,
        "status": "indexing",
        "notice": "Derived indexes only; stored snapshot files stay unchanged. Previously excluded files require a new snapshot.",
    }


@app.get("/api/repositories/{repo_id}/graph")
def graph(repo_id: str):
    require_repo(repo_id)
    nodes = [
        {k: v for k, v in s.items() if k not in ("source", "docstring", "repo_id")}
        for s in db.symbols(repo_id)
    ]
    return {"nodes": nodes, "edges": db.edges(repo_id)}


@app.post("/api/repositories/{repo_id}/ask")
def ask(repo_id: str, body: Question):
    require_repo(repo_id)
    try:
        if body.deep:
            if not agent_enabled():
                raise ValueError("Deep investigation is disabled on this server.")
            from .agent_investigation import investigate

            result = investigate(repo_id, **body.model_dump(exclude={"deep"}))
        else:
            result = answer(repo_id, **body.model_dump(exclude={"deep"}))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    iid = uuid.uuid4().hex
    result["id"] = iid
    if result.get("retrieval_trace"):
        result["retrieval_trace"]["final_context"] = result.get("generation_context", [])
        result["retrieval_trace"]["answer"] = result["answer"]
        result["retrieval_trace"]["claims"] = result.get("claims", [])
    with db.connection() as c:
        c.execute(
            "INSERT INTO investigations VALUES (?,?,?,?,?)",
            (iid, repo_id, now(), body.question, json.dumps(result)),
        )
        if result.get("retrieval_trace"):
            c.execute(
                "INSERT INTO retrieval_traces VALUES (?,?,?,?,?)",
                (iid, repo_id, now(), result["snapshot"], json.dumps(result["retrieval_trace"])),
            )
    return result


@app.get("/api/repositories/{repo_id}/history")
def history(repo_id: str):
    require_repo(repo_id, False)
    with db.connection() as c:
        rows = c.execute(
            "SELECT * FROM investigations WHERE repo_id=? ORDER BY created_at DESC LIMIT 30",
            (repo_id,),
        ).fetchall()
    return [{**dict(r), "result": json.loads(r["result"])} for r in rows]


@app.post("/api/repositories/{repo_id}/learning-cases", status_code=201)
def create_learning_case(repo_id: str, body: LearningCaseInput):
    require_repo(repo_id)
    from .learning import create_case

    try:
        return create_case(repo_id, body.question, body.investigation_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/repositories/{repo_id}/learning-cases")
def learning_cases(
    repo_id: str,
    status: Literal["all", "pending", "reviewed"] = "all",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    require_repo(repo_id, False)
    from .learning import list_cases

    return list_cases(repo_id, status, limit, offset)


@app.post("/api/repositories/{repo_id}/learning-cases/{case_id}/review")
def review_learning_case(repo_id: str, case_id: str, body: LearningCaseReview):
    require_repo(repo_id)
    from .learning import review_case

    try:
        return review_case(repo_id, case_id, body.model_dump())
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/repositories/{repo_id}/localise")
def localise(repo_id: str, body: Question):
    require_repo(repo_id)
    try:
        evidence, warning, semantic = retrieve(
            repo_id, body.question, "hybrid", body.limit, body.hops
        )
        return {
            "suspects": evidence,
            "warning": warning,
            "verification": "hypothesis",
            "semantic_used": semantic,
        }
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/repositories/{repo_id}/propose")
def create_proposal(repo_id: str, body: ProposalInput):
    require_repo(repo_id)
    try:
        return propose(repo_id, body.request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class EvaluationCase(BaseModel):
    question: str = Field(min_length=2, max_length=6000)
    expected_symbols: list[str] = Field(min_length=1, max_length=50)


class EvaluationInput(BaseModel):
    cases: list[EvaluationCase] = Field(min_length=1, max_length=50)
    limit: int = Field(default=8, ge=1, le=15)


@app.post("/api/repositories/{repo_id}/evaluate")
def evaluate(repo_id: str, body: EvaluationInput):
    require_repo(repo_id)
    import time

    modes = ["lexical", "graph", "hybrid"]
    if require_repo(repo_id)["stats"].get("embedding_status") == "ready":
        modes.insert(1, "semantic")
    results = []
    for mode in modes:
        cases = []
        for case in body.cases:
            start = time.perf_counter()
            evidence, warning, semantic = retrieve(repo_id, case.question, mode, body.limit)
            actual = [s["qualified"] for s in evidence]
            expected = set(case.expected_symbols)
            hits = expected.intersection(actual)
            first = next((i + 1 for i, s in enumerate(actual) if s in expected), None)
            cases.append(
                {
                    "question": case.question,
                    "recall": len(hits) / len(expected),
                    "precision": len(hits) / max(len(actual), 1),
                    "reciprocal_rank": 1 / first if first else 0,
                    "retrieved": actual,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000),
                    "warning": warning,
                }
            )
        results.append(
            {
                "mode": mode,
                "recall": sum(c["recall"] for c in cases) / len(cases),
                "precision": sum(c["precision"] for c in cases) / len(cases),
                "mrr": sum(c["reciprocal_rank"] for c in cases) / len(cases),
                "cases": cases,
            }
        )
    return {
        "results": results,
        "snapshot": require_repo(repo_id)["fingerprint"],
        "note": "Retrieval metrics only. Graph mode uses lexical seeds; hybrid falls back to lexical + graph without embeddings.",
    }


from .api.research import router as research_router  # noqa: E402

# Legacy routes reuse the existing request contracts defined above.
from .legacy.routes import router as legacy_router  # noqa: E402

app.include_router(research_router)
app.include_router(legacy_router)

dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(dist / "index.html")
