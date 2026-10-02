import json

from scripts import promote_reviewed_questions


def test_only_complete_reviewed_cards_are_promoted(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"repo": {"id": "repo-id", "fingerprint": "pinned"}}))
    queue = tmp_path / "queue"
    queue.mkdir()
    cards = [
        {
            "id": "pending",
            "repository": "repo",
            "review_status": "pending",
        },
        {
            "id": "reviewed",
            "repository": "repo",
            "snapshot": "pinned",
            "qualified": "pkg.fn",
            "path": "pkg.py",
            "start_line": 12,
            "question": "Where is the behavior implemented?",
            "expected_answer": "It is in pkg.fn.",
            "review_status": "reviewed",
        },
    ]
    (queue / "repo.jsonl").write_text("".join(json.dumps(card) + "\n" for card in cards))
    monkeypatch.setattr(
        promote_reviewed_questions.db, "repository", lambda _: {"fingerprint": "pinned"}
    )
    monkeypatch.setattr(
        promote_reviewed_questions.db, "symbols", lambda _: [{"qualified": "pkg.fn"}]
    )
    output = tmp_path / "cases.jsonl"
    assert promote_reviewed_questions.promote(queue, manifest, output) == 1
    case = json.loads(output.read_text())
    assert case["id"] == "reviewed"
    assert case["source_reviewed"] == "pkg.py:12"
    assert (
        promote_reviewed_questions.promote(
            queue, manifest, tmp_path / "expanded.jsonl", base=output
        )
        == 1
    )
