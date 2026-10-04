"""Bounded Repository Structural Graph queries and evidence-backed enrichment."""

from collections import defaultdict

from . import db
from .models import file_id


def neighborhood(repo_id, seed=None, path=None, kinds=None, depth=1, direction="both", limit=200):
    if (
        not 0 <= depth <= 3
        or not 1 <= limit <= 500
        or direction not in ("both", "outgoing", "incoming")
    ):
        raise ValueError("Invalid bounded graph query")
    symbols = db.symbols(repo_id)
    nodes = {
        s["id"]: {k: v for k, v in s.items() if k not in ("source", "docstring")} for s in symbols
    }
    with db.connection() as c:
        files = [
            dict(r)
            for r in c.execute(
                "SELECT file_id,path,language,role FROM files WHERE repo_id=?", (repo_id,)
            )
        ]
    repository_id = "repository:" + repo_id
    nodes[repository_id] = dict(
        id=repository_id,
        name=db.repository(repo_id)["name"],
        qualified=db.repository(repo_id)["name"],
        kind="repository",
        path="",
        start_line=1,
        end_line=1,
    )
    edges = db.edges(repo_id)
    roots = defaultdict(list)
    for symbol in symbols:
        if symbol["parent_id"] is None:
            roots[symbol["path"]].append(symbol)
    for f in files:
        fid = f["file_id"] or file_id(repo_id, f["path"])
        nodes[fid] = dict(
            id=fid,
            name=f["path"],
            qualified=f["path"],
            kind="file",
            path=f["path"],
            language=f["language"],
            role=f["role"],
            start_line=1,
            end_line=1,
        )
        edges.append(
            dict(source=repository_id, target=fid, kind="contains", confidence="filesystem", line=1)
        )
        edges.extend(
            dict(
                source=fid, target=s["id"], kind="defines", confidence="exact", line=s["start_line"]
            )
            for s in roots[f["path"]]
        )
    if seed:
        if seed not in nodes:
            raise ValueError("Graph seed not found")
        seeds = [seed]
    elif path:
        seeds = [s["id"] for s in symbols if s["path"] == path and s["parent_id"] is None]
        if not seeds:
            raise ValueError("Graph file not found")
    else:
        seeds = [repository_id]
    adjacency = defaultdict(list)
    for edge in edges:
        if kinds and edge["kind"] not in kinds:
            continue
        if direction != "incoming":
            adjacency[edge["source"]].append((edge["target"], edge))
        if direction != "outgoing":
            adjacency[edge["target"]].append((edge["source"], edge))
    selected, frontier, selected_edges = set(seeds[:limit]), seeds[:limit], []
    truncated = len(seeds) > limit
    for _ in range(depth):
        following = []
        for current in frontier:
            for target, edge in adjacency[current]:
                if target not in nodes:
                    continue
                if target not in selected:
                    if len(selected) >= limit:
                        truncated = True
                        continue
                    selected.add(target)
                    following.append(target)
                if edge not in selected_edges:
                    selected_edges.append(edge)
        frontier = following
    return {
        "name": "Repository Structural Graph",
        "nodes": [nodes[s] for s in sorted(selected)],
        "edges": selected_edges,
        "depth": depth,
        "truncated": truncated,
        "notice": "Static relationships and declared metadata; no runtime execution or compiler-grade proof.",
    }
