import json

from backend import db, ingestion, retrieval
from scripts.evaluate_dataset import evaluate
from scripts.export_learning_cases import export


def _source_ref(repo_id, qualified):
    symbol = next(item for item in db.symbols(repo_id) if item["qualified"] == qualified)
    return {
        "qualified": qualified,
        "path": symbol["path"],
        "start_line": symbol["start_line"],
        "end_line": symbol["end_line"],
    }


def _review(qualified, source_ref, split="development"):
    return {
        "answerable": True,
        "expected_symbols": [qualified],
        "expected_answer": "The reviewed function calculates a shipping quote from parcel details.",
        "source_refs": [source_ref],
        "answer_correct": None,
        "all_claims_supported": None,
        "appropriate_abstention": False,
        "split": split,
        "notes": "Checked the implementation and its source location.",
    }


def test_learning_case_requires_source_validated_review_and_stays_pending(client, repo):
    rid = repo["id"]
    result = client.post(
        f"/api/repositories/{rid}/ask",
        json={"question": "How is the shipping quote calculated?", "use_model": False},
    ).json()
    created = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={
            "question": "How is the shipping quote calculated?",
            "investigation_id": result["id"],
        },
    )
    assert created.status_code == 201, created.text
    case = created.json()
    assert case["review_status"] == "pending"
    assert case["initial_result"]["generated"] is False
    duplicate = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={
            "question": "How is the shipping quote calculated?",
            "investigation_id": result["id"],
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == case["id"]
    assert (
        client.get(f"/api/repositories/{rid}/learning-cases?status=pending").json()[0]["id"]
        == case["id"]
    )

    qualified = "parcel.pricing.calculate_quote"
    source_ref = _source_ref(rid, qualified)
    invalid_ref = {**source_ref, "start_line": source_ref["start_line"] - 1}
    rejected = client.post(
        f"/api/repositories/{rid}/learning-cases/{case['id']}/review",
        json=_review(qualified, invalid_ref),
    )
    assert rejected.status_code == 422
    assert "source range" in rejected.json()["detail"]

    reviewed = client.post(
        f"/api/repositories/{rid}/learning-cases/{case['id']}/review",
        json=_review(qualified, source_ref),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "reviewed"
    assert reviewed.json()["repository_split"] == "development"
    revised = _review(qualified, source_ref)
    revised["expected_answer"] = "The quote is calculated in the reviewed pricing function."
    revised["notes"] = "Corrected the wording after a second source check."
    updated = client.post(
        f"/api/repositories/{rid}/learning-cases/{case['id']}/review", json=revised
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["review_history"]) == 1
    assert updated.json()["review_history"][0]["expected_answer"] != revised["expected_answer"]


def test_reviewed_cases_keep_whole_repositories_in_one_split(client, repo):
    rid = repo["id"]
    first = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={"question": "Where is the quote calculated?"},
    ).json()
    qualified = "parcel.pricing.calculate_quote"
    source_ref = _source_ref(rid, qualified)
    accepted = client.post(
        f"/api/repositories/{rid}/learning-cases/{first['id']}/review",
        json=_review(qualified, source_ref, split="development"),
    )
    assert accepted.status_code == 200

    second = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={"question": "Which method calculates the quote?"},
    ).json()
    mismatch = client.post(
        f"/api/repositories/{rid}/learning-cases/{second['id']}/review",
        json=_review(qualified, source_ref, split="holdout"),
    )
    assert mismatch.status_code == 422
    assert "stay in its development split" in mismatch.json()["detail"]


