"""Resumable, review-gated LangGraph repair verification."""

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .. import db
from ..execution import execute, validate_runner_settings
from ..proposals import propose
from ..test_links import related_tests
from ..test_results import passed_tests, regression_transition


class RepairState(TypedDict, total=False):
    repo_id: str
    snapshot: str
    request: str
    image: str
    runner: str
    target: str
    timeout: int
    draft: dict
    approved: bool
    baseline: dict
    existing_baseline: dict
    existing_patched: dict
    existing_target: str
    patched: dict
    outcome: str
    regression_demonstrated: bool


def _now():
    return datetime.now(timezone.utc).isoformat()


def _check_snapshot(state):
    repo = db.repository(state["repo_id"])
    if not repo or repo["status"] != "ready" or repo["fingerprint"] != state["snapshot"]:
        raise ValueError("Repository snapshot changed; start a new guided repair.")


def _draft(state):
    _check_snapshot(state)
    draft = propose(state["repo_id"], state["request"])
    if not draft["patch"] or not draft["extra_tests"]:
        raise ValueError("Guided repair requires a generated test and an applicable patch.")
    return {"draft": draft}


def _review(state):
    decision = interrupt({"draft": state["draft"], "snapshot": state["snapshot"]})
    return {"approved": isinstance(decision, dict) and decision.get("approved") is True}


def _after_review(state):
    return "existing_baseline" if state["approved"] else "done"


def _target(state):
    tests = state["draft"]["extra_tests"]
    if len(tests) != 1:
        return state["target"]
    path = next(iter(tests))
    if state["runner"] == "python":
        return path
    item = PurePosixPath(path)
    if state["runner"] == "maven":
        return item.stem
    parts = item.parts
    if "java" not in parts:
        raise ValueError("Java test path is outside src/test/java.")
    return ".".join((*parts[parts.index("java") + 1 : -1], item.stem))


def _existing_baseline(state):
    _check_snapshot(state)
    target = state["target"] or "tests"
    generated = state["draft"]["extra_tests"]
    if target in generated or any(
        PurePosixPath(path).stem == target or target.endswith("." + PurePosixPath(path).stem)
        for path in generated
    ):
        source_paths = re.findall(r"(?m)^\+\+\+ b/(.+)$", state["draft"]["patch"])
        candidates = []
        for path in source_paths:
            candidates.extend(related_tests(state["repo_id"], path))
        if candidates:
            path = candidates[0]["path"]
            target = path if state["runner"] == "python" else PurePosixPath(path).stem
        else:
            target = "tests"
    result = execute(
        state["repo_id"], state["image"], target, state["timeout"], runner=state["runner"]
    )
    return {"existing_target": target, "existing_baseline": result}


def _after_existing_baseline(state):
    return "baseline" if passed_tests(state["existing_baseline"]) else "done"


def _baseline(state):
    _check_snapshot(state)
    target = _target(state)
    result = execute(
        state["repo_id"],
        state["image"],
        target,
        state["timeout"],
        extra_tests=state["draft"]["extra_tests"],
        runner=state["runner"],
    )
    return {"target": target, "baseline": result}


def _after_baseline(state):
    # A passing baseline cannot demonstrate a regression. Avoid a second container run.
    report = state["baseline"].get("test_report", {})
    if (
        state["baseline"].get("exit_code", 0) == 0
        or not report.get("available")
        or not report.get("failures")
        or report.get("errors")
        or not state["draft"]["patch"]
    ):
        return "done"
    return "patched"


def _patched(state):
    _check_snapshot(state)
    result = execute(
        state["repo_id"],
        state["image"],
        state["target"],
        state["timeout"],
        patch=state["draft"]["patch"],
        extra_tests=state["draft"]["extra_tests"],
        runner=state["runner"],
    )
    return {"patched": result}


def _after_patched(state):
    return (
        "existing_patched"
        if regression_transition(state.get("baseline"), state.get("patched"))
        else "done"
    )


def _existing_patched(state):
    _check_snapshot(state)
    result = execute(
        state["repo_id"],
        state["image"],
        state["existing_target"],
        state["timeout"],
        patch=state["draft"]["patch"],
        runner=state["runner"],
    )
    return {"existing_patched": result}


