"""Optional legacy execution APIs, disabled unless explicitly configured."""

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..config import agent_enabled, legacy_execution_enabled
from ..main import ExecutionInput, GuidedRepairInput, ReviewDecision, now, pool, require_repo
from .execution import docker_status, run_job


def enabled():
    if not legacy_execution_enabled():
        raise HTTPException(
            503, "Legacy execution is disabled; the core generates suggestions only"
        )


router = APIRouter(dependencies=[Depends(enabled)])


@router.post("/api/repositories/{repo_id}/execute", status_code=202)
def execute(repo_id: str, body: ExecutionInput):
    require_repo(repo_id)
    status = docker_status()
    if not status["available"]:
        raise HTTPException(503, status["reason"])
    if body.extra_tests and (
        len(body.extra_tests) > 10 or sum(len(v) for v in body.extra_tests.values()) > 100000
    ):
        raise HTTPException(422, "Generated tests exceed size limits.")
    run_id = uuid.uuid4().hex
    with db.connection() as c:
        c.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?)", (run_id, repo_id, now(), "running", "{}")
        )
    pool.submit(
        run_job,
        run_id,
        repo_id,
        body.image,
        body.target,
        body.timeout,
        body.patch,
        body.extra_tests,
        body.runner,
    )
    return {"id": run_id, "status": "running"}


@router.post("/api/repositories/{repo_id}/guided-repairs")
def create_guided_repair(repo_id: str, body: GuidedRepairInput):
    require_repo(repo_id)
    if not agent_enabled():
        raise HTTPException(503, "LangGraph workflows are disabled on this server.")
    from ..agent_repair import create_run

    try:
        return create_run(repo_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/repositories/{repo_id}/guided-repairs")
def list_guided_repairs(
    repo_id: str, status: Literal["review", "running", "complete", "failed"] | None = None
):
    require_repo(repo_id)
    if not agent_enabled():
        raise HTTPException(503, "LangGraph workflows are disabled on this server.")
    from ..agent_repair import list_runs

    return list_runs(repo_id, status)


@router.post("/api/repositories/{repo_id}/guided-repairs/{run_id}/review", status_code=202)
def review_guided_repair(repo_id: str, run_id: str, body: ReviewDecision):
    require_repo(repo_id)
    if not agent_enabled():
        raise HTTPException(503, "LangGraph workflows are disabled on this server.")
    from ..agent_repair import get_run, queue_review, resume_run

    run = get_run(run_id)
    if not run or run["repo_id"] != repo_id:
        raise HTTPException(404, "Guided run not found for this repository.")
    try:
        queue_review(run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    pool.submit(resume_run, run_id, body.approved)
    return {"id": run_id, "status": "running"}


@router.get("/api/guided-repairs/{run_id}")
def guided_repair(run_id: str):
    if not agent_enabled():
        raise HTTPException(503, "LangGraph workflows are disabled on this server.")
    from ..agent_repair import get_run

    result = get_run(run_id)
    if not result:
        raise HTTPException(404, "Guided run not found.")
    return result


@router.get("/api/executions/{run_id}")
def execution(run_id: str):
    with db.connection() as c:
        row = c.execute("SELECT * FROM executions WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Execution not found.")
    return {**dict(row), "result": json.loads(row["result"])}
