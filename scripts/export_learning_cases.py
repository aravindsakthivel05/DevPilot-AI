"""Export only human-reviewed learning cases into repository-separated datasets."""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from backend import db


def _repository_key(name, repo_id):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "repository"
    return f"{slug}-{repo_id[:8]}"


def build_exports():
    with db.connection() as connection:
        rows = connection.execute(
            """SELECT learning_cases.*, repositories.name, repositories.commit_id,
                      repositories.status AS repository_status,
                      learning_repository_splits.split AS repository_split
               FROM learning_cases
               JOIN repositories ON repositories.id=learning_cases.repo_id
               JOIN learning_repository_splits
                 ON learning_repository_splits.repo_id=learning_cases.repo_id
               WHERE learning_cases.review_status='reviewed'
               ORDER BY repositories.name, learning_cases.created_at, learning_cases.id"""
        ).fetchall()
    if not rows:
        raise ValueError("There are no human-reviewed learning cases to export.")

    manifest = {}
    datasets = {"development": [], "holdout": []}
    repository_splits = {}
    repository_cache = {}
    for row in rows:
        if row["repository_status"] != "ready":
            raise ValueError(f"Repository is not ready: {row['name']}")
        review = json.loads(row["review"])
        split = row["repository_split"]
        prior_split = repository_splits.setdefault(row["repo_id"], split)
        if prior_split != split:
            raise ValueError(f"Repository appears in multiple splits: {row['name']}")
        if row["repo_id"] not in repository_cache:
            repository_cache[row["repo_id"]] = db.repository(row["repo_id"])
        repo = repository_cache[row["repo_id"]]
        if not repo or repo["fingerprint"] != row["snapshot"]:
            raise ValueError(f"Review snapshot changed or is missing: {row['name']}/{row['id']}")
        key = _repository_key(row["name"], row["repo_id"])
        initial_result = json.loads(row["initial_result"] or "null")
        manifest[key] = {
            "id": row["repo_id"],
            "name": row["name"],
            "commit": row["commit_id"],
            "fingerprint": row["snapshot"],
            "split": split,
        }
        datasets[split].append(
            {
                "id": row["id"],
                "repository": key,
                "split": split,
                "question": row["question"],
                "expected_symbols": review["expected_symbols"],
                "expected_answer": review.get("expected_answer"),
                "answerable": review["answerable"],
                "review_status": "reviewed",
                "source_reviewed": review["source_refs"],
                "review_notes": review["notes"],
                "model_run": {
                    field: initial_result.get(field)
                    for field in (
                        "model",
                        "answer_prompt_version",
                        "retrieval_version",
                    )
                }
                if initial_result
                else None,
                "model_answer_review": {
                    "answer_correct": review.get("answer_correct"),
                    "all_claims_supported": review.get("all_claims_supported"),
                    "appropriate_abstention": review.get("appropriate_abstention"),
                },
                "snapshot": row["snapshot"],
            }
        )
    return datasets, manifest


def export(development_path, holdout_path, manifest_path):
    paths = [Path(development_path), Path(holdout_path), Path(manifest_path)]
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Development, holdout, and manifest paths must be different.")
    if any(path.exists() for path in paths):
        raise ValueError("Refusing to overwrite an export file.")

    datasets, manifest = build_exports()
    content = {
        paths[0]: "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in datasets["development"]
        ),
        paths[1]: "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in datasets["holdout"]
        ),
        paths[2]: json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    }
    staged = []
    created = []
    try:
        for path, data in content.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as output:
                output.write(data)
                staged.append((Path(output.name), path))
        for temporary, destination in staged:
            os.link(temporary, destination)
            created.append(destination)
    except Exception:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return {
        "development": len(datasets["development"]),
        "holdout": len(datasets["holdout"]),
        "repositories": len(manifest),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.development, args.holdout, args.manifest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
