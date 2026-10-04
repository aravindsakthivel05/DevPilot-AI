"""Real grammar and cross-file resolution fixtures, including ambiguity controls."""

import pytest

from backend.languages.registry import adapters, analyze_repository, detect_language

SAMPLES = {
    "python": ("main.py", "def run(value):\n    return value\n"),
    "java": ("Main.java", "class Main { int run(int value) { return value; } }"),
    "javascript": ("main.js", "export function run(value) { return value; }"),
    "typescript": ("main.ts", "export function run(value: number): number { return value; }"),
    "c": ("main.c", "int run(int value) { return value; }"),
    "cpp": ("main.cpp", "class Main { public: int run(int value) { return value; } };"),
    "go": ("main.go", "package demo\nfunc run(value int) int { return value }"),
    "rust": ("main.rs", "pub fn run(value: i32) -> i32 { value }"),
    "csharp": ("Main.cs", "class Main { int run(int value) { return value; } }"),
}


@pytest.mark.parametrize("language", SAMPLES)
def test_adapter_real_symbols_original_coordinates_and_syntax(language):
    adapter = next(a for a in adapters() if a.language == language)
    path, source = SAMPLES[language]
    result = adapter.analyze("r", {path: source})
    assert not result.errors
    fn = next(s for s in result.symbols if s["name"] == "run")
    assert fn["language"] == language and fn["file_id"] and fn["signature"]
    assert fn["start_line"] >= 1 and fn["end_line"] <= len(source.splitlines())
    assert detect_language(path) == language


@pytest.mark.parametrize("language", SAMPLES)
def test_grammars_report_invalid_source(language):
    adapter = next(a for a in adapters() if a.language == language)
    path, _ = SAMPLES[language]
    assert adapter.analyze("r", {path: "function { ((( ! invalid"}).errors


@pytest.mark.parametrize(
    "files",
    [
        {
            "helper.js": "export function normalize(x) { return x; }",
            "api.js": "import {normalize as clean} from './helper'; export function run(x) { return clean(x); }",
        },
        {
            "helper.ts": "export function normalize(x: number) { return x; }",
            "api.ts": "import {normalize} from './helper'; export function run(x: number) { return normalize(x); }",
        },
        {
            "helper.go": "package demo\nfunc normalize(x int) int { return x }",
            "api.go": "package demo\nfunc run(x int) int { return normalize(x) }",
        },
        {
            "helper.rs": "pub fn normalize(x: i32) -> i32 { x }",
            "lib.rs": "mod helper; use crate::helper::normalize; pub fn run(x: i32) -> i32 { normalize(x) }",
        },
        {
            "Helper.cs": "namespace Demo { class Helper { public static int Normalize(int x) { return x; } } }",
            "Main.cs": "namespace Demo { class Main { int Run(int x) { return Helper.Normalize(x); } } }",
        },
        {
            "helper.h": "int normalize(int x);",
            "api.c": '#include "helper.h"\nint run(int x) { return normalize(x); }',
        },
        {
            "helper.hpp": "int normalize(int x);",
            "api.cpp": '#include "helper.hpp"\nint run(int x) { return normalize(x); }',
        },
    ],
)
def test_real_cross_file_calls(files):
    result = analyze_repository("r", files)
    lookup = {s["id"]: s for s in result.symbols}
    assert not result.errors
    assert any(
        e["kind"] == "calls" and lookup[e["source"]]["path"] != lookup[e["target"]]["path"]
        for e in result.relationships
    )


def test_js_parameter_shadowing_and_dynamic_receiver_are_not_invented():
    result = analyze_repository(
        "r", {"api.js": "function send() {} function run(send, client) { send(); client.send(); }"}
    )
    assert not any(e["kind"] == "calls" for e in result.relationships)
    assert len(result.unresolved) == 2


def test_same_line_overloads_have_distinct_identity_and_stay_ambiguous():
    result = analyze_repository(
        "r", {"A.java": "class A { void ping() {} void ping(int x) {} void run() { ping(); } }"}
    )
    methods = [s for s in result.symbols if s["name"] == "ping"]
    assert len({s["id"] for s in methods}) == 2
    assert not any(e["kind"] == "calls" for e in result.relationships)


def test_comment_imports_and_local_shadowing_do_not_create_calls():
    result = analyze_repository(
        "r",
        {
            "helper.ts": "export function send() {}",
            "api.ts": "// import {send} from './helper';\nfunction run() { send(); }",
        },
    )
    assert not any(e["kind"] in ("calls", "imports") for e in result.relationships)
    result = analyze_repository(
        "r", {"api.js": "function send() {} function run() { const send = client.send; send(); }"}
    )
    assert not any(e["kind"] == "calls" for e in result.relationships)


def test_reassigned_js_function_and_comment_csharp_namespace_stay_unresolved():
    result = analyze_repository(
        "r", {"api.js": "function send() {} send = client.send; function run() { send(); }"}
    )
    assert not any(e["kind"] == "calls" for e in result.relationships)
    result = analyze_repository(
        "r",
        {
            "Helper.cs": "// namespace Fake\nnamespace One { class Helper { public static int Normalize(int x) { return x; } } }",
            "Main.cs": "// namespace Fake\nnamespace Two { class Main { int Run(int x) { return Helper.Normalize(x); } } }",
        },
    )
    assert not any(e["kind"] == "calls" for e in result.relationships)
