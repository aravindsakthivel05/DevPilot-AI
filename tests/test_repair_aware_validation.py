"""Paired regressions: recover sound explanations without certifying false ones."""

import json

import pytest

from backend import providers
from backend.evidence import excerpt
from backend.rag.claim_repair import preserves
from backend.rag.support_checks import support_warning


def source(code, **extra):
    return {
        "path": "sample.py",
        "qualified": "sample.process",
        "start_line": 1,
        "source": code,
        **extra,
    }


def claim(text, first, last, status="supported"):
    return {
        "text": text,
        "aspect_id": 1,
        "status": status,
        "citations": [{"source_id": 1, "start_line": first, "end_line": last}]
        if status == "supported"
        else [],
    }


def respond(monkeypatch, claims, coverage=None, verdicts=None):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1" if coverage or verdicts else "0")

    def request(_, payload):
        if "Review repository claims" in payload["messages"][0]["content"]:
            data = {
                "decisions": verdicts
                or [
                    {
                        "claim_index": i,
                        "verdict": "supported",
                        "reason": "Fixture source supports it.",
                    }
                    for i in range(len(claims))
                    if claims[i]["status"] == "supported"
                ],
                "coverage": coverage or [],
            }
        else:
            data = {"claims": claims}
        return {"choices": [{"message": {"content": json.dumps(data)}}]}

    monkeypatch.setattr(providers, "request", request)


def test_docstring_omission_preserves_executable_completeness_but_missing_branch_does_not():
    record = source('def process():\n    """Close the stream."""\n    stream.close()\n    notify()')
    complete = excerpt(record, "How does process close the stream?", 200)
    assert complete["truncated"]
    assert complete["executable_complete"]
    long = source(
        'def process():\n    """Close the stream."""\n'
        + "    unrelated_work()\n" * 100
        + "    if failed:\n        recover()"
    )
    partial = excerpt(long, "How does process close?", 30)
    assert not partial["executable_complete"]


def test_implicit_return_claim_survives_with_complete_guarded_body(monkeypatch):
    code = "def process():\n    if not closed:\n        connector.close()"
    respond(
        monkeypatch,
        [claim("If already closed, process does nothing and returns immediately.", 2, 2)],
    )
    text, _, metrics = providers.generate(
        "What happens if process is already closed?", [source(code)]
    )
    assert "returns immediately" in text
    assert metrics["citation_repairs"]
    assert metrics["claims"][0]["citations"] == [{"source_id": 1, "start_line": 1, "end_line": 3}]


def test_incomplete_declaration_cannot_establish_an_implicit_return(monkeypatch):
    respond(monkeypatch, [claim("process returns immediately with nothing.", 1, 1)])
    with pytest.raises(providers.AnswerValidationError, match="return expression"):
        providers.generate("What does process return?", [source("def process():", truncated=True)])


def test_implicit_return_does_not_prove_a_non_none_value(monkeypatch):
    respond(monkeypatch, [claim("process returns a connector object.", 1, 2)])
    with pytest.raises(providers.AnswerValidationError, match="return expression"):
        providers.generate(
            "What does process return?", [source("def process():\n    connector.close()")]
        )


def test_assigned_return_and_its_condition_are_added_to_citation(monkeypatch):
    respond(monkeypatch, [claim("If silent, process returns None.", 3, 3)])
    code = "def process(silent):\n    if silent:\n        rv = None\n    else:\n        rv = parse()\n    return rv"
    text, _, metrics = providers.generate("What does process return when silent?", [source(code)])
    assert "returns None" in text
    spans = metrics["claims"][0]["citations"]
    assert spans == [{"source_id": 1, "start_line": 2, "end_line": 6}]
    assert not metrics["claim_validation_failures"]


def test_websocket_terminology_is_allowed_but_unknown_configuration_is_not():
    s = [
        {
            "qualified": "Matcher.match",
            "lines": [{"text": "if rule.websocket: websocket_mismatch = True"}],
        }
    ]
    assert support_warning({"text": "A WebSocket mismatch is recorded."}, s) is None
    assert support_warning({"text": "WebSocketPolicy is enabled."}, s)


