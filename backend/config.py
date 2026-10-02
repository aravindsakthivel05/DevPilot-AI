"""Local-first configuration. Credentials stay on the backend."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DEVPILOT_DATA", str(ROOT / ".devpilot"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
SNAPSHOTS = DATA / "snapshots"
SNAPSHOTS.mkdir(exist_ok=True)
MAX_FILES = int(os.environ.get("DEVPILOT_MAX_INDEX_FILES", "4000"))
MAX_FILE_BYTES = int(os.environ.get("DEVPILOT_MAX_INDEX_FILE_BYTES", "1000000"))
MAX_TOTAL_BYTES = int(os.environ.get("DEVPILOT_MAX_INDEX_BYTES", "40000000"))
MAX_COVERAGE_ENTRIES = 20_000
IGNORE = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".devpilot",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    "vendor",
}
SUFFIXES = {
    ".py",
    ".pyi",
    ".java",
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".gradle",
    ".kts",
    ".kt",
    ".groovy",
    ".properties",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}

TEXT_FILENAMES = {"Dockerfile", "Makefile", "MANIFEST.in", "gradlew", "mvnw"}


def provider_settings():
    return {
        "base_url": os.environ.get("DEVPILOT_LLM_BASE_URL", "").rstrip("/"),
        "model": os.environ.get("DEVPILOT_LLM_MODEL", ""),
        "proposal_model": os.environ.get("DEVPILOT_PROPOSAL_MODEL", ""),
        "api_key": os.environ.get("DEVPILOT_API_KEY", ""),
        "embedding_model": os.environ.get("DEVPILOT_EMBEDDING_MODEL", ""),
    }


def agent_enabled():
    return os.environ.get("DEVPILOT_LANGGRAPH_ENABLED", "").lower() in ("1", "true", "yes")
