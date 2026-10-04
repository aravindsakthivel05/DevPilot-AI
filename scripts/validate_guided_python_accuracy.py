"""Synthetic NaN regression fixture: existing-suite baseline, fail/pass test, existing suite."""

import argparse
import difflib
import json
from pathlib import Path

from backend import agent_repair, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite a validation result.")
    db.init()
    with db.connection() as c:
        row = c.execute(
            "SELECT repositories.id,files.content FROM repositories JOIN files ON files.repo_id=repositories.id WHERE repositories.name='parcel-service' AND files.path='parcel/models.py' AND repositories.status='ready' ORDER BY repositories.created_at LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("Index the included parcel-service demo first.")
    source = row["content"]
    changed = "import math\n" + source.replace(
        "if self.weight_kg <= 0:", "if not math.isfinite(self.weight_kg) or self.weight_kg <= 0:"
    )
    patch = "diff --git a/parcel/models.py b/parcel/models.py\n" + "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            changed.splitlines(keepends=True),
            fromfile="a/parcel/models.py",
            tofile="b/parcel/models.py",
        )
    )
    draft = {
        "summary": "Synthetic finite-weight requirement; authored fixture, not an LLM repair.",
        "patch": patch,
        "extra_tests": {
            "tests/test_devpilot_nan.py": 'import pytest\nfrom parcel.api import shipping_quote\n\ndef test_nan_weight_is_rejected():\n    with pytest.raises(ValueError):\n        shipping_quote(float("nan"), "domestic")\n'
        },
    }
    original = agent_repair.propose
    agent_repair.propose = lambda *_: draft
    try:
        run = agent_repair.create_run(
            row["id"], "Synthetic NaN fixture", "devpilot-runner:local", "python", "tests", 60
        )
    finally:
        agent_repair.propose = original
    agent_repair.queue_review(run["id"])
    agent_repair.resume_run(run["id"], True)
    result = agent_repair.get_run(run["id"])
    report = {"fixture_only": True, "model_generated": False, "run": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "outcome": result["result"].get("outcome"),
                "verified": result["result"].get("regression_demonstrated"),
                "output": str(args.output),
            }
        )
    )
    if not result["result"].get("regression_demonstrated"):
        raise ValueError("Synthetic repair did not satisfy all four verification stages.")


if __name__ == "__main__":
    main()
