"""Build a readable report from completed runs and separate source reviews."""

import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation/complex-five-2026-10-04"


def main():
    report = json.loads((OUTPUT / "results.json").read_text())
    if not report.get("finished_at"):
        raise ValueError("Evaluation has not finished")
    snapshots = json.loads((OUTPUT / "snapshots.json").read_text())
    reviews = json.loads((OUTPUT / "source-review.json").read_text())
    answers = [row for row in report["results"] if row["answerable"]]
    guards = [row for row in report["results"] if not row["answerable"]]
    if len(answers) != 20 or len(guards) != 10:
        raise ValueError("Expected 20 answerable and 10 guard runs")
    for row in answers:
        key = row["case_id"] + ":" + row["mode"]
        if key not in reviews["results"]:
            raise ValueError(f"Missing separate source review: {key}")
        row["source_review"] = reviews["results"][key]

    def passed(row, strict=False):
        review = row["source_review"]
        return (
            review["correct"] is True
            and review["complete"] is True
            and (not strict or review["all_claims_supported"] is True)
        )

    quick = [row for row in answers if row["mode"] == "quick"]
    deep = [row for row in answers if row["mode"] == "deep"]
    guard_pass = [
        row
        for row in guards
        if row.get("result", {}).get("abstained")
        and not row["result"]["generated"]
        and row["result"].get("generation_diagnostics", {}).get("provider_calls", 0) == 0
    ]
    summary = {
        "answerable_unique_questions": 15,
        "answerable_runs": len(answers),
        "guard_runs": len(guards),
        "correct_and_complete": sum(passed(row) for row in answers),
        "correct_complete_exact_citation_support": sum(passed(row, True) for row in answers),
        "no_validated_answers": sum(row["source_review"]["correct"] is None for row in answers),
        "incorrect_answers": sum(row["source_review"]["correct"] is False for row in answers),
        "correct_but_incomplete_answers": sum(
            row["source_review"]["correct"] is True and row["source_review"]["complete"] is False
            for row in answers
        ),
        "mean_expected_symbol_recall_at_8": statistics.mean(
            row.get("recall_at_8", 0) for row in answers
        ),
        "median_answer_seconds": round(
            statistics.median(row["wall_ms"] for row in answers) / 1000, 2
        ),
        "minimum_answer_seconds": round(min(row["wall_ms"] for row in answers) / 1000, 2),
        "maximum_answer_seconds": round(max(row["wall_ms"] for row in answers) / 1000, 2),
        "accepted_generated": sum(row.get("result", {}).get("generated", False) for row in answers),
        "partial_generated": sum(
            row.get("result", {}).get("generated", False) and row["result"].get("partial", False)
            for row in answers
        ),
        "errors": sum("error" in row for row in report["results"]),
        "guards_passed": len(guard_pass),
        "review_author": reviews["review_author"],
        "backend_unchanged": report["backend_unchanged"],
        "by_repository": {},
    }
    for name in snapshots:
        rows = [row for row in quick if row["repository"] == name]
        hard_deep = next(row for row in deep if row["repository"] == name)
        summary["by_repository"][name] = {
            "quick_correct_complete": sum(passed(row) for row in rows),
            "quick_strict_supported_complete": sum(passed(row, True) for row in rows),
            "quick_questions": len(rows),
            "quick_recall_at_8": statistics.mean(row.get("recall_at_8", 0) for row in rows),
            "quick_median_seconds": round(
                statistics.median(row["wall_ms"] for row in rows) / 1000, 2
            ),
            "hard_deep_correct_complete": passed(hard_deep),
            "hard_deep_strict_supported_complete": passed(hard_deep, True),
            "hard_deep_seconds": round(hard_deep["wall_ms"] / 1000, 2),
        }
    (OUTPUT / "reviewed-results.json").write_text(
        json.dumps(
            {**report, "results": answers + guards, "summary": summary},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# DevPilot: five complex repository tests",
        "",
        "Date: 2026-10-04. Qwen 2.5 Coder 7B, context 8,192, source budget 4,096, local Ollama, claim audit enabled. Existing Quick answer pipeline and LangGraph Deep pipeline; no embedding corpus or fine-tuning. All repositories were newly pinned for evaluation only. The production backend was unchanged throughout the run.",
        "",
        "## Measured outcome",
        "",
        f"- **Correct and complete answers: {summary['correct_and_complete']}/20** answerable runs (15 Quick questions plus five hard-question Deep runs).",
        f"- **Correct, complete and fully supported by exact cited lines: {summary['correct_complete_exact_citation_support']}/20**.",
        f"- Expected-symbol retrieval recall@8: **{summary['mean_expected_symbol_recall_at_8']:.1%}** averaged per run. This measures labeled methods retrieved, not all relevant code or answer accuracy.",
        f"- Median full answer latency: **{summary['median_answer_seconds']} s**; range {summary['minimum_answer_seconds']}–{summary['maximum_answer_seconds']} s. Includes retrieval, generation, retries and audit.",
        f"- Generated explanations accepted: {summary['accepted_generated']}/20, of which {summary['partial_generated']} were marked partial. Acceptance is not a correctness score.",
        f"- Source review categories: {summary['correct_and_complete']} correct and complete, {summary['correct_but_incomplete_answers']} correct but incomplete, {summary['incorrect_answers']} incorrect, and {summary['no_validated_answers']} no validated answer.",
        f"- Private-runtime abstention checks: **{summary['guards_passed']}/10**. These use the same explicit private-state prompt across the five repositories and both modes; they are not ten distinct adversarial prompts.",
        f"- Unhandled run errors: {summary['errors']}.",
        "",
        "## Results by repository",
        "",
        "| Repository | Indexed files / symbols | Quick correct & complete | Quick strict citation-supported | Recall@8 | Quick median | Hard Deep correct & complete |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, snap in snapshots.items():
        row = summary["by_repository"][name]
        lines.append(
            f"| [{name}]({snap['url']}) | {snap['stats']['files']:,} / {snap['stats']['symbols']:,} | {row['quick_correct_complete']}/3 | {row['quick_strict_supported_complete']}/3 | {row['quick_recall_at_8']:.1%} | {row['quick_median_seconds']} s | {'Pass' if row['hard_deep_correct_complete'] else 'Fail'} |"
        )
    lines += [
        "",
        "## What the results show",
        "",
        "Retrieval often finds the named entry points, but the complete explanation frequently fails. MyBatis caching and Resilience4j transitions also miss crucial helper methods. Deep mode completed zero of the five hard answers, as did Quick on those same questions; this small single-run sample does not establish general equivalence or a universal latency advantage.",
        "",
        "The most useful next changes would be to preserve every requested obligation when splitting questions; retrieve helper methods under the exact requested class/overload; include operative branch/call lines in claim citations; and distinguish valid exception/owner references from wrong-owner citations without rejecting the entire useful answer unnecessarily. These are findings and suggested follow-up work, not changes made during this evaluation. The same-model audit both catches some wrong claims and accepts some unsupported ones, so it cannot replace source review.",
        "",
        "## Source-reviewed findings",
        "",
    ]
    for row in answers:
        review = row["source_review"]
        lines += [
            f"### {row['case_id']} — {row['mode']}",
            "",
            "**Question:** " + row["question"],
            "",
            "**Verdict:** " + review["verdict"].replace("_", " ") + ". " + review["notes"],
            "",
            f"Time: {row['wall_ms'] / 1000:.2f} s; expected-symbol recall@8: {row.get('recall_at_8', 0):.1%}.",
            "",
        ]
    lines += [
        "## Scope and reproducibility",
        "",
        "These are Codex source reviews, not independent human grading. Completeness is judged against explicit question obligations; exact citation support uses each claim’s actual cited line ranges. A safe fallback is recorded as no validated answer, rather than a factual hallucination or a successful substantive answer. A correct but incomplete explanation fails the complete-answer metric.",
        "",
        "One repeat per mode on this Mac is a small sample, not a general model accuracy estimate or a controlled before/after comparison. Repository complexity is a qualitative architecture label. Full roots were scanned, but only supported file types were indexed; coverage exclusions are recorded. No parser errors occurred, which does not prove complete call-graph resolution. Dynamic dispatch, external/native code and many references remain unresolved.",
        "",
        "This tests DevPilot indexing, retrieval and repository question answering. Upstream project test suites, service deployment, patch generation and repair success were not tested. No new training ran and these repositories were not added to training data.",
        "",
        "Artifacts in `evaluation/complex-five-2026-10-04/`: frozen questions and expected source; pinned snapshots; raw results and all draft/audit/context diagnostics; separate source reviews; reviewed results and summary. Backend SHA-256 hashes and model digest are in results.json. The interrupted pre-finalization checkpoint is retained separately and excluded from scores.",
        "",
        "The evaluation runner refuses to overwrite existing results and checks every expected symbol range and snapshot fingerprint before answering. Reproduction requires the recorded commits, frozen questions, model digest, settings and a separate output directory; re-cloning a moving branch alone is not the same benchmark.",
        "",
    ]
    (OUTPUT / "report.md").write_text("\n".join(lines))
    manifest = {
        "created_at": report["finished_at"],
        "questions_unchanged": hashlib.sha256((OUTPUT / "questions.jsonl").read_bytes()).hexdigest()
        == report["questions_sha256"],
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(OUTPUT.iterdir())
            if path.is_file() and path.name != "artifact-manifest.json"
        },
    }
    (OUTPUT / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
