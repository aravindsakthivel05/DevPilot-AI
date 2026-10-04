"""Declared Python package exports, including bounded re-export chains.

These are static names, not claims about runtime monkeypatching or dispatch.
"""

import ast
from pathlib import Path

from .analysis import module_name


def declared_aliases(metadata, files, package_prefix=""):
    lookup = {item["id"]: item for item in metadata}
    targets = {}
    for item in metadata:
        if item["path"].endswith(".py") and item["kind"] != "module":
            canonical = ".".join(part for part in (package_prefix, item["qualified"]) if part)
            targets.setdefault(canonical, []).append(item["id"])
    imports, stars, exports = {}, [], {}
    for path, source in sorted(files.items()):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        package = ".".join(p for p in (package_prefix, module_name(path)) if p)
        known_names, all_names = set(), None
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                known_names.add(node.name)
            elif isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                    try:
                        value = ast.literal_eval(node.value)
                        if isinstance(value, (list, tuple)) and all(
                            isinstance(n, str) for n in value
                        ):
                            all_names = set(value)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(node, ast.ImportFrom):
                parts = package.split(".") if package else []
                if node.level:
                    base = ".".join(
                        parts[: max(0, len(parts) - node.level + 1)]
                        + ([node.module] if node.module else [])
                    )
                else:
                    base = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        stars.append((package, base))
                    else:
                        name = alias.asname or alias.name
                        known_names.add(name)
                        imports[package + "." + name] = base + "." + alias.name
        exports[package] = (
            all_names
            if all_names is not None
            else {n for n in known_names if not n.startswith("_")}
        )
    for destination, source in stars:
        for name in exports.get(source, ()):
            imports[destination + "." + name] = source + "." + name
    aliases = {}
    for alias in sorted(set(imports) | set(targets)):
        current, seen = alias, set()
        for _ in range(8):
            if current in seen:
                break
            seen.add(current)
            if len(targets.get(current, [])) == 1:
                aliases.setdefault(targets[current][0], set()).add(alias)
                break
            if current not in imports:
                break
            current = imports[current]
    result = {}
    for item in metadata:
        names = set(aliases.get(item["id"], ()))
        parent = lookup.get(item.get("parent_id"))
        while parent and parent["kind"] != "class":
            parent = lookup.get(parent.get("parent_id"))
        if parent and parent["id"] in aliases:
            suffix = item["qualified"].removeprefix(parent["qualified"])
            names.update(alias + suffix for alias in aliases[parent["id"]])
        if names:
            result[item["id"]] = sorted(names)
    return result


def scoped_package_prefix(repo, file_paths):
    # A scope rooted at a Python package has an indexed root __init__.py.
    # For ordinary repository roots (src/ layout etc.), existing names already
    # include their package and require no inferred prefix.
    if "__init__.py" in file_paths:
        name = Path(repo["source"]).name
        return name if name.isidentifier() else ""
    return ""
