"""Run the same evidence and answer checks on pinned medium/complex repositories."""

import argparse
import json
from pathlib import Path

from backend import db
from backend.agent_investigation import investigate
from backend.config import provider_settings
from backend.retrieval import answer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation/training-repository-snapshots.json"
QUESTIONS = ROOT / "evaluation/public-repository-tier-questions.jsonl"


def _load_cases():
    return [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]


def run(output, use_model=True):
    manifest = json.loads(MANIFEST.read_text())
    cases = _load_cases()
    results = []
    for case in cases:
        pinned = manifest[case["repository"]]
        repo = db.repository(pinned["id"])
        if not repo or repo["status"] != "ready":
            raise ValueError(f"Repository is not ready: {case['repository']}")
        if repo["fingerprint"] != pinned["fingerprint"]:
            raise ValueError(f"Indexed snapshot changed: {case['repository']}")
        symbols = {item["qualified"] for item in db.symbols(pinned["id"])}
        missing = set(case["expected_symbols"]) - symbols
        if missing:
            raise ValueError(
                f"Expected symbols are not indexed for {case['repository']}: {missing}"
            )

        run_result = {
            "id": case["id"],
            "tier": case["tier"],
            "repository": case["repository"],
            "url": case["url"],
            "commit": pinned["commit"],
            "fingerprint": pinned["fingerprint"],
            "index_scope": pinned["index_scope"],
            "indexed_files": repo["stats"]["files"],
            "indexed_symbols": repo["stats"]["symbols"],
            "question": case["question"],
            "expected_symbols": case["expected_symbols"],
            "runs": {},
        }
        for name, runner in (
            ("quick", answer),
            ("deep", investigate),
        ):
            result = runner(pinned["id"], case["question"], use_model=use_model)
            retrieved = [item["qualified"] for item in result["evidence"]]
            found = sorted(set(retrieved) & set(case["expected_symbols"]))
            run_result["runs"][name] = {
                "elapsed_ms": result["elapsed_ms"],
                "retrieved_expected": found,
                "expected_count": len(case["expected_symbols"]),
                "recall_at_8": len(found) / len(case["expected_symbols"]),
                "evidence": [
                    {
                        "qualified": item["qualified"],
                        "path": item["path"],
                        "start_line": item["start_line"],
                        "end_line": item["end_line"],
                    }
                    for item in result["evidence"]
                ],
                "answer": result["answer"],
                "generated": result["generated"],
                "semantic_used": result["semantic_used"],
                "citation_check": result["citation_check"],
                "warning": result["warning"],
                "model": result["model"],
                "workflow": result.get("workflow"),
                "usage": result["usage"],
            }
        results.append(run_result)

    scores = [item["runs"][mode]["recall_at_8"] for item in results for mode in ("quick", "deep")]
    report = {
        "source_manifest": str(MANIFEST.relative_to(ROOT)),
        "questions": str(QUESTIONS.relative_to(ROOT)),
        "llm_configured": bool(provider_settings()["model"]),
        "model": provider_settings()["model"] or None,
        "embedding_model": provider_settings()["embedding_model"] or None,
        "use_model": use_model,
        "cases": len(results),
        "mean_recall_at_8": sum(scores) / len(scores),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing report: {output}")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evaluation/public-repository-tier-test.json"
    )
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()
    report = run(args.output, use_model=not args.retrieval_only)
    generated = sum(
        case["runs"][mode]["generated"] for case in report["results"] for mode in ("quick", "deep")
    )
    print(
        f"{report['cases']} repositories, mean recall@8 {report['mean_recall_at_8']:.1%}; "
        f"model answers accepted {generated}/{2 * report['cases']}; output {args.output}"
    )


if __name__ == "__main__":
    main()
