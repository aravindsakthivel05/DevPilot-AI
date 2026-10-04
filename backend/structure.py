"""Additional structural edges only when a syntactic relationship is established."""

import ast

from .analysis import symbol_id
from .models import normalize_symbol
from .structural_metadata import declared_metadata
from .test_links import is_test_path


def enrich(repo_id, files, symbols, edges):
    additions, relationships = [], []
    by_path = {}
    by_id = {s["id"]: s for s in symbols}
    for s in symbols:
        by_path.setdefault(s["path"], []).append(s)
    for edge in edges:
        source = by_id.get(edge["source"])
        if source and is_test_path(source["path"]) and edge["kind"] in ("calls", "imports"):
            relationships.append({**edge, "kind": "tests", "confidence": "static"})
    for path, text in files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            matches = [
                s
                for s in by_path.get(path, [])
                if s["name"] == node.name
                and s["start_line"] <= node.lineno <= s["end_line"]
                and s["kind"] in ("function", "method")
            ]
            if len(matches) != 1:
                continue
            owner = matches[0]
            for argument in [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
                *([node.args.vararg] if node.args.vararg else []),
                *([node.args.kwarg] if node.args.kwarg else []),
            ]:
                pid = symbol_id(
                    repo_id,
                    path,
                    owner["qualified"] + "." + argument.arg + "#parameter",
                    argument.lineno,
                )
                additions.append(
                    normalize_symbol(
                        dict(
                            id=pid,
                            repo_id=repo_id,
                            path=path,
                            name=argument.arg,
                            qualified=owner["qualified"] + "." + argument.arg,
                            kind="parameter",
                            start_line=argument.lineno,
                            end_line=argument.end_lineno,
                            source="\n".join(lines[argument.lineno - 1 : argument.end_lineno]),
                            docstring="",
                            parent_id=owner["id"],
                        ),
                        "python",
                    )
                )
                relationships.append(
                    dict(
                        repo_id=repo_id,
                        source=owner["id"],
                        target=pid,
                        kind="accepts",
                        line=argument.lineno,
                        confidence="exact",
                        label=argument.arg,
                    )
                )
    declared, declared_edges = declared_metadata(repo_id, files, symbols)
    additions.extend(declared)
    relationships.extend(declared_edges)
    return additions, relationships
