"""Acceptance regressions from failed public-repository evaluations."""

import pytest

from backend.languages.registry import analyze_repository, detect_language


def test_repeated_unnamed_parameters_have_unique_ids_and_parents():
    result = analyze_repository(
        "isolated",
        {
            "hints.rs": "pub fn suggest<T>(_: &str, _: T) -> bool { true }",
            "reader.hpp": "struct Reader { void on_text(const char*, const char*) {} };",
        },
    )
    assert not result.errors
    assert len({s["id"] for s in result.symbols}) == len(result.symbols)
    for path in ("hints.rs", "reader.hpp"):
        params = [s for s in result.symbols if s["path"] == path and s["kind"] == "parameter"]
        assert len(params) == 2
        assert params[0]["parent_id"] == params[1]["parent_id"]
        assert params[0]["id"] != params[1]["id"]


def test_cxx_header_detection_ignores_comment_and_literal_examples():
    assert (
        detect_language("reader.h", "namespace io { template<class T> T read(T x) { return x; } }")
        == "cpp"
    )
    assert (
        detect_language("reader.h", '// namespace io {}\nconst char *label = "std::vector";') == "c"
    )
    result = analyze_repository(
        "isolated", {"reader.h": "namespace io { template<class T> T read(T x) { return x; } }"}
    )
    assert not result.errors
    assert next(s for s in result.symbols if s["name"] == "read")["language"] == "cpp"


def test_go_explicit_receiver_calls_resolve_but_dynamic_receivers_do_not():
    result = analyze_repository(
        "isolated",
        {
            "context.go": "package demo\ntype Context struct{}\nfunc (c *Context) Bind() {}\nfunc (c *Context) JSON(client any) { c.Bind(); client.Bind() }"
        },
    )
    names = {s["id"]: s["name"] for s in result.symbols}
    calls = [e for e in result.relationships if e["kind"] == "calls"]
    assert [(names[e["source"]], names[e["target"]]) for e in calls] == [("JSON", "Bind")]
    assert any(u["label"] == "client.Bind" for u in result.unresolved)


def test_test_project_names_are_excluded_from_implementation_evidence():
    from backend.test_links import is_test_path

    assert is_test_path("src/Validators.Tests/CascadeTester.cs")
    assert is_test_path("src/Validators.Tests.Benchmarks/Runner.cs")
    assert not is_test_path("src/Validators/PropertyRule.cs")


def test_query_identifiers_and_word_stems_preserve_searchable_terms():
    from backend.question_analysis import symbol_references
    from backend.retrieval import tokens

    assert "shouldbindjson" in symbol_references("How does ShouldBindJSON work?")
    assert "my_func" in symbol_references("Explain my_func")
    assert tokens("binding stopping errors") == ["bind", "stop", "error"]


def test_macro_context_keeps_guard_alternatives_and_real_line_numbers():
    source = "#ifndef FAIL\n#if EXCEPTIONS\n#define FAIL(x) throw x\n#else\n#define FAIL(x) abort()\n#endif\n#endif\n"
    result = analyze_repository("isolated", {"error.hpp": source})
    macros = [s for s in result.symbols if s["kind"] == "macro"]
    assert len(macros) == 2
    assert len({s["id"] for s in macros}) == 2
    for macro in macros:
        assert "#ifndef FAIL" in macro["source"]
        assert "throw x" in macro["source"] and "abort()" in macro["source"]
        assert (
            macro["source"].splitlines()
            == source.splitlines()[macro["start_line"] - 1 : macro["end_line"]]
        )


def test_adjacent_documentation_is_searchable_without_changing_code_coordinates():
    result = analyze_repository(
        "isolated",
        {
            "value.rs": "/// Return a fallible value.\n/// A mismatch returns an error.\npub fn try_get() -> bool { true }"
        },
    )
    fn = next(s for s in result.symbols if s["name"] == "try_get")
    assert "fallible" in fn["docstring"] and "mismatch" in fn["docstring"]
    assert fn["start_line"] == 3
    assert fn["source"].startswith("pub fn")


def test_nomic_query_and_document_prefixes_are_distinct(monkeypatch):
    from backend import providers

    monkeypatch.setenv("DEVPILOT_EMBEDDING_MODEL", "nomic-embed-text:latest")
    received = []

    def request(endpoint, payload):
        received.append(payload["input"])
        return {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}

    monkeypatch.setattr(providers, "request", request)
    providers.embed(["binding"], purpose="query")
    providers.embed(["binding"], purpose="document")
    assert received == [["search_query: binding"], ["search_document: binding"]]


