"""Evaluate five fresh repositories with frozen source labels; never run target code.

Stages are separate so questions can be source-reviewed and frozen before model
outputs are seen. Results and the isolated database can resume interrupted runs.
No answer score is inferred from model acceptance or retrieval metrics.
"""

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation/new-five-2026-10-04"
CHECKOUTS = ROOT / ".devpilot/new-five-2026-10-04-checkouts"
REPOSITORIES = {
    "axios": "axios/axios",
    "gin": "gin-gonic/gin",
    "clap": "clap-rs/clap",
    "fmt": "fmtlib/fmt",
    "fluentvalidation": "FluentValidation/FluentValidation",
}


def save(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "backend").rglob("*.py"))
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["index", "run"])
    args = parser.parse_args()
    os.environ.setdefault("DEVPILOT_DATA", str(ROOT / ".devpilot/new-five-2026-10-04"))
    os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("DEVPILOT_LLM_MODEL", "qwen2.5-coder:14b")
    os.environ.setdefault("DEVPILOT_EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("DEVPILOT_EMBEDDING_MODEL", "nomic-embed-text:latest")
    os.environ.setdefault("DEVPILOT_PROVIDER_TIMEOUT_SECONDS", "180")
    os.environ.setdefault("DEVPILOT_LANGGRAPH_ENABLED", "0")
    os.environ.setdefault("DEVPILOT_LEGACY_EXECUTION", "0")
    from backend import db
    from backend.config import provider_settings
    from backend.errors.detector import analyze
    from backend.evaluation import experiment
    from backend.graph import neighborhood
    from backend.ingestion import ingest
    from backend.providers import ANSWER_PROMPT_VERSION
    from backend.readiness import index_status
    from backend.retrieval import RETRIEVAL_VERSION, answer, retrieve

    if db.DB_PATH == ROOT / ".devpilot/devpilot.sqlite3":
        parser.error("An isolated evaluation database is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    db.init()
    snapshots_path = OUTPUT / "snapshots.json"
    snapshots = json.loads(snapshots_path.read_text()) if snapshots_path.exists() else {}
    if args.stage == "index":
        for name, slug in REPOSITORIES.items():
            if name in snapshots:
                print(name, "already recorded", snapshots[name]["status"], flush=True)
                continue
            checkout = CHECKOUTS / name
            rid = uuid.uuid4().hex
            commit = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            with db.connection() as c:
                c.execute(
                    "INSERT INTO repositories(id,name,source,status,progress,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        rid,
                        name,
                        str(checkout),
                        "queued",
                        "Evaluation indexing",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            print(name, "indexing", commit, flush=True)
            started = time.perf_counter()
            ingest(rid, str(checkout))
            repo = db.repository(rid)
            elapsed = time.perf_counter() - started
            record = {
                "id": rid,
                "url": "https://github.com/" + slug,
                "commit": commit,
                "fingerprint": repo.get("fingerprint"),
                "status": repo["status"],
                "error": repo.get("error"),
                "index_wall_seconds": round(elapsed, 3),
                "stats": repo.get("stats", {}),
                "split": "evaluation_only_no_tuning",
            }
            if repo["status"] == "ready":
                started = time.perf_counter()
                retrieve(rid, "repository architecture", mode="lexical", limit=5)
                record["lexical_warmup_seconds"] = round(time.perf_counter() - started, 3)
                record["index_status"] = index_status(rid)
                started = time.perf_counter()
                issues = analyze(rid)
                record["static_analysis_seconds"] = round(time.perf_counter() - started, 3)
                save(OUTPUT / (name + "-issues.json"), issues)
                record["static_candidate_count"] = len(issues["issues"])
                from collections import Counter

                record["static_candidate_types"] = dict(
                    Counter(item["type"] for item in issues["issues"])
                )
            snapshots[name] = record
            save(snapshots_path, snapshots)
            print(
                name,
                repo["status"],
                "files=" + str(record["stats"].get("files")),
                "symbols=" + str(record["stats"].get("symbols")),
                "seconds=" + str(record["index_wall_seconds"]),
                flush=True,
            )
        return

    cases_path = OUTPUT / "questions.json"
    raw = cases_path.read_bytes()
    cases = json.loads(raw)["cases"]
    result_path = OUTPUT / "results.json"
    original_hashes = hashes()
    if result_path.exists():
        report = json.loads(result_path.read_text())
        if (
            report["questions_sha256"] != hashlib.sha256(raw).hexdigest()
            or report["backend_hashes"] != original_hashes
        ):
            parser.error("Refusing to resume after changing questions or implementation")
    else:
        report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": provider_settings()["model"],
            "embedding_model": os.environ["DEVPILOT_EMBEDDING_MODEL"],
            "answer_prompt_version": ANSWER_PROMPT_VERSION,
            "retrieval_version": RETRIEVAL_VERSION,
            "backend_hashes": original_hashes,
            "questions_sha256": hashlib.sha256(raw).hexdigest(),
            "repeats": 1,
            "results": [],
            "retrieval_experiments": {},
            "notice": "Fresh repositories and source-authored questions; Codex review is not independent human evaluation. No tuning, training, patch application or target code execution.",
        }
        save(result_path, report)
    for name, snapshot in snapshots.items():
        if snapshot["status"] != "ready":
            continue
        rid = snapshot["id"]
        symbols = db.symbols(rid)
        labelled = []
        missing_labels = []
        expected_count = 0
        for case in (case for case in cases if case["repository"] == name and case["answerable"]):
            ids = []
            for expected in case["expected_sources"]:
                expected_count += 1
                matching = [
                    s
                    for s in symbols
                    if s["path"] == expected["path"]
                    and s["name"] == expected["name"]
                    and s["start_line"] <= expected["anchor_line"] <= s["end_line"]
                    and s["kind"]
                    in ("function", "method", "constructor", "class", "struct", "module")
                ]
                if not matching:
                    missing_labels.append({"case_id": case["id"], **expected})
                    print(case["id"], "label not parsed", expected, flush=True)
                    continue
                matching.sort(key=lambda s: s["end_line"] - s["start_line"])
                ids.append(matching[0]["id"])
            if ids:
                labelled.append({"question": case["question"], "expected_ids": ids})
        if name not in report["retrieval_experiments"]:
            report["retrieval_experiments"][name] = experiment(
                rid,
                labelled,
                [
                    {
                        "name": "lexical",
                        "mode": "lexical",
                        "hops": 0,
                        "settings": {"rerank": False},
                    },
                    {"name": "semantic", "mode": "semantic", "hops": 0},
                    {"name": "graph", "mode": "graph", "hops": 2},
                    {"name": "hybrid", "mode": "hybrid", "hops": 2},
                ],
            )
            report["retrieval_experiments"][name]["labelled_questions"] = len(labelled)
            report["retrieval_experiments"][name]["expected_source_count"] = expected_count
            report["retrieval_experiments"][name]["missing_source_labels"] = missing_labels
            report["retrieval_experiments"][name]["labelled_symbols"] = len(
                {sid for c in labelled for sid in c["expected_ids"]}
            )
            save(result_path, report)
            print(name, "four retrieval modes complete", flush=True)
    completed = {row["case_id"] for row in report["results"]}
    for case in cases:
        if case["id"] in completed:
            continue
        pinned = snapshots[case["repository"]]
        rid = pinned["id"]
        repo = db.repository(rid)
        if repo["status"] != "ready":
            report["results"].append(
                {
                    "case_id": case["id"],
                    "repository": case["repository"],
                    "question": case["question"],
                    "answerable": case["answerable"],
                    "difficulty": case["difficulty"],
                    "status": "blocked_by_indexing",
                    "error": repo.get("error"),
                    "wall_seconds": 0,
                    "notice": "No answer attempt on an invalid/incomplete index.",
                }
            )
            save(result_path, report)
            print(case["id"], "blocked_by_indexing", repo.get("error"), flush=True)
            continue
        if repo["fingerprint"] != pinned["fingerprint"]:
            raise RuntimeError("Pinned snapshot unavailable or changed")
        for source in case["expected_sources"]:
            with db.connection() as connection:
                stored = connection.execute(
                    "SELECT content FROM files WHERE repo_id=? AND path=?", (rid, source["path"])
                ).fetchone()
            if not stored:
                raise RuntimeError("Expected source file was not indexed: " + source["path"])
            content = stored[0]
            # Validate frozen source facts without giving those labels to retrieval.
            if source["anchor_text"] not in content:
                raise RuntimeError("Frozen source label changed: " + str(source))
        row = {
            "case_id": case["id"],
            "repository": case["repository"],
            "question": case["question"],
            "answerable": case["answerable"],
            "difficulty": case["difficulty"],
            "expected_sources": case["expected_sources"],
            "expected_answer": case["expected_answer"],
            "snapshot": pinned["fingerprint"],
            "commit": pinned["commit"],
            "source_review": None,
        }
        started = time.perf_counter()
        try:
            row["result"] = answer(
                rid, case["question"], mode="hybrid", limit=8, hops=2, use_model=True
            )
            if case["answerable"]:
                evidence = row["result"]["evidence"][:8]
                expected = case["expected_sources"]
                row["required_ranges_recall_at_8"] = sum(
                    any(
                        item["path"] == span["path"]
                        and item["start_line"] <= span["anchor_line"] <= item["end_line"]
                        for item in evidence
                    )
                    for span in expected
                ) / len(expected)
                context = row["result"].get("generation_context", [])
                row["required_anchor_context_recall"] = sum(
                    any(
                        item["path"] == span["path"]
                        and span["anchor_line"] in item.get("source_line_numbers", [])
                        for item in context
                    )
                    for span in expected
                ) / len(expected)
                graph_seed = next(
                    (item["id"] for item in evidence if item["kind"] in ("function", "method")),
                    None,
                )
                if graph_seed:
                    graph = neighborhood(rid, seed=graph_seed, depth=2, limit=100)
                    row["graph_check"] = {
                        "nodes": len(graph["nodes"]),
                        "edges": len(graph["edges"]),
                        "truncated": graph["truncated"],
                    }
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["wall_seconds"] = round(time.perf_counter() - started, 3)
        report["results"].append(row)
        save(result_path, report)
        print(
            case["id"],
            "generated=" + str(row.get("result", {}).get("generated")),
            "partial=" + str(row.get("result", {}).get("partial")),
            "recall=" + str(row.get("required_ranges_recall_at_8")),
            "seconds=" + str(row["wall_seconds"]),
            flush=True,
        )
    report["backend_unchanged"] = report["backend_hashes"] == hashes()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(result_path, report)


if __name__ == "__main__":
    main()
