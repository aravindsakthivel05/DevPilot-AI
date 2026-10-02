"""Check Java test injection and exact-edit patch verification on a disposable Commons snapshot."""

import json
from pathlib import Path

from backend.config import SNAPSHOTS
from backend.execution import execute
from backend.proposals import validate_proposal


def main():
    info = json.loads(Path("docs/indexed-reference-repositories.json").read_text())["commons-lang"]
    test_path = "src/test/java/org/apache/commons/lang3/DevPilotStringUtilsTest.java"
    reference_test = (
        SNAPSHOTS / info["id"] / "src/test/java/org/apache/commons/lang3/StringUtilsTest.java"
    )
    license_header = reference_test.read_text().split("*/", 1)[0] + "*/\n"
    draft = validate_proposal(
        {
            "summary": "Temporary runner fixture: treat whitespace as empty",
            "patch": "",
            "edits": [
                {
                    "path": "src/main/java/org/apache/commons/lang3/StringUtils.java",
                    "old": "return cs == null || cs.length() == 0;",
                    "new": "return cs == null || cs.length() == 0 || cs.toString().trim().isEmpty();",
                }
            ],
            "extra_tests": {
                test_path: (
                    license_header + "package org.apache.commons.lang3;\n"
                    "import static org.junit.jupiter.api.Assertions.assertTrue;\n"
                    "import org.junit.jupiter.api.Test;\n"
                    "class DevPilotStringUtilsTest {\n"
                    '  @Test void whitespaceIsEmpty() { assertTrue(StringUtils.isEmpty(" ")); }\n'
                    "}\n"
                )
            },
        },
        info["id"],
        "java",
    )
    args = (info["id"], "devpilot-java-commons-lang:local", "DevPilotStringUtilsTest", 120)
    baseline = execute(*args, extra_tests=draft["extra_tests"], runner="maven")
    patched = execute(*args, patch=draft["patch"], extra_tests=draft["extra_tests"], runner="maven")
    report = {
        "snapshot": info["fingerprint"],
        "test_path": test_path,
        "baseline": baseline,
        "patched": patched,
        "regression_demonstrated": baseline["exit_code"] != 0 and patched["exit_code"] == 0,
        "fixture_only": True,
    }
    Path("docs/java-generated-test-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("baseline", baseline["status"], "patched", patched["status"])
    if not report["regression_demonstrated"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
