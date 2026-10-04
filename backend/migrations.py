"""Idempotent additive migrations. Never rewrite immutable snapshot content."""

from .models import file_id, file_role

VERSION = 2


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        file_id TEXT NOT NULL, language TEXT NOT NULL, kind TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS issues (
        id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        snapshot TEXT NOT NULL, payload TEXT NOT NULL, detector_version TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS suggestions (
        id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        snapshot TEXT NOT NULL, issue_id TEXT, created_at TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS retrieval_traces (
        id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL, snapshot TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS evaluations (
        id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL, snapshot TEXT NOT NULL, payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS chunks_repo_language ON chunks(repo_id,language);
    CREATE INDEX IF NOT EXISTS issues_repo ON issues(repo_id);
    CREATE INDEX IF NOT EXISTS traces_repo ON retrieval_traces(repo_id,created_at);
    CREATE INDEX IF NOT EXISTS suggestions_repo ON suggestions(repo_id);
    CREATE INDEX IF NOT EXISTS evaluations_repo ON evaluations(repo_id);
    CREATE INDEX IF NOT EXISTS edge_type ON edges(repo_id,kind);
    """)
    for table, columns in {
        "files": {"file_id": "TEXT", "role": "TEXT NOT NULL DEFAULT 'source'"},
        "symbols": {
            "file_id": "TEXT",
            "language": "TEXT NOT NULL DEFAULT 'text'",
            "signature": "TEXT NOT NULL DEFAULT ''",
            "role": "TEXT NOT NULL DEFAULT 'source'",
        },
    }.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    # One-time enrichment of legacy metadata; source and IDs stay unchanged.
    if not conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone():
        for row in conn.execute("SELECT repo_id,path,language FROM files").fetchall():
            conn.execute(
                "UPDATE files SET file_id=?,role=? WHERE repo_id=? AND path=?",
                (file_id(row[0], row[1]), file_role(row[1]), row[0], row[1]),
            )
        conn.execute(
            "UPDATE symbols SET file_id=(SELECT file_id FROM files f WHERE f.repo_id=symbols.repo_id AND f.path=symbols.path), language=COALESCE((SELECT language FROM files f WHERE f.repo_id=symbols.repo_id AND f.path=symbols.path),'text')"
        )
        conn.execute("INSERT INTO schema_migrations VALUES (?)", (VERSION,))
    conn.execute(
        "CREATE INDEX IF NOT EXISTS symbols_qualified_language ON symbols(repo_id,qualified,language)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS files_id ON files(file_id)")
