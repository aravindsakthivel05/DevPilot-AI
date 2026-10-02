import json

import pytest

from scripts.evaluate_dataset import evaluate


def test_evaluator_rejects_a_repository_in_both_splits(tmp_path, monkeypatch):
    cases = [
        {
            "id": "development-case",
            "repository": "sample-repo",
            "split": "development",
            "question": "Where is the behavior?",
            "expected_symbols": ["sample.run"],
            "answerable": True,
            "review_status": "reviewed",
        },
        {
            "id": "holdout-case",
            "repository": "sample-repo",
            "split": "holdout",
            "question": "How does the behavior work?",
            "expected_symbols": ["sample.run"],
            "answerable": True,
            "review_status": "reviewed",
        },
    ]
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("".join(json.dumps(case) + "\n" for case in cases))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sample-repo": {"id": "repo-id", "fingerprint": "pinned"}}))
    monkeypatch.setattr(
        "scripts.evaluate_dataset.db.repository",
        lambda _repo_id: {"fingerprint": "pinned"},
    )

    with pytest.raises(ValueError, match="cannot span development and holdout"):
        evaluate(dataset, manifest)
