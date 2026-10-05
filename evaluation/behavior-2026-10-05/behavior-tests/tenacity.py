from types import SimpleNamespace
import pytest
from tenacity import Future
from tenacity.retry import retry_if_result, retry_if_not_result, retry_if_exception_cause_type


def state(value=None, exception=None):
    future = Future(1)
    if exception is None:
        future.set_result(value)
    else:
        future.set_exception(exception)
    return SimpleNamespace(outcome=future)


@pytest.mark.parametrize("strategy", [retry_if_result, retry_if_not_result])
def test_unset(strategy):
    with pytest.raises(RuntimeError):
        strategy(lambda value: True)(SimpleNamespace(outcome=None))


@pytest.mark.parametrize("strategy", [retry_if_result, retry_if_not_result])
def test_failure_does_not_call_result_predicate(strategy):
    def forbidden(value):
        raise AssertionError("predicate must not run for a failed outcome")

    assert strategy(forbidden)(state(exception=ValueError())) is False


@pytest.mark.parametrize("predicate_value", [True, False])
def test_success_negation_and_input(predicate_value):
    seen = []

    def predicate(value):
        seen.append(value)
        return predicate_value

    assert retry_if_result(predicate)(state(value=17)) is predicate_value
    assert retry_if_not_result(predicate)(state(value=17)) is (not predicate_value)
    assert seen == [17, 17]


def test_top_exception_is_not_a_cause_match():
    assert retry_if_exception_cause_type(ValueError)(state(exception=ValueError())) is False


def test_deeper_cause_matches():
    outer = RuntimeError()
    middle = TypeError()
    inner = ValueError()
    outer.__cause__ = middle
    middle.__cause__ = inner
    assert retry_if_exception_cause_type(ValueError)(state(exception=outer)) is True


def test_cause_cycle_terminates_without_match():
    first = RuntimeError()
    second = TypeError()
    first.__cause__ = second
    second.__cause__ = first
    assert retry_if_exception_cause_type(ValueError)(state(exception=first)) is False


def test_cause_success_false_and_unset_raises():
    strategy = retry_if_exception_cause_type(ValueError)
    assert strategy(state(value=4)) is False
    with pytest.raises(RuntimeError):
        strategy(SimpleNamespace(outcome=None))
