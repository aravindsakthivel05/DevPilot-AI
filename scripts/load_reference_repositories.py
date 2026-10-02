"""Load public reference and benchmark repositories into the local DevPilot workspace."""

import json
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from backend.config import DATA

SOURCES = {
    "flask": "https://github.com/pallets/flask",
    "requests": "https://github.com/psf/requests",
    "httpx": "https://github.com/encode/httpx",
    "pytest": "https://github.com/pytest-dev/pytest",
    "rich": "https://github.com/Textualize/rich",
    "petclinic": "https://github.com/spring-projects/spring-petclinic",
    "commons-lang": "https://github.com/apache/commons-lang",
    "mockito": "https://github.com/mockito/mockito",
    "fastapi": "https://github.com/fastapi/fastapi",
    "spring-data-elasticsearch": "https://github.com/spring-projects/spring-data-elasticsearch",
    "django": "https://github.com/django/django",
    "numpy": "https://github.com/numpy/numpy",
    "scikit-learn": "https://github.com/scikit-learn/scikit-learn",
    "pytorch": "https://github.com/pytorch/pytorch",
    "elasticsearch-java": "https://github.com/elastic/elasticsearch-java",
}

# These monorepositories exceed DevPilot's intentionally bounded full-checkout index limits.
# Index their primary library directories as explicit scoped snapshots instead of silently
# increasing resource limits or ingesting an arbitrary first N files.
SCOPES = {
    "django": "django",
    "pytorch": "torch",
    "elasticsearch-java": "java-client/src/main/java",
}


def source_for(name, url):
    scope = SCOPES.get(name)
    if not scope:
        return url
    checkout = DATA / "reference-checkouts" / name
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        run = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "--",
                url,
                str(checkout),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if run.returncode:
            raise RuntimeError(f"Clone failed for {name}: {run.stderr[-1500:]}")
    elif not (checkout / ".git").exists():
        raise RuntimeError(f"Refusing to use incomplete reference checkout: {checkout}")
    run = subprocess.run(
        ["git", "-C", str(checkout), "sparse-checkout", "set", "--", scope],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run.returncode:
        raise RuntimeError(f"Sparse checkout failed for {name}: {run.stderr[-1500:]}")
    source = (checkout / scope).resolve()
    if not source.is_dir():
        raise RuntimeError(f"Selected source scope is missing for {name}: {scope}")
    return str(source)


def main():
    from backend.main import app

    refresh = "--refresh" in sys.argv[1:]
    names = [value for value in sys.argv[1:] if value != "--refresh"] or list(SOURCES)
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f"Unknown repositories: {sorted(unknown)}")
    results = {}
    with TestClient(app) as client:
        existing = {item["source"]: item for item in client.get("/api/repositories").json()}
        for name in names:
            source = source_for(name, SOURCES[name])
            current = existing.get(source)
            if current and current["status"] == "ready" and not refresh:
                repo = current
            else:
                response = client.post("/api/repositories", json={"source": source, "name": name})
                response.raise_for_status()
                repo_id = response.json()["id"]
                for _ in range(1800):
                    repo = client.get(f"/api/repositories/{repo_id}").json()
                    if repo["status"] in ("ready", "failed"):
                        break
                    time.sleep(0.1)
            results[name] = {
                "id": repo["id"],
                "status": repo["status"],
                "commit": repo["commit_id"],
                "fingerprint": repo["fingerprint"],
                "files": repo["stats"].get("files") if repo["stats"] else None,
                "error": repo["error"],
            }
    print(json.dumps(results, indent=2))
    if any(item["status"] != "ready" for item in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
