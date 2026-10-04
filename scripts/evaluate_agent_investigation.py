"""Compare opt-in LangGraph retrieval with the unchanged quick path, without model calls."""

import argparse
import json
import time
from pathlib import Path

from backend import db
from backend.agent_investigation import investigate
from backend.retrieval import answer


def evaluate(dataset, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    results = []
    repository_splits = {}
    for case in rows:
        if not case["answerable"]:
            continue
        if case.get("review_status") != "reviewed":
            raise ValueError(f"Unreviewed question: {case['id']}")
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
            raise ValueError(f"Snapshot differs from pinned manifest: {case['repository']}")
        expected = set(case["expected_symbols"])
        start = time.perf_counter()
        quick = answer(info["id"], case["question"], use_model=False)
        quick_ms = round((time.perf_counter() - start) * 1000)
        deep = investigate(info["id"], case["question"], use_model=False)
        results.append(
            {
                "id": case["id"],
                "repository": case["repository"],
                "quick_recall_at_8": len(expected & {s["qualified"] for s in quick["evidence"][:8]})
                / len(expected),
                "deep_recall_at_8": len(expected & {s["qualified"] for s in deep["evidence"][:8]})
                / len(expected),
                "deep_recall_at_15": len(expected & {s["qualified"] for s in deep["evidence"][:15]})
                / len(expected),
                "quick_ms": quick_ms,
                "deep_ms": deep["elapsed_ms"],
                "retrieval_passes": deep["workflow"]["retrieval_passes"],
            }
        )
    return {
        "dataset": str(dataset),
        "manifest": str(manifest_path),
        "cases": len(results),
        "quick_recall_at_8": sum(row["quick_recall_at_8"] for row in results) / len(results),
        "deep_recall_at_8": sum(row["deep_recall_at_8"] for row in results) / len(results),
        "deep_recall_at_15": sum(row["deep_recall_at_15"] for row in results) / len(results),
        "quick_mean_ms": round(sum(row["quick_ms"] for row in results) / len(results)),
        "deep_mean_ms": round(sum(row["deep_ms"] for row in results) / len(results)),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"Result file already exists: {args.output}")
    result = evaluate(args.dataset, args.manifest)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"{result['cases']} cases: quick {result['quick_recall_at_8']:.1%}, "
        f"deep {result['deep_recall_at_8']:.1%}; "
        f"mean {result['quick_mean_ms']} vs {result['deep_mean_ms']} ms"
    )


if __name__ == "__main__":
    main()
