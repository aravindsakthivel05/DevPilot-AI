"""Evaluate a fixed JSONL case set against persistent DevPilot snapshots."""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.retrieval import retrieve

DATASET = Path("evaluation/cases.jsonl")
MANIFEST = Path("docs/indexed-reference-repositories.json")


def evaluate(dataset=DATASET, manifest_path=MANIFEST):
    cases = [json.loads(line) for line in Path(dataset).read_text().splitlines() if line.strip()]
    manifest = json.loads(Path(manifest_path).read_text())
    ids = set()
    repository_splits = {}
    for case in cases:
        if case["id"] in ids:
            raise ValueError(f"Duplicate case ID: {case['id']}")
        ids.add(case["id"])
        if case.get("review_status") != "reviewed":
            raise ValueError(f"Unreviewed case cannot be scored: {case['id']}")
        if case.get("split") not in ("development", "holdout"):
            raise ValueError(f"Invalid split: {case['id']}")
        previous = repository_splits.setdefault(case["repository"], case["split"])
        if previous != case["split"]:
            raise ValueError(
                f"Repository cannot span development and holdout splits: {case['repository']}"
            )
        if case["repository"] not in manifest:
            raise ValueError(f"Unknown repository: {case['repository']}")
        info = manifest[case["repository"]]
        if case.get("snapshot") and case["snapshot"] != info["fingerprint"]:
            raise ValueError(f"Case snapshot differs from its manifest: {case['id']}")
        repo = db.repository(info["id"])
        if not repo or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {case['repository']}")
    indexed = {
        name: {symbol["qualified"] for symbol in db.symbols(info["id"])}
        for name, info in manifest.items()
    }
    results = []
    for case in cases:
        expected = set(case["expected_symbols"])
        if case["answerable"] and (not expected or not expected <= indexed[case["repository"]]):
            raise ValueError(f"Expected symbol missing from index: {case['id']}")
        for mode in ("lexical", "graph", "hybrid"):
            evidence, warning, _ = retrieve(
                manifest[case["repository"]]["id"], case["question"], mode=mode, limit=8
            )
            actual = [symbol["qualified"] for symbol in evidence]
            hits = expected.intersection(actual)
            first = next((n for n, symbol in enumerate(actual, 1) if symbol in expected), None)
            results.append(
                {
                    "id": case["id"],
                    "repository": case["repository"],
                    "split": case["split"],
                    "mode": mode,
                    "answerable": case["answerable"],
                    "recall_at_8": len(hits) / len(expected) if expected else None,
                    "reciprocal_rank": 1 / first if first else 0,
                    "retrieved": actual,
                    "warning": warning,
                }
            )
    groups = defaultdict(list)
    for result in results:
        if result["answerable"]:
            groups[(result["split"], result["mode"])].append(result)
    summary = [
        {
            "split": split,
            "mode": mode,
            "cases": len(rows),
            "recall_at_8": sum(row["recall_at_8"] for row in rows) / len(rows),
            "mrr": sum(row["reciprocal_rank"] for row in rows) / len(rows),
        }
        for (split, mode), rows in sorted(groups.items())
    ]
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset),
        "manifest": str(manifest_path),
        "case_count": len(cases),
        "summary": summary,
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, args.manifest), indent=2))
