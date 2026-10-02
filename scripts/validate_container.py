"""Exercise baseline-fail and patched-pass execution in the real container runner."""

import json
import os
import tempfile
import time

from fastapi.testclient import TestClient

PATCH = """diff --git a/parcel/models.py b/parcel/models.py
--- a/parcel/models.py
+++ b/parcel/models.py
@@ -7,7 +7,7 @@ class Parcel:
     destination: str

     def validate(self):
-        if self.weight_kg <= 0:
+        if self.weight_kg < 0:
             raise ValueError("Weight must be positive")
         if self.destination not in ("domestic", "international"):
             raise ValueError("Unsupported destination")
"""
TEST = """from parcel.api import shipping_quote

def test_zero_weight_uses_minimum_quote():
    assert shipping_quote(0, "domestic")["amount"] == 10.0
"""


def main():
    with tempfile.TemporaryDirectory(prefix="devpilot-container-check-") as data:
        os.environ["DEVPILOT_DATA"] = data
        from backend.main import app

        with TestClient(app) as client:
            repo_id = client.post("/api/demo", json={}).json()["id"]
            for _ in range(100):
                repo = client.get(f"/api/repositories/{repo_id}").json()
                if repo["status"] in ("ready", "failed"):
                    break
                time.sleep(0.1)
            if repo["status"] != "ready":
                raise SystemExit(repo["error"])
            response = client.post(
                f"/api/repositories/{repo_id}/execute",
                json={
                    "patch": PATCH,
                    "extra_tests": {"tests/test_zero_weight.py": TEST},
                    "target": "tests",
                    "timeout": 60,
                },
            )
            response.raise_for_status()
            run_id = response.json()["id"]
            for _ in range(300):
                run = client.get(f"/api/executions/{run_id}").json()
                if run["status"] in ("complete", "failed"):
                    break
                time.sleep(0.1)
            result = run["result"]
            print(
                json.dumps(
                    {
                        "status": run["status"],
                        "baseline_exit": result.get("baseline", {}).get("exit_code"),
                        "patched_exit": result.get("patched", {}).get("exit_code"),
                        "baseline_output": result.get("baseline", {}).get("output", "")[-1500:],
                        "patched_output": result.get("patched", {}).get("output", "")[-1500:],
                        "regression_demonstrated": result.get("regression_demonstrated"),
                        "error": result.get("error"),
                    },
                    indent=2,
                )
            )
            if not result.get("regression_demonstrated"):
                raise SystemExit(1)


if __name__ == "__main__":
    main()
