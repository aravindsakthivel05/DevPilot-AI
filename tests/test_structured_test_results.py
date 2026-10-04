from backend import agent_repair
from backend.test_results import collect_reports, passed_tests, regression_transition


def test_empty_or_missing_report_cannot_be_a_verified_pass(tmp_path):
    result = {"exit_code": 0, "test_report": collect_reports(tmp_path, "python")}
    assert not passed_tests(result)
    (tmp_path / ".devpilot-test-results.xml").write_text('<testsuite tests="0"/>')
    assert not passed_tests({"exit_code": 0, "test_report": collect_reports(tmp_path, "python")})


def test_same_assertion_test_must_fail_before_and_pass_after(tmp_path):
    report = tmp_path / ".devpilot-test-results.xml"
    report.write_text(
        '<testsuite><testcase classname="pricing" name="test_price"><failure type="AssertionError">incorrect price</failure></testcase></testsuite>'
    )
    before = {"exit_code": 1, "test_report": collect_reports(tmp_path, "python")}
    report.write_text(
        '<testsuite><testcase classname="pricing" name="unrelated_test"/></testsuite>'
    )
    after = {"exit_code": 0, "test_report": collect_reports(tmp_path, "python")}
    assert not regression_transition(before, after)
    report.write_text('<testsuite><testcase classname="pricing" name="test_price"/></testsuite>')
    after["test_report"] = collect_reports(tmp_path, "python")
    assert regression_transition(before, after)


def test_compilation_or_import_error_is_not_a_regression(tmp_path):
    report = tmp_path / ".devpilot-test-results.xml"
    report.write_text(
        '<testsuite><testcase name="test_price"><error type="ImportError"/></testcase></testsuite>'
    )
    before = {"exit_code": 1, "test_report": collect_reports(tmp_path, "python")}
    report.write_text('<testsuite><testcase name="test_price"/></testsuite>')
    assert not regression_transition(
        before, {"exit_code": 0, "test_report": collect_reports(tmp_path, "python")}
    )


def test_guided_verification_requires_existing_suite_passes():
    failure = {
        "exit_code": 1,
        "test_report": {
            "available": True,
            "errors": 0,
            "cases": [{"id": "regression", "status": "failed"}],
        },
    }
    success = {
        "exit_code": 0,
        "test_report": {
            "available": True,
            "passed": 1,
            "errors": 0,
            "cases": [{"id": "regression", "status": "passed"}],
        },
    }
    state = {
        "approved": True,
        "baseline": failure,
        "patched": success,
        "existing_baseline": success,
        "existing_patched": {"exit_code": 0},
    }
    assert not agent_repair._done(state)["regression_demonstrated"]
    state["existing_patched"] = success
    assert agent_repair._done(state)["regression_demonstrated"]


def test_reports_with_entity_declarations_are_rejected(tmp_path):
    (tmp_path / ".devpilot-test-results.xml").write_text(
        '<!DOCTYPE x [<!ENTITY x "data">]><testsuite/>'
    )
    report = collect_reports(tmp_path, "python")
    assert not report["available"]
    assert report["parse_errors"]
