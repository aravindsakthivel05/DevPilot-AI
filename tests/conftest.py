"""Isolated integration tests. No user repositories or live provider credentials."""

import time

import pytest
from fastapi.testclient import TestClient

from backend import db, execution, ingestion, proposals
from backend.main import app, pool


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    monkeypatch.setattr(ingestion, "SNAPSHOTS", snapshots)
    monkeypatch.setattr(execution, "SNAPSHOTS", snapshots)
    monkeypatch.setattr(proposals, "SNAPSHOTS", snapshots)
    for name in (
        "DEVPILOT_LLM_BASE_URL",
        "DEVPILOT_LLM_MODEL",
        "DEVPILOT_PROPOSAL_MODEL",
        "DEVPILOT_API_KEY",
        "DEVPILOT_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEVPILOT_LEGACY_EXECUTION", "1")
    with TestClient(app) as session:
        yield session
        # All submitted test jobs must finish before restoring the temporary paths.
        pool.submit(lambda: None).result(timeout=15)
        pool.submit(lambda: None).result(timeout=15)


def wait_repo(client, repo_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/repositories/{repo_id}").json()
        if result["status"] in ("ready", "failed"):
            return result
        time.sleep(0.025)
    raise AssertionError("Indexing did not finish within 10 seconds")


@pytest.fixture
def repo(client):
    response = client.post("/api/demo", json={})
    assert response.status_code == 202
    result = wait_repo(client, response.json()["id"])
    assert result["status"] == "ready", result
    return result


@pytest.fixture(autouse=True)
def isolated_model_audit(monkeypatch):
    # Most protocol fixtures exercise generation alone; audit tests explicitly
    # enable the separate reviewer. Never call a live provider in unit tests.
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "0")
