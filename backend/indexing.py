"""Rebuild analysis/search from stored immutable files, without changing snapshots."""

import json
from collections import Counter

from . import db
from .config import provider_settings
from .config_links import configuration_edges
from .embedding_policy import eligible
from .languages.registry import analyze_repository, detect_language
from .models import file_id, file_role
from .providers import embedding_signature, index_embeddings
from .rag.chunking import repository_chunks
from .retrieval import retrieve
from .structure import enrich

INDEX_VERSION = "2026-10-04-language-adapters-v4"


def rebuild(repo_id, embeddings=False):
    repo = db.repository(repo_id)
    if not repo or repo["status"] not in ("ready", "indexing"):
        raise ValueError("Repository must be ready before rebuilding indexes.")
    with db.connection() as c:
        files = {
            r["path"]: r["content"]
            for r in c.execute("SELECT path,content FROM files WHERE repo_id=?", (repo_id,))
        }
        previous = {
            r["id"]: (r["qualified"], r["source"], r["docstring"], r["signature"])
            for r in c.execute(
                "SELECT id,qualified,source,docstring,signature FROM symbols WHERE repo_id=?",
                (repo_id,),
            )
        }
        old_vectors = [
            dict(r)
            for r in c.execute(
                "SELECT e.* FROM embeddings e JOIN symbols s ON e.symbol_id=s.id WHERE s.repo_id=?",
                (repo_id,),
            )
        ]
    analysis = analyze_repository(repo_id, files)
    symbols, edges, errors, unresolved = (
        analysis.symbols,
        analysis.relationships,
        analysis.errors,
        analysis.unresolved,
    )
    edges += configuration_edges(repo_id, files, symbols)
    extra, relationships = enrich(repo_id, files, symbols, edges)
    symbols += extra
    edges += relationships
    chunks = repository_chunks(symbols, edges)
    unchanged = {
        s["id"]
        for s in symbols
        if previous.get(s["id"]) == (s["qualified"], s["source"], s["docstring"], s["signature"])
    }
    retained_vectors = [v for v in old_vectors if v["symbol_id"] in unchanged]
    # Whole replacement is transactional. Old model vectors cannot accidentally
    # remain associated with altered symbol contents.
    with db.connection() as c:
        c.execute("DELETE FROM edges WHERE repo_id=?", (repo_id,))
        c.execute("DELETE FROM symbols WHERE repo_id=?", (repo_id,))
        c.executemany(
            "INSERT INTO symbols(id,repo_id,path,name,qualified,kind,start_line,end_line,source,docstring,parent_id,file_id,language,signature,role) VALUES (:id,:repo_id,:path,:name,:qualified,:kind,:start_line,:end_line,:source,:docstring,:parent_id,:file_id,:language,:signature,:role)",
            symbols,
        )
        c.executemany(
            "INSERT OR IGNORE INTO edges VALUES (:repo_id,:source,:target,:kind,:line,:confidence,:label)",
            edges,
        )
        c.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?)",
            [
                (
                    s["id"],
                    repo_id,
                    s["file_id"],
                    s["language"],
                    s["kind"],
                    json.dumps(chunks[s["id"]]),
                )
                for s in symbols
            ],
        )
        c.executemany(
            "INSERT OR REPLACE INTO embeddings (symbol_id,model,vector,signature) VALUES (:symbol_id,:model,:vector,:signature)",
            retained_vectors,
        )
        c.executemany(
            "UPDATE files SET file_id=?,language=?,role=? WHERE repo_id=? AND path=?",
            [
                (file_id(repo_id, p), detect_language(p, files[p]), file_role(p), repo_id, p)
                for p in files
            ],
        )
        c.execute("DELETE FROM issues WHERE repo_id=?", (repo_id,))
        c.execute("DELETE FROM unresolved_references WHERE repo_id=?", (repo_id,))
        c.executemany(
            "INSERT INTO unresolved_references VALUES (?,?)",
            [(repo_id, json.dumps(item)) for item in unresolved],
        )
    cfg = provider_settings()
    current_vectors = [
        v
        for v in retained_vectors
        if v["model"] == cfg["embedding_model"] and v["signature"] == embedding_signature()
    ]
    embedding_ready = bool(cfg["embedding_model"]) and len(current_vectors) == sum(
        eligible(s) for s in symbols
    )
    stats = {
        **repo["stats"],
        "languages": dict(Counter(detect_language(p, files[p]) for p in files)),
        "symbols": len(symbols),
        "edges": len(edges),
        "parse_errors": errors,
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:100],
        "index_version": INDEX_VERSION,
        "embedding_status": "ready"
        if embedding_ready
        else ("stale" if cfg["embedding_model"] else "not_configured"),
    }
    if embeddings:
        try:
            stats["embedding_status"] = (
                "ready"
                if embedding_ready
                else index_embeddings(symbols, cached_vectors=current_vectors)
            )
        except Exception as exc:
            stats.update(embedding_status="failed", embedding_error=str(exc))
    db.update_repository(repo_id, stats=json.dumps(stats))
    retrieve(repo_id, "index readiness", mode="lexical", limit=1)
    if db.repository(repo_id)["fingerprint"] != repo["fingerprint"]:
        raise ValueError("Snapshot changed during rebuild.")
    return {
        "repo_id": repo_id,
        "name": repo["name"],
        "symbols": len(symbols),
        "edges": len(edges),
        "index_version": INDEX_VERSION,
        "embedding_status": stats["embedding_status"],
    }
