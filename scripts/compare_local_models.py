"""Compare locally installed chat models on identical indexed source evidence."""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.providers import generate
from backend.retrieval import retrieve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", help="Installed Ollama model names")
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("evaluation/model-comparison.json"))
    args = parser.parse_args()
    os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    manifest = json.loads(Path("docs/indexed-reference-repositories.json").read_text())
    cases = [json.loads(line) for line in Path("evaluation/cases.jsonl").read_text().splitlines()]
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
    results = []
    for case in selected:
        evidence, warning, _ = retrieve(
            manifest[case["repository"]]["id"], case["question"], mode="hybrid", limit=8
        )
        for model in args.models:
            os.environ["DEVPILOT_LLM_MODEL"] = model
            started = time.perf_counter()
            try:
                answer, usage, generation = generate(case["question"], evidence)
                citations = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
                result = {
                    "answer": answer,
                    "usage": usage,
                    "generation": generation,
                    "has_citations": bool(citations),
                    "invalid_citations": sorted(
                        set(n for n in citations if n < 1 or n > len(evidence))
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
            {"evaluated_at": datetime.now(timezone.utc).isoformat(), "results": results}, indent=2
        )
        + "\n"
    )
    print(args.output)


if __name__ == "__main__":
    main()
