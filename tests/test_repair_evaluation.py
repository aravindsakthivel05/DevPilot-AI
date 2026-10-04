import json

from scripts import evaluate_repairs


def test_repair_result_requires_expected_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"repo": {"id": "repo-id", "fingerprint": "pinned"}}))
    (tmp_path / "fix.patch").write_text("patch")
    (tmp_path / "regression.py").write_text("def test_regression(): pass\n")
    dataset = tmp_path / "tasks.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "repair-1",
                "repository": "repo",
                "snapshot": "pinned",
                "review_status": "reviewed",
                "issue": "Observed wrong result",
                "patch_provenance": "reviewed human patch",
                "patch_file": "fix.patch",
                "test_files": {"tests/test_regression.py": "regression.py"},
                "expected_failure": "assertion failed",
                "image": "runner:local",
                "target": "tests/test_regression.py",
                "runner": "python",
            }
        )
        + "\n"
    )
    monkeypatch.setattr(evaluate_repairs.db, "repository", lambda _: {"fingerprint": "pinned"})
    calls = []

    def fake_execute(*args, **kwargs):
        calls.append(kwargs)
        return (
            {
                "status": "failed",
                "exit_code": 1,
                "output": "assertion failed",
                "test_report": {
                    "available": True,
                    "failures": 1,
                    "errors": 0,
                    "cases": [{"id": "r", "status": "failed"}],
                },
            }
            if not kwargs.get("patch")
            else {
                "status": "passed",
                "exit_code": 0,
                "output": "",
                "test_report": {
                    "available": True,
                    "passed": 1,
                    "failures": 0,
                    "errors": 0,
                    "cases": [{"id": "r", "status": "passed"}],
                },
            }
        )

    monkeypatch.setattr(evaluate_repairs, "execute", fake_execute)
    report = evaluate_repairs.run(dataset, manifest, tmp_path / "result.json")
    assert report["verified"] == 1
    assert calls[0]["extra_tests"] == {"tests/test_regression.py": "def test_regression(): pass\n"}
