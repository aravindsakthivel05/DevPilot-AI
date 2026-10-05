from backend.rag.behavior import behavior_table
from backend.rag.obligations import checklist


def record(source, start=40):
    return {"path": "sample.py", "source": source, "start_line": start}


def test_negated_nested_branch_and_else_keep_original_coordinates():
    item = record(
        "def f(x):\n    if x:\n        if not x.ready:\n            return 1\n    else:\n        return 2\n    return 3"
    )
    rows = behavior_table(item)
    assert rows[0]["start_line"] == 43
    assert [g["expression"] for g in rows[0]["guards"]] == ["x", "not x.ready"]
    assert rows[1]["guards"][0]["branch"] == "if_false"
    assert rows[2]["guards"] == []  # Not an assertion that this return is reachable.


def test_missing_outer_guard_never_emits_effect_as_unconditional():
    item = record("def f(x):\n    if x:\n        return 1")
    visible = {**item, "source": "def f(x):\n        return 1", "source_line_numbers": [40, 42]}
    assert behavior_table(item, visible) == []


def test_exception_finally_and_nested_definition_have_separate_scopes():
    item = record(
        "def f():\n    try:\n        run()\n    except ValueError:\n        return None\n    finally:\n        close()\n    def nested():\n        return 2"
    )
    rows = behavior_table(item)
    assert rows[1]["guards"][0]["branch"] == "except"
    assert rows[1]["guards"][0]["expression"] == "ValueError"
    assert rows[2]["guards"][0] == {
        "branch": "finally",
        "expression": "on leaving try",
        "start_line": 45,
        "end_line": 45,
    }
    assert rows[3]["scope"] == "f.nested"
    assert rows[3]["guards"] == []


def test_unsupported_match_and_language_do_not_create_unguarded_rows():
    assert (
        behavior_table(record("def f(x):\n    match x:\n        case 1:\n            return True"))
        == []
    )
    assert behavior_table({"path": "a.cpp", "source": "return false;"}) == []


def test_checklist_separates_source_identity_from_semantic_coverage():
    rows = checklist(
        "Compare Left.run versus Right.run and their return values", [{"qualified": "pkg.Left.run"}]
    )
    assert rows[0]["missing_named_definitions"] == ["right.run"]
    assert "conditions_and_alternatives" in rows[0]["inspect"]
    assert rows[0]["semantic_coverage"] == "unverified"


def test_priority_selects_numeric_exception_branch_before_setup_assignments():
    item = record(
        "def f(cur, key):\n    setup = 1\n    other = 2\n    try:\n        cur = cur[key]\n    except TypeError:\n        key = int(key)\n        cur = cur[key]\n    return cur"
    )
    rows = behavior_table(item, limit=2, question="How is a numeric index handled?")
    assert any(row["statement"] == "key = int(key)" for row in rows)
    assert not any(row["statement"] == "setup = 1" for row in rows)


def test_else_header_and_all_context_managers_are_required():
    item = record("def f(x):\n    if x:\n        return 1\n    else:\n        return 2")
    visible = {
        **item,
        "source": "def f(x):\n    if x:\n        return 1\n        return 2",
        "source_line_numbers": [40, 41, 42, 44],
    }
    assert [row["statement"] for row in behavior_table(item, visible)] == ["return 1"]
    item = record("def f():\n    with first(), second():\n        return 1")
    assert [g["expression"] for g in behavior_table(item)[0]["guards"]] == ["first()", "second()"]
