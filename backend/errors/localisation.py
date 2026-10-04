"""Attach exact owning definitions and bounded structural neighbors."""

from collections import defaultdict

from .. import db


def attach(repo_id, issues):
    symbols = db.symbols(repo_id)
    lookup = {s["id"]: s for s in symbols}
    graph = db.edges(repo_id)
    by_path = defaultdict(list)
    adjacency = defaultdict(list)
    for s in symbols:
        by_path[s["path"]].append(s)
    for edge in graph:
        adjacency[edge["source"]].append(edge)
        adjacency[edge["target"]].append(edge)
    for issue in issues:
        owners = [
            s for s in by_path[issue["file"]] if s["start_line"] <= issue["line"] <= s["end_line"]
        ]
        owners.sort(key=lambda s: s["end_line"] - s["start_line"])
        if owners:
            owner = owners[0]
            issue["symbol"] = owner["qualified"]
            neighbors = []
            for e in adjacency[owner["id"]]:
                if owner["id"] in (e["source"], e["target"]):
                    other = e["target"] if e["source"] == owner["id"] else e["source"]
                    if other in lookup:
                        s = lookup[other]
                        neighbors.append(
                            {
                                "id": other,
                                "symbol": s["qualified"],
                                "file": s["path"],
                                "line": s["start_line"],
                                "relationship": e["kind"],
                                "confidence": e["confidence"],
                            }
                        )
            issue["related_symbols"] = neighbors[:20]
    return issues
