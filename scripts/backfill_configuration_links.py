"""Attach newly supported configuration relationships to existing pinned snapshots."""

import argparse
import json
from pathlib import Path

from backend import db
from backend.config_links import configuration_edges


def backfill(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    results = {}
    for name, info in manifest.items():
        repo = db.repository(info["id"])
        if not repo or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {name}")
        with db.connection() as connection:
            files = {
                row["path"]: row["content"]
                for row in connection.execute(
                    "SELECT path,content FROM files WHERE repo_id=? "
                    "AND (path LIKE '%.pyi' OR path LIKE '%mockito-extensions/%')",
                    (info["id"],),
                )
            }
        edges = configuration_edges(info["id"], files, db.symbols(info["id"]))
        with db.connection() as connection:
            before = connection.total_changes
            connection.executemany(
                "INSERT OR IGNORE INTO edges VALUES (:repo_id,:source,:target,:kind,:line,:confidence,:label)",
                edges,
            )
            added = connection.total_changes - before
            count = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE repo_id=?", (info["id"],)
            ).fetchone()[0]
            stats = repo["stats"]
            stats["edges"] = count
            connection.execute(
                "UPDATE repositories SET stats=? WHERE id=?", (json.dumps(stats), info["id"])
            )
        results[name] = added
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="+", help="Pinned snapshot manifests")
    args = parser.parse_args()
    for path in args.manifest:
        for name, added in backfill(path).items():
            print(f"{name}: {added} new configuration links")


if __name__ == "__main__":
    main()
