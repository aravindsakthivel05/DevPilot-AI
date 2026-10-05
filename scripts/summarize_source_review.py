"""Summarize explicit source review; never substitute model acceptance for labels."""

import argparse
import json
import statistics
from pathlib import Path


def summarize(cases, results, review):
    labels = {row["case_id"]: row for row in review["cases"]}
    outputs = {row["case_id"]: row for row in results["results"]}
    answerable, guards, details, times = [], [], [], []
    unnecessary_abstentions = 0
    for case in cases:
        cid = case["id"]
        if cid not in outputs or cid not in labels:
            raise ValueError(f"Missing result or explicit review: {cid}")
        label = labels[cid]
        if not isinstance(label.get("correct"), bool) or not isinstance(
            label.get("unsupported_claims"), list
        ):
            raise ValueError(
                "Source correctness and unsupported claims must be explicitly reviewed"
            )
        if case["answerable"]:
            unnecessary_abstentions += label.get("unnecessary_abstention") is True
            coverage = label.get("required_detail_coverage", [])
            if len(coverage) != len(case["required_details"]) or any(
                type(value) is not bool for value in coverage
            ):
                raise ValueError("Review must cover every frozen required detail")
            adequate = label["correct"] and all(coverage) and not label["unsupported_claims"]
            if not outputs[cid].get("result", {}).get("generated") or outputs[cid].get("error"):
                adequate = False
            answerable.append(
                {
                    "case_id": cid,
                    "correct": label["correct"],
                    "fully_adequate": adequate,
                    "covered_details": sum(coverage),
                    "required_details": len(coverage),
                    "unsupported_claims": len(label["unsupported_claims"]),
                }
            )
            details.extend(coverage)
            times.append(outputs[cid]["wall_seconds"])
        else:
            if type(label.get("abstention_correct")) is not bool:
                raise ValueError("Guard cases require an explicit abstention review")
            guards.append(label["abstention_correct"])
    return {
        "reviewer": review["reviewer"],
        "answerable_questions": len(answerable),
        "correct_answers": sum(row["correct"] for row in answerable),
        "fully_adequate": sum(row["fully_adequate"] for row in answerable),
        "covered_details": sum(details),
        "required_details": len(details),
        "detail_coverage_fraction": sum(details) / len(details) if details else None,
        "unsupported_claim_count": sum(row["unsupported_claims"] for row in answerable),
        "abstention_correct": sum(guards),
        "guard_questions": len(guards),
        "source_reviewed_unnecessary_abstentions": unnecessary_abstentions,
        "median_answerable_seconds": statistics.median(times) if times else None,
        "per_case": answerable,
        "notice": "Small source-reviewed sample; correctness is distinct from completeness. Not independent human review.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    report = summarize(
        json.loads((root / "questions.json").read_text())["cases"],
        json.loads((root / "results.json").read_text()),
        json.loads((root / "source-review.json").read_text()),
    )
    (root / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
