"""Behavioral regressions for concrete evidence/planning failures, without a live model."""

import json

import pytest

from backend import db, providers
from backend.agent_investigation import investigate
from backend.analysis import analyse
from backend.evidence import excerpt, identity_supported
from backend.java_analysis import analyse_java
from backend.question_analysis import answer_aspects
from backend.retrieval import answer, generation_context, is_multi_stage, retrieve


def _response(monkeypatch, claims):
    monkeypatch.setattr(
        providers,
        "request",
        lambda *_args: {"choices": [{"message": {"content": json.dumps({"claims": claims})}}]},
    )


def _claim(text, aspect=1, status="supported", citations=None):
    return {
        "text": text,
        "aspect_id": aspect,
        "status": status,
        "citations": citations
        if citations is not None
        else [{"source_id": 1, "start_line": 40, "end_line": 42}],
    }


def _raw_queryset():
    return {
        "path": "query.py",
        "start_line": 40,
        "end_line": 42,
        "qualified": "django.db.models.query.RawQuerySet._fetch_all",
        "source": "def _fetch_all(self):\n    if self._result_cache is None:\n        self._result_cache = list(self.iterator())",
    }


def test_long_wrapper_excerpt_keeps_returned_callee_and_forwarded_keyword():
    signature = "\n".join(f"    argument_{i}: bool = False," for i in range(24))
    forwarded = "\n".join(f"        argument_{i}=argument_{i}," for i in range(24))
    source = f'def export(\n{signature}\n):\n    """Return a formatted dictionary with many options."""\n    return self.serializer.encode(\n{forwarded}\n    )'
    result = excerpt(
        {"source": source, "path": "export.py", "start_line": 100},
        "Which method returns the dictionary and how is argument_23 forwarded?",
        180,
    )
    assert "return self.serializer.encode(" in result["source"]
    assert "argument_23=argument_23" in result["source"]
    for n, text in zip(result["source_line_numbers"], result["source"].splitlines()):
        assert source.splitlines()[n - 100] == text


def test_instance_attribute_call_can_be_named_without_self_prefix():
    item = {
        "path": "model.py",
        "qualified": "Model.export",
        "source": "return self.serializer.encode(value)",
    }
    assert identity_supported("serializer.encode", [item])
    assert not identity_supported("other_serializer.encode", [item])
    assert not identity_supported("Model.encode", [item])


def test_claim_cannot_attribute_raw_queryset_source_to_queryset(monkeypatch):
    _response(
        monkeypatch, [_claim("QuerySet._fetch_all fills _result_cache with list(self.iterator()).")]
    )
    with pytest.raises(providers.AnswerValidationError, match="Named symbol QuerySet._fetch_all"):
        providers.generate("Where does QuerySet._fetch_all populate the cache?", [_raw_queryset()])


def test_valid_owner_and_original_file_lines_are_preserved(monkeypatch):
    _response(
        monkeypatch,
        [_claim("RawQuerySet._fetch_all fills _result_cache with list(self.iterator()).")],
    )
    text, _, metrics = providers.generate(
        "Where does RawQuerySet._fetch_all populate the cache?", [_raw_queryset()]
    )
    assert "[1]" in text
    assert metrics["supporting_lines"][0]["start_line"] == 40
    assert metrics["supporting_lines"][0]["path"] == "query.py"
    assert metrics["entailment_checked"] is False


def test_a_citation_cannot_bridge_omitted_excerpt_lines(monkeypatch):
    evidence = {
        **_raw_queryset(),
        "source": "def _fetch_all(self):\n    self._result_cache = []",
        "source_line_numbers": [40, 90],
    }
    _response(
        monkeypatch,
        [
            _claim(
                "RawQuerySet._fetch_all fills the cache.",
                citations=[{"source_id": 1, "start_line": 40, "end_line": 42}],
            )
        ],
    )
    with pytest.raises(providers.AnswerValidationError, match="not present"):
        providers.generate("How does RawQuerySet._fetch_all fill the cache?", [evidence])


