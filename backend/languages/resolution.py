"""Conservative cross-file call/import policies, without guessing runtime types."""

import re
from pathlib import PurePosixPath

from .tree_parser import parser_for, walk


def import_source(language, path, source):
    """Retain only grammar-established import/package declarations at original offsets."""
    data = source.encode()
    tree = parser_for(language, path).parse(data)
    buffer = bytearray(bytes(10 if byte == 10 else 32 for byte in data))
    kinds = {
        "import_statement",
        "import_declaration",
        "preproc_include",
        "mod_item",
        "use_declaration",
        "package_clause",
    }
    for node in walk(tree.root_node):
        if node.type in kinds:
            buffer[node.start_byte : node.end_byte] = data[node.start_byte : node.end_byte]
    return buffer.decode()


def literal_imports(language, path, source):
    patterns = {
        "javascript": r"(?:from\s*|require\s*\(\s*)['\"]([^'\"]+)['\"]",
        "typescript": r"(?:from\s*|require\s*\(\s*)['\"]([^'\"]+)['\"]",
        "c": r'^\s*#\s*include\s*"([^\"]+)"',
        "cpp": r'^\s*#\s*include\s*"([^\"]+)"',
        "rust": r"\bmod\s+([A-Za-z_]\w*)\s*;",
    }
    return [
        (m.group(1), source.count("\n", 0, m.start()) + 1)
        for m in re.finditer(patterns.get(language, r"(?!)"), source, re.M)
    ]


def resolve(repo_id, files, symbols, calls, language):
    modules = {s["path"]: s for s in symbols if s["kind"] == "module"}
    by_name = {}
    by_id = {s["id"]: s for s in symbols}
    for s in symbols:
        if s["kind"] in ("function", "method", "constructor"):
            by_name.setdefault(s["name"], []).append(s)
    allowed, aliases, edges = {}, {}, []
    assignments, namespaces = {}, {}
    for path, source in files.items():
        data = source.encode()
        root = parser_for(language, path).parse(data).root_node
        assignments[path] = set()
        namespaces[path] = set()
        for node in walk(root):
            if node.type in ("assignment_expression", "augmented_assignment_expression"):
                left = node.child_by_field_name("left")
                if left and left.type == "identifier":
                    assignments[path].add(data[left.start_byte : left.end_byte].decode())
            if node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
                name = node.child_by_field_name("name")
                if name:
                    namespaces[path].add(data[name.start_byte : name.end_byte].decode())

    for path, source in files.items():
        source = import_source(language, path, source)
        allowed[path] = {path}
        aliases[path] = {}
        for imported, line in literal_imports(language, path, source):
            base = PurePosixPath(path).parent / imported
            # Normalize literal relative paths without reading outside the snapshot.
            parts = []
            for part in base.parts:
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            target = "/".join(parts)
            candidates = [
                target,
                *(target + ext for ext in (".js", ".jsx", ".ts", ".tsx", ".rs")),
                *(target + "/index" + ext for ext in (".js", ".ts")),
                target + "/mod.rs",
            ]
            matches = [p for p in candidates if p in modules]
            if len(matches) == 1:
                destination = matches[0]
                allowed[path].add(destination)
                edges.append(
                    dict(
                        repo_id=repo_id,
                        source=modules[path]["id"],
                        target=modules[destination]["id"],
                        kind="imports",
                        line=line,
                        confidence="static",
                        label=imported,
                    )
                )
                if language in ("javascript", "typescript"):
                    match = re.search(
                        r"import\s*\{([^}]+)\}\s*from\s*['\"]" + re.escape(imported) + r"['\"]",
                        source,
                    )
                    if match:
                        for entry in match.group(1).split(","):
                            names = re.split(r"\s+as\s+", entry.strip())
                            aliases[path][names[-1]] = (destination, names[0])
        if language == "rust":
            for match in re.finditer(
                r"\buse\s+crate::([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)(?:\s+as\s+(\w+))?\s*;", source
            ):
                names = match.group(1).split("::")
                if len(names) < 2:
                    continue
                imported_path = "/".join(names[:-1]) + ".rs"
                options = [imported_path, str(PurePosixPath(path).parent / imported_path)]
                matches = list(dict.fromkeys(p for p in options if p in modules))
                if len(matches) == 1:
                    aliases[path][match.group(2) or names[-1]] = (matches[0], names[-1])
                    allowed[path].add(matches[0])
                    edges.append(
                        dict(
                            repo_id=repo_id,
                            source=modules[path]["id"],
                            target=modules[matches[0]]["id"],
                            kind="imports",
                            line=source.count("\n", 0, match.start()) + 1,
                            confidence="static",
                            label=match.group(0),
                        )
                    )
        if language == "go":
            pkg = re.search(r"^\s*package\s+(\w+)", source)
            if pkg:
                allowed[path].update(
                    p
                    for p, t in files.items()
                    if PurePosixPath(p).parent == PurePosixPath(path).parent
                    and re.search(r"^\s*package\s+" + re.escape(pkg.group(1)) + r"\b", t)
                )
    for call in calls:
        label, path = call["label"], call["path"]
        name = label.rsplit(".", 1)[-1]
        candidates = []
        if label not in call["shadowed"] and label not in assignments[path]:
            if label in aliases[path]:
                imported_path, imported_name = aliases[path][label]
                candidates = [
                    s
                    for s in by_name.get(imported_name, [])
                    if s["path"] == imported_path and s["parent_id"] == modules[imported_path]["id"]
                ]
            elif "." not in label:
                candidates = [
                    s
                    for s in by_name.get(name, [])
                    if s["path"] in allowed[path]
                    and s["kind"] == "function"
                    and s["parent_id"] == modules[s["path"]]["id"]
                ]
            elif label.startswith(("this.", "self.")):
                owner = by_id.get(call["source"])
                if owner:
                    candidates = [
                        s
                        for s in by_name.get(name, [])
                        if s["parent_id"] == owner["parent_id"] and s["path"] == path
                    ]
            elif language == "csharp":
                # Resolve explicit class-qualified static calls only. Instance
                # receiver names are not inferred from capitalization alone.
                namespace = namespaces[path]
                candidates = [
                    s
                    for s in by_name.get(name, [])
                    if s["qualified"].endswith("." + label)
                    and re.search(r"\bstatic\b", s.get("signature", ""))
                    and len(namespace) <= 1
                    and len(namespaces[s["path"]]) <= 1
                    and namespace == namespaces[s["path"]]
                ]
            elif language in ("cpp", "rust"):
                candidates = [
                    s
                    for s in by_name.get(name, [])
                    if s["path"] in allowed[path] and s["qualified"].endswith("." + label)
                ]
        if len(candidates) == 1:
            edges.append(
                dict(
                    repo_id=repo_id,
                    source=call["source"],
                    target=candidates[0]["id"],
                    kind="calls",
                    line=call["line"],
                    confidence="static",
                    label=label,
                )
            )
        else:
            unresolved = {k: v for k, v in call.items() if k != "shadowed"}
            unresolved.update(
                repo_id=repo_id, kind="calls", reason="ambiguous_or_external_or_dynamic"
            )
            # Kept separately, never asserted as a relationship or a defect.
            call["unresolved"] = unresolved
    return edges, [c["unresolved"] for c in calls if "unresolved" in c]
