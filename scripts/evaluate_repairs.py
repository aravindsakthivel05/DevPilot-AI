"""Run reviewed regression tasks on pinned snapshots in offline containers."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.execution import execute


def load_tasks(dataset, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    tasks = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    seen = set()
    for task in tasks:
        if task["id"] in seen:
            raise ValueError(f"Duplicate repair task: {task['id']}")
        seen.add(task["id"])
        if task.get("review_status") != "reviewed":
            raise ValueError(f"Repair task has not been reviewed: {task['id']}")
        if not task.get("issue") or not task.get("patch_provenance"):
            raise ValueError(f"Repair task lacks issue or patch provenance: {task['id']}")
        info = manifest[task["repository"]]
        repo = db.repository(info["id"])
        if not repo or repo["fingerprint"] != info["fingerprint"]:
            raise ValueError(f"Snapshot changed or missing: {task['repository']}")
        if task.get("snapshot") != info["fingerprint"]:
            raise ValueError(f"Task snapshot does not match manifest: {task['id']}")
        if (
            not task.get("patch_file")
            or not task.get("test_files")
            or not task.get("expected_failure")
        ):
            raise ValueError(f"Repair task needs patch, test, and expected failure: {task['id']}")
    return tasks, manifest


def run(dataset, manifest_path, output, limit=None):
    if output.exists():
        raise ValueError(f"Result file already exists: {output}")
    tasks, manifest = load_tasks(dataset, manifest_path)
    if limit is not None:
        tasks = tasks[:limit]
    results = []
    for task in tasks:
        info = manifest[task["repository"]]
        tests = {
            path: (dataset.parent / source).read_text()
            for path, source in task["test_files"].items()
        }
        patch = (dataset.parent / task["patch_file"]).read_text()
        args = (info["id"], task["image"], task["target"], task.get("timeout", 120))
        baseline = execute(*args, extra_tests=tests, runner=task["runner"])
        patched = execute(*args, patch=patch, extra_tests=tests, runner=task["runner"])
        results.append(
            {
                "id": task["id"],
                "repository": task["repository"],
                "snapshot": info["fingerprint"],
                "baseline": baseline,
                "patched": patched,
                "regression_demonstrated": baseline["status"] == "failed"
                and task["expected_failure"] in baseline["output"]
                and patched["exit_code"] == 0,
            }
        )
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset),
        "tasks": len(results),
        "verified": sum(result["regression_demonstrated"] for result in results),
        "results": results,
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("docs/indexed-reference-repositories.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    report = run(args.dataset, args.manifest, args.output, args.limit)
    print(f"Verified {report['verified']}/{report['tasks']} repair tasks")


if __name__ == "__main__":
    main()
