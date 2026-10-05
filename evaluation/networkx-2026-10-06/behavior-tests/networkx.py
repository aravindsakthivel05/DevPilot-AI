import networkx as nx
import pytest


def test_component_sets():
    graph = nx.Graph([(0, 1), (2, 3)])
    graph.add_node(4)
    components = list(nx.connected_components(graph))
    assert all(isinstance(component, set) for component in components)
    assert {frozenset(component) for component in components} == {
        frozenset({0, 1}),
        frozenset({2, 3}),
        frozenset({4}),
    }


def test_generations_multiedges_and_list_type():
    graph = nx.MultiDiGraph([("a", "b"), ("a", "b"), ("a", "c"), ("b", "c")])
    generations = list(nx.topological_generations(graph))
    assert generations == [["a"], ["b"], ["c"]]
    assert all(isinstance(generation, list) for generation in generations)


def test_cycle_raises_unfeasible():
    with pytest.raises(nx.NetworkXUnfeasible):
        list(nx.topological_generations(nx.DiGraph([(0, 1), (1, 0)])))


def test_removed_generation_node_raises_runtimeerror():
    graph = nx.DiGraph([(0, 1), (1, 2)])
    generations = nx.topological_generations(graph)
    assert next(generations) == [0]
    graph.remove_node(1)
    with pytest.raises(RuntimeError):
        next(generations)


def test_new_child_missing_from_indegree_map_raises_runtimeerror():
    graph = nx.DiGraph([(0, 1)])
    generations = nx.topological_generations(graph)
    assert next(generations) == [0]
    graph.add_edge(1, 2)
    with pytest.raises(RuntimeError):
        next(generations)


def test_invalid_method_rejected_even_without_weight():
    graph = nx.DiGraph([("a", "b")])
    with pytest.raises(ValueError):
        nx.shortest_path(graph, source="a", target="b", method="invalid", weight=None)


@pytest.mark.parametrize(
    "method,weight,path",
    [
        ("dijkstra", None, ["a", "c"]),
        ("dijkstra", "weight", ["a", "b", "c"]),
        ("bellman-ford", "weight", ["a", "b", "c"]),
    ],
)
def test_target_only_directed_paths(method, weight, path):
    graph = nx.DiGraph()
    graph.add_weighted_edges_from([("a", "b", 1), ("b", "c", 1), ("a", "c", 5)])
    result = nx.shortest_path(graph, target="c", method=method, weight=weight)
    assert isinstance(result, dict)
    assert result["a"] == path and result["b"] == ["b", "c"] and result["c"] == ["c"]
    assert graph.has_edge("a", "b") and not graph.has_edge("b", "a")
