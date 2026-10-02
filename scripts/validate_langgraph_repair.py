"""Exercise LangGraph review/checkpoint/Docker with the labelled synthetic Java fixture."""

import argparse
import json
from pathlib import Path

from backend import agent_repair, db

TASKS = Path("evaluation/repairs/fixture-commons/tasks.jsonl")
OUTPUT = Path("docs/langgraph-guided-fixture-validation.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"Validation result already exists: {args.output}")
    db.init()
    task = json.loads(TASKS.read_text().splitlines()[0])
    manifest = json.loads(Path("docs/indexed-reference-repositories.json").read_text())
    info = manifest[task["repository"]]
    if info["fingerprint"] != task["snapshot"]:
        raise ValueError("Fixture snapshot no longer matches the pinned repository.")
    draft = {
        "summary": "Synthetic Commons Lang runner fixture; no model generated this draft.",
        "patch": (TASKS.parent / task["patch_file"]).read_text(),
        "extra_tests": {
            path: (TASKS.parent / source).read_text() for path, source in task["test_files"].items()
        },
    }
    original = agent_repair.propose
    agent_repair.propose = lambda *_: draft
    try:
        run = agent_repair.create_run(
            info["id"],
            "Synthetic fixture for graph validation",
            task["image"],
            task["runner"],
            task["target"],
            task["timeout"],
        )
    finally:
        agent_repair.propose = original
    if run["status"] != "review":
        raise ValueError("Graph did not pause for review.")
    agent_repair.queue_review(run["id"])
    agent_repair.resume_run(run["id"], True)
    result = agent_repair.get_run(run["id"])
    report = {
        "fixture_only": True,
        "model_generated": False,
        "run_id": run["id"],
        "snapshot": task["snapshot"],
        "paused_for_review": True,
        "status": result["status"],
        "outcome": result["result"].get("outcome"),
        "baseline_status": (result["result"].get("baseline") or {}).get("status"),
        "patched_status": (result["result"].get("patched") or {}).get("status"),
        "regression_demonstrated": result["result"].get("regression_demonstrated", False),
        "error": result["result"].get("error"),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
