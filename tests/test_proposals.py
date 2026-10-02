"""Proposal generation stays reviewable and separate from execution."""

import json

import pytest
from conftest import wait_repo

from backend import providers
from backend.proposals import validate_proposal


def test_model_proposal_uses_repo_evidence_and_returns_review_draft(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    monkeypatch.setenv("DEVPILOT_PROPOSAL_MODEL", "fixture-code")
    calls = []

    def fake_request(endpoint, payload):
        calls.append((endpoint, payload))
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Cover zero weight",
                                "patch": "",
                                "extra_tests": {
                                    "tests/test_generated_weight.py": "def test_weight():\n    assert True\n"
                                },
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 30},
        }

    monkeypatch.setattr(providers, "request", fake_request)
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Add a regression test for Parcel validate weight"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "draft_unverified"
    assert result["extra_tests"]["tests/test_generated_weight.py"].startswith("def test_weight")
    assert calls[0][0] == "chat/completions"
    assert calls[0][1]["model"] == "fixture-code"
    assert "parcel.models.Parcel.validate" in calls[0][1]["messages"][1]["content"]
    assert "tests/test_devpilot_regression.py" in calls[0][1]["messages"][1]["content"]


def test_proposal_rejects_unsafe_test_path(client, repo, monkeypatch):
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
                                "summary": "bad path",
                                "patch": "",
                                "extra_tests": {"tests/../../bad.py": "pass"},
                            }
                        )
                    }
                }
            ]
        },
    )
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Test Parcel validate weight"},
    )
    assert response.status_code == 422


def test_proposal_suggests_an_unused_regression_test_path(client, tmp_path, monkeypatch):
    source = tmp_path / "python-project"
    (source / "tests").mkdir(parents=True)
    (source / "calculator.py").write_text("def total(value):\n    return value\n")
    (source / "tests/test_devpilot_regression.py").write_text(
        "def test_existing():\n    assert True\n"
    )
    created = client.post("/api/repositories", json={"source": str(source)})
    repo = wait_repo(client, created.json()["id"])
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")

    def fake_request(_endpoint, payload):
        suggested = json.loads(payload["messages"][1]["content"])["suggested_new_test_path"]
        assert suggested == "tests/test_devpilot_regression_2.py"
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Add a new total regression test",
                                "extra_tests": {suggested: "def test_total():\n    assert True\n"},
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(providers, "request", fake_request)
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Add a regression test for calculator.total"},
    )
    assert response.status_code == 200, response.text
    assert "tests/test_devpilot_regression_2.py" in response.json()["extra_tests"]


def test_proposal_retries_invalid_patch_format_once(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    calls = []

    def fake_request(endpoint, payload):
        calls.append(payload)
        draft = (
            {"summary": "bad format", "patch": "*** Begin Patch", "extra_tests": {}}
            if len(calls) == 1
            else {
                "summary": "Add a test",
                "patch": "",
                "extra_tests": {
                    "tests/test_generated.py": "def test_example():\n    assert True\n"
                },
            }
        )
        return {"choices": [{"message": {"content": json.dumps(draft)}}]}

    monkeypatch.setattr(providers, "request", fake_request)
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Add a regression test for Parcel validate weight"},
    )
    assert response.status_code == 200, response.text
    assert len(calls) == 2
    assert "failed validation" in calls[1]["messages"][-1]["content"]


def test_proposal_retries_unappliable_patch(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    calls = []

    def fake_request(endpoint, payload):
        calls.append(payload)
        draft = (
            {
                "summary": "bad hunk",
                "patch": (
                    "diff --git a/parcel/models.py b/parcel/models.py\n"
                    "--- a/parcel/models.py\n+++ b/parcel/models.py\n"
                    "@@ -1 +1 @@\n-nonexistent line\n+replacement\n"
                ),
                "extra_tests": {},
            }
            if len(calls) == 1
            else {
                "summary": "reviewed test",
                "patch": "",
                "extra_tests": {
                    "tests/test_generated.py": "def test_example():\n    assert True\n"
                },
            }
        )
        return {"choices": [{"message": {"content": json.dumps(draft)}}]}

    monkeypatch.setattr(providers, "request", fake_request)
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Change Parcel validate weight handling"},
    )
    assert response.status_code == 200, response.text
    assert len(calls) == 2
    assert "cannot be applied" in calls[1]["messages"][-1]["content"]