def test_partial_audit_retains_supported_claim_in_same_aspect(monkeypatch):
    import json

    from backend.claim_audit import audit

    monkeypatch.setenv("DEVPILOT_VERIFY_CLAIMS", "1")
    claims = [
        {"aspect_id": 1, "status": "supported", "text": text, "citations": []}
        for text in ("The value is returned.", "The helper always retries.")
    ]

    def request(*args):
        decisions = [
            {"claim_index": i, "verdict": verdict, "reason": "review"}
            for i, verdict in enumerate(("supported", "uncertain"))
        ]
        return {"choices": [{"message": {"content": json.dumps({"decisions": decisions})}}]}

    revised, _, _ = audit(claims, ["value"], [], request, 8192)
    assert revised[0] == claims[0]
    assert revised[1]["status"] == "insufficient_evidence"


def test_baseline_failure_comparison_does_not_prove_zero_total_failures():
    from backend.rag.support_checks import support_warning

    sources = [
        {"lines": [{"text": "if (context.Failures.Count <= totalFailures) RunDependent();"}]}
    ]
    assert support_warning({"text": "Dependent rules run when there are no failures."}, sources)
    assert (
        support_warning({"text": "Dependent rules run when there are no new failures."}, sources)
        is None
    )


def test_invalid_claim_does_not_discard_an_individually_valid_claim(monkeypatch):
    import json

    from backend import providers

    claims = [
        {
            "text": "get_value returns the stored value.",
            "aspect_id": 1,
            "status": "supported",
            "citations": [{"source_id": 1, "start_line": 1, "end_line": 1}],
        },
        {
            "text": "get_value returns a retry count.",
            "aspect_id": 1,
            "status": "supported",
            "citations": [{"source_id": 1, "start_line": 2, "end_line": 3}],
        },
    ]

    def request(*args):
        return {"choices": [{"message": {"content": json.dumps({"claims": claims})}}]}

    monkeypatch.setattr(providers, "request", request)
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    text, _, metrics = providers.generate(
        "What does get_value return?",
        [
            {
                "path": "value.py",
                "qualified": "value.get_value",
                "start_line": 1,
                "source": "def get_value(): return stored_value",
            }
        ],
    )
    assert "stored value" in text
    assert "retry count" not in text
    assert metrics["aspect_statuses"][0]["status"] == "partial"
    assert len(metrics["claim_validation_failures"]) == 1
    assert metrics["draft_claims"][1]["text"] == "get_value returns a retry count."


def test_rebuild_reuses_only_unchanged_symbol_vectors(repo):
    from backend import db
    from backend.indexing import rebuild

    rid = repo["id"]
    original = next(s for s in db.symbols(rid) if s["kind"] == "function")
    with db.connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)",
            (original["id"], "fixture", "[1.0,0.0]", "fixture-revision"),
        )
    rebuild(rid)
    with db.connection() as connection:
        assert (
            connection.execute(
                "SELECT vector FROM embeddings WHERE symbol_id=?", (original["id"],)
            ).fetchone()[0]
            == "[1.0,0.0]"
        )
        row = connection.execute(
            "SELECT content FROM files WHERE repo_id=? AND path=?", (rid, original["path"])
        ).fetchone()
        altered = row[0].replace(
            original["source"], original["source"] + "\n    changed = True\n", 1
        )
        assert altered != row[0]
        connection.execute(
            "UPDATE files SET content=? WHERE repo_id=? AND path=?",
            (altered, rid, original["path"]),
        )
    rebuild(rid)
    with db.connection() as connection:
        assert (
            connection.execute(
                "SELECT vector FROM embeddings WHERE symbol_id=?", (original["id"],)
            ).fetchone()
            is None
        )


def test_bounded_source_reads_follow_call_wrappers_and_rust_generics(repo):
    from backend import db
    from backend.rag.investigation import recover

    rid = repo["id"]
    result = analyze_repository(
        rid,
        {
            "helpers.js": "function transformData(x) { return x; }\nfunction dispatch(x) { return transformData.call(x); }",
            "helpers.rs": "fn try_get<T>(x:T)->T { x }\nfn lookup<T>(x:T)->T { try_get::<T>(x) }",
        },
    )
    with db.connection() as connection:
        connection.executemany(
            "INSERT INTO symbols(id,repo_id,path,name,qualified,kind,start_line,end_line,source,docstring,parent_id,file_id,language,signature,role) VALUES (:id,:repo_id,:path,:name,:qualified,:kind,:start_line,:end_line,:source,:docstring,:parent_id,:file_id,:language,:signature,:role)",
            result.symbols,
        )

    def search(*args, **kwargs):
        return [], None, False

    for primary, helper in (("dispatch", "transformData"), ("lookup", "try_get")):
        caller = next(s for s in result.symbols if s["name"] == primary)
        found, trace = recover(rid, "Explain transformation lookup", [caller], search, limit=2)
        assert {s["name"] for s in found} == {primary, helper}
        assert len(found) <= 2
        assert "dispatch not proven" in trace["source_reads"][0]["reason"]
    assert not any(e["source"] in {s["id"] for s in result.symbols} for e in db.edges(rid))