def test_negative_callback_statement_uses_executable_completeness():
    s = [
        {
            "qualified": "Response.close",
            "excerpt_complete": False,
            "executable_complete": True,
            "lines": [{"text": "stream.close(); notify()"}],
        }
    ]
    assert (
        support_warning(
            {"text": "Response.close does not guarantee callbacks after an exception."}, s
        )
        is None
    )
    s[0]["executable_complete"] = False
    assert support_warning(
        {"text": "Response.close does not guarantee callbacks after an exception."}, s
    )


def test_unknown_negative_text_never_becomes_a_declarative_answer(monkeypatch):
    raw = "process does not clear authentication on an origin change."
    respond(monkeypatch, [claim(raw, 1, 1, status="insufficient_evidence")])
    text, _, metrics = providers.generate(
        "Does process clear authentication?", [source("def process():\n    auth = None")]
    )
    assert raw not in text
    assert "could not be established" in text
    assert metrics["draft_claims"][0]["text"] == raw


def test_missing_coverage_marks_partial_without_removing_correct_claim(monkeypatch):
    respond(
        monkeypatch,
        [claim("process returns the cached value.", 2, 2)],
        coverage=[
            {
                "aspect_id": 1,
                "status": "partial",
                "missing_details": ["Error behavior is not explained."],
            }
        ],
    )
    text, _, metrics = providers.generate(
        "How does process handle cached values and errors?",
        [source("def process():\n    return cached_value")],
    )
    assert "returns the cached value" in text
    assert metrics["aspect_statuses"][0]["status"] == "partial"
    assert metrics["aspect_statuses"][0]["coverage_status"] == "partial"
    assert metrics["claims"][0]["status"] == "supported"


def test_reviewer_contradiction_keeps_good_claim_and_removes_false_claim(monkeypatch):
    claims = [
        claim("process returns the cached value.", 2, 2),
        claim("process returns a new object every time.", 2, 2),
    ]
    respond(
        monkeypatch,
        claims,
        verdicts=[
            {"claim_index": 0, "verdict": "supported", "reason": "Returns cached_value."},
            {
                "claim_index": 1,
                "verdict": "unsupported",
                "reason": "No new object; cached_value is returned.",
                "basis": [{"source_id": 1, "start_line": 2, "end_line": 2}],
            },
        ],
    )
    text, _, metrics = providers.generate(
        "What does process return?", [source("def process():\n    return cached_value")]
    )
    assert "cached value" in text and "new object every time" not in text
    assert metrics["claim_audit"]["decisions"][1]["verdict"] == "unsupported"


def test_reviewer_without_valid_basis_cannot_label_a_proven_contradiction(monkeypatch):
    respond(
        monkeypatch,
        [claim("process returns the cached value.", 2, 2)],
        verdicts=[
            {
                "claim_index": 0,
                "verdict": "unsupported",
                "reason": "It seems wrong.",
                "basis": [{"source_id": 1, "start_line": 1, "end_line": 10000000}],
            }
        ],
    )
    _, _, metrics = providers.generate(
        "What does process return?", [source("def process():\n    return cached_value")]
    )
    assert metrics["claim_audit"]["decisions"][0]["verdict"] == "uncertain"


def test_repair_cannot_replace_retained_claim_with_fewer_details():
    old = [claim("process returns the cached value.", 2, 2)]
    assert preserves(old, old + [claim("Errors are raised.", 3, 3)])
    assert not preserves(old, [claim("process works correctly.", 2, 2)])


