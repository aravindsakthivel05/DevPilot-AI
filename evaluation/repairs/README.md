# Reviewed repair tasks

Place a JSONL task file here, with patch and regression-test files beside it. Each task must
identify a repository in `docs/indexed-reference-repositories.json`, its exact fingerprint,
the issue and patch provenance, a new regression test, and a distinctive expected failure.
Do not mark a task `reviewed` until a person has checked the issue, patch, and test. A task is
verified only when that failure occurs before the patch and the same test passes afterward in
the offline container. A compilation or dependency failure is not a verified regression.

Example record (illustrative paths, not a verified task):

```json
{"id":"issue-001","repository":"requests","snapshot":"<manifest fingerprint>","review_status":"reviewed","issue":"<issue URL and expected behavior>","patch_provenance":"<source commit or reviewed human patch>","runner":"python","image":"devpilot-runner:local","target":"tests/test_devpilot_regression.py","timeout":120,"patch_file":"patches/issue-001.patch","test_files":{"tests/test_devpilot_regression.py":"tests/issue-001.py"},"expected_failure":"AssertionError"}
```

Run `.venv/bin/python -m scripts.evaluate_repairs --dataset evaluation/repairs/tasks.jsonl
--output evaluation/repairs/result.json`. Results are never silently overwritten. The
task runner checks failure identity and pass-after-patch, but reviewers must still inspect
whether the test captures the real issue and whether broader tests pass.

`fixture-commons/` is a deliberately synthetic Commons Lang behavior change used to check the
evaluation machinery. Its offline Maven result is 1/1 verified by the runner, but it is **not**
a real issue or part of the planned 30–50 real-repository repair tasks.
