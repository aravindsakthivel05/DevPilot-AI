import json
import sqlite3
from contextlib import contextmanager

from .config import DATA

DB_PATH = DATA / "devpilot.sqlite3"


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    with connection() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS repositories (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
            commit_id TEXT, fingerprint TEXT, status TEXT NOT NULL,
            progress TEXT, created_at TEXT NOT NULL, stats TEXT DEFAULT '{}', error TEXT
        );
        CREATE TABLE IF NOT EXISTS files (
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            path TEXT NOT NULL, content TEXT NOT NULL, language TEXT NOT NULL,
            PRIMARY KEY(repo_id,path)
        );
        CREATE TABLE IF NOT EXISTS coverage (
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            path TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
            reason TEXT, size INTEGER, extension TEXT,
            PRIMARY KEY(repo_id,path)
        );
        CREATE INDEX IF NOT EXISTS coverage_repo_status ON coverage(repo_id,status);
        CREATE TABLE IF NOT EXISTS symbols (
            id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            path TEXT NOT NULL, name TEXT NOT NULL, qualified TEXT NOT NULL,
            kind TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
            source TEXT NOT NULL, docstring TEXT DEFAULT '', parent_id TEXT
        );
        CREATE INDEX IF NOT EXISTS symbols_repo ON symbols(repo_id);
        CREATE TABLE IF NOT EXISTS edges (
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL,
            line INTEGER, confidence TEXT NOT NULL, label TEXT,
            UNIQUE(repo_id,source,target,kind,line)
        );
        CREATE INDEX IF NOT EXISTS edges_repo ON edges(repo_id);
        CREATE TABLE IF NOT EXISTS embeddings (
            symbol_id TEXT PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            model TEXT NOT NULL, vector TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS investigations (
            id TEXT PRIMARY KEY, repo_id TEXT REFERENCES repositories(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, question TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_repository_splits (
            repo_id TEXT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
            split TEXT NOT NULL CHECK(split IN ('development','holdout')),
            assigned_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_cases (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            snapshot TEXT NOT NULL,
            investigation_id TEXT REFERENCES investigations(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            initial_result TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending'
                CHECK(review_status IN ('pending','reviewed')),
            review TEXT,
            review_history TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS learning_cases_repo_status
            ON learning_cases(repo_id,review_status,created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS learning_cases_investigation
            ON learning_cases(repo_id,investigation_id) WHERE investigation_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY, repo_id TEXT REFERENCES repositories(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL, result TEXT NOT NULL
        );
        """)


def repository(repo_id):
    with connection() as c:
        row = c.execute("SELECT * FROM repositories WHERE id=?", (repo_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["stats"] = json.loads(result["stats"])
    return result


def update_repository(repo_id, **values):
    allowed = {"status", "progress", "commit_id", "fingerprint", "stats", "error"}
    assert set(values) <= allowed
    with connection() as c:
        c.execute(
            "UPDATE repositories SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
            [*values.values(), repo_id],
        )


def symbols(repo_id):
    with connection() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM symbols WHERE repo_id=? ORDER BY path,start_line", (repo_id,)
            )
        ]


def symbols_by_ids(repo_id, ids):
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with connection() as c:
        rows = c.execute(
            f"SELECT * FROM symbols WHERE repo_id=? AND id IN ({placeholders})",
            (repo_id, *ids),
        ).fetchall()
    found = {row["id"]: dict(row) for row in rows}
    return [found[sid] for sid in ids if sid in found]


def edges(repo_id):
    with connection() as c:
        return [dict(r) for r in c.execute("SELECT * FROM edges WHERE repo_id=?", (repo_id,))]
