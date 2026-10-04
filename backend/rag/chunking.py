"""Structural chunks preserve definitions; documents use overlapping windows."""


def chunk_metadata(symbol, relationships):
    related = [e for e in relationships if symbol["id"] in (e["source"], e["target"])]
    return {
        "repository": symbol["repo_id"],
        "file": symbol["path"],
        "language": symbol.get("language", "text"),
        "symbol": symbol["id"],
        "kind": symbol["kind"],
        "qualified_name": symbol["qualified"],
        "parent": symbol["parent_id"],
        "start_line": symbol["start_line"],
        "end_line": symbol["end_line"],
        "relationships": related[:100],
        "relationship_count": len(related),
    }


def repository_chunks(symbols, relationships):
    from collections import defaultdict

    adjacent = defaultdict(list)
    for edge in relationships:
        adjacent[edge["source"]].append(edge)
        if edge["target"] != edge["source"]:
            adjacent[edge["target"]].append(edge)
    by_id = {symbol["id"]: symbol for symbol in symbols}
    file_imports = defaultdict(list)
    for edge in relationships:
        if edge["kind"] == "imports" and edge["source"] in by_id:
            file_imports[by_id[edge["source"]]["path"]].append(edge)
    chunks = {}
    for symbol in symbols:
        neighbors = adjacent[symbol["id"]]
        chunk = chunk_metadata(symbol, neighbors)
        chunk.update(
            imports=file_imports[symbol["path"]][:100],
            calls=[
                edge
                for edge in neighbors
                if edge["source"] == symbol["id"] and edge["kind"] == "calls"
            ][:100],
            callers=[
                edge
                for edge in neighbors
                if edge["target"] == symbol["id"] and edge["kind"] == "calls"
            ][:100],
            callees=[
                by_id[edge["target"]]["qualified"]
                for edge in neighbors
                if edge["source"] == symbol["id"]
                and edge["kind"] == "calls"
                and edge["target"] in by_id
            ][:100],
            inheritance=[
                edge
                for edge in neighbors
                if edge["source"] == symbol["id"] and edge["kind"] in ("inherits", "implements")
            ][:100],
            related_tests=[
                edge
                for edge in neighbors
                if edge["target"] == symbol["id"] and edge["kind"] == "tests"
            ][:100],
        )
        chunks[symbol["id"]] = chunk
    return chunks