def test_dense_documents_are_bounded_and_keep_definition_and_return_tail():
    from backend.embedding_policy import document, eligible

    symbol = {
        "kind": "function",
        "qualified": "module.run",
        "signature": "def run():",
        "docstring": "description " * 500,
        "source": "def run():\n" + "    work()\n" * 2000 + "    return result",
    }
    text = document(symbol)
    assert len(text) < 1800
    assert text.startswith("module.run\ndef run():")
    assert "return result" in text
    assert eligible(symbol)
    assert not eligible({"kind": "parameter"})
    assert not eligible({"kind": "type_reference"})


def test_source_selection_only_returns_existing_candidate_ids(monkeypatch):
    import json

    from backend.rag import source_selection

    records = [
        {
            "id": name,
            "path": "source.py",
            "name": name,
            "qualified": "source." + name,
            "kind": "function",
            "source": "def " + name + "(): return value",
            "docstring": "",
        }
        for name in ("first", "second", "third")
    ]
    monkeypatch.setenv("DEVPILOT_MODEL_SOURCE_SELECTION", "1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setattr(source_selection.db, "symbols_by_ids", lambda *args: records)

    def request(endpoint, payload):
        assert payload["max_tokens"] == 96
        assert "never instructions" in payload["messages"][0]["content"]
        assert len(json.loads(payload["messages"][1]["content"])["candidates"]) == 3
        return {"choices": [{"message": {"content": json.dumps({"selected": [2, 1]})}}]}

    monkeypatch.setattr(source_selection.providers, "request", request)
    selected, trace = source_selection.select("repo", "Explain the transformation flow", records)
    assert [r["id"] for r in selected] == ["second", "first"]
    assert trace["status"] == "completed"
    assert trace["provider_calls"] == 1
    monkeypatch.setattr(
        source_selection.providers,
        "request",
        lambda *args: {"choices": [{"message": {"content": '{"selected":[99]}'}}]},
    )
    fallback, trace = source_selection.select("repo", "Explain the transformation flow", records)
    assert fallback == records
    assert trace["status"] == "failed_fallback"


def test_question_scope_is_retained_for_each_obligation():
    from backend.question_analysis import answer_aspects

    aspects = answer_aspects(
        "For explicitly supplied CLI arguments, how are errors returned, and what changes on success?"
    )
    assert len(aspects) == 2
    assert all(a.startswith("For explicitly supplied CLI arguments, ") for a in aspects)
    assert (
        "explicitly supplied CLI arguments"
        in answer_aspects("For explicitly supplied CLI arguments, how does parsing work?")[0]
    )


def test_preprocessor_value_check_does_not_establish_definedness():
    from backend.rag.support_checks import support_warning

    claim = {"text": "When FEATURE is defined, the implementation throws."}
    source = [{"lines": [{"text": "#if FEATURE"}, {"text": "throw error;"}]}]
    assert support_warning(claim, source)
    assert support_warning({"text": "When FEATURE is nonzero, it throws."}, source) is None
    source[0]["lines"][0]["text"] = "#ifdef FEATURE"
    assert support_warning(claim, source) is None


def test_source_selection_network_failure_preserves_candidates(monkeypatch):
    import httpx

    from backend.rag import source_selection

    records = [
        {
            "id": str(i),
            "path": "source.py",
            "kind": "function",
            "qualified": f"source.fn{i}",
            "source": "return value",
            "docstring": "",
        }
        for i in range(3)
    ]
    monkeypatch.setenv("DEVPILOT_MODEL_SOURCE_SELECTION", "1")
    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_LLM_BASE_URL", "http://fixture.invalid/v1")
    monkeypatch.setattr(source_selection.db, "symbols_by_ids", lambda *args: records)

    def request(*args):
        raise httpx.ReadTimeout("Local provider timed out")

    monkeypatch.setattr(source_selection.providers, "request", request)
    result, trace = source_selection.select("repo", "Explain transformation", records)
    assert result == records
    assert trace["status"] == "failed_fallback"
    assert trace["error_type"] == "ReadTimeout"


def test_signature_change_invalidates_retained_embeddings(repo):
    from backend import db
    from backend.indexing import rebuild

    rid = repo["id"]
    symbol = next(s for s in db.symbols(rid) if s["kind"] == "function")
    with db.connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)",
            (symbol["id"], "fixture", "[1.0,0.0]", "fixture-revision"),
        )
        connection.execute(
            "UPDATE symbols SET signature=? WHERE id=?", ("stale-parser-signature", symbol["id"])
        )
    rebuild(rid)
    with db.connection() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM embeddings WHERE symbol_id=?", (symbol["id"],)
            ).fetchone()
            is None
        )


