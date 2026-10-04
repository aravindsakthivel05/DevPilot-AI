"""Core integration without execution, plus real static errors and research metrics."""

from conftest import wait_repo

from backend import db
from backend.errors.rules import candidates
from backend.evaluation import metrics
from backend.rag.vector_store import LocalVectorStore


def test_core_has_no_docker_requirement(client, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LEGACY_EXECUTION", "0")
    monkeypatch.setattr(
        "backend.main.docker_status",
        lambda: (_ for _ in ()).throw(AssertionError("Docker should not be probed")),
    )
    result = client.get("/api/health").json()
    assert result["core_workflow"] == "evidence_grounded_suggestions"
    assert result["legacy_execution_enabled"] is False
    assert len(client.get("/api/languages").json()["languages"]) == 9


def test_static_rule_true_and_negative_cases():
    files = {
        "bad.py": "def f():\n    return missing_name\n    print('unreachable')\n",
        "calls.py": "def work(x): return x\nwork(1,2)\n",
        "pkg/imports.py": "from .absent import value\n",
        "good.py": "import os\ndef f(x):\n    return os.path.join(x, 'ok')\n",
    }
    found = candidates(files, [])
    assert {r["kind"] for r in found} >= {
        "undefined_symbol",
        "unreachable_statement",
        "signature_mismatch",
        "missing_relative_import",
    }
    assert not any(r["path"] == "good.py" for r in found)
    assert not candidates(
        {"dynamic.py": "from somewhere import *\ndef f(): return dynamic_name\n"}, []
    )


def test_multilanguage_ingestion_errors_graph_trace_and_suggestions(client, tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "helper.ts").write_text("export function normalize(x: number) { return x; }")
    (source / "api.ts").write_text(
        "import {normalize} from './helper'; export function run(x: number) { return normalize(x); }"
    )
    (source / "broken.py").write_text("def work(x): return x\nwork(1,2)\n")
    response = client.post("/api/repositories", json={"source": str(source)})
    repo = wait_repo(client, response.json()["id"])
    rid = repo["id"]
    assert repo["status"] == "ready", repo
    assert repo["stats"]["languages"] == {"python": 1, "typescript": 2}
    response = client.post(f"/api/repositories/{rid}/errors/analyze")
    assert response.status_code == 200, response.text
    issues = response.json()["issues"]
    assert any(i["type"] == "signature_mismatch" for i in issues)
    item = next(i for i in issues if i["type"] == "signature_mismatch")
    assert item["evidence"][0]["file"] == "broken.py" and item["verified"] is False
    draft = client.post(f"/api/repositories/{rid}/fix-suggestions", json={"issue_id": item["id"]})
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft_unverified" and not draft.json()["patch"]
    symbols = db.symbols(rid)
    fn = next(s for s in symbols if s["name"] == "run")
    graph = client.get(
        f"/api/repositories/{rid}/graph/neighborhood",
        params={"seed": fn["id"], "depth": 2, "limit": 10},
    )
    assert graph.status_code == 200 and any(e["kind"] == "calls" for e in graph.json()["edges"])
    assert len(graph.json()["nodes"]) <= 10
    trace = client.post(
        f"/api/repositories/{rid}/retrieve",
        json={"question": "How does run normalize an input?", "mode": "hybrid"},
    ).json()
    assert trace["trace"]["lexical_candidates"] and trace["trace"]["reranked_candidates"]
    assert client.get(f"/api/repositories/{rid}/retrieval-traces").json()[0]["id"] == trace["id"]
    evaluation = client.post(
        f"/api/repositories/{rid}/research-evaluate",
        json={
            "cases": [
                {
                    "question": "Where is normalize implemented?",
                    "expected_ids": [next(s["id"] for s in symbols if s["name"] == "normalize")],
                }
            ]
        },
    )
    assert evaluation.status_code == 200, evaluation.text
    semantic = next(r for r in evaluation.json()["results"] if r["variant"]["mode"] == "semantic")
    assert semantic["cases"][0]["available"] is False
    assert (source / "broken.py").read_text() == "def work(x): return x\nwork(1,2)\n"


def test_real_vector_ranking_and_metrics():
    store = LocalVectorStore([("a", [1, 0]), ("b", [0, 1]), ("c", [0.5, 0.5])])
    assert [sid for sid, _ in store.search([1, 0], 2)] == ["a", "c"]
    result = metrics(["other", "a", "b"], ["a", "b"], 3)
    assert result["recall"] == 1 and result["mrr"] == 0.5 and 0 < result["ndcg"] < 1
    assert result["all_required_evidence"]


def test_additive_migration_is_idempotent_and_preserves_snapshot(client, repo):
    fingerprint = repo["fingerprint"]
    ids = {s["id"] for s in db.symbols(repo["id"])}
    db.init()
    db.init()
    assert db.repository(repo["id"])["fingerprint"] == fingerprint
    assert {s["id"] for s in db.symbols(repo["id"])} == ids
    with db.connection() as c:
        assert c.execute("SELECT COUNT(*) FROM chunks WHERE repo_id=?", (repo["id"],)).fetchone()[
            0
        ] == len(ids)
