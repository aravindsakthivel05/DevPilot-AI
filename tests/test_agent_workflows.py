import time

from backend import agent_repair, retrieval


def test_deep_investigation_is_opt_in(client, repo, monkeypatch):
    path = f"/api/repositories/{repo['id']}/ask"
    payload = {
        "question": "Where is the shipping quote calculated?",
        "use_model": False,
        "deep": True,
    }
    assert client.post(path, json=payload).status_code == 422
    monkeypatch.setenv("DEVPILOT_LANGGRAPH_ENABLED", "1")
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["workflow"]["engine"] == "langgraph"
    assert result["workflow"]["retrieval_passes"] >= 1
    assert result["evidence"]
    assert result["snapshot"] == repo["fingerprint"]
    quick = client.post(path, json={**payload, "deep": False}).json()
    assert "workflow" not in quick


def test_deep_answer_uses_existing_citation_policy(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LANGGRAPH_ENABLED", "1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "test-model")
    monkeypatch.setattr(
        retrieval,
        "generate",
        lambda *_args, **_kwargs: ("The source contains the quote path. [1]", {}),
    )
    response = client.post(
        f"/api/repositories/{repo['id']}/ask",
        json={"question": "Where is the shipping quote calculated?", "deep": True},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["generated"] is True
    assert result["citation_check"]["has_citations"] is True


def test_guided_repair_pauses_before_execution(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LANGGRAPH_ENABLED", "1")
    calls = []
    draft = {
        "summary": "Temporary reviewed test",
        "patch": "diff --git a/parcel/pricing.py b/parcel/pricing.py\n",
        "extra_tests": {"tests/test_generated.py": "def test_change(): assert False\n"},
        "status": "draft_unverified",
    }
    monkeypatch.setattr(agent_repair, "propose", lambda *_: draft)

    def fake_execute(*args, **kwargs):
        calls.append((args, kwargs))
        if kwargs.get("patch"):
            return {"status": "passed", "exit_code": 0, "output": "1 passed"}
        return {"status": "failed", "exit_code": 1, "output": "AssertionError"}

    monkeypatch.setattr(agent_repair, "execute", fake_execute)
    path = f"/api/repositories/{repo['id']}/guided-repairs"
    response = client.post(path, json={"request": "Change parcel pricing behavior"})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "review"
    assert run["result"]["draft"] == draft
    assert not calls
    pending = client.get(f"{path}?status=review").json()
    assert [item["id"] for item in pending] == [run["id"]]
    review_path = f"{path}/{run['id']}/review"
    assert client.post(review_path, json={"approved": True}).status_code == 202
    assert client.post(review_path, json={"approved": True}).status_code == 409
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        completed = client.get(f"/api/guided-repairs/{run['id']}").json()
        if completed["status"] != "running":
            break
        time.sleep(0.02)
    assert completed["status"] == "complete", completed
    assert completed["result"]["regression_demonstrated"] is True
    assert len(calls) == 2
    assert all(args[2] == "tests/test_generated.py" for args, _ in calls)


def test_declined_guided_repair_never_executes(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LANGGRAPH_ENABLED", "1")
    monkeypatch.setattr(
        agent_repair,
        "propose",
        lambda *_: {
            "summary": "draft",
            "patch": "diff --git a/x b/x\n",
            "extra_tests": {"tests/test_generated.py": "def test_x(): pass\n"},
        },
    )
    calls = []
    monkeypatch.setattr(agent_repair, "execute", lambda *_args, **_kwargs: calls.append(1))
    path = f"/api/repositories/{repo['id']}/guided-repairs"
    run = client.post(path, json={"request": "Change parcel pricing behavior"}).json()
    assert client.post(f"{path}/{run['id']}/review", json={"approved": False}).status_code == 202
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/guided-repairs/{run['id']}").json()
        if result["status"] != "running":
            break
        time.sleep(0.02)
    assert result["status"] == "complete", result
    assert result["result"]["outcome"] == "declined"
    assert not calls
