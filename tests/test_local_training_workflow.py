import hashlib
import json

import pytest

from scripts.prepare_grounded_training import export, validate_target
from scripts.train_grounded_adapter import validate_export


def test_duplicate_questions_cannot_satisfy_training_gate(tmp_path):
    pack = tmp_path / "review.jsonl"
    pack.write_text(
        "\n".join(
            json.dumps(
                {
                    "id": f"case-{i}",
                    "repository": "repo",
                    "question": "same question",
                    "split": "development",
                    "target_reviewed": False,
                }
            )
            for i in range(2)
        )
    )
    with pytest.raises(ValueError, match="Duplicate"):
        export(pack, tmp_path / "training")


def test_unreviewed_correction_pair_is_not_training_truth():
    row = {
        "target_reviewed": True,
        "reviewer": "fixture",
        "incorrect_answer": "wrong",
        "aspects": ["Question"],
        "source_evidence": [],
        "target": {
            "claims": [
                {
                    "text": "Evidence is unavailable.",
                    "aspect_id": 1,
                    "status": "insufficient_evidence",
                    "citations": [],
                }
            ]
        },
    }
    with pytest.raises(ValueError, match="Correction pairs"):
        validate_target(row)
    row.update(
        correction_reviewed=True, correction_reason="Source does not establish the asserted value"
    )
    validate_target(row)


def make_export(path):
    provenance = {
        "training_ready": True,
        "minimum_examples": 100,
        "ready_examples": 100,
        "development_repositories": 5,
        "holdout_repositories": 2,
        "file_sha256": {},
        "counts": {},
    }
    for split, repos in [("train", range(4)), ("valid", [4]), ("test", [5, 6])]:
        rows = [
            {"provenance": {"repository": f"repo-{repo}", "reviewer": "fixture"}}
            for repo in repos
            for _ in range(20 if split != "test" else 2)
        ]
        file = path / f"{split}.jsonl"
        file.write_text("".join(json.dumps(row) + "\n" for row in rows))
        provenance["file_sha256"][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
        provenance["counts"][split] = len(rows)
    (path / "provenance.json").write_text(json.dumps(provenance))
    return provenance


def test_training_preflight_rejects_tampering_and_repository_leakage(tmp_path):
    provenance = make_export(tmp_path)
    assert validate_export(tmp_path)["training_ready"]
    path = tmp_path / "test.jsonl"
    path.write_text(path.read_text().replace("repo-5", "repo-0"))
    with pytest.raises(ValueError, match="changed after review"):
        validate_export(tmp_path)
    provenance["file_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "provenance.json").write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match="leakage"):
        validate_export(tmp_path)
