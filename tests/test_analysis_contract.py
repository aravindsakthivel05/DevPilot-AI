"""Behavioural analyser checks including unresolved and shadowed references."""

from backend.analysis import analyse


def named_edges(files):
    symbols, edges, errors, unresolved = analyse("test", files)
    names = {s["id"]: s["qualified"] for s in symbols}
    return {(names[e["source"]], names[e["target"]], e["kind"]) for e in edges}, errors, unresolved


def test_relative_import_and_inheritance():
    edges, errors, _ = named_edges(
        {
            "pkg/__init__.py": "",
            "pkg/base.py": "class Base: pass\n",
            "pkg/child.py": "from .base import Base\nclass Child(Base): pass\n",
        }
    )
    assert not errors
    assert ("pkg.child.Child", "pkg.base.Base", "inherits") in edges


def test_async_and_self_method_calls():
    edges, _, _ = named_edges(
        {
            "worker.py": "class Worker:\n    async def start(self):\n        self.stop()\n    def stop(self):\n        pass\n"
        }
    )
    assert ("worker.Worker.start", "worker.Worker.stop", "calls") in edges


def test_external_reference_stays_unresolved():
    edges, _, unresolved = named_edges({"service.py": "def f(client):\n    client.send()\n"})
    assert not any(e[2] == "calls" for e in edges)
    assert any(u["label"] == "client.send" for u in unresolved)


def test_parameter_shadowing_does_not_create_false_call_edge():
    edges, _, _ = named_edges({"service.py": "def send():\n    pass\ndef run(send):\n    send()\n"})
    assert ("service.run", "service.send", "calls") not in edges


def test_function_local_import_does_not_leak_into_other_function():
    edges, _, _ = named_edges(
        {
            "a.py": "def target(): pass\n",
            "b.py": "def target(): pass\n",
            "service.py": "def first():\n    from a import target\n    target()\ndef second():\n    from b import target\n    target()\n",
        }
    )
    assert ("service.first", "a.target", "calls") in edges
    assert ("service.first", "b.target", "calls") not in edges


def test_decorated_source_locations_include_decorator():
    symbols, _, _, _ = analyse("r", {"a.py": "@decorate\ndef work():\n    return 1\n"})
    fn = next(s for s in symbols if s["name"] == "work")
    assert fn["start_line"] == 1 and fn["end_line"] == 3
    assert fn["source"].startswith("@decorate")