def test_exact_source_edit_becomes_applicable_patch(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture-chat")
    draft = {
        "summary": "Permit zero weight",
        "patch": "model-supplied malformed diff",
        "edits": [
            {
                "path": "parcel/models.py",
                "old": "if self.weight_kg <= 0:",
                "new": "if self.weight_kg < 0:",
            }
        ],
        "extra_tests": {},
    }
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {"choices": [{"message": {"content": json.dumps(draft)}}]},
    )
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Allow zero weight in Parcel validate"},
    )
    assert response.status_code == 200, response.text
    patch = response.json()["patch"]
    assert patch.startswith("diff --git a/parcel/models.py b/parcel/models.py")
    assert response.json()["ignored_model_patch"] is True
    assert "-        if self.weight_kg <= 0:" in patch
    assert "+        if self.weight_kg < 0:" in patch


def test_proposal_cannot_edit_an_unretrieved_indexed_file(repo):
    draft = {
        "summary": "Change parcel validation",
        "edits": [
            {"path": "parcel/models.py", "old": "if self.weight_kg <= 0:", "new": "if False:"}
        ],
    }
    with pytest.raises(ValueError, match="not retrieved as evidence"):
        validate_proposal(draft, repo["id"], allowed_paths=set())


def test_java_proposal_accepts_new_test_and_exact_edit(client, tmp_path, monkeypatch):
    source = tmp_path / "java-project"
    java = source / "src/main/java/demo/Quote.java"
    java.parent.mkdir(parents=True)
    java.write_text("package demo;\npublic class Quote { int value() { return 1; } }\n")
    created = client.post("/api/repositories", json={"source": str(source)})
    repo = wait_repo(client, created.json()["id"])
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_PROPOSAL_MODEL", "fixture-code")
    draft = {
        "summary": "Change quote value and test it",
        "patch": "",
        "edits": [
            {"path": "src/main/java/demo/Quote.java", "old": "return 1;", "new": "return 2;"}
        ],
        "extra_tests": {
            "src/test/java/demo/QuoteRegressionTest.java": (
                "package demo;\nclass QuoteRegressionTest { "
                "void verifiesValue() { assert new Quote().value() == 2; } }\n"
            )
        },
    }
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {"choices": [{"message": {"content": json.dumps(draft)}}]},
    )
    response = client.post(
        f"/api/repositories/{repo['id']}/propose",
        json={"request": "Change Quote value to 2 and add a Java regression test"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["language"] == "java"
    assert "-public class Quote { int value() { return 1; } }" in response.json()["patch"]
    assert "src/test/java/demo/QuoteRegressionTest.java" in response.json()["extra_tests"]


def test_java_proposal_accepts_unique_line_with_missing_indentation(client, tmp_path, monkeypatch):
    source = tmp_path / "java-project"
    java = source / "src/main/java/demo/Quote.java"
    java.parent.mkdir(parents=True)
    java.write_text("package demo;\nclass Quote {\n  int value() {\n    return 1;\n  }\n}\n")
    created = client.post("/api/repositories", json={"source": str(source)})
    repo = wait_repo(client, created.json()["id"])
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setenv("DEVPILOT_PROPOSAL_MODEL", "fixture-code")
    draft = {
        "summary": "Change quote value",
        "edits": [
            {"path": "src/main/java/demo/Quote.java", "old": "return 1;", "new": "return 2;"}
        ],
    }
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {"choices": [{"message": {"content": json.dumps(draft)}}]},
    )
    response = client.post(
        f"/api/repositories/{repo['id']}/propose", json={"request": "Change Quote value"}
    )
    assert response.status_code == 200, response.text
    assert "-    return 1;" in response.json()["patch"]
    assert "+    return 2;" in response.json()["patch"]
