from backend.retrieval import (
    anchor_named_symbols,
    answer_focus_warning,
    check_citations,
    generation_context,
)


def test_citations_do_not_validate_a_separate_reference_list():
    result = check_citations("Claim [1].\n\nReferences:\n[1] source.py:10", 1)
    assert result["reference_section"] is True
    assert result["entailment_checked"] is False


def test_answer_is_scoped_to_the_named_symbol_when_the_claim_omits_it():
    question = "In BaseModel.model_dump(), which serializer method returns the dictionary?"
    answer = anchor_named_symbols(
        question, "__pydantic_serializer__.to_python() produces the returned dictionary [1]."
    )
    assert "BaseModel.model_dump" in answer
    assert answer_focus_warning(question, answer) is None


def test_answer_is_not_relabelled_when_it_names_a_similar_wrong_method():
    question = "In BaseModel.model_dump(), which method produces the returned dictionary?"
    answer = "BaseModel.model_dump_json() returns a JSON string [1]."
    anchored = anchor_named_symbols(question, answer)
    assert anchored == answer
    assert answer_focus_warning(question, anchored)


def test_multistage_generation_uses_a_bounded_front_page(monkeypatch):
    evidence = [
        {"id": str(index), "qualified": f"pkg.fn_{index}", "citation_number": index + 1}
        for index in range(8)
    ]
    monkeypatch.setattr(
        "backend.retrieval.db.symbols_by_ids",
        lambda _repo_id, ids: [
            {"id": item_id, "path": "pkg.py", "source": "x" * 3000} for item_id in ids
        ],
    )

    context = generation_context(
        "repo",
        "Trace how the first step happens and what follows during validation, then explain the result.",
        evidence,
    )

    assert 1 <= len(context) <= 6
    assert [item["citation_number"] for item in context] == list(range(1, len(context) + 1))
    assert sum(len(item["source"]) for item in context) <= 12_000