def test_partial_answer_does_not_force_an_unsupported_claim(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    _response(
        monkeypatch,
        [
            _claim(
                "The snapshot does not establish the price.",
                status="insufficient_evidence",
                citations=[],
            ),
            _claim(
                "The running database value cannot be determined from this source.",
                aspect=2,
                status="insufficient_evidence",
                citations=[],
            ),
        ],
    )
    result = answer(repo["id"], "What is the price, and where is its database value?")
    assert result["generated"] is True
    assert result["abstained"] is True
    assert not result["citation_check"]["uncited_paragraphs"]
    assert all(s["status"] == "insufficient_evidence" for s in result["aspect_statuses"])


@pytest.mark.parametrize(
    "question,minimum",
    [
        (
            "How does FastAPI.openapi() obtain the OpenAPI schema for the app and where are route schemas assembled?",
            2,
        ),
        (
            "In QuerySet._fetch_all(), how does it fetch and cache results and hand off SQL execution?",
            3,
        ),
        (
            "In Module._call_impl(), how does it run forward pre-hooks, call forward(), and run forward hooks?",
            3,
        ),
    ],
)
def test_short_compound_questions_are_investigated(question, minimum):
    assert is_multi_stage(question)
    assert len(answer_aspects(question)) >= minimum


def test_deep_runs_focused_passes_for_short_compound_question(client, repo):
    result = investigate(
        repo["id"], "How does calculate_quote fetch prices and return the quote?", use_model=False
    )
    assert result["workflow"]["retrieval_passes"] > 1
    assert result["workflow"]["investigation_rounds"] <= 2
    assert all(not c["factual_support_verified"] for c in result["workflow"]["candidate_coverage"])


def test_java_super_resolves_parent_not_child():
    symbols, edges, _, _ = analyse_java(
        "r",
        {
            "Example.java": "package sample; class Base { void ping() {} } class Child extends Base { void ping() {} void invoke() { super.ping(); } }"
        },
    )
    names = {s["id"]: s["qualified"] for s in symbols}
    calls = {(names[e["source"]], names[e["target"]]) for e in edges if e["kind"] == "calls"}
    assert ("sample.Child.invoke", "sample.Base.ping") in calls
    assert ("sample.Child.invoke", "sample.Child.ping") not in calls


def test_unknown_java_super_is_not_invented():
    _, edges, _, unresolved = analyse_java(
        "r",
        {
            "Child.java": "class Child extends External { void ping() {} void invoke() { super.ping(); } }"
        },
    )
    assert not any(e["kind"] == "calls" for e in edges)
    assert any(u["label"] == "super.ping" for u in unresolved)


def test_document_tail_is_indexed_with_true_coordinates():
    source = "\n".join(["ordinary text"] * 250 + ["special_feature_switch = enabled"])
    symbols, _, _, _ = analyse("r", {"config.toml": source})
    matching = [s for s in symbols if "special_feature_switch" in s["source"]]
    assert matching
    assert all(
        source.splitlines()[s["start_line"] - 1 : s["end_line"]] == s["source"].splitlines()
        for s in matching
    )


def test_excerpt_includes_relevant_late_behavior():
    record = {
        "qualified": "pkg.run",
        "source": "def run():\n"
        + "\n".join(["    ordinary = 1"] * 400)
        + "\n    forward_hooks(result)",
        "start_line": 100,
    }
    result = excerpt(record, "Where are forward_hooks called?", 90)
    assert "forward_hooks(result)" in result["source"]
    assert result["source_line_numbers"][-1] == 501
    assert result["truncated"] is True


def test_generation_keeps_named_entry_point_and_helper(client, repo):
    evidence, _, _ = retrieve(repo["id"], "parcel.pricing.calculate_quote and base_rate", limit=8)
    context = generation_context(
        repo["id"], "How does parcel.pricing.calculate_quote call base_rate?", evidence
    )
    names = {s["qualified"] for s in context}
    assert "parcel.pricing.calculate_quote" in names
    assert "parcel.pricing.base_rate" in names


def test_persistent_search_invalidates_on_source_change(client, repo):
    retrieve(repo["id"], "shipping quote")
    with db.connection() as c:
        sid = c.execute(
            "SELECT id FROM symbols WHERE repo_id=? AND name=?", (repo["id"], "base_rate")
        ).fetchone()[0]
        c.execute(
            "UPDATE symbols SET source=? WHERE id=?",
            ("def base_rate():\n    return unique_revision_token", sid),
        )
    evidence, _, _ = retrieve(repo["id"], "unique_revision_token", mode="lexical")
    assert any(e["id"] == sid for e in evidence)


def test_failed_embedding_batch_publishes_no_partial_index(client, repo, monkeypatch):
    monkeypatch.setenv("DEVPILOT_EMBEDDING_MODEL", "fixture")
    symbols = db.symbols(repo["id"])
    symbols = [*symbols, *[{**symbols[0], "id": "extra"} for _ in range(24)]]
    calls = 0

    def embed(texts):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("provider failure")
        return [[1, 0] for _ in texts]

    monkeypatch.setattr(providers, "embed", embed)
    with pytest.raises(ValueError, match="provider failure"):
        providers.index_embeddings(symbols)
    with db.connection() as c:
        assert c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


def test_docstrings_do_not_shift_executable_file_coordinates():
    record = {
        "path": "service.py",
        "source": 'def run():\n    """A documented contract.\n    More text.\n    """\n    return actual_value',
        "start_line": 70,
    }
    item = excerpt(record, "What does run return?", 100)
    assert "documented contract" not in item["source"]
    assert item["source_line_numbers"][-1] == 74


def test_dispatch_alias_is_a_static_relationship():
    symbols, edges, _, _ = analyse(
        "r",
        {
            "service.py": "class Callable:\n    def wrapper(self):\n        return 1\n    __call__ = wrapper\n"
        },
    )
    names = {s["id"]: s["qualified"] for s in symbols}
    assert any(
        e["kind"] == "aliases" and names[e["target"]] == "service.Callable.wrapper" for e in edges
    )


def test_index_readiness_reports_actual_embedding_coverage(client, repo):
    retrieve(repo["id"], "shipping quote")
    status = client.get(f"/api/repositories/{repo['id']}/index-status").json()
    assert status["lexical_ready"] is True
    assert status["semantic_ready"] is False
    assert status["embedded_symbols"] == 0


def test_provider_readiness_without_probe_does_not_call_model(client, monkeypatch):
    monkeypatch.setattr(providers, "request", lambda *_: pytest.fail("probe was not requested"))
    result = client.get("/api/provider-status").json()
    assert result["generation_probe"] == "not_requested"


def test_declared_package_reexports_support_scoped_public_names():
    from backend.namespaces import declared_aliases

    metadata = [
        {
            "id": "module",
            "path": "nn/modules/module.py",
            "qualified": "nn.modules.module",
            "kind": "module",
            "parent_id": None,
        },
        {
            "id": "class",
            "path": "nn/modules/module.py",
            "qualified": "nn.modules.module.Module",
            "kind": "class",
            "parent_id": "module",
        },
        {
            "id": "method",
            "path": "nn/modules/module.py",
            "qualified": "nn.modules.module.Module._call_impl",
            "kind": "method",
            "parent_id": "class",
        },
    ]
    aliases = declared_aliases(
        metadata,
        {
            "nn/modules/__init__.py": 'from .module import Module\n__all__ = ["Module"]',
            "nn/__init__.py": "from torch.nn.modules import *",
        },
        "torch",
    )
    assert "torch.nn.Module" in aliases["class"]
    assert "torch.nn.Module._call_impl" in aliases["method"]
    from backend.evidence import identity_supported

    source = {
        "qualified": metadata[2]["qualified"],
        "source": "def _call_impl(self): pass",
        "path": metadata[2]["path"],
        "public_aliases": aliases["method"],
    }
    assert identity_supported("torch.nn.Module", [source])
    assert not identity_supported("torch.nn.OtherModule", [source])


def test_native_citation_schema_excludes_omitted_file_lines():
    evidence = {
        **_raw_queryset(),
        "citation_number": 4,
        "source": "def _fetch_all(self):\n    return value",
        "source_line_numbers": [40, 90],
    }
    schema = providers.answer_schema(1, [evidence])
    choices = schema["properties"]["claims"]["items"]["properties"]["citations"]["items"]["anyOf"]
    assert [choice["properties"]["source_id"]["enum"] for choice in choices] == [[4], [4]]
    assert [choice["properties"]["start_line"]["enum"] for choice in choices] == [[40], [90]]
