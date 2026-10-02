"""Create unscored, source-linked question review queues for reference repositories."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from backend import db

PRIMARY_PATHS = {
    "flask": ("src/flask/",),
    "requests": ("src/requests/",),
    "httpx": ("httpx/",),
    "pytest": ("src/_pytest/",),
    "rich": ("rich/",),
    "petclinic": ("src/main/java/",),
    "commons-lang": ("src/main/java/",),
    "spring-data-elasticsearch": ("src/main/java/",),
    "elasticsearch-java": ("co/elastic/clients/",),
    "fastapi": ("fastapi/",),
    "django": ("",),
    "numpy": ("numpy/",),
    "scikit-learn": ("sklearn/",),
    "pytorch": ("",),
}


def candidates(repo_id, name, limit):
    symbols = [
        item
        for item in db.symbols(repo_id)
        if item["kind"] in ("function", "method")
        and (
            item["path"].startswith(PRIMARY_PATHS[name])
            if name in PRIMARY_PATHS
            else "/src/main/java/" in item["path"]
        )
        and len(item["source"].strip()) >= 80
    ]
    duplicate_names = Counter(item["qualified"] for item in symbols)
    by_path = defaultdict(list)
    for item in sorted(symbols, key=lambda row: (row["path"], row["start_line"])):
        if duplicate_names[item["qualified"]] == 1:
            by_path[item["path"]].append(item)
    selected = []
    paths = sorted(by_path)
    depth = 0
    while len(selected) < limit and any(len(by_path[path]) > depth for path in paths):
        for path in paths:
            if len(by_path[path]) > depth:
                selected.append(by_path[path][depth])
                if len(selected) == limit:
                    break
        depth += 1
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/review-queue"))
    parser.add_argument("--per-repo", type=int, default=25)
    parser.add_argument("--repositories", nargs="*", help="Optional repository names to seed")
    args = parser.parse_args()
    if not 1 <= args.per_repo <= 100:
        raise ValueError("--per-repo must be between 1 and 100")
    manifest = json.loads(args.manifest.read_text())
    if args.repositories is not None:
        unknown = set(args.repositories) - set(manifest)
        if unknown:
            raise ValueError(f"Repositories are missing from the manifest: {sorted(unknown)}")
        if not args.repositories:
            raise ValueError("--repositories must include at least one repository name")
        manifest = {name: manifest[name] for name in args.repositories}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, info in manifest.items():
        output = args.output_dir / f"{name}.jsonl"
        if output.exists():
            raise ValueError(f"Review queue already exists: {output}")
        repo = db.repository(info["id"])
        if not repo or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {name}")
        rows = []
        for index, item in enumerate(candidates(info["id"], name, args.per_repo), 1):
            rows.append(
                {
                    "id": f"{name}-candidate-{index:03}",
                    "repository": name,
                    "split": "holdout" if name in ("rich", "petclinic") else "development",
                    "snapshot": info["fingerprint"],
                    "qualified": item["qualified"],
                    "path": item["path"],
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                    "source_excerpt": item["source"][:1000],
                    "question": "",
                    "expected_answer": "",
                    "review_status": "pending",
                }
            )
        output.write_text("".join(json.dumps(row) + "\n" for row in rows))
        print(f"{name}: {len(rows)} pending candidates")


if __name__ == "__main__":
    main()
