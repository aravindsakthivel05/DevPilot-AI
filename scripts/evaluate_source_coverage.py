"""Measure retrieved and actually supplied source spans, without generating answers.

Expected labels are used only after retrieval. They never enter search queries.
Use an isolated DEVPILOT_DATA directory, a frozen questions file and snapshots.
"""

import argparse
import json
import os
import time
from pathlib import Path

from backend import db
from backend.rag.investigation import recover
from backend.retrieval import generation_context, retrieve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", default="source-coverage.json")
    parser.add_argument("--reranker", default="")
    args = parser.parse_args()
    if args.reranker:
        os.environ["DEVPILOT_NEURAL_RERANKER"] = args.reranker
    else:
        os.environ.pop("DEVPILOT_NEURAL_RERANKER", None)
    db.init()
    snapshots = json.loads((args.directory / "snapshots.json").read_text())
    cases = json.loads((args.directory / "questions.json").read_text())["cases"]
    rows = []
    for case in cases:
        if not case["answerable"]:
            continue
        started = time.perf_counter()
        rid = snapshots[case["repository"]]["id"]
        evidence, warning, semantic = retrieve(rid, case["question"], limit=8)
        evidence, reads = recover(rid, case["question"], evidence, retrieve, limit=8)
        context = generation_context(rid, case["question"], evidence)
        expected = case["expected_sources"]
        hits = [
            any(
                s["path"] == label["path"] and label["anchor_line"] in s["source_line_numbers"]
                for s in context
            )
            for label in expected
        ]
        rows.append(
            {
                "id": case["id"],
                "anchors_present": hits,
                "seconds": round(time.perf_counter() - started, 3),
                "semantic_used": semantic,
                "warning": warning,
                "investigation": reads,
                "context": context,
            }
        )
        print(case["id"], hits, rows[-1]["seconds"], flush=True)
        (args.directory / args.output).write_text(
            json.dumps(
                {
                    "notice": "Source-span coverage is not answer correctness. Development benchmark, not held-out accuracy.",
                    "reranker": args.reranker or None,
                    "cases": rows,
                    "anchors_present": sum(sum(row["anchors_present"]) for row in rows),
                    "anchors_total": sum(len(row["anchors_present"]) for row in rows),
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
