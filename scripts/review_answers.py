"""Prepare and score human-reviewed answers on pinned repository snapshots.

Preparing calls the configured local model. Reviewers then fill the null fields in the
output JSONL. Scoring refuses incomplete reviews and never treats citation syntax as proof.
"""

import argparse
import json
from pathlib import Path

from backend import db
from backend.config import provider_settings
from backend.providers import ANSWER_PROMPT_VERSION
from backend.retrieval import RETRIEVAL_VERSION, answer


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prepare(dataset, manifest_path, output, limit=None, only_unanswerable=False):
    if output.exists():
        raise ValueError(f"Review file already exists: {output}")
    manifest = json.loads(manifest_path.read_text())
    cases = read_jsonl(dataset)
    if only_unanswerable:
        cases = [case for case in cases if not case["answerable"]]
    if limit is not None:
        cases = cases[:limit]
    records = []
    model = provider_settings()["model"]
    for case in cases:
        info = manifest[case["repository"]]
        repo = db.repository(info["id"])
        if not repo or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {case['repository']}")
        result = answer(info["id"], case["question"])
        records.append(
            {
                "id": case["id"],
                "repository": case["repository"],
                "snapshot": info["fingerprint"],
                "model": model,
                "answer_prompt_version": ANSWER_PROMPT_VERSION,
                "retrieval_version": RETRIEVAL_VERSION,
                "question": case["question"],
                "expected_answerable": case["answerable"],
                "answer": result["answer"],
                "generated": result["generated"],
                "abstained": result.get("abstained", False),
                "evidence": [
                    {
                        "qualified": item["qualified"],
                        "path": item["path"],
                        "start_line": item["start_line"],
                        "end_line": item["end_line"],
                        "source_excerpt": item["source"][:1200],
                    }
                    for item in result["evidence"]
                ],
                "citation_check": result["citation_check"],
                "warning": result["warning"],
                "review": {
                    "answer_correct": None,
                    "all_claims_supported": None,
                    "appropriate_abstention": None,
                    "notes": "",
                },
            }
        )
    output.write_text("".join(json.dumps(row) + "\n" for row in records))
    return len(records)


def score(path):
    rows = read_jsonl(path)
    if not rows:
        raise ValueError("Review file is empty.")
    seen = set()
    for row in rows:
        if row["id"] in seen:
            raise ValueError(f"Duplicate review ID: {row['id']}")
        seen.add(row["id"])
        review = row["review"]
        for field in ("answer_correct", "all_claims_supported", "appropriate_abstention"):
            if not isinstance(review.get(field), bool):
                raise ValueError(f"Incomplete review {row['id']}: {field}")
    n = len(rows)
    generated = [row for row in rows if row["generated"]]
    return {
        "cases": n,
        "generated": len(generated),
        "abstained": sum(row.get("abstained", False) for row in rows),
        "answer_correct": sum(row["review"]["answer_correct"] for row in rows) / n,
        "all_claims_supported": sum(row["review"]["all_claims_supported"] for row in rows) / n,
        "generated_answer_correct": (
            sum(row["review"]["answer_correct"] for row in generated) / len(generated)
            if generated
            else None
        ),
        "generated_all_claims_supported": (
            sum(row["review"]["all_claims_supported"] for row in generated) / len(generated)
            if generated
            else None
        ),
        "appropriate_abstention": sum(row["review"]["appropriate_abstention"] for row in rows) / n,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--dataset", type=Path, default=Path("evaluation/cases.jsonl"))
    prep.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--limit", type=int)
    prep.add_argument("--only-unanswerable", action="store_true")
    scoring = sub.add_parser("score")
    scoring.add_argument("review_file", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(
            f"Prepared {prepare(args.dataset, args.manifest, args.output, args.limit, args.only_unanswerable)} cases"
        )
    else:
        print(json.dumps(score(args.review_file), indent=2))


if __name__ == "__main__":
    main()
