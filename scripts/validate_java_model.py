"""Smoke-test local model-authored Java draft against a pinned Commons Lang snapshot."""

import argparse
import json
import os
from pathlib import Path

from backend import providers
from backend.execution import execute
from backend.proposals import propose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("stringutils", "bitfield"), default="stringutils")
    args = parser.parse_args()
    os.environ.setdefault("DEVPILOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("DEVPILOT_PROPOSAL_MODEL", "qwen2.5-coder:7b")
    info = json.loads(Path("docs/indexed-reference-repositories.json").read_text())["commons-lang"]
    report = {"snapshot": info["fingerprint"], "model": os.environ["DEVPILOT_PROPOSAL_MODEL"]}
    requests = {
        "stringutils": (
            "For a temporary experiment, change StringUtils.isEmpty so a single space counts "
            "as empty. Add a new JUnit 5 regression test named DevPilotStringUtilsTest under "
            "src/test/java/org/apache/commons/lang3. Follow the existing test license header. "
            "The test should fail before the fix and pass afterward."
        ),
        "bitfield": (
            "For a temporary experiment, change BitField.clear(int) so it returns the holder "
            "unchanged. Add a new JUnit 5 regression test named DevPilotBitFieldTest under "
            "src/test/java/org/apache/commons/lang3. Follow the existing test license header. "
            "The test should fail before the change and pass afterward."
        ),
    }
    report["scenario"] = args.scenario
    original_request = providers.request

    def record_request(endpoint, payload):
        response = original_request(endpoint, payload)
        try:
            draft = json.loads(response["choices"][0]["message"]["content"])
            report.setdefault("model_attempts", []).append(
                {
                    "edit_paths": [edit.get("path") for edit in draft.get("edits", [])],
                    "test_paths": list(draft.get("extra_tests", {})),
                    "patch_supplied": bool(draft.get("patch")),
                }
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            report.setdefault("model_attempts", []).append({"unparseable": True})
        return response

    providers.request = record_request
    try:
        draft = propose(info["id"], requests[args.scenario])
        report["draft"] = draft
        if draft["extra_tests"] and draft["patch"]:
            path = next(iter(draft["extra_tests"]))
            target = Path(path).stem
            runner_args = (info["id"], "devpilot-java-commons-lang:local", target, 120)
            report["baseline"] = execute(
                *runner_args, extra_tests=draft["extra_tests"], runner="maven"
            )
            report["patched"] = execute(
                *runner_args,
                patch=draft["patch"],
                extra_tests=draft["extra_tests"],
                runner="maven",
            )
            report["regression_demonstrated"] = (
                report["baseline"]["exit_code"] != 0 and report["patched"]["exit_code"] == 0
            )
    except Exception as exc:
        report["error"] = str(exc)
    output = (
        Path("docs/java-model-validation-bitfield.json")
        if args.scenario == "bitfield"
        else Path("docs/java-model-validation.json")
    )
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "draft",
        "ready" if report.get("draft") else "failed",
        "regression",
        report.get("regression_demonstrated"),
        "error",
        report.get("error"),
    )


if __name__ == "__main__":
    main()
