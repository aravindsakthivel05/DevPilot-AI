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
