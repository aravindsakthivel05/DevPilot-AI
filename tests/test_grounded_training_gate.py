import json

import pytest

from backend.rag.obligations import requirements
from scripts.prepare_grounded_training import export, validate_target


def test_current_training_target_requires_reviewed_requirement_references():
    question = "What does get_value return?"
    req = requirements(question)
    row = {
        "target_reviewed": True,
        "reviewer": "fixture-reviewer",
        "question": question,
        "aspects": [question.strip("?")],
        "answer_requirements": req,
        "source_evidence": [
            {
                "path": "a.py",
                "qualified": "get_value",
                "start_line": 1,
                "source": "def get_value():\n    return value",
            }
        ],
        "target": {
            "claims": [
                {
                    "text": "get_value returns value.",
                    "aspect_id": 1,
                    "status": "supported",
                    "citations": [{"source_id": 1, "start_line": 2, "end_line": 2}],
                }
            ]
        },
    }
    with pytest.raises(ValueError, match="reviewed requirement coverage"):
        validate_target(row)
    row["target"]["requirement_coverage"] = [
        {"requirement_id": r["id"], "status": "covered", "claim_indices": [0]} for r in req
    ]
    validate_target(row)
    row["target"]["requirement_coverage"][0]["claim_indices"] = [999]
    with pytest.raises(ValueError, match="own aspect"):
        validate_target(row)


def test_pending_targets_do_not_create_training_files(tmp_path):
    pack = tmp_path / "review.jsonl"
    pack.write_text(
        json.dumps(
            {
                "id": "pending",
                "repository": "repo",
                "split": "development",
                "target_reviewed": False,
            }
        )
        + "\n"
    )
    output = tmp_path / "training"
    gate = export(pack, output)
    assert gate["training_ready"] is False
    assert gate["pending_targets"] == 1
    assert not output.exists()


def test_training_gate_rejects_repository_split_leakage(tmp_path):
    pack = tmp_path / "review.jsonl"
    pack.write_text(
        "\n".join(
            json.dumps(
                {"id": split, "repository": "repo", "split": split, "target_reviewed": False}
            )
            for split in ("development", "holdout")
        )
    )
    with pytest.raises(ValueError, match="leakage"):
        export(pack, tmp_path / "training")


def test_structured_training_target_requires_owner_and_real_lines():
    row = {
        "target_reviewed": True,
        "reviewer": "fixture-reviewer",
        "aspects": ["What does Child.run return?"],
        "source_evidence": [
            {
                "path": "service.py",
                "qualified": "pkg.Other.run",
                "start_line": 20,
                "source": "def run():\n    return value",
            }
        ],
        "target": {
            "claims": [
                {
                    "text": "Child.run returns value.",
                    "aspect_id": 1,
                    "status": "supported",
                    "citations": [{"source_id": 1, "start_line": 21, "end_line": 21}],
                }
            ]
        },
    }
    with pytest.raises(ValueError, match="different source owner"):
        validate_target(row)
    row["target"]["claims"][0]["text"] = "Other.run returns value."
    validate_target(row)
    row["target"]["claims"][0]["citations"][0]["end_line"] = 25
    with pytest.raises(ValueError, match="missing lines"):
        validate_target(row)


def test_reviewed_targets_follow_current_four_claim_contract():
    claim = {
        "text": "Details are not available.",
        "aspect_id": 1,
        "status": "insufficient_evidence",
        "citations": [],
    }
    row = {
        "target_reviewed": True,
        "reviewer": "fixture-reviewer",
        "aspects": ["Explain the workflow"],
        "source_evidence": [],
        "target": {"claims": [dict(claim) for _ in range(4)]},
    }
    validate_target(row)
    row["target"]["claims"].append(dict(claim))
    with pytest.raises(ValueError, match="Too many target claims"):
        validate_target(row)