def test_bounded_excerpt_keeps_distinct_conditions_and_effects():
    padding = "\n".join("    irrelevant_work()" for _ in range(120))
    code = (
        "def process(status, method, body, origin):\n" + padding + "\n"
        "    if status == 303 and method != HEAD:\n        method = GET\n"
        "    if body.consumed:\n        raise ReplayError()\n"
        "    if origin != target_origin:\n        cookies = None\n        headers.pop(AUTHORIZATION)"
    )
    e = excerpt(
        source(code),
        "When process handles a response, which status changes the method, when can a body be replayed, and which authentication state is cleared on an origin change?",
        180,
    )
    assert "method != HEAD" in e["source"]
    assert "body.consumed" in e["source"]
    assert "headers.pop(AUTHORIZATION)" in e["source"]


def test_failed_repair_restores_original_citation_context(repo, monkeypatch):
    import httpx

    from backend.rag import pipeline

    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_REPAIR_REJECTED_CLAIMS", "1")
    original_context = pipeline.generation_context
    contexts = []

    def context(*args, **kwargs):
        result = original_context(*args, **kwargs)
        if contexts:
            result = [{**item, "citation_number": 99 + i} for i, item in enumerate(result)]
        contexts.append(result)
        return result

    calls = []

    def generate(question, evidence, citation_feedback=None):
        calls.append(citation_feedback)
        if len(calls) == 2:
            raise httpx.ReadTimeout("Repair timed out")
        first = evidence[0]
        sid = first["citation_number"]
        line = first["source_line_numbers"][0]
        positive = {
            "text": "It computes the quote.",
            "status": "supported",
            "aspect_id": 1,
            "citations": [{"source_id": sid, "start_line": line, "end_line": line}],
        }
        missing = {
            "text": "Missing error details.",
            "status": "insufficient_evidence",
            "aspect_id": 1,
            "citations": [],
        }
        return (
            f"It computes the quote [{sid}].\n\nAspect 1: Missing error details.",
            {},
            {
                "claims": [positive, missing],
                "aspect_statuses": [{"aspect_id": 1, "question": question, "status": "partial"}],
                "claim_audit": {
                    "status": "completed",
                    "decisions": [{"verdict": "uncertain", "reason": "Need the error branch."}],
                },
                "supporting_lines": [{"source_id": sid, "start_line": line, "end_line": line}],
            },
        )

    monkeypatch.setattr(pipeline, "generation_context", context)
    monkeypatch.setattr(pipeline, "generate", generate)
    result = pipeline.answer(repo["id"], "How does calculate_quote compute the quote?")
    assert len(calls) == 2 and len(contexts) == 2
    assert result["generation_diagnostics"]["selected_attempt"] == 1
    assert result["generation_context"][0]["source_id"] == contexts[0][0]["citation_number"]
    assert result["citation_provenance"][0]["file"] == contexts[0][0]["path"]
    assert not result["citation_check"]["invalid"]


def test_repair_feedback_reserves_source_context_budget(repo):
    from backend import db
    from backend.rag.pipeline import generation_context

    symbol = next(s for s in db.symbols(repo["id"]) if s["kind"] == "function")
    code = f"def {symbol['name']}():\n" + "    compute_quote()\n" * 700 + "    return quote"
    with db.connection() as c:
        c.execute(
            "UPDATE symbols SET source=?,start_line=1,end_line=? WHERE id=?",
            (code, len(code.splitlines()), symbol["id"]),
        )
    normal = generation_context(repo["id"], "How is the quote computed?", [symbol])
    repair = generation_context(
        repo["id"], "How is the quote computed?", [symbol], reserve_tokens=2000
    )
    assert sum(c["estimated_source_tokens"] for c in repair) < sum(
        c["estimated_source_tokens"] for c in normal
    )
    assert all(c["source_line_numbers"] for c in repair)


def test_preprocessor_conditions_are_executable_coverage_not_python_comments():
    record = {
        "path": "sample.hpp",
        "qualified": "FAIL",
        "start_line": 1,
        "source": "#if FEATURE\n#define FAIL() throw Error()\n#else\n#define FAIL() abort()\n#endif",
    }
    assert excerpt(record, "How does FAIL behave?", 200)["executable_complete"]
    assert not excerpt(record, "How does FAIL behave?", 5)["executable_complete"]
