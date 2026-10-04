"""Draft contracts across languages; no target repository code is executed."""

import json

import pytest
from conftest import wait_repo

from backend import db, providers
from backend.errors.rules import candidates
from backend.evaluation import detection_metrics
from backend.languages.registry import analyze_repository
from backend.proposals import validate_proposal
from backend.rag.chunking import repository_chunks
from backend.structure import enrich

TESTS = [
    ("python", "tests/test_new.py", "def test_one():\n    assert 1 == 1\n"),
    ("java", "src/test/java/NewTest.java", "class NewTest { void testOne() {} }"),
    ("javascript", "tests/new.test.js", "function testOne() { return true; }"),
    ("typescript", "tests/new.test.ts", "function testOne(): boolean { return true; }"),
    ("c", "tests/test_new.c", "int test_one(void) { return 1; }"),
    ("cpp", "tests/test_new.cpp", "int test_one() { return 1; }"),
    ("go", "new_test.go", "package demo\nfunc TestOne() {}"),
    ("rust", "tests/test_new.rs", "#[test]\nfn test_one() { assert!(true); }"),
    ("csharp", "tests/NewTests.cs", "class NewTests { void TestOne() {} }"),
]


@pytest.mark.parametrize("language,path,source", TESTS)
def test_suggestion_syntax_for_nine_languages(client, repo, language, path, source):
    result = validate_proposal(
        {"summary": "Unverified test draft", "extra_tests": {path: source}}, repo["id"], language
    )
    assert result["extra_tests"][path] == source and not result["patch"]


def test_test_only_rejects_model_edits_and_retries(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "test")
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://local.invalid/v1")
    payloads = []

    def request(endpoint, payload):
        payloads.append(json.loads(json.dumps(payload)))
        data = {
            "summary": "Regression test draft",
            "extra_tests": {"tests/test_new.py": "def test_one():\n    assert True\n"},
        }
        if len(payloads) == 1:
            data["edits"] = [{"path": "parcel/pricing.py", "old": "invented", "new": "invented"}]
        return {"choices": [{"message": {"content": json.dumps(data)}}]}

    monkeypatch.setattr(providers, "request", request)
    response = client.post(
        f"/api/repositories/{repo['id']}/test-suggestions",
        json={"request": "Test calculate_quote pricing behavior"},
    )
    assert response.status_code == 200, response.text
    assert len(payloads) == 2 and response.json()["kind"] == "test"
    assert not response.json()["patch"] and response.json()["verified"] is False
    assert "Test-only" in payloads[0]["messages"][0]["content"]


def test_exception_and_match_bindings_are_not_undefined():
    source = """def handle(value):
    try:
        return int(value)
    except ValueError as error:
        return str(error)

def match_value(value):
    match value:
        case {"key": captured, **rest}:
            return captured, rest
"""
    assert not [r for r in candidates({"a.py": source}, []) if r["kind"] == "undefined_symbol"]
    flagged = candidates({"a.py": "def bad():\n    return missing_name\n"}, [])
    assert any(r["kind"] == "undefined_symbol" for r in flagged)


def test_manifest_and_annotation_edges_are_declared_and_chunked():
    files = {
        "package.json": '{"dependencies":{"express":"4.0.0"}}',
        "api.ts": 'export function run(x: number): string { throw new Error("bad"); }',
    }
    result = analyze_repository("r", files)
    added, edges = enrich("r", files, result.symbols, result.relationships)
    all_symbols = result.symbols + added
    assert any(s["kind"] == "dependency" and s["name"] == "express 4.0.0" for s in added)
    assert {"depends_on", "raises", "returns"} <= {e["kind"] for e in edges}
    chunks = repository_chunks(all_symbols, result.relationships + edges)
    fn = next(s for s in all_symbols if s["name"] == "run")
    assert any(e["kind"] == "raises" for e in chunks[fn["id"]]["relationships"])
    assert all(
        e["confidence"] == "declared"
        for e in edges
        if e["kind"] in ("depends_on", "raises", "returns")
    )


def test_rebuild_preserves_snapshot_and_replaces_derived_index(client, tmp_path):
    from scripts.rebuild_indexes import rebuild

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.ts").write_text("export function run(x: number) { return x; }\n")
    repo = wait_repo(
        client, client.post("/api/repositories", json={"source": str(source)}).json()["id"]
    )
    rid = repo["id"]
    before = repo["fingerprint"]
    rebuilt = rebuild(rid)
    assert db.repository(rid)["fingerprint"] == before and rebuilt["symbols"] > 0
    with db.connection() as c:
        assert (
            c.execute("SELECT COUNT(*) FROM chunks WHERE repo_id=?", (rid,)).fetchone()[0]
            == rebuilt["symbols"]
        )


def test_detection_metrics_include_false_positives_and_negatives():
    result = detection_metrics(
        [
            {"type": "syntax_error", "file": "a", "line": 1},
            {"type": "undefined_symbol", "file": "b", "line": 2},
        ],
        [
            {"type": "syntax_error", "file": "a", "line": 1},
            {"type": "syntax_error", "file": "c", "line": 3},
        ],
    )
    assert result["precision"] == 0.5 and result["recall"] == 0.5
    assert result["false_positives"] == 1 and result["false_negatives"] == 1
    assert result["f1"] == 0.5 and result["true_negatives"] is None


def test_missing_test_framework_import_is_rejected(client, repo):
    with pytest.raises(ValueError, match="without importing"):
        validate_proposal(
            {
                "summary": "Draft",
                "extra_tests": {
                    "tests/test_missing.py": 'def test_it():\n    with pytest.raises(ValueError):\n        int("x")\n'
                },
            },
            repo["id"],
        )


def test_index_rebuild_api_preserves_fingerprint(client, repo):
    response = client.post(
        f"/api/repositories/{repo['id']}/rebuild-index", json={"embeddings": False}
    )
    assert response.status_code == 202, response.text
    rebuilt = wait_repo(client, repo["id"])
    assert rebuilt["status"] == "ready" and rebuilt["fingerprint"] == repo["fingerprint"]