def test_readiness_rejects_vectors_from_a_different_model(repo, monkeypatch):
    from backend import db, providers
    from backend.embedding_policy import eligible
    from backend.readiness import index_status

    monkeypatch.setenv("DEVPILOT_EMBEDDING_MODEL", "current-model")
    with db.connection() as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)",
            [
                (s["id"], "previous-model", "[1.0,0.0]", providers.embedding_signature())
                for s in db.symbols(repo["id"])
                if eligible(s)
            ],
        )
    status = index_status(repo["id"])
    assert status["embedding_eligible_symbols"] > 0
    assert status["embedded_symbols"] == 0
    assert not status["semantic_ready"]


def test_coordinated_subjects_receive_separate_answer_obligations():
    from backend.question_analysis import answer_aspects

    aspects = answer_aspects(
        "How do skipped hooks, ordering options and synchronous versus asynchronous hooks change the processing chain?"
    )
    assert len(aspects) == 3
    assert all(a.endswith("change the processing chain") for a in aspects)
    assert "skipped hooks" in aspects[0]
    assert "ordering options" in aspects[1]
    assert "synchronous versus asynchronous hooks" in aspects[2]
    scoped = answer_aspects(
        "In property validation, how do rule conditions, component conditions, cancellation and dependent rules control execution?"
    )
    assert len(scoped) == 4
    assert all(a.startswith("In property validation, ") for a in scoped)


def test_elif_macro_value_is_not_a_definedness_test():
    from backend.rag.support_checks import support_warning

    source = [
        {
            "lines": [
                {"text": "#ifdef CUSTOM_THROW"},
                {"text": "#elif FEATURE"},
                {"text": "throw error;"},
            ]
        }
    ]
    assert support_warning({"text": "When FEATURE is defined, it throws."}, source)
    assert support_warning({"text": "When CUSTOM_THROW is defined, it is used."}, source) is None


def test_coordinated_objects_retain_the_shared_subject_and_scope():
    from backend.question_analysis import answer_aspects

    parts = answer_aspects(
        "In async validation, how do rule conditions control property access, cancellation and dependent rules?"
    )
    assert len(parts) == 3
    assert all(p.startswith("In async validation, how do rule conditions control ") for p in parts)
    assert parts[2].endswith("dependent rules")


def test_claim_repair_requires_rejections_not_just_a_missing_answer(monkeypatch):
    from backend.rag.claim_repair import feedback

    monkeypatch.setenv("DEVPILOT_REPAIR_REJECTED_CLAIMS", "1")
    metrics = {
        "claims": [
            {"status": "supported", "aspect_id": 1},
            {"status": "insufficient_evidence", "aspect_id": 1},
        ]
    }
    assert feedback(metrics) is None
    metrics["claim_audit"] = {
        "status": "completed",
        "decisions": [{"verdict": "uncertain", "reason": "The type contrast is incorrect."}],
    }
    assert "The type contrast is incorrect." in feedback(metrics)
    metrics["claims"] = [{"status": "insufficient_evidence", "aspect_id": 1}]
    assert feedback(metrics) is None


