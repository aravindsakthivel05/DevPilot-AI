import pytest
from boltons.iterutils import get_path, PathAccessError
from boltons.cacheutils import LRU


def test_numeric_string_list_index_and_success():
    assert get_path({"a": [11, 22]}, "a.1") == 22


def test_numeric_mapping_keyerror_is_not_converted():
    with pytest.raises(PathAccessError):
        get_path({1: "integer-key"}, "1")


@pytest.mark.parametrize(
    "root,path", [({}, "absent"), ([], (2,)), (3, ("a",)), ([1], ("invalid",))]
)
def test_errors_wrapped_and_explicit_none_default(root, path):
    with pytest.raises(PathAccessError):
        get_path(root, path)
    assert get_path(root, path, default=None) is None


def test_hit_changes_eviction_recency_and_counter():
    cache = LRU(max_size=2)
    cache["a"] = 1
    cache["b"] = 2
    assert cache["a"] == 1
    assert cache.hit_count == 1
    cache["c"] = 3
    assert "a" in cache and "b" not in cache and "c" in cache


def test_miss_without_callback_raises_and_counts():
    cache = LRU()
    with pytest.raises(KeyError):
        cache["missing"]
    assert cache.miss_count == 1 and cache.hit_count == 0


def test_callback_result_inserted_without_hit_increment():
    calls = []
    cache = LRU(on_miss=lambda key: calls.append(key) or 19)
    assert cache["new"] == 19
    assert dict(cache) == {"new": 19}
    assert calls == ["new"] and cache.miss_count == 1 and cache.hit_count == 0
    assert cache["new"] == 19 and cache.hit_count == 1


def test_callback_exception_not_inserted_and_miss_still_counted():
    def fail(key):
        raise ValueError("failed callback")

    cache = LRU(on_miss=fail)
    with pytest.raises(ValueError):
        cache["new"]
    assert "new" not in cache and cache.miss_count == 1 and cache.hit_count == 0
