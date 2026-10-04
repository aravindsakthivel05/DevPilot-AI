"""Java symbols and conservative same-class call links."""

from backend.ingestion import collect_files
from backend.java_analysis import analyse_java


def test_java_package_types_methods_and_calls():
    symbols, edges, errors, _ = analyse_java(
        "r",
        {
            "src/main/java/demo/Quote.java": (
                "package demo; class Quote { int amount() { return base(); } int base() { return 4; } }"
            )
        },
    )
    names = {symbol["id"]: symbol["qualified"] for symbol in symbols}
    assert not errors
    assert {"demo.Quote", "demo.Quote.amount", "demo.Quote.base"} <= set(names.values())
    assert ("demo.Quote.amount", "demo.Quote.base", "calls") in {
        (names[edge["source"]], names[edge["target"]], edge["kind"]) for edge in edges
    }


def test_large_java_source_remains_indexable(tmp_path):
    path = tmp_path / "Large.java"
    path.write_text("package demo;\n" + "// padding\n" * 35000 + "class Large { void run() {} }\n")
    files, skipped = collect_files(tmp_path)
    assert "Large.java" in files
    assert skipped == 0
    symbols, _, errors, _ = analyse_java("r", files)
    assert not errors
    assert any(symbol["qualified"] == "demo.Large.run" for symbol in symbols)


def test_imported_static_call_and_declared_receiver_are_conservative():
    symbols, edges, _, _ = analyse_java(
        "r",
        {
            "Helper.java": "package helper; class Helper { static void work() {} }",
            "Service.java": "package app; import helper.Helper; class Service { Helper delegate; void invoke() { Helper.work(); delegate.work(); } }",
        },
    )
    names = {s["id"]: s["qualified"] for s in symbols}
    calls = [
        e for e in edges if e["kind"] == "calls" and names[e["source"]] == "app.Service.invoke"
    ]
    assert len(calls) == 2
    assert all(names[e["target"]] == "helper.Helper.work" for e in calls)
    assert {e["confidence"] for e in calls} == {"static", "declared_type"}


def test_overloaded_parent_call_does_not_fall_back_to_grandparent():
    symbols, edges, _, unresolved = analyse_java(
        "r",
        {
            "Example.java": "class Grand { void ping() {} } class Base extends Grand { void ping() {} void ping(int x) {} } class Child extends Base { void invoke() { super.ping(); } }"
        },
    )
    names = {s["id"]: s["qualified"] for s in symbols}
    assert not any(e["kind"] == "calls" and names[e["source"]] == "Child.invoke" for e in edges)
    assert any(u["label"] == "super.ping" for u in unresolved)
