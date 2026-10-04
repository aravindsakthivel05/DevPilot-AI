import json

from backend import providers
from backend.claim_audit import audit


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
    assert received[0]["per_claim_evidence"][0]["cited_source"][0]["lines"] == [
        {"line": 1, "text": "result = None"}
    ]
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
