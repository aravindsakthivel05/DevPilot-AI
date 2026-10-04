"""Actual application + SQLite + background indexing + retrieval integration."""

import hashlib
import json

import pytest
from conftest import wait_repo

from backend import execution, ingestion, providers, retrieval


def test_health_without_external_services(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["model_configured"] is False
    assert r.json()["embedding_configured"] is False


def test_demo_index_files_graph_and_snapshot(client, repo):
    rid = repo["id"]
    assert repo["stats"]["python_files"] == 5
    assert repo["stats"]["parse_errors"] == []
    files = client.get(f"/api/repositories/{rid}/files").json()
    assert {f["path"] for f in files} >= {
        "parcel/api.py",
        "parcel/pricing.py",
        "tests/test_pricing.py",
    }
    content = client.get(
        f"/api/repositories/{rid}/file", params={"path": "parcel/pricing.py"}
    ).json()["content"]
    assert "def calculate_quote" in content
    assert (ingestion.SNAPSHOTS / rid / "parcel/pricing.py").read_text() == content
    graph = client.get(f"/api/repositories/{rid}/graph").json()
    nodes = {n["id"]: n["qualified"] for n in graph["nodes"]}
    edges = {(nodes[e["source"]], nodes[e["target"]], e["kind"]) for e in graph["edges"]}
    assert ("parcel.api.shipping_quote", "parcel.pricing.calculate_quote", "calls") in edges
    assert ("parcel.pricing.calculate_quote", "parcel.pricing.base_rate", "calls") in edges
    assert any(r["id"] == rid for r in client.get("/api/repositories").json())


def test_index_coverage_explains_skipped_paths(client, tmp_path):
    source = tmp_path / "coverage-repo"
    source.mkdir()
    (source / "app.py").write_text("def run():\n    return 1\n")
    (source / "image.png").write_bytes(b"not indexed")
    (source / ".env").write_text("LOCAL_ONLY=fixture\n")
    (source / "large.txt").write_text("x" * 1_000_001)
    ignored = source / "node_modules"
    ignored.mkdir()
    (ignored / "dependency.py").write_text("pass\n")
    created = client.post("/api/repositories", json={"source": str(source)})
    assert created.status_code == 202
    repo = wait_repo(client, created.json()["id"])
    assert repo["stats"]["coverage"]["indexed_files"] == 1
    assert repo["stats"]["coverage"]["skipped_files"] == 3
    assert repo["stats"]["coverage"]["ignored_directories"] == 1
    response = client.get(f"/api/repositories/{repo['id']}/coverage")
    assert response.status_code == 200
    report = response.json()
    assert report["available"] is True
    reasons = {entry["path"]: entry["reason"] for entry in report["entries"]}
    assert reasons["app.py"] is None
    assert reasons["image.png"] == "unsupported_extension"
    assert reasons[".env"] == "secret_file"
    assert reasons["large.txt"] == "file_too_large"
    assert reasons["node_modules/"] == "ignored_directory"
    assert "node_modules/dependency.py" not in reasons
    skipped = client.get(
        f"/api/repositories/{repo['id']}/coverage", params={"status": "skipped", "limit": 2}
    ).json()
    assert skipped["total"] == 4
    assert len(skipped["entries"]) == 2


def test_related_tests_are_labelled_as_static_or_heuristic(client, repo):
    response = client.get(
        f"/api/repositories/{repo['id']}/related-tests",
        params={"path": "parcel/pricing.py"},
    )
    assert response.status_code == 200
    result = response.json()
    assert "do not prove execution coverage" in result["notice"]
    assert any(link["path"] == "tests/test_pricing.py" for link in result["links"])
    assert {link["confidence"] for link in result["links"]} <= {"static", "heuristic"}
    assert (
        client.get(
            f"/api/repositories/{repo['id']}/related-tests",
            params={"path": "missing.py"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("mode", ["lexical", "graph", "hybrid"])
def test_question_citations_history_and_localisation(client, repo, mode):
    rid = repo["id"]
    response = client.post(
        f"/api/repositories/{rid}/ask",
        json={
            "question": "How does calculate_quote determine international shipping prices?",
            "mode": mode,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["generated"] is False
    assert result["verification"] == "not_executed"
    assert result["snapshot"] == repo["fingerprint"]
    assert result["citation_check"]["invalid"] == []
    assert "parcel.pricing.calculate_quote" in [s["qualified"] for s in result["evidence"]]
    for evidence in result["evidence"]:
        original = client.get(
            f"/api/repositories/{rid}/file", params={"path": evidence["path"]}
        ).json()["content"]
        excerpt = "\n".join(
            original.splitlines()[evidence["start_line"] - 1 : evidence["end_line"]]
        )
        assert excerpt.startswith(evidence["source"])
    history = client.get(f"/api/repositories/{rid}/history").json()
    assert history[0]["result"]["id"] == result["id"]
    localised = client.post(
        f"/api/repositories/{rid}/localise",
        json={"question": "ValueError Weight must be positive Parcel validate"},
    ).json()
    assert localised["verification"] == "hypothesis"
    assert any(s["qualified"] == "parcel.models.Parcel.validate" for s in localised["suspects"])


def test_no_matches_and_semantic_unavailable(client, repo):
    base = f"/api/repositories/{repo['id']}/ask"
    r = client.post(base, json={"question": "zxqv987nonexistent"})
    assert r.status_code == 200
    assert r.json()["evidence"] == []
    r = client.post(base, json={"question": "shipping", "mode": "semantic"})
    assert r.status_code == 422


def test_evaluation_reports_bounded_metrics(client, repo):
    r = client.post(
        f"/api/repositories/{repo['id']}/evaluate",
        json={
            "cases": [
                {
                    "question": "calculate_quote",
                    "expected_symbols": ["parcel.pricing.calculate_quote"],
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert {v["mode"] for v in result["results"]} == {"lexical", "graph", "hybrid"}
    for value in result["results"]:
        assert 0 <= value["precision"] <= 1
        assert value["recall"] == 1
        assert 0 < value["mrr"] <= 1


def test_snapshot_is_immutable_and_filters_secrets(client, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_text("def original():\n    return 1\n")
    (source / ".env").write_text("SECRET=do-not-index")
    (source / ".venv").mkdir()
    (source / ".venv" / "hidden.py").write_text("SECRET=1")
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET=2")
    (source / "link.py").symlink_to(outside)
    response = client.post("/api/repositories", json={"source": str(source)})
    repo = wait_repo(client, response.json()["id"])
    assert repo["status"] == "ready"
    (source / "code.py").write_text("def changed():\n    return 2\n")
    paths = client.get(f"/api/repositories/{repo['id']}/files").json()
    assert [f["path"] for f in paths] == ["code.py"]
    assert (
        "original"
        in client.get(f"/api/repositories/{repo['id']}/file", params={"path": "code.py"}).json()[
            "content"
        ]
    )


@pytest.mark.parametrize(
    "source", ["/nonexistent/devpilot-testing", "https://example.com/not-allowed"]
)
def test_failed_ingestion_is_reported(client, source):
    response = client.post("/api/repositories", json={"source": source})
    result = wait_repo(client, response.json()["id"])
    assert result["status"] == "failed"
    assert result["error"]
    assert client.get(f"/api/repositories/{result['id']}/graph").status_code == 409


def test_malformed_python_keeps_other_files(client, tmp_path):
    (tmp_path / "broken.py").write_text("def bad(:\n")
    (tmp_path / "valid.py").write_text("def good():\n    pass\n")
    response = client.post("/api/repositories", json={"source": str(tmp_path)})
    result = wait_repo(client, response.json()["id"])
    assert result["status"] == "ready"
    assert result["stats"]["parse_errors"][0]["path"] == "broken.py"


def test_validation_and_missing_resources(client, repo):
    assert client.post("/api/repositories", json={"source": ""}).status_code == 422
    assert client.get("/api/repositories/missing").status_code == 404
    assert client.get("/api/executions/missing").status_code == 404
    assert (
        client.post(f"/api/repositories/{repo['id']}/ask", json={"question": "x"}).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/repositories/{repo['id']}/ask", json={"question": "hello", "limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/repositories/{repo['id']}/file", params={"path": "../../.env"}
        ).status_code
        == 404
    )


def test_browser_origin_and_host_restrictions(client):
    assert client.get("/api/health", headers={"host": "attacker.example"}).status_code == 403
    assert (
        client.post(
            "/api/demo", json={}, headers={"origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/health", headers={"origin": "http://localhost:8000"}).status_code == 200


def test_missing_docker_has_explicit_error(client, repo, monkeypatch):
    monkeypatch.setattr(execution.shutil, "which", lambda _: None)
    r = client.post(f"/api/repositories/{repo['id']}/execute", json={})
    assert r.status_code == 503
    assert "Docker" in r.json()["detail"]


@pytest.fixture
def fake_provider(monkeypatch):
    """Protocol fixture only: not a live LLM or embedding-quality test."""
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    monkeypatch.setenv("DEVPILOT_EMBEDDING_MODEL", "fixture-embedding")
    requests = []

    def provider(endpoint, payload):
        requests.append((endpoint, payload))
        if endpoint == "embeddings":
            data = []
            for i, text in enumerate(payload["input"]):
                # Stable synthetic vectors exercise persistence and similarity plumbing.
                digest = hashlib.sha256(text.encode()).digest()
                data.append({"index": i, "embedding": [v / 255 for v in digest[:8]]})
            return {"data": data}
        request_data = json.loads(payload["messages"][1]["content"])
        context = request_data["source_evidence"][0]
        source_id = context["source_id"]
        qualifier = context["qualified"]
        claims = [
            {
                "text": f"The {aspect['question']} is handled by {qualifier}.",
                "citations": [
                    {
                        "source_id": source_id,
                        "start_line": context["lines"][0]["line"],
                        "end_line": context["lines"][0]["line"],
                    }
                ],
                "status": "supported",
                "aspect_id": aspect["aspect_id"],
            }
            for aspect in request_data["requested_aspects"]
        ]
        return {
            "choices": [{"message": {"content": json.dumps({"claims": claims})}}],
            "usage": {"total_tokens": 42},
        }

    monkeypatch.setattr(providers, "request", provider)
    return requests


def test_provider_embeddings_answer_and_usage(client, fake_provider):
    result = wait_repo(client, client.post("/api/demo", json={}).json()["id"])
    assert result["stats"]["embedding_status"] == "ready"
    r = client.post(
        f"/api/repositories/{result['id']}/ask",
        json={"question": "shipping quote", "mode": "semantic"},
    )
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["generated"] is True
    assert answer["semantic_used"] is True
    assert answer["usage"]["total_tokens"] == 42
    assert any(endpoint == "chat/completions" for endpoint, _ in fake_provider)
    assert answer["verification"] == "not_executed"


def test_provider_failure_falls_back_to_evidence(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")

    calls = []

    def fail(*args):
        calls.append(args)
        raise ValueError("Provider unavailable in test")

    monkeypatch.setattr(providers, "request", fail)
    r = client.post(f"/api/repositories/{repo['id']}/ask", json={"question": "shipping quote"})
    assert r.status_code == 200
    assert r.json()["generated"] is False
    assert r.json()["warning"] == "Provider unavailable in test"
    assert r.json()["evidence"]
    assert len(calls) == 1, "provider failures must not trigger an expensive generation retry"


def test_uncited_model_answer_falls_back_to_source_locations(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    monkeypatch.setattr(
        providers,
        "request",
        lambda *args: {"choices": [{"message": {"content": "Unsupported model claim."}}]},
    )
    result = client.post(
        f"/api/repositories/{repo['id']}/ask", json={"question": "shipping quote"}
    ).json()
    assert result["generated"] is False
    assert "source-backed JSON claims" in result["warning"]
    assert "Unsupported model claim" not in result["answer"]
    assert result["evidence"]


def test_model_cannot_supply_unverified_source_line(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "claims": [
                                    {
                                        "text": "The code secretly erases every repository",
                                        "source_id": 1,
                                        "source_line": 99999,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        },
    )
    result = client.post(
        f"/api/repositories/{repo['id']}/ask", json={"question": "shipping quote"}
    ).json()
    assert result["generated"] is False
    assert "invalid shape" in result["warning"]
    assert "secretly erases" not in result["answer"]


def test_model_answer_must_cover_every_question_aspect(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")

    def one_aspect_only(_endpoint, payload):
        request_data = json.loads(payload["messages"][1]["content"])
        context = request_data["source_evidence"][0]
        source_id = context["source_id"]
        qualifier = context["qualified"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "claims": [
                                    {
                                        "text": f"The method returns the requested dictionary through {qualifier}",
                                        "citations": [
                                            {
                                                "source_id": source_id,
                                                "start_line": context["lines"][0]["line"],
                                                "end_line": context["lines"][0]["line"],
                                            }
                                        ],
                                        "status": "supported",
                                        "aspect_id": 1,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(providers, "request", one_aspect_only)
    result = client.post(
        f"/api/repositories/{repo['id']}/ask",
        json={"question": "Which method returns the dictionary, and how is exclude_none passed?"},
    ).json()
    assert result["generated"] is False
    assert "for each aspect" in result["warning"]
    assert "The serializer returns" not in result["answer"]


def test_partly_uncited_model_answer_falls_back_to_source_locations(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    monkeypatch.setattr(
        providers,
        "request",
        lambda *args: {
            "choices": [
                {"message": {"content": "Supported-looking claim [1].\n\nUncited extra claim."}}
            ]
        },
    )
    result = client.post(
        f"/api/repositories/{repo['id']}/ask", json={"question": "shipping quote"}
    ).json()
    assert result["generated"] is False
    assert "Uncited extra claim" not in result["answer"]


def test_model_retries_a_partly_uncited_answer(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    replies = iter(
        [
            "First claim [1].\n\nUncited claim.",
            "First claim [1].\n\nSecond claim [1].",
        ]
    )
    monkeypatch.setattr(retrieval, "generate", lambda *_args, **_kwargs: (next(replies), {}))
    result = client.post(
        f"/api/repositories/{repo['id']}/ask", json={"question": "shipping quote"}
    ).json()
    assert result["generated"] is True
    assert result["citation_check"]["uncited_paragraphs"] == []
    assert result["generation_diagnostics"]["attempt_count"] == 2


def test_lexical_baseline_does_not_call_embedding_provider(client, fake_provider):
    result = wait_repo(client, client.post("/api/demo", json={}).json()["id"])
    fake_provider.clear()
    r = client.post(
        f"/api/repositories/{result['id']}/ask",
        json={"question": "shipping quote", "mode": "lexical", "use_model": False},
    )
    assert r.status_code == 200
    assert fake_provider == [], "Text-only baseline must not invoke or combine embedding retrieval"


def test_live_deployment_question_abstains_without_model_call(client, repo, fake_provider):
    fake_provider.clear()
    result = client.post(
        f"/api/repositories/{repo['id']}/ask",
        json={"question": "What is the current secret value in my running deployment?"},
    ).json()
    assert result["abstained"] is True
    assert result["generated"] is False
    assert "cannot establish" in result["answer"]
    assert fake_provider == []


@pytest.mark.parametrize("mode", ["hybrid", "graph", "lexical"])
def test_retrieval_limit_is_honoured(client, repo, mode):
    r = client.post(
        f"/api/repositories/{repo['id']}/ask",
        json={"question": "shipping quote", "mode": mode, "limit": 1},
    )
    assert r.status_code == 200
    assert len(r.json()["evidence"]) <= 1


def test_hybrid_preserves_direct_retrieval_without_embeddings(client, repo):
    route = f"/api/repositories/{repo['id']}/ask"
    body = {"question": "shipping quote pricing parcel", "limit": 8, "use_model": False}
    lexical = client.post(route, json={**body, "mode": "lexical"}).json()
    hybrid = client.post(route, json={**body, "mode": "hybrid"}).json()
    assert {item["id"] for item in lexical["evidence"]} <= {
        item["id"] for item in hybrid["evidence"]
    }
