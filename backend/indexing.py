"""Rebuild analysis/search from stored immutable files, without changing snapshots."""

import json
from collections import Counter

from . import db
from .config_links import configuration_edges
from .languages.registry import analyze_repository, detect_language
from .models import file_id, file_role
from .providers import index_embeddings
from .rag.chunking import repository_chunks
from .retrieval import retrieve
from .structure import enrich

INDEX_VERSION = "2026-10-04-language-adapters-v1"


def rebuild(repo_id, embeddings=False):
    repo = db.repository(repo_id)
    if not repo or repo["status"] not in ("ready", "indexing"):
        raise ValueError("Repository must be ready before rebuilding indexes.")
    with db.connection() as c:
        files = {
            r["path"]: r["content"]
            for r in c.execute("SELECT path,content FROM files WHERE repo_id=?", (repo_id,))
        }
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
            "UPDATE files SET file_id=?,language=?,role=? WHERE repo_id=? AND path=?",
            [(file_id(repo_id, p), detect_language(p), file_role(p), repo_id, p) for p in files],
        )
        c.execute("DELETE FROM issues WHERE repo_id=?", (repo_id,))
        c.execute("DELETE FROM unresolved_references WHERE repo_id=?", (repo_id,))
        c.executemany(
            "INSERT INTO unresolved_references VALUES (?,?)",
            [(repo_id, json.dumps(item)) for item in unresolved],
        )
    stats = {
        **repo["stats"],
        "languages": dict(Counter(detect_language(p) for p in files)),
        "symbols": len(symbols),
        "edges": len(edges),
        "parse_errors": errors,
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:100],
        "index_version": INDEX_VERSION,
        "embedding_status": "not_configured",
    }
    if embeddings:
        try:
            stats["embedding_status"] = index_embeddings(symbols)
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
