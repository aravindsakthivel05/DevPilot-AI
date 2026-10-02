"""Attach coverage to pinned references, reindexing when scanner rules changed."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.ingestion import collect_files, ingest
from scripts.load_reference_repositories import SOURCES

MANIFEST = Path("docs/indexed-reference-repositories.json")


def fingerprint(files):
    return hashlib.sha256(
        "".join(
            path + "\0" + hashlib.sha256(source.encode()).hexdigest()
            for path, source in sorted(files.items())
        ).encode()
    ).hexdigest()


def backfill(name, info):
    repo = db.repository(info["id"])
    if not repo or repo["fingerprint"] != info["fingerprint"]:
        raise ValueError(f"Pinned snapshot missing or changed: {name}")
    source = info.get("source") or SOURCES[name]
    with tempfile.TemporaryDirectory(prefix="devpilot-coverage-") as temp:
        root = Path(temp) / "repo"
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--depth",
                "1",
                "--",
                source,
                str(root),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if head != info["commit"]:
            subprocess.run(
                ["git", "-C", str(root), "fetch", "--depth", "1", "origin", info["commit"]],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            subprocess.run(
                ["git", "-C", str(root), "checkout", "--detach", info["commit"]],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        files, entries, summary = collect_files(root, with_coverage=True)
        current_fingerprint = fingerprint(files)
        if current_fingerprint != info["fingerprint"]:
            repo_id = uuid.uuid4().hex
            with db.connection() as connection:
                connection.execute(
                    "INSERT INTO repositories(id,name,source,status,progress,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        repo_id,
                        name,
                        source,
                        "queued",
                        "Waiting to index",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            ingest(repo_id, str(root))
            updated = db.repository(repo_id)
            if updated["status"] != "ready" or updated["fingerprint"] != current_fingerprint:
                raise ValueError(f"Reindex failed for {name}: {updated['error']}")
            info = {
                "id": repo_id,
                "status": "ready",
                "commit": updated["commit_id"],
                "fingerprint": updated["fingerprint"],
                "files": updated["stats"]["files"],
                "error": None,
            }
        else:
            stats = repo["stats"]
            stats["coverage"] = summary
            stats["skipped_files"] = summary["skipped_files"]
            with db.connection() as connection:
                connection.execute("DELETE FROM coverage WHERE repo_id=?", (info["id"],))
                connection.executemany(
                    "INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                    [
                        (
                            info["id"],
                            entry["path"],
                            entry["kind"],
                            entry["status"],
                            entry["reason"],
                            entry["size"],
                            entry["extension"],
                        )
                        for entry in entries
                    ],
                )
                connection.execute(
                    "UPDATE repositories SET stats=? WHERE id=?",
                    (json.dumps(stats), info["id"]),
                )
        return info, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--coverage-output", type=Path)
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    db.init()
    manifest = json.loads(args.manifest.read_text())
    names = args.names or list(manifest)
    if set(names) - set(manifest):
        raise SystemExit("Unknown reference repository name.")
    results = {}
    for name in names:
        info, summary = backfill(name, manifest[name])
        manifest[name] = info
        results[name] = summary
        print(
            f"{name}: {summary['indexed_files']} indexed, {summary['skipped_files']} skipped files",
            flush=True,
        )
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.coverage_output:
        args.coverage_output.write_text(json.dumps(results, indent=2) + "\n")
    elif args.manifest == MANIFEST:
        Path("docs/reference-coverage.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
