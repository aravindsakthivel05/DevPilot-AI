"""Replay unique questions from a pinned prior report without inventing missing labels."""

import argparse
import json
from pathlib import Path

from backend import db
from backend.agent_investigation import investigate
from backend.providers import ANSWER_PROMPT_VERSION
from backend.retrieval import RETRIEVAL_VERSION, answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing result")
    old = json.loads(args.previous.read_text())
    repo = db.repository(old["repo_id"])
    if not repo or repo["fingerprint"] != old["snapshot"]:
        raise ValueError("Prior snapshot is missing or changed")
    cases = {row["id"]: row["question"] for row in old["results"]}
    report = {
        "repo_id": repo["id"],
        "snapshot": repo["fingerprint"],
        "commit": old["commit"],
        "previous_report": str(args.previous),
        "answer_prompt_version": ANSWER_PROMPT_VERSION,
        "retrieval_version": RETRIEVAL_VERSION,
        "results": [],
    }
    for case_id, question in cases.items():
        for path, runner in [("quick", answer)] + (
            [] if args.quick_only else [("deep", investigate)]
        ):
            result = runner(repo["id"], question)
            report["results"].append(
                {"id": case_id, "path": path, "question": question, **result, "source_review": None}
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(
                case_id,
                path,
                result["generated"],
                result.get("partial"),
                result["elapsed_ms"],
                flush=True,
            )


if __name__ == "__main__":
    main()