def _done(state):
    if not state["approved"]:
        return {"outcome": "declined", "regression_demonstrated": False}
    transition = regression_transition(state.get("baseline"), state.get("patched"))
    existing = passed_tests(state.get("existing_baseline")) and passed_tests(
        state.get("existing_patched")
    )
    if existing:
        before_ids = {
            c["id"]
            for c in state["existing_baseline"]["test_report"].get("cases", [])
            if c["status"] == "passed"
        }
        after_ids = {
            c["id"]
            for c in state["existing_patched"]["test_report"].get("cases", [])
            if c["status"] == "passed"
        }
        existing = bool(before_ids) and before_ids <= after_ids
    return {
        "outcome": "verified_test_transition" if transition and existing else "not_verified",
        "regression_demonstrated": bool(transition and existing),
    }


def build_graph():
    builder = StateGraph(RepairState)
    for name, node in (
        ("draft", _draft),
        ("review", _review),
        ("existing_baseline", _existing_baseline),
        ("baseline", _baseline),
        ("existing_patched", _existing_patched),
        ("patched", _patched),
        ("done", _done),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_conditional_edges(
        "review", _after_review, {"existing_baseline": "existing_baseline", "done": "done"}
    )
    builder.add_conditional_edges(
        "existing_baseline", _after_existing_baseline, {"baseline": "baseline", "done": "done"}
    )
    builder.add_conditional_edges(
        "baseline", _after_baseline, {"patched": "patched", "done": "done"}
    )
    builder.add_conditional_edges(
        "patched", _after_patched, {"existing_patched": "existing_patched", "done": "done"}
    )
    builder.add_edge("existing_patched", "done")
    builder.add_edge("done", END)
    return builder


BUILDER = build_graph()


@contextmanager
def _graph():
    path = db.DB_PATH.parent / "agent-checkpoints.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield BUILDER.compile(checkpointer=saver)


def create_run(repo_id, request, image, runner, target, timeout):
    repo = db.repository(repo_id)
    if not repo or repo["status"] != "ready":
        raise ValueError("Repository is not ready.")
    validate_runner_settings(image, target, runner)
    run_id = uuid4().hex
    initial = {
        "repo_id": repo_id,
        "snapshot": repo["fingerprint"],
        "request": request,
        "image": image,
        "runner": runner,
        "target": target,
        "timeout": timeout,
    }
    with _graph() as graph:
        graph.invoke(initial, {"configurable": {"thread_id": run_id}})
        state = graph.get_state({"configurable": {"thread_id": run_id}})
    if "review" not in state.next or "draft" not in state.values:
        raise ValueError("Guided draft did not reach review.")
    result = {"draft": state.values["draft"], "snapshot": repo["fingerprint"]}
    with db.connection() as c:
        c.execute(
            "INSERT INTO agent_runs VALUES (?,?,?,?,?,?)",
            (run_id, repo_id, repo["fingerprint"], _now(), "review", json.dumps(result)),
        )
    return {"id": run_id, "repo_id": repo_id, "status": "review", "result": result}


def get_run(run_id):
    with db.connection() as c:
        row = c.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
    return {**dict(row), "result": json.loads(row["result"])} if row else None


def list_runs(repo_id, status=None, limit=10):
    where = "repo_id=?" + (" AND status=?" if status else "")
    values = (repo_id, status) if status else (repo_id,)
    with db.connection() as c:
        rows = c.execute(
            f"SELECT * FROM agent_runs WHERE {where} ORDER BY created_at DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
    return [{**dict(row), "result": json.loads(row["result"])} for row in rows]


def queue_review(run_id):
    with db.connection() as c:
        updated = c.execute(
            "UPDATE agent_runs SET status='running' WHERE id=? AND status='review'", (run_id,)
        ).rowcount
    if not updated:
        raise ValueError("Guided run is not awaiting review.")


def resume_run(run_id, approved):
    try:
        run = get_run(run_id)
        if not run:
            raise ValueError("Guided run does not exist.")
        with _graph() as graph:
            state = graph.invoke(
                Command(resume={"approved": approved}),
                {"configurable": {"thread_id": run_id}},
            )
        result = {
            "draft": state["draft"],
            "snapshot": state["snapshot"],
            "target": state.get("target"),
            "baseline": state.get("baseline"),
            "existing_baseline": state.get("existing_baseline"),
            "existing_patched": state.get("existing_patched"),
            "existing_target": state.get("existing_target"),
            "verification_scope": "selected existing test target plus generated regression; not a proof of all repository behavior",
            "patched": state.get("patched"),
            "outcome": state["outcome"],
            "regression_demonstrated": state["regression_demonstrated"],
        }
        status = "complete"
    except Exception as exc:
        result = {"error": str(exc)}
        status = "failed"
    with db.connection() as c:
        c.execute(
            "UPDATE agent_runs SET status=?,result=? WHERE id=?",
            (status, json.dumps(result), run_id),
        )
