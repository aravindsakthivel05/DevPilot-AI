"""Regressions for subject scope, omitted details, corrections and cache reuse."""

import json

import pytest

from backend import db, providers
from backend.claim_audit import audit
from backend.rag import pipeline
from backend.rag.claim_repair import preserves, revision_requests
from backend.rag.obligations import reconcile, requirements
from backend.rag.subject_scope import contextual_subjects
from backend.rag.support_checks import support_warning


def claim(text="process returns the stored value.", aspect=1):
    return {
        "text": text,
        "aspect_id": aspect,
        "status": "supported",
        "citations": [{"source_id": 1, "start_line": 2, "end_line": 2}],
    }


def test_question_subject_does_not_require_function_to_declare_class(monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    good = claim("For a MultiDiGraph, process subtracts the number of parallel edges.")
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {"choices": [{"message": {"content": json.dumps({"claims": [good]})}}]},
    )
    question = "How does process count parallel edges for a MultiDiGraph?"
    evidence = {
        "qualified": "pkg.process",
        "path": "a.py",
        "start_line": 1,
        "source": "def process(G, child):\n    degree[child] -= len(G[node][child]) if G.is_multigraph() else 1",
    }
    answer, _, metrics = providers.generate(question, [evidence])
    assert "parallel edges" in answer
    assert metrics["claim_validation_failures"] == []
    sources = [{"qualified": "pkg.process", "lines": [{"text": evidence["source"]}]}]
    assert support_warning(good, sources, contextual_subjects(good["text"], question)) is None
    # Merely naming the class in a question cannot authorize invented identity.
    bad = claim("MultiDiGraph is declared inside process.")
    assert contextual_subjects(bad["text"], question) == set()
    assert support_warning(bad, sources, contextual_subjects(bad["text"], question))


def test_dispatch_requirements_keep_each_requested_alternative():
    rows = requirements(
        "How does shortest_path choose an algorithm and orient returned paths for unweighted, Dijkstra, and Bellman-Ford cases?"
    )
    details = [r["detail"] for r in rows]
    assert any("arguments" in detail for detail in details)
    assert sum(r["id"].split(".")[-1].startswith("case") for r in rows) == 3
    assert len({r["id"] for r in rows}) == len(rows)
    yielded = requirements("What does connected_components yield?")
    assert not any("keys" in r["detail"] for r in yielded)


def test_plural_conditional_subject_preserves_source_based_behavior_only():
    question = "How are parallel edges counted for a MultiDiGraph?"
    good = claim("For MultiDiGraphs, process subtracts len(G[node][child]).")
    sources = [
        {
            "qualified": "process",
            "lines": [{"text": "indegree_map[child] -= len(G[node][child]) if multigraph else 1"}],
        }
    ]
    assert support_warning(good, sources, contextual_subjects(good["text"], question)) is None
    bad = claim("MultiDiGraphs is declared inside process.")
    assert support_warning(bad, sources, contextual_subjects(bad["text"], question))
    unrelated = claim("For DifferentGraphs, process subtracts one.")
    assert support_warning(unrelated, sources, contextual_subjects(unrelated["text"], question))


def test_requirement_coverage_cannot_refer_to_other_aspect_or_duplicate_id():
    rows = requirements("What does process return? How are errors handled?")
    declared = [{"requirement_id": r["id"], "status": "missing", "claim_indices": []} for r in rows]
    declared[0] = {"requirement_id": rows[0]["id"], "status": "covered", "claim_indices": [1]}
    with pytest.raises(ValueError, match="own aspect"):
        reconcile(rows, declared, [claim(), claim(aspect=2)])
    declared[0]["claim_indices"] = [0]
    declared[1]["requirement_id"] = declared[0]["requirement_id"]
    with pytest.raises(ValueError, match="duplicate"):
        reconcile(rows, declared, [claim(), claim(aspect=2)])


def test_removed_claim_cannot_leave_a_covered_requirement():
    rows = requirements("Explain process")
    declared = [{"requirement_id": rows[0]["id"], "status": "covered", "claim_indices": [0]}]
    result = reconcile(rows, declared, [{**claim(), "status": "insufficient_evidence"}])
    assert result["items"][0]["status"] == "missing"
    assert result["semantic_coverage"] == "unverified"


def test_malformed_coverage_metadata_does_not_discard_cited_answer(monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    response = {
        "claims": [claim()],
        "requirement_coverage": [
            {"requirement_id": "invented", "status": "covered", "claim_indices": [999]}
        ],
    }
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_: {"choices": [{"message": {"content": json.dumps(response)}}]},
    )
    answer, _, metrics = providers.generate(
        "What does process return?",
        [
            {
                "qualified": "process",
                "path": "a.py",
                "start_line": 1,
                "source": "def process():\n    return stored_value",
            }
        ],
    )
    assert "stored value" in answer
    assert metrics["requirement_coverage"]["status"] == "unavailable"
    assert metrics["requirement_coverage_error"]


