"""Score frozen model comparisons from explicit source review, not model flags."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(comparison, cases, review):
    questions = {case["id"]: case for case in cases}
    identity = comparison["identity"]
    expected = {
        (case_id, model, reviewer, repeat)
        for case_id in identity["cases"]
        for model, reviewer in identity["variants"]
        for repeat in range(1, identity["repeats"] + 1)
    }
    if len(questions) != len(cases) or not set(identity["cases"]) <= set(questions):
        raise ValueError("Frozen case IDs must have unique question definitions")
    keyed = {}
    for row in review["cases"]:
        key = tuple(row[k] for k in ("case_id", "model", "reviewer", "repeat"))
        if key in keyed:
            raise ValueError("Duplicate source-review row")
        keyed[key] = row
    groups = defaultdict(list)
    observed = set()
    for row in comparison["results"]:
        key = tuple(row[k] for k in ("case_id", "model", "reviewer", "repeat"))
        if key in observed or key not in keyed or row["case_id"] not in questions:
            raise ValueError("Missing or duplicate output/review/question")
        observed.add(key)
        label, question = keyed[key], questions[row["case_id"]]
        coverage = label.get("required_detail_coverage")
        if (
            type(label.get("correct")) is not bool
            or not isinstance(label.get("unsupported_claims"), list)
            or not isinstance(coverage, list)
            or len(coverage) != len(question["required_details"])
            or any(type(item) is not bool for item in coverage)
        ):
            raise ValueError(
                "Every frozen detail and factual correctness must be explicitly reviewed"
            )
        if row.get("error") and label["correct"]:
            raise ValueError("Failed generations cannot be scored as correct")
        groups[(row["model"], row["reviewer"])].append(
            {
                "case_id": row["case_id"],
                "correct": label["correct"],
                "fully_adequate": label["correct"]
                and all(coverage)
                and not label["unsupported_claims"]
                and not row.get("error"),
                "covered_details": sum(coverage),
                "required_details": len(coverage),
                "unsupported_claims": len(label["unsupported_claims"]),
                "validation_false_rejections": len(label.get("validation_false_rejections", [])),
                "elapsed_ms": row["elapsed_ms"],
                "failed": bool(row.get("error")),
                "audit_failed": row.get("generation", {}).get("claim_audit", {}).get("status")
                == "failed",
            }
        )
    if observed != set(keyed):
        raise ValueError("Review includes outputs absent from the comparison")
    if observed != expected:
        raise ValueError("Incomplete comparison: every scheduled variant and repeat is required")
    expected_count = len(identity["cases"]) * identity["repeats"]
    summary = []
    for model, reviewer in identity["variants"]:
        rows = groups[(model, reviewer)]
        if len(rows) != expected_count:
            raise ValueError(
                "Incomplete comparison: keep all scheduled failures in the denominator"
            )
        summary.append(
            {
                "model": model,
                "reviewer": reviewer,
                "cases": len(rows),
                "correct": sum(r["correct"] for r in rows),
                "fully_adequate": sum(r["fully_adequate"] for r in rows),
                "covered_details": sum(r["covered_details"] for r in rows),
                "required_details": sum(r["required_details"] for r in rows),
                "unsupported_claims": sum(r["unsupported_claims"] for r in rows),
                "validation_false_rejections": sum(r["validation_false_rejections"] for r in rows),
                "failures": sum(r["failed"] for r in rows),
                "audit_failures": sum(r["audit_failed"] for r in rows),
                "median_seconds": statistics.median(r["elapsed_ms"] for r in rows) / 1000,
                "per_case": rows,
            }
        )
    return {
        "reviewer": review["reviewer"],
        "variants": summary,
        "notice": "Small frozen-context comparison. Reviewer/model agreement is not proof. Loading and review latency are included; no automatic model promotion.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing scored comparison")
    raw = args.questions.read_text()
    cases = (
        json.loads(raw)["cases"]
        if args.questions.suffix == ".json"
        else [json.loads(line) for line in raw.splitlines() if line.strip()]
    )
    result = summarize(
        json.loads(args.comparison.read_text()), cases, json.loads(args.review.read_text())
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
