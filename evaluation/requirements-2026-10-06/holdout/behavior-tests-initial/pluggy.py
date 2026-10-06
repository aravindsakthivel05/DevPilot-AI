"""Pinned dispatch/history functions with controlled implementation fixtures."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


class HookCallError(Exception):
    pass


def load(path, names):
    tree = ast.parse(Path(path).read_text())
    selected = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert len(selected) == len(names)
    module = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            *selected,
        ],
        type_ignores=[],
    )
    namespace = {"HookCallError": HookCallError, "TYPE_CHECKING": False}
    exec(compile(module, path, "exec"), namespace)
    return namespace


def impl(function, names=()):
    return SimpleNamespace(
        argnames=names, kwargnames=(), function=function, wrapper=False, hookwrapper=False
    )


@pytest.mark.parametrize("firstresult", [False, True])
def test_reverse_order_and_non_none_result_handling(firstresult):
    called = []

    def f(name, value):
        def run():
            called.append(name)
            return value

        return impl(run)

    namespace = load("src/pluggy/_execution.py", {"_multicall"})
    result = namespace["_multicall"](
        "sample", [f("a", 1), f("b", 2), f("c", None)], {}, firstresult
    )
    assert called == (["c", "b"] if firstresult else ["c", "b", "a"])
    assert result == (2 if firstresult else [2, 1])


def test_empty_firstresult_returns_none():
    namespace = load("src/pluggy/_execution.py", {"_multicall"})
    assert namespace["_multicall"]("sample", [impl(lambda: None)], {}, True) is None


def test_missing_required_argument_is_chained():
    namespace = load("src/pluggy/_execution.py", {"_multicall"})
    with pytest.raises(HookCallError, match="required") as caught:
        namespace["_multicall"](
            "sample", [impl(lambda required: required, ("required",))], {}, False
        )
    assert isinstance(caught.value.__cause__, KeyError)


def history_fixture(historic=True):
    events, callback_values = [], []
    methods = [object(), object()]

    def dispatch(name, supplied, kwargs, firstresult):
        events.append((name, supplied, kwargs, firstresult))
        return [10, 20] if len(supplied) > 1 else [30]

    caller = SimpleNamespace(
        name="sample",
        _hookimpls=methods,
        _call_history=[],
        _apply_defaults=lambda kwargs: {"default": 1, **kwargs},
        _verify_all_args_are_provided=lambda kwargs: events.append(("verified", dict(kwargs))),
        _hookexec=dispatch,
        is_historic=lambda: historic,
    )
    return caller, events, callback_values


def test_history_recorded_before_dispatch_and_callback_per_result():
    namespace = load("src/pluggy/_caller.py", {"call_historic"})
    caller, events, values = history_fixture()
    callback = values.append
    assert namespace["call_historic"](caller, callback, {"argument": 2}) is None
    assert caller._call_history == [({"default": 1, "argument": 2}, callback)]
    assert events[0][0] == "verified"
    name, methods, kwargs, first = events[1]
    assert name == "sample" and methods == caller._hookimpls and methods is not caller._hookimpls
    assert kwargs == caller._call_history[0][0] and first is False
    assert values == [10, 20]


def test_replay_single_new_method_with_saved_arguments():
    namespace = load("src/pluggy/_caller.py", {"_maybe_apply_history"})
    caller, events, values = history_fixture()
    caller._call_history.append(({"argument": 2}, values.append))
    method = object()
    namespace["_maybe_apply_history"](caller, method)
    assert events == [("sample", [method], {"argument": 2}, False)]
    assert values == [30]


def test_nonhistoric_hook_does_not_replay():
    namespace = load("src/pluggy/_caller.py", {"_maybe_apply_history"})
    caller, events, _ = history_fixture(False)
    namespace["_maybe_apply_history"](caller, object())
    assert events == []
