"""Pin and evaluate an external question set without modifying DevPilot's pipeline.

Uses an isolated database. Source correctness is reviewed separately; model
acceptance and symbol retrieval are never reported as factual accuracy.
"""

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation/complex-five-2026-10-04"
REPOSITORIES = {
    "sqlalchemy": "sqlalchemy/sqlalchemy",
    "celery": "celery/celery",
    "scrapy": "scrapy/scrapy",
    "mybatis": "mybatis/mybatis-3",
    "resilience4j": "resilience4j/resilience4j",
}


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "run"])
    args = parser.parse_args()
    os.environ.setdefault("DEVPILOT_DATA", str(ROOT / ".devpilot/complex-five-2026-10-04"))
    os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("DEVPILOT_LLM_MODEL", "qwen2.5-coder:7b")
    os.environ.setdefault("DEVPILOT_PROVIDER_TIMEOUT_SECONDS", "180")
    os.environ.setdefault("DEVPILOT_OLLAMA_NUM_CTX", "8192")
    os.environ.setdefault("DEVPILOT_SOURCE_TOKEN_BUDGET", "4096")
    os.environ.setdefault("DEVPILOT_VERIFY_CLAIMS", "1")
    # This evaluates the existing lexical/graph configuration, not newly trained
    # weights or an unbuilt semantic corpus.
    if os.environ.get("DEVPILOT_EMBEDDING_MODEL"):
        parser.error("Run with embeddings disabled for this frozen evaluation")
    from backend import db
    from backend.agent_investigation import investigate
    from backend.config import DATA, provider_settings
    from backend.ingestion import ingest
    from backend.providers import ANSWER_PROMPT_VERSION
    from backend.readiness import index_status, provider_status
    from backend.retrieval import RETRIEVAL_VERSION, answer, retrieve

    OUTPUT.mkdir(parents=True, exist_ok=True)
    db.init()
    if args.stage == "prepare":
        if (OUTPUT / "snapshots.json").exists():
            parser.error("Refusing to replace existing pinned snapshots")
        snapshots = {}
        for name, slug in REPOSITORIES.items():
            checkout = ROOT / ".devpilot/complex-five-checkouts" / name
            repo_id = uuid.uuid4().hex
            with db.connection() as conn:
                conn.execute(
                    "INSERT INTO repositories(id,name,source,status,progress,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        repo_id,
                        name,
                        str(checkout),
                        "queued",
                        "Evaluation indexing",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            started = time.perf_counter()
            ingest(repo_id, str(checkout))
            repo = db.repository(repo_id)
            if repo["status"] != "ready":
                raise RuntimeError(f"{name}: {repo['error']}")
            # Materialize FTS before timing answer queries, record indexing cost.
            retrieve(repo_id, "repository architecture")
            snapshots[name] = {
                "id": repo_id,
                "url": "https://github.com/" + slug,
                "commit": repo["commit_id"],
                "fingerprint": repo["fingerprint"],
                "index_scope": "repository root; supported files only",
                "index_ms": round((time.perf_counter() - started) * 1000),
                "stats": repo["stats"],
                "index_status": index_status(repo_id),
                "split": "evaluation_only",
            }
            save(OUTPUT / "snapshots.json", snapshots)
            print(
                name,
                repo["stats"]["files"],
                repo["stats"]["symbols"],
                snapshots[name]["index_ms"],
                flush=True,
            )
        return

    result_path = OUTPUT / "results.json"
    if result_path.exists():
        parser.error("Refusing to overwrite a previous run")
    snapshots = json.loads((OUTPUT / "snapshots.json").read_text())
    cases_path = OUTPUT / "questions.jsonl"
    cases = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    implementation = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "backend").glob("*.py"))
    }
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "data_directory": str(DATA),
        "model": provider_settings()["model"],
        "embedding_model": None,
        "answer_prompt_version": ANSWER_PROMPT_VERSION,
        "retrieval_version": RETRIEVAL_VERSION,
        "context_window": os.environ["DEVPILOT_OLLAMA_NUM_CTX"],
        "source_token_budget": os.environ["DEVPILOT_SOURCE_TOKEN_BUDGET"],
        "claim_audit": os.environ["DEVPILOT_VERIFY_CLAIMS"],
        "backend_hashes": implementation,
        "questions_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "repeats": 1,
        "provider_readiness": provider_status(probe=True),
        "results": [],
    }
    save(result_path, report)
    for case in cases:
        pinned = snapshots[case["repository"]]
        repo = db.repository(pinned["id"])
        if not repo or repo["status"] != "ready" or repo["fingerprint"] != pinned["fingerprint"]:
            raise ValueError("Pinned snapshot changed")
        for expected in case["expected_sources"]:
            with db.connection() as conn:
                found = conn.execute(
                    "SELECT 1 FROM symbols WHERE repo_id=? AND path=? AND qualified=? AND start_line=? AND end_line=?",
                    (
                        repo["id"],
                        expected["path"],
                        expected["qualified"],
                        expected["start_line"],
                        expected["end_line"],
                    ),
                ).fetchone()
            if not found:
                raise ValueError(f"Missing exact labeled symbol {expected}")
        modes = [("quick", answer)]
        if case["difficulty"] in ("hard", "unanswerable"):
            modes.append(("deep", investigate))
        for mode, runner in modes:
            started = time.perf_counter()
            row = {
                "case_id": case["id"],
                "repository": case["repository"],
                "mode": mode,
                "question": case["question"],
                "answerable": case["answerable"],
                "commit": pinned["commit"],
                "snapshot": pinned["fingerprint"],
                "expected_sources": case["expected_sources"],
                "expected_answer": case["expected_answer"],
                "source_review": None,
            }
            try:
                result = runner(repo["id"], case["question"], use_model=True)
                row["result"] = result

                def contains(source, items):
                    return any(
                        item["qualified"] == source["qualified"]
                        and item["path"] == source["path"]
                        and item["start_line"] == source["start_line"]
                        and item["end_line"] == source["end_line"]
                        for item in items
                    )

                if case["answerable"]:
                    row["recall_at_8"] = sum(
                        contains(source, result["evidence"][:8])
                        for source in case["expected_sources"]
                    ) / len(case["expected_sources"])
                    row["recall_all_evidence"] = sum(
                        contains(source, result["evidence"]) for source in case["expected_sources"]
                    ) / len(case["expected_sources"])
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["wall_ms"] = round((time.perf_counter() - started) * 1000)
            report["results"].append(row)
            save(result_path, report)
            print(
                case["id"],
                mode,
                "generated=" + str(row.get("result", {}).get("generated")),
                "partial=" + str(row.get("result", {}).get("partial")),
                row["wall_ms"],
                flush=True,
            )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["provider_after_run"] = provider_status(probe=False)
    report["backend_unchanged"] = all(
        hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        for path, digest in implementation.items()
    )
    save(result_path, report)


if __name__ == "__main__":
    main()
