# NetworkX: DevPilot test results — 6 October 2026

Tested [NetworkX](https://github.com/networkx/networkx/tree/31b74e96903d7f873b30c8ff36d71a4c9252b107) at commit `31b74e96903d7f873b30c8ff36d71a4c9252b107` with local `qwen2.5-coder:14b` and `nomic-embed-text:latest` embeddings.

This is a DevPilot repository-understanding evaluation: three source-authored questions plus a private-runtime guard. Nine small reference-behavior scenarios also ran in network-disabled Docker containers. It is not the full NetworkX test suite. Questions and expected details were frozen before generation and withheld from retrieval and the model. The backend remained unchanged throughout the answer run. Review is by Codex against pinned source, not an independent human benchmark.

## Outcome

| Question | Source-review result | Required details | Time |
|---|---|---|---|
| Easy | Correct but incomplete | 2/4 | 115.101 s |
| Medium | Incorrect and incomplete | 1/5 | 168.140 s |
| Hard | Correct but incomplete | 3/8 | 166.573 s |
| Unanswerable | Correct abstention | — | 0.001 s |

**2/3 answers contained no identified factual error; 0/3 met the frozen full-detail requirement.** Detail coverage was 6/17. The private-runtime guard passed. Median answer time was 166.573 seconds. Compound dispatch details require the function and its requested arguments; a correct function name alone receives no full-detail credit.

## Index and execution evidence

- Indexed 929 files, 22,109 symbols and 29,376 structural edges in 226.471 seconds.
- No parser errors were reported.
- Embeddings: 9,377/9,377 eligible entities. This is not a claim that every repository file was indexed.
- All eight frozen source anchors were present in the generation contexts. Retrieval availability did not ensure complete or correct answers.
- Exclusions included one oversized file, one symlink and 44 unsupported-extension files; hidden/ignored directories were also excluded.
- Nine targeted repository scenarios passed in Docker (680 ms including container execution). They check component sets, list generations, parallel edges, cycle/mutation exceptions, invalid-method precedence and target-only path orientation.

## Main findings

1. The easy answer gave the right component and visited-node facts, but omitted the remaining-node-count argument and when global `seen` is updated.
2. On the medium question, validation suppressed a valid parallel-edge explanation because its cited function did not declare the user-specified `MultiDiGraph` class. This is a validation false rejection. The displayed answer also overgeneralized graph mutation as sufficient for `NetworkXUnfeasible`; the actual final condition is a remaining in-degree map, and some mutations raise `RuntimeError`.
3. The hard answer correctly rejected an invalid method despite `weight=None` and selected the correct routines. It omitted the reversed graph view, target starting-node arguments, weight forwarding and mapping keys.
4. The model reviewer labelled some incomplete aspects complete. Those labels were not used as the final score.

## Questions, actual answers and review

### Easy: networkx-easy

**Question:** In connected_components, what does it yield for an undirected graph, how are nodes already assigned to a component skipped, and how is _plain_bfs used?

**Actual DevPilot answer:**

For an undirected graph, `connected_components` yields sets of nodes that form connected components [1].

Nodes already assigned to a component are skipped by checking if the node is in the `seen` set before processing it [1].

`_plain_bfs` is used to perform a breadth-first search on the graph starting from an unvisited node [1].

**Source review:** Displayed facts are correct. It omits the n-len(seen) argument and updating global seen before yield. Source context contained both anchors.

**Frozen reference answer:**

It yields a set of nodes for each connected component. It loops over G and starts BFS only when v is not in the global seen set. It calls _plain_bfs(G, n-len(seen), v), adds the returned component to seen before yielding it. The helper explores adjacency breadth-first with its own seen set, returning the seen set when its size reaches n or when the frontier is exhausted.

**Source anchors:**

- [networkx/algorithms/components/connected.py:87](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/components/connected.py#L87)
- [networkx/algorithms/components/connected.py:278](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/components/connected.py#L278)

### Medium: networkx-medium

**Question:** In topological_generations, what collection type is yielded by the implementation, how are parallel edges counted for a MultiDiGraph, and which conditions raise RuntimeError versus NetworkXUnfeasible?

**Actual DevPilot answer:**

In topological_generations, the implementation yields a list of nodes for each generation [1].

Aspect 2: Some requested details could not be established from the supplied source evidence.

Aspect 3: Some requested details could not be established from the supplied source evidence.

In topological_generations, a NetworkXUnfeasible is raised if the graph contains a cycle or changes during iteration [1].

**Source review:** List output is correct. The final answer withholds multigraph counting and specific RuntimeError conditions. The NetworkXUnfeasible claim treats any mutation as sufficient; the actual condition is a remaining nonempty indegree_map after the loop. Removed-node and new-child mutations in the Docker tests raise RuntimeError instead. A valid draft counting parallel edges was blocked by the named-class identity guard.

**Frozen reference answer:**

The implementation yields this_generation, a list initially built from zero-in-degree nodes. For a multigraph it subtracts len(G[node][child]) from the child in-degree, otherwise 1. RuntimeError is raised if a node in this_generation no longer belongs to G, or when accessing indegree_map[child] raises KeyError, with that error chained. After zero_indegree is exhausted, a remaining nonempty indegree_map raises NetworkXUnfeasible with the message that the graph contains a cycle or changed during iteration. It does not prove that every possible mutation is detected as RuntimeError.

**Source anchors:**

- [networkx/algorithms/dag.py:287](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/dag.py#L287)
- [networkx/algorithms/dag.py:297](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/dag.py#L297)
- [networkx/algorithms/dag.py:305](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/dag.py#L305)

### Hard: networkx-hard

**Question:** In the native shortest_path implementation, what happens if method is invalid while weight is None, and how does the target-only branch on a directed graph choose an algorithm and orient the returned paths for unweighted, Dijkstra, and Bellman-Ford cases?

**Actual DevPilot answer:**

If the method is invalid while weight is None in the native shortest_path implementation, a ValueError is raised [1].

In the target-only branch on a directed graph, if weight is None (method is 'unweighted'), the algorithm nx.single_source_shortest_path is used [1].

In the target-only branch on a directed graph, if weight is not None (method is 'dijkstra'), the algorithm nx.single_source_dijkstra_path is used [1].

In the target-only branch on a directed graph, if weight is not None (method is 'bellman-ford'), the algorithm nx.single_source_bellman_ford_path is used [1].

In the target-only branch on a directed graph, for unweighted, Dijkstra, and Bellman-Ford cases, the returned paths are oriented by reversing them [1].

**Source review:** Gets invalid-method ValueError, unweighted override, the three selected function names and path reversal right. Omits reverse graph view, target starting-node arguments, weight forwarding and the source-keyed mapping. Compound frozen dispatch details require both the function and its arguments to count as complete.

**Frozen reference answer:**

It rejects an unsupported method with ValueError before changing method to unweighted when weight is None. In the source=None,target!=None branch, a directed G becomes G.reverse(copy=False), a reverse view. It runs single_source_shortest_path(G,target) for unweighted; single_source_dijkstra_path(G,target,weight=weight) for Dijkstra; single_source_bellman_ford_path(G,target,weight=weight) for Bellman-Ford. It then replaces every returned path by list(reversed(paths[target])) so each list runs from an original source to the original target, and returns the source-keyed path mapping.

**Source anchors:**

- [networkx/algorithms/shortest_paths/generic.py:135](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/shortest_paths/generic.py#L135)
- [networkx/algorithms/shortest_paths/generic.py:151](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/shortest_paths/generic.py#L151)
- [networkx/algorithms/shortest_paths/generic.py:160](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/networkx/algorithms/shortest_paths/generic.py#L160)

### Unanswerable: networkx-guard

**Question:** What is the exact shortest path and edge weight in my currently running private production graph now?

**Actual DevPilot answer:**

The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.

**Source review:** The pipeline abstained from inventing private live graph contents.

## Reproducibility files

- [Frozen questions](questions.json) and [rubric](review-rubric.json)
- [Raw answers, contexts, drafts and validation diagnostics](results.json)
- [Manual source review](source-review.json) and [summary](summary.json)
- [Pinned snapshot/index metadata](snapshots.json)
- [Docker evidence](execution.json) and [scenario source](behavior-tests/networkx.py)
- [Local model digests](local-model-manifest.json)

Questions SHA-256: `70f5fd08603782494c54bb8cfc614bc8ee8a45d13258b62c38f3f1500d62cd50`.
