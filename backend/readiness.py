"""Explicit provider probes and repository index status; never expose credentials."""

from . import db, providers
from .config import provider_settings
from .search import VERSION


def provider_status(probe=False):
    cfg = provider_settings()
    result = {
        "model": cfg["model"] or None,
        "configured": bool(cfg["model"] and cfg["base_url"]),
        "context_window": providers.context_window(),
        "reachable": None,
        "generation_probe": "not_requested",
        "embedding_probe": "not_requested",
    }
    if not probe:
        return result
    native = providers._ollama_native_url(cfg) if cfg["base_url"] else None
    if native:
        try:
            base = native.removesuffix("/api/chat")
            client = providers._client(10, base)
            tags = client.get(base + "/api/tags")
            tags.raise_for_status()
            models = tags.json().get("models", [])
            name = cfg["model"] if ":" in cfg["model"] else cfg["model"] + ":latest"
            model = next(
                (m for m in models if m.get("name") == name or m.get("model") == name), None
            )
            result.update(
                reachable=True,
                model_installed=bool(model),
                model_digest=(model or {}).get("digest"),
                model_details=(model or {}).get("details"),
            )
        except Exception as exc:
            result.update(
                reachable=False, error=f"Local provider inspection failed: {type(exc).__name__}"
            )
    if result["configured"]:
        try:
            response = providers.request(
                "chat/completions",
                {
                    "model": cfg["model"],
                    "temperature": 0,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                },
            )
            content = response["choices"][0]["message"]["content"]
            result.update(
                reachable=True, generation_probe="passed" if content.strip() else "empty_response"
            )
        except Exception as exc:
            result.update(generation_probe="failed", generation_error=str(exc)[:250])
    if cfg["embedding_model"]:
        try:
            vector = providers.embed(["DevPilot provider readiness check"])[0]
            result.update(
                embedding_probe="passed",
                embedding_dimensions=len(vector),
                embedding_signature=providers.embedding_signature(),
            )
        except Exception as exc:
            result.update(embedding_probe="failed", embedding_error=str(exc)[:250])
    if native:
        try:
            ps = providers._client(10, native.removesuffix("/api/chat")).get(
                native.removesuffix("/api/chat") + "/api/ps"
            )
            ps.raise_for_status()
            result["loaded_models"] = [
                {k: row.get(k) for k in ("name", "digest", "context_length", "size_vram")}
                for row in ps.json().get("models", [])
            ]
        except Exception as exc:
            result["runtime_inspection_error"] = type(exc).__name__
    return result


def index_status(repo_id):
    repo = db.repository(repo_id)
    with db.connection() as c:
        total = c.execute("SELECT COUNT(*) FROM symbols WHERE repo_id=?", (repo_id,)).fetchone()[0]
        embedded = c.execute(
            "SELECT COUNT(*) FROM embeddings e JOIN symbols s ON s.id=e.symbol_id "
            "WHERE s.repo_id=? AND e.signature=?",
            (repo_id, providers.embedding_signature()),
        ).fetchone()[0]
        state = c.execute("SELECT * FROM search_state WHERE repo_id=?", (repo_id,)).fetchone()
        revision = c.execute(
            "SELECT revision FROM search_revisions WHERE repo_id=?", (repo_id,)
        ).fetchone()
        unresolved = c.execute(
            "SELECT COUNT(*) FROM unresolved_references WHERE repo_id=?", (repo_id,)
        ).fetchone()[0]
    return {
        "snapshot": repo["fingerprint"],
        "index_version": repo["stats"].get("index_version", "legacy"),
        "symbols": total,
        "embedded_symbols": embedded,
        "embedding_coverage": embedded / total if total else 0,
        "semantic_ready": bool(
            total and embedded == total and provider_settings()["embedding_model"]
        ),
        "lexical_ready": bool(
            state and state["version"] == VERSION and revision and state["revision"] == revision[0]
        ),
        "unresolved_references_stored": unresolved,
        "derived_index_current": repo["stats"].get("index_version")
        == "2026-10-04-language-adapters-v1",
        "analysis_scope": __import__(
            "backend.languages.registry", fromlist=["capabilities"]
        ).capabilities(),
        "coverage": repo["stats"].get("coverage"),
    }