def test_generated_answer_review_requires_explicit_correctness_and_support_labels(
    client, repo, monkeypatch
):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "test-local-model")
    monkeypatch.setattr(
        retrieval,
        "generate",
        lambda *_args, **_kwargs: ("calculate_quote determines the price [1].", {}),
    )
    rid = repo["id"]
    result = client.post(
        f"/api/repositories/{rid}/ask", json={"question": "How is the shipping quote calculated?"}
    ).json()
    assert result["generated"] is True
    assert result["model"] == "test-local-model"
    case = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={
            "question": "How is the shipping quote calculated?",
            "investigation_id": result["id"],
        },
    ).json()
    qualified = "parcel.pricing.calculate_quote"
    source_ref = _source_ref(rid, qualified)
    review = _review(qualified, source_ref)
    missing_score = client.post(
        f"/api/repositories/{rid}/learning-cases/{case['id']}/review", json=review
    )
    assert missing_score.status_code == 422
    assert "correctness" in missing_score.json()["detail"]

    review.update(answer_correct=True, all_claims_supported=False, appropriate_abstention=True)
    accepted = client.post(
        f"/api/repositories/{rid}/learning-cases/{case['id']}/review", json=review
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["initial_result"]["answer_prompt_version"]
    assert accepted.json()["review"]["all_claims_supported"] is False


def test_export_includes_only_reviewed_examples_and_separates_repo_splits(
    client, repo, tmp_path, monkeypatch
):
    monkeypatch.setattr(ingestion, "SNAPSHOTS", tmp_path / "snapshots")
    development_repo = repo["id"]
    holdout_repo = client.post("/api/demo", json={}).json()["id"]
    # The test client fixture's wait helper is shared with the existing integration tests.
    from conftest import wait_repo

    holdout_info = wait_repo(client, holdout_repo)
    qualified = "parcel.pricing.calculate_quote"

    for rid, split in ((development_repo, "development"), (holdout_repo, "holdout")):
        pending = client.post(
            f"/api/repositories/{rid}/learning-cases",
            json={"question": "How is a shipping quote calculated?"},
        ).json()
        response = client.post(
            f"/api/repositories/{rid}/learning-cases/{pending['id']}/review",
            json=_review(qualified, _source_ref(rid, qualified), split=split),
        )
        assert response.status_code == 200, response.text

    # A separate unreviewed case must never enter either exported dataset.
    unreviewed = client.post(
        f"/api/repositories/{holdout_repo}/learning-cases",
        json={"question": "What handles a missing shipping quote?"},
    )
    assert unreviewed.status_code == 201

    dev_path = tmp_path / "development.jsonl"
    holdout_path = tmp_path / "holdout.jsonl"
    manifest_path = tmp_path / "manifest.json"
    assert export(dev_path, holdout_path, manifest_path) == {
        "development": 1,
        "holdout": 1,
        "repositories": 2,
    }
    development = [json.loads(line) for line in dev_path.read_text().splitlines()]
    holdout = [json.loads(line) for line in holdout_path.read_text().splitlines()]
    manifest = json.loads(manifest_path.read_text())
    assert development[0]["split"] == "development"
    assert holdout[0]["split"] == "holdout"
    assert "unreviewed" not in {row["id"] for row in [*development, *holdout]}
    assert manifest[holdout[0]["repository"]]["fingerprint"] == holdout_info["fingerprint"]
    dev_result = evaluate(dev_path, manifest_path)
    holdout_result = evaluate(holdout_path, manifest_path)
    assert dev_result["case_count"] == 1
    assert holdout_result["case_count"] == 1
    assert {item["split"] for item in dev_result["summary"]} == {"development"}
    assert {item["split"] for item in holdout_result["summary"]} == {"holdout"}


def test_delete_repository_removes_snapshot_and_cascades_learning_data(client, repo, monkeypatch):
    snapshots = ingestion.SNAPSHOTS
    monkeypatch.setattr("backend.main.SNAPSHOTS", snapshots)
    rid = repo["id"]
    pending = client.post(
        f"/api/repositories/{rid}/learning-cases",
        json={"question": "Where is the quote calculated?"},
    ).json()
    assert client.get(f"/api/repositories/{rid}/learning-cases").json()

    deleted = client.delete(f"/api/repositories/{rid}")
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/repositories/{rid}").status_code == 404
    assert client.get(f"/api/repositories/{rid}/learning-cases").status_code == 404
    assert not (snapshots / rid).exists()
    with db.connection() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM learning_cases WHERE id=?", (pending["id"],)
            ).fetchone()
            is None
        )
