"""Compare locally installed chat models on identical indexed source evidence."""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.providers import ANSWER_PROMPT_VERSION, generate
from backend.retrieval import RETRIEVAL_VERSION, asks_external_state, generation_context, retrieve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", help="Installed Ollama model names")
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("evaluation/model-comparison.json"))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    args = parser.parse_args()
    if args.cases < 1 or args.repeats < 1:
        parser.error("cases and repeats must be positive")
    if args.output.exists():
        parser.error("refusing to overwrite an existing comparison")
    os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    manifest = json.loads(args.manifest.read_text())
    cases = [
        json.loads(line)
        for line in (args.dataset or Path("evaluation/cases.jsonl")).read_text().splitlines()
        if line.strip()
    ]
    # One case from each repository before taking a second, preserving equal coverage.
    selected = []
    for case in cases:
        if case["repository"] not in {c["repository"] for c in selected}:
            selected.append(case)
        if len(selected) == args.cases:
            break
    if args.cases > len(selected):
        selected.extend(case for case in cases if case not in selected)
        selected = selected[: args.cases]
    if args.dataset:
        selected = cases[: args.cases]
    frozen = []
    for case in selected:
        info = manifest[case["repository"]]
        repo = db.repository(info["id"])
        if not repo or repo["status"] != "ready" or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {case['repository']}")
        external = asks_external_state(case["question"])
        evidence, warning, _ = (
            ([], None, False)
            if external
            else retrieve(info["id"], case["question"], mode="hybrid", limit=8)
        )
        evidence = generation_context(info["id"], case["question"], evidence)
        frozen.append((case, evidence, warning, external))
    results = []
    # Batch by model to avoid repeated model-loading costs on memory-constrained Macs.
    for model in args.models:
        os.environ["DEVPILOT_LLM_MODEL"] = model
        for repeat in range(args.repeats):
            for case, evidence, warning, external in frozen:
                started = time.perf_counter()
                try:
                    if external:
                        answer, usage, generation = (
                            "The indexed source cannot establish this live or private runtime value.",
                            {},
                            {"provider_calls": 0, "abstained": True},
                        )
                    else:
                        answer, usage, generation = generate(case["question"], evidence)
                    citations = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
                    result = {
                        "answer": answer,
                        "usage": usage,
                        "generation": generation,
                        "has_citations": bool(citations),
                        "invalid_citations": sorted(
                            set(
                                n
                                for n in citations
                                if n not in {item["citation_number"] for item in evidence}
                            )
                        ),
                    }
                except Exception as exc:
                    result = {"error": str(exc)}
                results.append(
                    {
                        "case_id": case["id"],
                        "repository": case["repository"],
                        "question": case["question"],
                        "model": model,
                        "repeat": repeat + 1,
                        "snapshot": manifest[case["repository"]]["fingerprint"],
                        "expected_sources": case.get("expected_sources", []),
                        "expected_answer": case.get("expected_answer"),
                        "answerable": case.get("answerable", True),
                        "answer_prompt_version": ANSWER_PROMPT_VERSION,
                        "retrieval_version": RETRIEVAL_VERSION,
                        "evidence": evidence,
                        "review": {"correct": None, "complete": None, "all_claims_supported": None},
                        "evidence_symbols": [item["qualified"] for item in evidence],
                        "retrieval_warning": warning,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                        **result,
                    }
                )
                print(f"{case['id']} {model}: {results[-1]['elapsed_ms']} ms", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "dataset": str(args.dataset or "evaluation/cases.jsonl"),
                "manifest": str(args.manifest),
                "repeats": args.repeats,
                "evaluation_mode": "one generation attempt on frozen identical context; not end-to-end retry policy",
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(args.output)


if __name__ == "__main__":
    main()
