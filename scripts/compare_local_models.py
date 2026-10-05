"""Compare locally installed chat models on identical indexed source evidence."""

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend import db
from backend.providers import ANSWER_PROMPT_VERSION, context_window, generate
from backend.retrieval import RETRIEVAL_VERSION, asks_external_state, generation_context, retrieve


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2) + "\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", help="Installed Ollama model names")
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("evaluation/model-comparison.json"))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--reviewers", nargs="+", help="Reviewer models; omitted means same model")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--investigate",
        action="store_true",
        help="Freeze deterministic helper reads before model comparison",
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    args = parser.parse_args()
    if args.cases < 1 or args.repeats < 1:
        parser.error("cases and repeats must be positive")
    if args.output.exists() and not args.resume:
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
    if len({case["id"] for case in selected}) != len(selected):
        parser.error("Case IDs must be unique")
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
        if args.investigate and not external:
            from backend.rag.investigation import recover

            evidence, _ = recover(info["id"], case["question"], evidence, retrieve, limit=8)
        evidence = generation_context(info["id"], case["question"], evidence)
        frozen.append((case, evidence, warning, external))
    variants = [
        (model, reviewer) for model in args.models for reviewer in (args.reviewers or [model])
    ]
    root = Path(__file__).resolve().parents[1]
    tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10).json()["models"]
    installed = {item["name"]: item["digest"] for item in tags}
    if any(model not in installed for pair in variants for model in pair):
        parser.error("All generator and reviewer models must be installed")
    identity = {
        "comparison_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(
            (args.dataset or Path("evaluation/cases.jsonl")).read_bytes()
        ).hexdigest(),
        "backend_hashes": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "backend").rglob("*.py"))
        },
        "model_digests": {model: installed[model] for pair in variants for model in pair},
        "variants": variants,
        "repeats": args.repeats,
        "cases": [case["id"] for case, *_ in frozen],
        "investigate": args.investigate,
        "context_hashes": {case["id"]: digest(evidence) for case, evidence, *_ in frozen},
        "thinking": os.environ.get("DEVPILOT_OLLAMA_THINK", "0"),
        "context_window": context_window(),
        "keep_alive": os.environ.get("DEVPILOT_OLLAMA_KEEP_ALIVE", "10m"),
        "audit_enabled": os.environ.get("DEVPILOT_VERIFY_CLAIMS", "1"),
        "provider_timeout": os.environ.get("DEVPILOT_PROVIDER_TIMEOUT_SECONDS", "90"),
        "provider_base_url": os.environ["DEVPILOT_LLM_BASE_URL"],
    }
    if args.resume and args.output.exists():
        report = json.loads(args.output.read_text())
        if digest(report["identity"]) != digest(identity):
            parser.error("Cannot resume after changing dataset, code, models, context or settings")
    else:
        report = {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "identity": identity,
            "evaluation_mode": "One attempt with frozen identical context, not end-to-end retries. Source review still required.",
            "frozen_context": {case["id"]: evidence for case, evidence, *_ in frozen},
            "results": [],
        }
    results = report["results"]
    save(args.output, report)
    completed = {(r["case_id"], r["model"], r["reviewer"], r["repeat"]) for r in results}
    # Batch by model to avoid repeated model-loading costs on memory-constrained Macs.
    for model, reviewer in variants:
        os.environ["DEVPILOT_LLM_MODEL"] = model
        os.environ["DEVPILOT_VERIFY_MODEL"] = reviewer
        for repeat in range(args.repeats):
            for case, evidence, warning, external in frozen:
                if (case["id"], model, reviewer, repeat + 1) in completed:
                    continue
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
                    result = {"error": str(exc), "generation": getattr(exc, "metrics", {})}
                results.append(
                    {
                        "case_id": case["id"],
                        "repository": case["repository"],
                        "question": case["question"],
                        "model": model,
                        "reviewer": reviewer,
                        "context_sha256": digest(evidence),
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
                save(args.output, report)
    print(args.output)


if __name__ == "__main__":
    main()