@pytest.mark.parametrize("outcome", ["timeout", "regression", "improvement"])
def test_bounded_repair_selects_supported_coverage_and_preserves_fallback(
    repo, monkeypatch, outcome
):
    import httpx

    from backend.rag import pipeline

    monkeypatch.setenv("DEVPILOT_LLM_MODEL", "fixture")
    monkeypatch.setenv("DEVPILOT_REPAIR_REJECTED_CLAIMS", "1")
    calls = []

    def generate(question, context, citation_feedback=None):
        calls.append(citation_feedback)
        if len(calls) == 2 and outcome == "timeout":
            raise httpx.ReadTimeout("Correction request timed out")
        number = context[0]["citation_number"]
        claims = [
            {
                "text": "It computes the quote.",
                "status": "supported",
                "aspect_id": 1,
                "citations": [
                    {
                        "source_id": number,
                        "start_line": context[0]["start_line"],
                        "end_line": context[0]["start_line"],
                    }
                ],
            },
            {
                "text": "Further details are missing.",
                "status": "insufficient_evidence",
                "aspect_id": 1,
                "citations": [],
            },
        ]
        if len(calls) == 2:
            if outcome == "improvement":
                return (
                    f"It computes the quote [{number}].",
                    {},
                    {
                        "claims": claims[:1],
                        "aspect_statuses": [
                            {"aspect_id": 1, "question": question, "status": "supported"}
                        ],
                    },
                )
            return (
                "Aspect 1: Further details are missing.",
                {},
                {
                    "claims": claims[1:],
                    "aspect_statuses": [
                        {"aspect_id": 1, "question": question, "status": "insufficient_evidence"}
                    ],
                },
            )
        return (
            f"It computes the quote [{number}].\n\nAspect 1: Further details are missing.",
            {},
            {
                "claims": claims,
                "aspect_statuses": [{"aspect_id": 1, "question": question, "status": "partial"}],
                "claim_audit": {
                    "status": "completed",
                    "decisions": [
                        {"verdict": "uncertain", "reason": "A condition is not established."}
                    ],
                },
            },
        )

    monkeypatch.setattr(pipeline, "generate", generate)
    result = pipeline.answer(repo["id"], "How does calculate_quote compute a quote?")
    assert len(calls) == 2 and calls[1]
    assert result["generated"]
    assert result["partial"] is (outcome != "improvement")
    assert "It computes the quote" in result["answer"]
    assert result["generation_diagnostics"]["selected_attempt"] == (
        2 if outcome == "improvement" else 1
    )
    assert len(result["claims"]) == (1 if outcome == "improvement" else 2)
    if outcome == "timeout":
        assert result["generation_diagnostics"]["attempts"][-1]["outcome"] == "provider_failure"


def test_named_configuration_identifier_requires_its_actual_source():
    from backend.rag.support_checks import support_warning

    sources = [
        {
            "qualified": "Options.Cascade",
            "lines": [{"text": "Configurable(ruleBuilder).CascadeMode = cascadeMode;"}],
        }
    ]
    assert support_warning({"text": "ClassLevelCascadeMode is set using Cascade."}, sources)
    assert support_warning({"text": "CascadeMode is set using Cascade."}, sources) is None
    assert support_warning({"text": "This is a JavaScript implementation."}, sources) is None


def test_getter_cache_guard_distinguishes_capture_from_per_read_local():
    from backend.rag.support_checks import support_warning

    def source(code):
        return [{"lines": [{"text": code}]}]

    claim = {"text": "The error is not reused; a new instance is created on each read."}
    captured = "let error; return {get error() { if (!error) { error = new Err(); issues = undefined; } return error; }};"
    assert support_warning(claim, source(captured))
    assert (
        support_warning(
            {"text": "The error is cached and reused on later reads."}, source(captured)
        )
        is None
    )
    local = "get error() { let error; if (!error) { error = new Err(); } return error; }"
    assert support_warning(claim, source(local)) is None
    reset = "let error; return {get error() { if (!error) { error = new Err(); } error = new Err(); return error; }};"
    assert support_warning(claim, source(reset)) is None
    cleared = "let error; return {get error() { if (!error) { error = new Err(); error = undefined; } return error; }};"
    assert support_warning(claim, source(cleared)) is None


def test_stop_setting_does_not_replace_failure_increase_guard():
    from backend.rag.support_checks import support_warning

    sources = [
        {
            "lines": [
                {
                    "text": "if (ClassLevelCascadeMode == CascadeMode.Stop && result.Errors.Count > totalFailures) break;"
                }
            ]
        }
    ]
    assert support_warning(
        {"text": "Stopping occurs when ClassLevelCascadeMode is CascadeMode.Stop."}, sources
    )
    assert (
        support_warning(
            {
                "text": "Stopping occurs when failures increase and ClassLevelCascadeMode is CascadeMode.Stop."
            },
            sources,
        )
        is None
    )
    assert (
        support_warning(
            {"text": "ClassLevelCascadeMode is configured as CascadeMode.Stop."}, sources
        )
        is None
    )
    assert (
        support_warning(
            {"text": "NaN is spelled nan."}, [{"lines": [{"text": 'auto value = "nan";'}]}]
        )
        is None
    )
