"""Graph, error analysis, unverified suggestions and research evaluation APIs."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from ..config import provider_settings
from ..errors.detector import analyze, list_issues
from ..errors.explanation import explain
from ..errors.suggestions import suggest
from ..evaluation import experiment
from ..graph import neighborhood
from ..languages.registry import capabilities
from ..proposals import propose
from ..rag.pipeline import TRACE, retrieve

router = APIRouter(prefix="/api")


def ready(repo_id):
    repo = db.repository(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    if repo["status"] != "ready":
        raise HTTPException(409, "Repository is not ready")
    return repo


def find_issue(repo_id, issue_id):
    rows = list_issues(repo_id)
    issue = next(
        (
            row
            for row in rows
            if row["id"] == issue_id and row["snapshot"] == ready(repo_id)["fingerprint"]
        ),
        None,
    )
    if not issue:
        raise HTTPException(404, "Issue not found in this snapshot; run analysis first")
    return issue


@router.get("/languages")
def languages():
    return {"languages": capabilities()}


@router.get("/repositories/{repo_id}/graph/neighborhood")
def graph(
    repo_id: str,
    seed: str | None = None,
    path: str | None = None,
    depth: int = Query(1, ge=0, le=3),
    direction: str = "both",
    kinds: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    ready(repo_id)
    try:
        return neighborhood(
            repo_id, seed, path, kinds.split(",") if kinds else None, depth, direction, limit
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/repositories/{repo_id}/symbols/{symbol_id}")
def symbol(repo_id: str, symbol_id: str):
    ready(repo_id)
    rows = db.symbols_by_ids(repo_id, [symbol_id])
    if not rows:
        raise HTTPException(404, "Symbol not found")
    with db.connection() as connection:
        chunk = connection.execute(
            "SELECT metadata FROM chunks WHERE id=? AND repo_id=?", (symbol_id, repo_id)
        ).fetchone()
    return {**rows[0], "chunk": json.loads(chunk[0]) if chunk else None}


@router.get("/repositories/{repo_id}/errors")
def errors(repo_id: str):
    ready(repo_id)
    return {
        "issues": list_issues(repo_id),
        "notice": "Static candidates; no fixes or tests have been executed.",
    }


@router.post("/repositories/{repo_id}/errors/analyze")
def analyze_errors(repo_id: str):
    ready(repo_id)
    return analyze(repo_id)


@router.post("/repositories/{repo_id}/errors/{issue_id}/explain")
def explain_error(repo_id: str, issue_id: str):
    ready(repo_id)
    return explain(repo_id, find_issue(repo_id, issue_id))


class SuggestionInput(BaseModel):
    request: str = Field(default="", max_length=6000)
    issue_id: str | None = None


def save_suggestion(repo_id, payload, issue_id=None):
    sid = uuid.uuid4().hex
    payload = {**payload, "id": sid, "verified": False, "status": "draft_unverified"}
    with db.connection() as c:
        c.execute(
            "INSERT INTO suggestions VALUES (?,?,?,?,?,?)",
            (
                sid,
                repo_id,
                ready(repo_id)["fingerprint"],
                issue_id,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(payload),
            ),
        )
    return payload


@router.post("/repositories/{repo_id}/fix-suggestions")
def fix_suggestions(repo_id: str, body: SuggestionInput):
    ready(repo_id)
    try:
        if body.issue_id:
            issue = find_issue(repo_id, body.issue_id)
            if not provider_settings()["model"]:
                return save_suggestion(
                    repo_id,
                    {
                        "summary": issue["suggested_fix"],
                        "patch": "",
                        "extra_tests": {},
                        "evidence": issue["evidence"],
                        "missing_information": [
                            "A model is required for a source-edit and regression-test draft."
                        ],
                        "suggested_test": "Add a regression case exercising the indicated condition and its expected behavior.",
                    },
                    body.issue_id,
                )
            return save_suggestion(repo_id, suggest(repo_id, issue), body.issue_id)
        if not body.request.strip():
            raise ValueError("Supply a request or issue_id")
        return save_suggestion(repo_id, propose(repo_id, body.request))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/repositories/{repo_id}/test-suggestions")
def test_suggestions(repo_id: str, body: SuggestionInput):
    ready(repo_id)
    try:
        if body.issue_id:
            issue = find_issue(repo_id, body.issue_id)
            if not provider_settings()["model"]:
                return save_suggestion(
                    repo_id,
                    {
                        "summary": "Regression-test guidance for: " + issue["message"],
                        "patch": "",
                        "extra_tests": {},
                        "kind": "test",
                        "evidence": issue["evidence"],
                        "suggested_test": "Exercise the indicated condition and assert the intended behavior.",
                        "missing_information": [
                            "A configured model is needed to draft test source."
                        ],
                    },
                    body.issue_id,
                )
            return save_suggestion(repo_id, suggest(repo_id, issue, test_only=True), body.issue_id)
        if not body.request.strip():
            raise ValueError("Supply a request or issue_id")
        return save_suggestion(repo_id, propose(repo_id, body.request, test_only=True))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/repositories/{repo_id}/fix-suggestions")
def saved_suggestions(repo_id: str):
    ready(repo_id)
    with db.connection() as c:
        return [
            json.loads(r[0])
            for r in c.execute(
                "SELECT payload FROM suggestions WHERE repo_id=? ORDER BY created_at DESC LIMIT 100",
                (repo_id,),
            )
        ]


class RetrievalInput(BaseModel):
    question: str = Field(min_length=2, max_length=6000)
    mode: str = "hybrid"
    limit: int = Field(default=10, ge=1, le=15)
    hops: int = Field(default=2, ge=0, le=3)


@router.post("/repositories/{repo_id}/retrieve")
def debug_retrieve(repo_id: str, body: RetrievalInput):
    repo = ready(repo_id)
    if body.mode not in ("lexical", "semantic", "graph", "hybrid"):
        raise HTTPException(422, "Unknown retrieval mode")
    try:
        evidence, warning, semantic = retrieve(
            repo_id, body.question, body.mode, body.limit, body.hops
        )
        trace = TRACE.get()
        tid = uuid.uuid4().hex
        with db.connection() as c:
            c.execute(
                "INSERT INTO retrieval_traces VALUES (?,?,?,?,?)",
                (
                    tid,
                    repo_id,
                    datetime.now(timezone.utc).isoformat(),
                    repo["fingerprint"],
                    json.dumps(trace),
                ),
            )
        return {
            "id": tid,
            "evidence": evidence,
            "trace": trace,
            "warning": warning,
            "semantic_used": semantic,
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/repositories/{repo_id}/retrieval-traces")
def traces(repo_id: str):
    ready(repo_id)
    with db.connection() as c:
        return [
            {"id": r[0], "created_at": r[1], "trace": json.loads(r[2])}
            for r in c.execute(
                "SELECT id,created_at,payload FROM retrieval_traces WHERE repo_id=? ORDER BY created_at DESC LIMIT 30",
                (repo_id,),
            )
        ]


class LabeledCase(BaseModel):
    question: str = Field(min_length=2, max_length=6000)
    expected_ids: list[str] = Field(min_length=1, max_length=50)


class ExperimentInput(BaseModel):
    cases: list[LabeledCase] = Field(min_length=1, max_length=30)


@router.post("/repositories/{repo_id}/research-evaluate")
def evaluate(repo_id: str, body: ExperimentInput):
    repo = ready(repo_id)
    try:
        result = experiment(repo_id, [case.model_dump() for case in body.cases])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    eid = uuid.uuid4().hex
    with db.connection() as c:
        c.execute(
            "INSERT INTO evaluations VALUES (?,?,?,?,?)",
            (
                eid,
                repo_id,
                datetime.now(timezone.utc).isoformat(),
                repo["fingerprint"],
                json.dumps(result),
            ),
        )
    return {"id": eid, **result}


@router.get("/repositories/{repo_id}/research-evaluations")
def saved_evaluations(repo_id: str):
    ready(repo_id)
    with db.connection() as c:
        return [
            json.loads(r[0])
            for r in c.execute(
                "SELECT payload FROM evaluations WHERE repo_id=? ORDER BY created_at DESC LIMIT 30",
                (repo_id,),
            )
        ]
