import json

import pytest

from scripts import review_answers
from scripts.review_answers import score


def test_score_requires_completed_reviews(tmp_path):
    path = tmp_path / "answers.jsonl"
    row = {
        "id": "case-1",
        "generated": True,
        "review": {
            "answer_correct": True,
            "all_claims_supported": None,
            "appropriate_abstention": True,
        },
    }
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="Incomplete review"):
        score(path)
    row["review"]["all_claims_supported"] = False
    path.write_text(json.dumps(row) + "\n")
    assert score(path)["all_claims_supported"] == 0


def test_score_separates_generated_answers_from_fallbacks(tmp_path):
    path = tmp_path / "answers.jsonl"
    rows = [
        {
            "id": "generated",
            "generated": True,
            "review": {
                "answer_correct": True,
                "all_claims_supported": False,
                "appropriate_abstention": True,
            },
        },
        {
            "id": "fallback",
            "generated": False,
            "review": {
                "answer_correct": False,
                "all_claims_supported": True,
                "appropriate_abstention": False,
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = score(path)
    assert result["all_claims_supported"] == 0.5
    assert result["generated_all_claims_supported"] == 0
    assert result["generated_answer_correct"] == 1


def test_prepare_can_select_unanswerable_cases(tmp_path, monkeypatch):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "".join(
            json.dumps(
                {"id": ident, "repository": "repo", "question": ident, "answerable": answerable}
            )
            + "\n"
            for ident, answerable in [("known", True), ("unknown", False)]
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"repo": {"id": "repo-id", "fingerprint": "pinned"}}))
    monkeypatch.setattr(review_answers.db, "repository", lambda _: {"fingerprint": "pinned"})
    monkeypatch.setattr(review_answers, "provider_settings", lambda: {"model": "local-test"})
    monkeypatch.setattr(
        review_answers,
        "answer",
        lambda *_: {
            "answer": "Not in the snapshot.",
            "generated": True,
            "evidence": [],
            "citation_check": {},
            "warning": None,
        },
    )
    output = tmp_path / "review.jsonl"
    assert review_answers.prepare(dataset, manifest, output, only_unanswerable=True) == 1
    assert review_answers.read_jsonl(output)[0]["id"] == "unknown"
