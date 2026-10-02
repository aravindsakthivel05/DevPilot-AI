"""Write the reviewed seed questions to an inspectable JSONL dataset."""

import json
from pathlib import Path

from .evaluate_repositories import CASES

HOLDOUT = {"rich", "petclinic"}


def main():
    target = Path("evaluation/cases.jsonl")
    target.parent.mkdir(exist_ok=True)
    with target.open("w") as output:
        for repo, cases in CASES.items():
            for number, case in enumerate(cases, 1):
                row = {
                    "id": f"{repo}-{number:03d}",
                    "repository": repo,
                    "split": "holdout" if repo in HOLDOUT else "development",
                    "question": case["question"],
                    "expected_symbols": case["expected_symbols"],
                    "answerable": True,
                    "review_status": "reviewed",
                }
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {sum(map(len, CASES.values()))} cases to {target}")


if __name__ == "__main__":
    main()
