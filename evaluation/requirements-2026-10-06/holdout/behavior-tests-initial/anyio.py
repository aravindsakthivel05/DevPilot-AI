"""Pinned wrapper source with controlled backends, not full AnyIO integration."""

import ast
import asyncio
import contextlib
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(path, names, backend):
    tree = ast.parse(Path(path).read_text())
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    assert {node.name for node in selected} == set(names)
    module = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            *selected,
        ],
        type_ignores=[],
    )
    namespace = {
        "get_async_backend": lambda: backend,
        "contextmanager": contextlib.contextmanager,
        "math": math,
        "warn": __import__("warnings").warn,
    }
    exec(compile(module, path, "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    "alias, expected, warns", [(None, True, False), (False, False, True), (True, True, True)]
)
def test_thread_alias_and_exact_forwarding(alias, expected, warns):
    captured = []

    async def worker(*args, **kwargs):
        captured.append((args, kwargs))
        return "backend result"

    namespace = load(
        "src/anyio/to_thread.py", {"run_sync"}, SimpleNamespace(run_sync_in_worker_thread=worker)
    )
    function, limiter = object(), object()
    with __import__("warnings").catch_warnings(record=True) as caught:
        __import__("warnings").simplefilter("always")
        result = asyncio.run(
            namespace["run_sync"](
                function, 1, 2, abandon_on_cancel=True, cancellable=alias, limiter=limiter
            )
        )
    assert result == "backend result"
    assert captured == [((function, (1, 2)), {"abandon_on_cancel": expected, "limiter": limiter})]
    assert bool(caught) is warns
    if warns:
        assert caught[0].category is DeprecationWarning
        assert "cancellable" in str(caught[0].message)


class Scope:
    def __init__(self, deadline, shield, caught=False):
        self.deadline, self.shield, self.cancelled_caught = deadline, shield, caught

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("method", ["fail_after", "move_on_after"])
@pytest.mark.parametrize("delay", [None, 3])
def test_deadline_and_shield_forwarding(method, delay):
    created = []

    def create(**kwargs):
        created.append(kwargs)
        return Scope(**kwargs)

    backend = SimpleNamespace(current_time=lambda: 10, create_cancel_scope=create)
    namespace = load(
        "src/anyio/_core/_tasks.py", {"fail_after", "fail_at", "move_on_after"}, backend
    )
    scope = namespace[method](delay, shield=True)
    if method == "fail_after":
        with scope as yielded:
            assert yielded.shield
    else:
        assert scope.shield
    assert created == [{"deadline": math.inf if delay is None else 13, "shield": True}]


@pytest.mark.parametrize(
    "caught, now, raises",
    [(False, 49, False), (False, 50, False), (True, 49, False), (True, 50, True)],
)
def test_timeout_requires_both_conditions(caught, now, raises):
    backend = SimpleNamespace(
        current_time=lambda: now,
        create_cancel_scope=lambda **kwargs: Scope(**kwargs, caught=caught),
    )
    namespace = load("src/anyio/_core/_tasks.py", {"fail_at"}, backend)
    if raises:
        with pytest.raises(TimeoutError, match="deadline explanation"):
            with namespace["fail_at"](50, reason="deadline explanation"):
                pass
    else:
        with namespace["fail_at"](50, reason="deadline explanation"):
            pass
