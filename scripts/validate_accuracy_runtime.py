"""Live local provider and complete semantic-index smoke check in disposable storage."""

import argparse
import json
import os
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite a result")
    with tempfile.TemporaryDirectory(prefix="devpilot-accuracy-runtime-") as data:
        os.environ["DEVPILOT_DATA"] = data
        os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        os.environ.setdefault("DEVPILOT_LLM_MODEL", "qwen2.5-coder:7b")
        os.environ.setdefault("DEVPILOT_EMBEDDING_MODEL", "nomic-embed-text:latest")
        from fastapi.testclient import TestClient

        from backend.main import app

        with TestClient(app) as client:
            creation = client.post("/api/demo", json={})
            creation.raise_for_status()
            repo_id = creation.json()["id"]
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                repo = client.get("/api/repositories/" + repo_id).json()
                if repo["status"] in ("ready", "failed"):
                    break
                time.sleep(0.1)
            if repo["status"] != "ready":
                raise ValueError("Demo index failed or timed out: " + str(repo.get("error")))
            response = client.post(
                f"/api/repositories/{repo_id}/ask",
                json={
                    "question": "How does calculate_quote validate and price an international parcel?",
                    "mode": "semantic",
                    "use_model": False,
                },
            )
            response.raise_for_status()
            answer = response.json()
            index = client.get(f"/api/repositories/{repo_id}/index-status").json()
            readiness = client.get("/api/provider-status?probe=true").json()
            report = {
                "scope": "live provider plumbing and disposable demo; not evidence of a semantic retrieval accuracy gain",
                "provider": readiness,
                "index": index,
                "semantic_used": answer["semantic_used"],
                "evidence_symbols": [s["qualified"] for s in answer["evidence"]],
                "source_snapshot_unchanged": client.get("/api/repositories/" + repo_id).json()[
                    "fingerprint"
                ]
                == repo["fingerprint"],
            }
            report["passed"] = bool(
                index["semantic_ready"]
                and answer["semantic_used"]
                and report["source_snapshot_unchanged"]
                and readiness["generation_probe"] == "passed"
                and readiness["embedding_probe"] == "passed"
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
            if not report["passed"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
