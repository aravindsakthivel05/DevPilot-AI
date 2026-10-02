import json

import pytest

from backend import providers
from backend.retrieval import check_citations


def test_answer_schema_bounds_claims_to_aspects_and_source_ids():
    schema = providers.answer_schema(2)

    assert schema["required"] == ["claims"]
    claims = schema["properties"]["claims"]
    assert claims["minItems"] == claims["maxItems"] == 2
    assert claims["items"]["properties"]["aspect_id"]["enum"] == [1, 2]
    assert set(claims["items"]["required"]) == {"text", "source_id", "aspect_id"}


def test_answer_aspects_keep_all_six_hard_trace_obligations():
    question = (
        "Trace what happens during class creation and on the first validation attempt after "
        "that type is defined: how is the validator mocked, how is rebuilding triggered, "
        "and where is the real validator installed? What happens if the type is still undefined?"
    )
    assert len(providers.answer_aspects(question)) == 6


def test_answer_relevance_terms_allow_simple_word_forms_but_reject_drift():
    assert (
        len(
            providers._answer_terms("validators are mocked")
            & providers._answer_terms("how is the validator mocked")
        )
        >= 2
    )
    assert not (
        providers._answer_terms("the source lacks executable lines")
        & providers._answer_terms("what happens during class creation")
    )


def test_generated_claim_cites_each_sentence(monkeypatch):
    request_payloads = []

    def fake_request(_endpoint, payload):
        request_payloads.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"claims":[{"text":"It computes the quote. It applies the rate.",'
                        '"source_id":1,"aspect_id":1}]}'
                    }
                }
            ],
            "usage": {"total_tokens": 30},
        }

    monkeypatch.setattr(
        providers,
        "request",
        fake_request,
    )
    answer, usage, metrics = providers.generate(
        "What does calculate_quote do?",
        [
            {
                "citation_number": 1,
                "path": "pricing.py",
                "start_line": 1,
                "end_line": 2,
                "qualified": "pricing.calculate_quote",
                "source": "def calculate_quote(base_rate, weight):\n\n    return base_rate * weight\n",
            }
        ],
    )

    assert answer == "It computes the quote [1]. It applies the rate [1]."
    assert usage["total_tokens"] == 30
    assert metrics["request_ms"] >= 0
    assert check_citations(answer, 1)["uncited_sentences"] == []
    evidence = json.loads(request_payloads[0]["messages"][1]["content"])["source_evidence"]
    assert "def calculate_quote(base_rate, weight)" in evidence
    assert metrics["supporting_lines"][0]["text"].startswith("def calculate_quote")


def test_irrelevant_claim_is_rejected_even_with_a_valid_source_id(monkeypatch):
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_args: {
            "choices": [
                {
                    "message": {
                        "content": '{"claims":[{"text":"Database migrations are applied with Alembic",'
                        '"source_id":1,"aspect_id":1}]}'
                    }
                }
            ]
        },
    )

    with pytest.raises(providers.AnswerValidationError, match="cited code does not support"):
        providers.generate(
            "How is migration applied?",
            [
                {
                    "citation_number": 1,
                    "path": "ui.py",
                    "start_line": 1,
                    "end_line": 2,
                    "qualified": "ui.render_template",
                    "source": "def render_template():\n    return '<html>'\n",
                }
            ],
        )


def test_local_ollama_is_detected_but_other_local_providers_are_not(monkeypatch):
    monkeypatch.delenv("DEVPILOT_OLLAMA_NATIVE_API", raising=False)

    assert providers._ollama_native_url({"base_url": "http://127.0.0.1:11434/v1"}) == (
        "http://127.0.0.1:11434/api/chat"
    )
    assert providers._ollama_native_url({"base_url": "http://localhost:1234/v1"}) is None


def test_ollama_native_request_uses_schema_keepalive_and_reports_timing(monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("DEVPILOT_OLLAMA_KEEP_ALIVE", "15m")
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "message": {"content": '{"claims": []}'},
                "prompt_eval_count": 120,
                "eval_count": 22,
                "load_duration": 3_000_000,
                "prompt_eval_duration": 5_000_000,
                "eval_duration": 7_000_000,
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, json, headers):
            calls.append((url, json, headers))
            return Response()

    monkeypatch.setattr(providers.httpx, "Client", Client)
    result = providers.request(
        "chat/completions",
        {
            "model": "qwen2.5-coder:7b",
            "messages": [{"role": "user", "content": "test"}],
            "temperature": 0,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
            "_ollama_schema": providers.answer_schema(1),
        },
    )

    assert calls[0][0] == "http://localhost:11434/api/chat"
    assert calls[0][1]["format"] == providers.answer_schema(1)
    assert calls[0][1]["keep_alive"] == "15m"
    assert calls[0][1]["options"]["num_predict"] == 512
    assert result["usage"]["total_tokens"] == 142
    assert result["_devpilot_metrics"]["load_duration_ms"] == 3
    assert result["_devpilot_metrics"]["eval_duration_ms"] == 7
