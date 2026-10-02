"""Exercise live Ollama embeddings, repository answer, and proposal APIs."""

import json
import os
import tempfile
import time

from fastapi.testclient import TestClient


def main():
    with tempfile.TemporaryDirectory(prefix="devpilot-model-check-") as data:
        os.environ["DEVPILOT_DATA"] = data
        os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        os.environ.setdefault("DEVPILOT_LLM_MODEL", "llama3.2:latest")
        os.environ.setdefault("DEVPILOT_EMBEDDING_MODEL", "nomic-embed-text")
        from backend.main import app

        with TestClient(app) as client:
            repo_id = client.post("/api/demo", json={}).json()["id"]
            for _ in range(300):
                repo = client.get(f"/api/repositories/{repo_id}").json()
                if repo["status"] in ("ready", "failed"):
                    break
                time.sleep(0.1)
            if repo["status"] != "ready":
                raise SystemExit(repo["error"])
            answer = client.post(
                f"/api/repositories/{repo_id}/ask",
                json={
                    "question": "How does calculate_quote determine a shipping quote?",
                    "mode": "semantic",
                },
            )
            answer.raise_for_status()
            result = answer.json()
            proposal = client.post(
                f"/api/repositories/{repo_id}/propose",
                json={
                    "request": (
                        "Change shipping_quote so zero-weight domestic parcels receive the "
                        "minimum 10.0 quote, and add a regression test that fails before the fix."
                    )
                },
            )
            execution = None
            if proposal.status_code == 200:
                draft = proposal.json()
                submitted = client.post(
                    f"/api/repositories/{repo_id}/execute",
                    json={
                        "patch": draft["patch"],
                        "extra_tests": draft["extra_tests"],
                        "target": "tests",
                        "timeout": 60,
                    },
                )
                if submitted.status_code == 202:
                    for _ in range(700):
                        run = client.get("/api/executions/" + submitted.json()["id"]).json()
                        if run["status"] in ("complete", "failed"):
                            break
                        time.sleep(0.1)
                    execution = {
                        "status": run["status"],
                        "baseline_exit": (run["result"].get("baseline") or {}).get("exit_code"),
                        "patched_exit": (run["result"].get("patched") or {}).get("exit_code"),
                        "regression_demonstrated": run["result"].get("regression_demonstrated"),
                        "error": run["result"].get("error"),
                    }
                else:
                    execution = {"status_code": submitted.status_code, "error": submitted.text}
            print(
                json.dumps(
                    {
                        "embedding_status": repo["stats"]["embedding_status"],
                        "answer_generated": result["generated"],
                        "semantic_used": result["semantic_used"],
                        "citation_check": result["citation_check"],
                        "answer_warning": result["warning"],
                        "proposal_status_code": proposal.status_code,
                        "proposal_status": proposal.json().get("status"),
                        "proposal_error": proposal.json().get("detail"),
                        "proposal_test_count": len(proposal.json().get("extra_tests", {})),
                        "proposal_patch_present": bool(proposal.json().get("patch")),
                        "proposal_execution": execution,
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
