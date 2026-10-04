"""Reproducible development integration check; never execute indexed source."""

import argparse
import json
import time
from datetime import datetime, timezone

from backend import db
from backend.config import ROOT
from backend.errors.detector import analyze
from backend.evaluation import detection_metrics, experiment
from backend.ingestion import ingest
from backend.languages.registry import capabilities
from backend.proposals import propose
from backend.readiness import provider_status
from backend.retrieval import answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Use the configured real chat and embedding provider"
    )
    parser.add_argument(
        "--output", default="evaluation/implementation-2026-10-04/live-integration.json"
    )
    args = parser.parse_args()
    if db.DB_PATH == ROOT / ".devpilot" / "devpilot.sqlite3":
        parser.error(
            "Set DEVPILOT_DATA to an isolated validation directory; this script never alters the user database."
        )
    db.init()
    rid = "research-prototype-" + str(time.time_ns())
    source = ROOT / "examples/research-repository"
    with db.connection() as c:
        c.execute(
            "INSERT INTO repositories(id,name,source,status,created_at) VALUES (?,?,?,?,?)",
            (
                rid,
                "Nine-language research fixture",
                str(source),
                "queued",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    ingest(rid, str(source))
    repo = db.repository(rid)
    if repo["status"] != "ready":
        raise RuntimeError(repo.get("error"))
    labels = json.loads(
        (ROOT / "evaluation/implementation-2026-10-04/research-cases.json").read_text()
    )
    symbols = db.symbols(rid)
    cases = []
    for case in labels["retrieval"]:
        ids = []
        for qualified in case["expected_symbols"]:
            matching = [s["id"] for s in symbols if s["qualified"] == qualified]
            if len(matching) != 1:
                raise RuntimeError(
                    f"Expected unique source label: {qualified}; found {len(matching)}"
                )
            ids.extend(matching)
        cases.append({"question": case["question"], "expected_ids": ids})
    detected = analyze(rid)
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fixture": str(source.relative_to(ROOT)),
        "provenance": labels["provenance"],
        "repository": repo,
        "capabilities": capabilities(),
        "retrieval": experiment(rid, cases),
        "errors": detected,
        "error_metrics": detection_metrics(detected["issues"], labels["errors"]),
        "abstention": answer(rid, labels["abstention"], use_model=args.live),
        "live_provider": args.live,
        "answers": [],
        "suggestions": [],
    }
    if args.live:
        result["provider"] = provider_status(probe=True)
        for case in cases[:2]:
            result["answers"].append(
                {"question": case["question"], "result": answer(rid, case["question"])}
            )
        for test_only in (False, True):
            started = time.perf_counter()
            request = "For Python shipping_cost in python/pricing.py, suggest a regression test that verifies zero weight raises ValueError. Keep the implementation unchanged."
            try:
                draft = propose(rid, request, test_only=test_only)
            except Exception as exc:
                draft = {"error": str(exc), "status": "failed"}
            result["suggestions"].append(
                {
                    "test_only": test_only,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "result": draft,
                }
            )
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "output": str(output),
                "languages": repo["stats"]["languages"],
                "symbols": repo["stats"]["symbols"],
                "errors": result["error_metrics"],
                "generated_answers": sum(item["result"]["generated"] for item in result["answers"]),
                "draft_statuses": [item["result"].get("status") for item in result["suggestions"]],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
