"""Run the frozen Marshmallow holdout on an isolated local DevPilot database."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
env = dict(os.environ)
env.update(
    {
        "DEVPILOT_DATA": str(root / ".devpilot/marshmallow-2026-10-06"),
        "DEVPILOT_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
        "DEVPILOT_LLM_MODEL": "qwen2.5-coder:14b",
        "DEVPILOT_VERIFY_MODEL": "qwen2.5-coder:14b",
        "DEVPILOT_EMBEDDING_BASE_URL": "http://127.0.0.1:11434/v1",
        "DEVPILOT_EMBEDDING_MODEL": "nomic-embed-text:latest",
        "DEVPILOT_PROVIDER_TIMEOUT_SECONDS": "180",
        "DEVPILOT_VERIFY_CLAIMS": "1",
        "DEVPILOT_OLLAMA_KEEP_ALIVE": "10m",
        "DEVPILOT_OLLAMA_THINK": "0",
        "DEVPILOT_LANGGRAPH_ENABLED": "0",
        "DEVPILOT_LEGACY_EXECUTION": "0",
        "DEVPILOT_RETRIEVAL_CACHE": "1",
    }
)
settings = {
    k: v
    for k, v in env.items()
    if k.startswith("DEVPILOT_")
    and k
    in {
        "DEVPILOT_LLM_BASE_URL",
        "DEVPILOT_LLM_MODEL",
        "DEVPILOT_VERIFY_MODEL",
        "DEVPILOT_EMBEDDING_BASE_URL",
        "DEVPILOT_EMBEDDING_MODEL",
        "DEVPILOT_PROVIDER_TIMEOUT_SECONDS",
        "DEVPILOT_VERIFY_CLAIMS",
        "DEVPILOT_OLLAMA_KEEP_ALIVE",
        "DEVPILOT_OLLAMA_THINK",
        "DEVPILOT_LANGGRAPH_ENABLED",
        "DEVPILOT_LEGACY_EXECUTION",
        "DEVPILOT_RETRIEVAL_CACHE",
    }
}
settings["models"] = {
    r["name"]: r["digest"]
    for r in httpx.get("http://127.0.0.1:11434/api/tags", timeout=10).json()["models"]
    if r["name"] in ("qwen2.5-coder:14b", "nomic-embed-text:latest")
}
(out / "run-settings.json").write_text(json.dumps(settings, indent=2) + "\n")
for stage in ("index", "run"):
    print("Starting", stage, flush=True)
    with (out / (stage + ".log")).open("w") as log:
        code = subprocess.run(
            [
                str(root / ".venv/bin/python"),
                "-m",
                "scripts.test_new_repositories",
                stage,
                "--output",
                str(out),
                "--checkouts",
                str(root / ".devpilot/marshmallow-2026-10-06-checkouts"),
                "--repository",
                "marshmallow=marshmallow-code/marshmallow",
                "--split",
                "holdout",
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        ).returncode
    print("Finished", stage, "exit", code, flush=True)
    if code:
        sys.exit(code)
