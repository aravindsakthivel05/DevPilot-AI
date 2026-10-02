import json
from pathlib import Path

from scripts import load_reference_repositories, seed_review_queue


def test_test_repository_catalog_matches_loader_sources():
    catalog = json.loads(Path("evaluation/training-repository-catalog.json").read_text())
    entries = [entry for group in catalog["groups"].values() for entry in group]
    assert len(entries) == 15
    assert {entry["name"]: entry["url"] for entry in entries} == load_reference_repositories.SOURCES


def test_scoped_java_review_queue_uses_the_indexed_package_root(monkeypatch):
    rows = [
        {
            "kind": "method",
            "qualified": "co.elastic.clients.transport.Transport.performRequest",
            "path": "co/elastic/clients/transport/Transport.java",
            "start_line": 10,
            "end_line": 20,
            "source": "public Response performRequest() { return null; }" * 3,
        },
        {
            "kind": "method",
            "qualified": "outside.Unrelated.method",
            "path": "examples/Unrelated.java",
            "start_line": 1,
            "end_line": 5,
            "source": "public void method() { /* unrelated */ }" * 3,
        },
    ]
    monkeypatch.setattr(seed_review_queue.db, "symbols", lambda _: rows)

    selected = seed_review_queue.candidates("repo-id", "elasticsearch-java", 25)

    assert [item["qualified"] for item in selected] == [
        "co.elastic.clients.transport.Transport.performRequest"
    ]
