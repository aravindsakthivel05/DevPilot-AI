"""Promote completed source-linked review cards into a scored JSONL dataset."""

import argparse
import json
from pathlib import Path

from backend import db


def promote(queue_dir, manifest_path, output, base=None):
    if output.exists():
        raise ValueError(f"Dataset already exists: {output}")
    manifest = json.loads(manifest_path.read_text())
    cases = []
    if base:
        cases.extend(json.loads(line) for line in base.read_text().splitlines() if line.strip())
    existing = {case["id"]: case for case in cases}
    for path in sorted(queue_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            card = json.loads(line)
            if card["review_status"] != "reviewed":
                continue
            info = manifest[card["repository"]]
            repo = db.repository(info["id"])
            if not repo or repo["fingerprint"] != info["fingerprint"]:
                raise ValueError(f"Snapshot changed or missing: {card['repository']}")
            if card["snapshot"] != info["fingerprint"]:
                raise ValueError(f"Review card snapshot changed: {card['id']}")
            if card["id"] in existing:
                prior = existing[card["id"]]
                if prior["question"] == card["question"] and prior["expected_symbols"] == [
                    card["qualified"]
                ]:
                    continue
                raise ValueError(f"Duplicate question ID with changed label: {card['id']}")
            split = card.get("split", "development")
            if split not in ("development", "holdout"):
                raise ValueError(f"Invalid question split: {card['id']}")
            if not card["question"].strip() or not card["expected_answer"].strip():
                raise ValueError(f"Reviewed card lacks question or expected answer: {card['id']}")
            symbols = {item["qualified"] for item in db.symbols(info["id"])}
            if card["qualified"] not in symbols:
                raise ValueError(f"Expected symbol missing from index: {card['id']}")
            cases.append(
                {
                    "id": card["id"],
                    "repository": card["repository"],
                    "split": split,
                    "question": card["question"],
                    "expected_symbols": [card["qualified"]],
                    "expected_answer": card["expected_answer"],
                    "source_reviewed": f"{card['path']}:{card['start_line']}",
                    "answerable": True,
                    "review_status": "reviewed",
                }
            )
            existing[card["id"]] = cases[-1]
    output.write_text("".join(json.dumps(case) + "\n" for case in cases))
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-dir", type=Path, default=Path("evaluation/review-queue"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    parser.add_argument("--base", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Wrote {promote(args.queue_dir, args.manifest, args.output, args.base)} cases")


if __name__ == "__main__":
    main()
