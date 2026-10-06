import json

from backend import providers
from backend.claim_audit import audit
from backend.evidence import estimated_tokens


def _claim(aspect):
    return {
        "aspect_id": aspect,
        "text": "The value is returned.",
        "status": "supported",
        "citations": [{"source_id": 1, "start_line": 1, "end_line": 1}],
    }


def test_unsupported_aspect_is_removed_without_discarding_supported_aspects(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    calls = []

    def request(endpoint, payload):
        calls.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decisions": [
                                    {
                                        "claim_index": 0,
                                        "verdict": "supported",
                                        "reason": "Direct return statement.",
                                    },
                                    {
                                        "claim_index": 1,
                                        "verdict": "uncertain",
                                        "reason": "The helper body is missing.",
                                    },
                                ]
                            }
                        )
                    }
                }
            ]
        }

    claims, result, _ = audit([_claim(1), _claim(2)], ["return", "helper"], [], request, 8192)
    assert claims[0]["status"] == "supported"
    assert claims[1]["status"] == "insufficient_evidence"
    assert claims[1]["citations"] == []
    assert result["factual_support_proven"] is False
    assert "helper" in calls[0]["messages"][0]["content"]


def test_failed_audit_never_silently_certifies_claims(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")

    def request(*_):
        raise ValueError("Unavailable provider")

    claims, result, _ = audit([_claim(1)], ["return"], [], request, 8192)
    assert result["status"] == "failed"
    assert claims[0]["status"] == "insufficient_evidence"


def test_duplicate_audit_decisions_are_rejected(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")

    def request(*_):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decisions": [
                                    {"claim_index": 0, "verdict": "supported", "reason": "x"},
                                    {"claim_index": 0, "verdict": "supported", "reason": "x"},
                                ]
                            }
                        )
                    }
                }
            ]
        }

    claims, result, _ = audit([_claim(1), _claim(2)], ["a", "b"], [], request, 8192)
    assert result["status"] == "failed"
    assert all(c["status"] == "insufficient_evidence" for c in claims)


def test_auditor_receives_only_each_claims_cited_lines(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    received = []

    def request(endpoint, payload):
        received.append(json.loads(payload["messages"][1]["content"]))
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decisions": [
                                    {
                                        "claim_index": 0,
                                        "verdict": "uncertain",
                                        "reason": "Initialization is not hook execution.",
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    context = [
        {
            "source_id": 1,
            "qualified": "Module",
            "lines": [
                {"line": 1, "text": "result = None"},
                {"line": 2, "text": "hook(self, args)"},
            ],
        }
    ]
    claims, _, _ = audit([_claim(1)], ["hooks"], context, request, 8192)
    assert received[0]["per_claim_evidence"][0]["cited_source"][0]["cited_line_numbers"] == [1]
    assert received[0]["shared_cited_source"][0]["lines"] == [{"line": 1, "text": "result = None"}]
    assert claims[0]["status"] == "insufficient_evidence"


def test_generation_counts_the_additional_audit_call(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    responses = [
        {"claims": [{**_claim(1), "text": "get_value returns the stored value."}]},
        {"decisions": [{"claim_index": 0, "verdict": "supported", "reason": "Direct return."}]},
    ]

    def request(*_):
        return {"choices": [{"message": {"content": json.dumps(responses.pop(0))}}]}

    monkeypatch.setattr(providers, "request", request)
    _, _, metrics = providers.generate(
        "What does get_value return?",
        [
            {
                "path": "values.py",
                "qualified": "values.get_value",
                "start_line": 1,
                "source": "def get_value(): return stored_value",
            }
        ],
    )
    assert metrics["provider_calls"] == 2
    assert not responses


def _review_response():
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "decisions": [
                                {
                                    "claim_index": 0,
                                    "verdict": "supported",
                                    "reason": "Direct return.",
                                }
                            ],
                            "coverage": [
                                {"aspect_id": 1, "status": "complete", "missing_details": []}
                            ],
                        }
                    )
                }
            }
        ]
    }


def test_reviewer_output_reserve_adapts_without_truncating_source(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    captured = []
    context = [
        {"source_id": 1, "qualified": "process", "lines": [{"line": 1, "text": "return value"}]}
    ]

    def request(_, payload):
        captured.append(payload)
        return _review_response()

    audit([_claim(1)], ["return"], context, request, 100000)
    prompt = sum(estimated_tokens(m["content"]) for m in captured[0]["messages"])
    claims, result, _ = audit([_claim(1)], ["return"], context, request, prompt + 256 + 280)
    assert result["status"] == "completed"
    assert claims[0]["status"] == "supported"
    assert 280 <= captured[1]["max_tokens"] < captured[0]["max_tokens"]
    final_prompt = sum(estimated_tokens(m["content"]) for m in captured[1]["messages"])
    assert final_prompt + captured[1]["max_tokens"] + 256 <= prompt + 256 + 280
    assert (
        json.loads(captured[1]["messages"][1]["content"])["shared_cited_source"][0]["lines"]
        == context[0]["lines"]
    )


def test_reviewer_can_drop_duplicate_syntax_tables_but_keeps_all_source_lines(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    captured = []
    context = [
        {
            "source_id": 1,
            "qualified": "process",
            "lines": [
                {"line": 1, "text": "return value"},
                {"line": 2, "text": "# enclosing source"},
            ],
            "behavior_table": [{"expression": "duplicate derived table " * 2000}],
        }
    ]

    def request(_, payload):
        captured.append(payload)
        return _review_response()

    _, result, _ = audit(
        [_claim(1)],
        ["return"],
        context,
        request,
        8192,
        requirement_coverage=[{"detail": "generator labels are not review evidence"}],
    )
    assert result["status"] == "completed"
    payload = json.loads(captured[0]["messages"][1]["content"])
    assert "generator_requirement_coverage" not in payload
    assert "behavior_table" not in payload["enclosing_source"][0]
    assert payload["shared_cited_source"][0]["lines"] == [context[0]["lines"][0]]
    assert payload["enclosing_source"][0]["lines"] == [context[0]["lines"][1]]
    assert result["budget"]["derived_tables_omitted"] is True


def test_oversized_actual_source_cannot_be_silently_truncated_for_review(monkeypatch):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    context = [
        {
            "source_id": 1,
            "qualified": "process",
            "lines": [{"line": 1, "text": "return value " * 3000}],
        }
    ]

    def request(*_):
        raise AssertionError("An oversized review must fail before contacting the provider")

    claims, result, _ = audit([_claim(1)], ["return"], context, request, 8192)
    assert result["status"] == "failed"
    assert result["provider_calls"] == 0
    assert claims[0]["status"] == "insufficient_evidence"