def test_independent_requirement_review_marks_gap_without_erasing_sound_claim(monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    question = "What does process return?"
    rows = requirements(question)

    def request(_, payload):
        if "Review repository claims" in payload["messages"][0]["content"]:
            response = {
                "decisions": [
                    {"claim_index": 0, "verdict": "supported", "reason": "Direct return."}
                ],
                "coverage": [{"aspect_id": 1, "status": "complete", "missing_details": []}],
                "requirements": [
                    {
                        "requirement_id": r["id"],
                        "status": "missing" if r["id"].endswith("results") else "covered",
                    }
                    for r in rows
                ],
            }
        else:
            response = {
                "claims": [claim()],
                "requirement_coverage": [
                    {"requirement_id": r["id"], "status": "covered", "claim_indices": [0]}
                    for r in rows
                ],
            }
        return {"choices": [{"message": {"content": json.dumps(response)}}]}

    monkeypatch.setattr(providers, "request", request)
    answer, _, metrics = providers.generate(
        question,
        [
            {
                "path": "a.py",
                "qualified": "process",
                "start_line": 1,
                "source": "def process():\n    return stored_value",
            }
        ],
    )
    assert "stored value" in answer
    assert metrics["aspect_statuses"][0]["status"] == "partial"
    assert metrics["aspect_statuses"][0]["coverage_status"] == "partial"


@pytest.mark.parametrize("basis", [[], [{"source_id": 1, "start_line": 2, "end_line": 2}]])
def test_accepted_mistake_can_only_be_replaced_with_reviewed_correction(monkeypatch, basis):
    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    old = claim("process returns a fresh object.")
    new = claim()
    revisions = revision_requests(
        [
            {
                "previous_claim_index": 0,
                "replacement_claim_index": 0,
                "reason": "The return expression uses stored_value, not a constructor.",
            }
        ],
        [{"claim_index": 0, **old}],
        [new],
    )
    context = [
        {
            "source_id": 1,
            "qualified": "process",
            "path": "a.py",
            "lines": [{"line": 2, "text": "return stored_value"}],
        }
    ]

    def request(*_):
        value = {
            "decisions": [{"claim_index": 0, "verdict": "supported", "reason": "Direct return."}],
            "revision_decisions": [
                {
                    "revision_index": 0,
                    "verdict": "supported",
                    "reason": "Uses stored value.",
                    "basis": basis,
                }
            ],
        }
        return {"choices": [{"message": {"content": json.dumps(value)}}]}

    revised, result, _ = audit(
        [new], ["What does process return?"], context, request, 8192, revisions=revisions
    )
    assert preserves([old], revised, result["approved_revisions"]) is bool(basis)
    assert not preserves([old], [new])


def test_correction_cannot_replace_claim_from_other_aspect():
    with pytest.raises(ValueError, match="same aspect"):
        revision_requests(
            [
                {
                    "previous_claim_index": 0,
                    "replacement_claim_index": 0,
                    "reason": "Source correction.",
                }
            ],
            [{"claim_index": 0, **claim()}],
            [claim(aspect=2)],
        )


def test_lexical_cache_is_isolated_mutation_safe_and_invalidated_by_index_edit(repo):
    first = pipeline.retrieve(repo["id"], "calculate_quote", "lexical", 5, 0)
    # First read may create FTS state; next two reads should reuse stable state.
    second = pipeline.retrieve(repo["id"], "calculate_quote", "lexical", 5, 0)
    third = pipeline.retrieve(repo["id"], "calculate_quote", "lexical", 5, 0)
    assert [e["id"] for e in first[0]] == [e["id"] for e in third[0]]
    assert pipeline.TRACE.get()["cache_hit"] is True
    second[0][0]["source"] = "poisoned caller copy"
    assert (
        pipeline.retrieve(repo["id"], "calculate_quote", "lexical", 5, 0)[0][0]["source"]
        != "poisoned caller copy"
    )
    with db.connection() as connection:
        connection.execute(
            "UPDATE symbols SET source=source || '\n# changed' WHERE id=?", (first[0][0]["id"],)
        )
    refreshed = pipeline.retrieve(repo["id"], "calculate_quote", "lexical", 5, 0)
    assert not pipeline.TRACE.get().get("cache_hit")
    assert any("# changed" in e["source"] for e in refreshed[0])
