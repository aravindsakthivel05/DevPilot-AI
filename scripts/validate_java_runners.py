"""Run selected tests in all three pinned Java snapshots through DevPilot containers."""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.execution import execute

CASES = {
    "petclinic": ("maven", "OwnerControllerTests"),
    "commons-lang": ("maven", "StringUtilsTest"),
    "mockito": ("gradle", "org.mockito.internal.util.MockUtilTest"),
}


def main():
    manifest = json.loads(Path("docs/indexed-reference-repositories.json").read_text())
    results = {}
    for name, (runner, target) in CASES.items():
        info = manifest[name]
        image = f"devpilot-java-{name}:local"
        result = execute(info["id"], image, target, 180, runner=runner)
        results[name] = result
        print(f"{name}: {result['status']} ({result['elapsed_ms']} ms)", flush=True)
    report = {"validated_at": datetime.now(timezone.utc).isoformat(), "results": results}
    Path("docs/java-runner-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    if any(result["status"] != "passed" for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
