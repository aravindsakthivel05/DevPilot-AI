"""Comparison scoring must retain failed and missing scheduled attempts."""

from copy import deepcopy

import pytest

from scripts.summarize_model_comparison import summarize


def fixture():
    identity = {"cases": ["case"], "variants": [["generator", "reviewer"]], "repeats": 1}
    key = {"case_id": "case", "model": "generator", "reviewer": "reviewer", "repeat": 1}
    output = {**key, "elapsed_ms": 1000}
    label = {
        **key,
        "correct": True,
        "required_detail_coverage": [True, False],
        "unsupported_claims": [],
    }
    return (
        {"identity": identity, "results": [output]},
        [{"id": "case", "required_details": ["condition", "result"]}],
        {"reviewer": "explicit source review", "cases": [label]},
    )


def test_correct_partial_answer_is_not_counted_as_fully_adequate():
    result = summarize(*fixture())["variants"][0]
    assert result["correct"] == 1
    assert result["fully_adequate"] == 0
    assert (result["covered_details"], result["required_details"]) == (1, 2)


def test_provider_failure_remains_in_scored_denominator():
    comparison, questions, review = fixture()
    comparison["results"][0]["error"] = "provider timeout"
    review["cases"][0].update(correct=False, required_detail_coverage=[False, False])
    result = summarize(comparison, questions, review)["variants"][0]
    assert result["cases"] == result["failures"] == 1
    assert result["correct"] == result["fully_adequate"] == 0
    review["cases"][0]["correct"] = True
    with pytest.raises(ValueError, match="cannot be scored as correct"):
        summarize(comparison, questions, review)


def test_equal_row_count_cannot_replace_a_missing_scheduled_case():
    comparison, questions, review = fixture()
    questions.append({"id": "other", "required_details": ["x", "y"]})
    comparison["results"][0]["case_id"] = "other"
    review["cases"][0]["case_id"] = "other"
    with pytest.raises(ValueError, match="every scheduled"):
        summarize(comparison, questions, review)


def test_unavailable_review_is_reported_even_without_a_provider_exception():
    comparison, questions, review = fixture()
    comparison["results"][0]["generation"] = {"claim_audit": {"status": "failed"}}
    review["cases"][0].update(correct=False, required_detail_coverage=[False, False])
    result = summarize(comparison, questions, review)["variants"][0]
    assert result["audit_failures"] == 1
    assert result["failures"] == 0
    assert result["fully_adequate"] == 0


def test_missing_repeat_cannot_be_hidden_by_duplicate_reviews():
    comparison, questions, review = fixture()
    comparison["identity"]["repeats"] = 2
    with pytest.raises(ValueError, match="every scheduled"):
        summarize(comparison, questions, review)
    review["cases"].append(deepcopy(review["cases"][0]))
    with pytest.raises(ValueError, match="Duplicate source-review"):
        summarize(comparison, questions, review)
