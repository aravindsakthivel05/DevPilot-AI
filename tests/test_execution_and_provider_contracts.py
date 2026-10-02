"""Unavailable external services are simulated explicitly, never counted as live passes."""

import subprocess
import time
from types import SimpleNamespace

import httpx
import pytest

from backend import execution, providers


@pytest.mark.parametrize("target", ["../outside", "/tmp/outside", "--help"])
def test_execution_rejects_invalid_target_before_spawn(client, repo, monkeypatch, target):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    with pytest.raises(ValueError, match="relative path"):
        execution.execute(repo["id"], "fixture-image", target, 5)


def test_execution_rejects_generated_test_path_escape(client, repo, monkeypatch):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    with pytest.raises(ValueError, match="new files"):
        execution.execute(
            repo["id"], "fixture-image", "tests", 5, extra_tests={"../escape.py": "pass"}
        )


@pytest.mark.parametrize("code,expected", [(0, "passed"), (1, "failed")])
def test_runner_command_isolated_and_logs_persist(client, repo, monkeypatch, code, expected):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    captured = []

    class Process:
        def __init__(self, cmd, stdout, stderr):
            captured.append(cmd)
            stdout.write(b"Fixture-only container output\n")

        def wait(self, timeout=None):
            return code

    monkeypatch.setattr(execution.subprocess, "Popen", Process)
    monkeypatch.setattr(execution.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    result = execution.execute(repo["id"], "fixture-image", "tests", 5)
    command = captured[0]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop" in command
    assert command[command.index("--user") + 1] == "65534:65534"
    assert result["status"] == expected
    assert "Fixture-only" in result["output"]
    assert result["snapshot"] == repo["fingerprint"]


def test_runner_timeout_kills_and_cleans_container(client, repo, monkeypatch):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    actions = []

    class Process:
        def __init__(self, *args, **kwargs):
            pass

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return -1

        def kill(self):
            actions.append("killed")

    monkeypatch.setattr(execution.subprocess, "Popen", Process)
    monkeypatch.setattr(execution.subprocess, "run", lambda cmd, **kw: actions.append(cmd))
    result = execution.execute(repo["id"], "fixture-image", "tests", 5)
    assert result["status"] == "timeout"
    assert "killed" in actions
    assert any(isinstance(a, list) and a[:3] == ["docker", "rm", "-f"] for a in actions)


@pytest.mark.parametrize(
    "runner,manifest,target,expected",
    [
        ("maven", "pom.xml", "ExampleTest", "-Dtest=ExampleTest"),
        ("gradle", "build.gradle.kts", "ExampleTest", "--tests"),
    ],
)
def test_java_runner_command(client, repo, monkeypatch, runner, manifest, target, expected):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    (execution.SNAPSHOTS / repo["id"] / manifest).write_text("fixture")
    captured = []

    class Process:
        def __init__(self, cmd, stdout, stderr):
            captured.append(cmd)

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(execution.subprocess, "Popen", Process)
    monkeypatch.setattr(execution.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    test_path = (
        "src/test/java/ExampleTest.java"
        if runner == "maven"
        else "mockito-core/src/test/java/ExampleTest.java"
    )
    result = execution.execute(
        repo["id"],
        "fixture-image",
        target,
        5,
        runner=runner,
        extra_tests={test_path: "class ExampleTest {}"},
    )
    command = captured[0]
    assert expected in command
    assert "--offline" in command if runner == "gradle" else "-o" in command
    if runner == "gradle":
        assert "--init-script" in command
        assert command[command.index("--pids-limit") + 1] == "512"
    assert command[command.index("--network") + 1] == "none"
    assert result["runner"] == runner


@pytest.mark.parametrize("target", ["../outside", "/tmp/outside", "--help", "a/b"])
def test_java_runner_rejects_invalid_target(client, repo, monkeypatch, target):
    monkeypatch.setattr(execution, "docker_status", lambda: {"available": True})
    with pytest.raises(ValueError):
        execution.execute(repo["id"], "fixture-image", target, 5, runner="maven")


def test_before_after_execution_job_persists_result(client, repo, monkeypatch):
    monkeypatch.setattr("backend.main.docker_status", lambda: {"available": True})

    def fixture_execute(
        repo_id, image, target, timeout, patch=None, extra_tests=None, runner="python"
    ):
        return {
            "exit_code": 0 if patch else 1,
            "status": "passed" if patch else "failed",
            "output": "simulated",
        }

    monkeypatch.setattr(execution, "execute", fixture_execute)
    response = client.post(
        f"/api/repositories/{repo['id']}/execute", json={"patch": "fixture-patch"}
    )
    assert response.status_code == 202
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = client.get("/api/executions/" + response.json()["id"]).json()
        if run["status"] != "running":
            break
        time.sleep(0.01)
    assert run["status"] == "complete"
    assert run["result"]["regression_demonstrated"] is True


def test_embedding_response_order_and_batch_validation(monkeypatch):
    monkeypatch.setattr(
        providers,
        "request",
        lambda *a: {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]},
    )
    assert providers.embed(["a", "b"]) == [[1, 0], [0, 1]]
    with pytest.raises(ValueError, match="incomplete batch"):
        providers.embed(["a"])


def test_provider_http_contract_and_secret_not_returned(monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://provider.invalid/v1")
    monkeypatch.setenv("DEVPILOT_API_KEY", "fixture-only-key")
    calls = []
    real_client = httpx.Client

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw),
    )
    assert providers.request("embeddings", {"input": ["test"]}) == {"ok": True}
    assert str(calls[0].url) == "http://provider.invalid/v1/embeddings"
    assert calls[0].headers["Authorization"] == "Bearer fixture-only-key"


def test_real_container_execution_when_already_available(client, repo):
    if not execution.docker_status()["available"]:
        pytest.skip("Docker unavailable; no installation authorised in this test-only task")
    image = subprocess.run(
        ["docker", "image", "inspect", "devpilot-runner:local"], capture_output=True
    )
    if image.returncode:
        pytest.skip("Prepared runner image unavailable; image build deferred")
    result = execution.execute(repo["id"], "devpilot-runner:local", "tests", 60)
    assert result["exit_code"] == 0, result["output"]
