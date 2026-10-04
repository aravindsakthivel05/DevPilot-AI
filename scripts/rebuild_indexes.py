"""Rebuild analysis/search from stored immutable files, without changing snapshots."""

import argparse
import json

from backend import db
from backend.indexing import rebuild as rebuild

__all__ = ["rebuild"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_ids", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--embeddings", action="store_true")
    args = parser.parse_args()
    if not args.repo_ids and not args.all:
        parser.error("Specify repository IDs or --all.")
    db.init()
    with db.connection() as c:
        ids = (
            [r[0] for r in c.execute("SELECT id FROM repositories WHERE status='ready'")]
            if args.all
            else args.repo_ids
        )
    for repo_id in ids:
        print(json.dumps(rebuild(repo_id, args.embeddings)), flush=True)


if __name__ == "__main__":
    main()
