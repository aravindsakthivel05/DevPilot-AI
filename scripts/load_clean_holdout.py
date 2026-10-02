"""Pin two previously unused repositories before tuning retrieval or prompts."""

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

SOURCES = {
    "click": "https://github.com/pallets/click",
    "junit4": "https://github.com/junit-team/junit4",
}
OUTPUT = Path("evaluation/clean-holdout-snapshots.json")


def main(sources=SOURCES, output=OUTPUT):
    if output.exists():
        raise SystemExit(f"Holdout already pinned in {output}; do not silently replace it.")
    from backend.main import app

    results = {}
    with TestClient(app) as client:
        for name, source in sources.items():
            response = client.post("/api/repositories", json={"name": name, "source": source})
            response.raise_for_status()
            repo_id = response.json()["id"]
            for _ in range(1800):
                repo = client.get(f"/api/repositories/{repo_id}").json()
                if repo["status"] in ("ready", "failed"):
                    break
                time.sleep(0.1)
            if repo["status"] != "ready":
                raise SystemExit(f"{name}: {repo.get('error') or repo['status']}")
            results[name] = {
                "source": source,
                "id": repo_id,
                "commit": repo["commit_id"],
                "fingerprint": repo["fingerprint"],
                "files": repo["stats"]["files"],
            }
            print(f"{name}: {repo['commit_id']}", flush=True)
    output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
