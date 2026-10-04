"""Persist reproducible static issue candidates; execution is never required."""

import json

from .. import db
from .dependencies import import_cycles
from .localisation import attach
from .models import issue
from .rules import candidates

VERSION = "2026-10-04-conservative-static-v1"


def analyze(repo_id):
    repo = db.repository(repo_id)
    with db.connection() as c:
        files = {
            r["path"]: r["content"]
            for r in c.execute("SELECT path,content FROM files WHERE repo_id=?", (repo_id,))
        }
    rows = []
    for candidate in candidates(files, repo["stats"].get("parse_errors", [])):
        path = candidate.pop("path")
        kind = candidate.pop("kind")
        fix = candidate.pop("fix")
        rows.append(issue(repo_id, repo["fingerprint"], kind, path, fix=fix, **candidate))
    for paths, line in import_cycles(db.symbols(repo_id), db.edges(repo_id)):
        rows.append(
            issue(
                repo_id,
                repo["fingerprint"],
                "circular_dependency",
                paths[0],
                line,
                "Indexed imports form a cycle: " + " → ".join(paths),
                "Established file-import edges form a strongly connected component. Such cycles can be intentional and are not proof of runtime failure.",
                "Review initialization order and consider moving shared contracts into an independent module if the cycle causes a problem.",
                severity="info",
                confidence="medium",
            )
        )
    unique = {row["id"]: row for row in rows}
    rows = attach(repo_id, list(unique.values()))
    with db.connection() as c:
        c.execute("DELETE FROM issues WHERE repo_id=?", (repo_id,))
        c.executemany(
            "INSERT INTO issues VALUES (?,?,?,?,?)",
            [(r["id"], repo_id, repo["fingerprint"], json.dumps(r), VERSION) for r in rows],
        )
    return {
        "issues": rows,
        "snapshot": repo["fingerprint"],
        "detector_version": VERSION,
        "notice": "Static candidates, not execution-confirmed errors. Unresolved calls alone are not defects.",
    }


def list_issues(repo_id):
    with db.connection() as c:
        return [
            json.loads(r[0])
            for r in c.execute("SELECT payload FROM issues WHERE repo_id=? ORDER BY id", (repo_id,))
        ]
