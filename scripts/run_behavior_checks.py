"""Execute explicitly supplied behavior checks on pinned snapshots in Docker."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from backend import db
from backend.execution import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--tests", type=Path, required=True, help="Directory of repository-name.py checks"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="devpilot-runner:local")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite existing execution evidence")
    manifest = json.loads(args.manifest.read_text())
    image_id = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "image_id": image_id,
        "verification_scope": "Only supplied behavior scenarios, not all answers or repository tests",
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, pinned in manifest.items():
        path = args.tests / f"{name}.py"
        if not path.is_file():
            continue
        repo = db.repository(pinned["id"])
        if not repo or repo["status"] != "ready" or repo["fingerprint"] != pinned["fingerprint"]:
            raise ValueError("Snapshot is missing or changed")
        content = path.read_text()
        if len(content.encode()) > 50000:
            raise ValueError("Behavior check is too large")
        target = "tests/devpilot_scenarios/test_behavior_check.py"
        result = execute(
            pinned["id"],
            args.image,
            target,
            60,
            extra_tests={target: content},
            scenario_isolation=True,
        )
        report["results"].append(
            {
                "repository": name,
                "commit": pinned.get("commit"),
                "test_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                **result,
            }
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(name, result["status"], result.get("test_report"), flush=True)


if __name__ == "__main__":
    main()
