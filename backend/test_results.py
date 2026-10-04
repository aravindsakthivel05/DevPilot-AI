"""Parse bounded JUnit XML and require actual assertion-test transitions."""

from pathlib import Path
from xml.etree import ElementTree as ET


def collect_reports(work, runner):
    work = Path(work)
    if runner == "python":
        paths = [work / ".devpilot-test-results.xml"]
    else:
        patterns = (
            ("**/target/surefire-reports/*.xml", "**/target/failsafe-reports/*.xml")
            if runner == "maven"
            else ("**/build/test-results/test/*.xml",)
        )
        paths = sorted({p for pattern in patterns for p in work.glob(pattern)})
    cases, errors = [], []
    total_bytes = 0
    if len(paths) > 2000:
        return {"available": False, "error": "Too many test reports.", "total": 0, "cases": []}
    for path in paths:
        if not path.is_file():
            continue
        try:
            # Reject symlinks escaping the disposable workspace.
            if not path.resolve().is_relative_to(work.resolve()):
                raise ValueError("Test report is outside the workspace.")
            size = path.stat().st_size
            total_bytes += size
            if size > 2_000_000 or total_bytes > 20_000_000:
                raise ValueError("Test report size limit exceeded.")
            data = path.read_bytes()
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("Test report must not contain entity declarations.")
            root = ET.fromstring(data)
            for case in root.iter("testcase"):
                failure, error, skip = (
                    case.find("failure"),
                    case.find("error"),
                    case.find("skipped"),
                )
                status = (
                    "failed"
                    if failure is not None
                    else "error"
                    if error is not None
                    else "skipped"
                    if skip is not None
                    else "passed"
                )
                issue = failure if failure is not None else error
                cases.append(
                    {
                        "id": case.get("classname", "") + "::" + case.get("name", ""),
                        "status": status,
                        "failure_type": issue.get("type", "") if issue is not None else "",
                        "detail": (
                            (issue.get("message", "") + " " + (issue.text or ""))[:1500]
                            if issue is not None
                            else ""
                        ),
                        "report": path.relative_to(work).as_posix(),
                    }
                )
        except (OSError, ET.ParseError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    return {
        "available": bool(cases) and not errors,
        "total": len(cases),
        **{
            name: sum(c["status"] == status for c in cases)
            for name, status in [
                ("passed", "passed"),
                ("failures", "failed"),
                ("errors", "error"),
                ("skipped", "skipped"),
            ]
        },
        "cases": cases,
        "parse_errors": errors,
    }


def clear_reports(work, runner):
    patterns = (
        [".devpilot-test-results.xml"]
        if runner == "python"
        else (
            ["**/target/surefire-reports/*.xml", "**/target/failsafe-reports/*.xml"]
            if runner == "maven"
            else ["**/build/test-results/test/*.xml"]
        )
    )
    for pattern in patterns:
        for path in Path(work).glob(pattern):
            if path.resolve().is_relative_to(Path(work).resolve()) and path.is_file():
                path.unlink()


def passed_tests(result):
    report = (result or {}).get("test_report", {})
    return bool(
        result
        and result.get("exit_code") == 0
        and report.get("available")
        and report.get("passed", 0) > 0
        and not report.get("failures")
        and not report.get("errors")
    )


def regression_transition(before, after):
    report = (before or {}).get("test_report", {})
    if (
        not before
        or before.get("exit_code", 0) == 0
        or not report.get("available")
        or report.get("errors", 0)
        or not passed_tests(after)
    ):
        return False
    failed = {c["id"] for c in report.get("cases", []) if c["status"] == "failed"}
    passed = {c["id"] for c in after["test_report"].get("cases", []) if c["status"] == "passed"}
    return bool(failed) and failed <= passed
