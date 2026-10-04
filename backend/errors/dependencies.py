"""Iterative SCCs over established file imports; cycles are informational."""

from collections import defaultdict


def import_cycles(symbols, edges):
    lookup = {s["id"]: s for s in symbols}
    forward, reverse = defaultdict(set), defaultdict(set)
    positions = {}
    for edge in edges:
        if (
            edge["kind"] != "imports"
            or edge["source"] not in lookup
            or edge["target"] not in lookup
        ):
            continue
        source, target = lookup[edge["source"]]["path"], lookup[edge["target"]]["path"]
        if source == target:
            continue
        forward[source].add(target)
        reverse[target].add(source)
        positions.setdefault(source, edge.get("line") or 1)
    vertices = set(forward) | set(reverse)
    visited = set()
    order = []
    for vertex in sorted(vertices):
        stack = [(vertex, False)]
        while stack:
            current, done = stack.pop()
            if done:
                order.append(current)
                continue
            if current in visited:
                continue
            visited.add(current)
            stack.append((current, True))
            stack.extend(
                (n, False) for n in sorted(forward[current], reverse=True) if n not in visited
            )
    visited = set()
    components = []
    for vertex in reversed(order):
        if vertex in visited:
            continue
        component = []
        stack = [vertex]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(reverse[current] - visited)
        if len(component) > 1:
            components.append(sorted(component))
    return [(component, positions.get(component[0], 1)) for component in components]
