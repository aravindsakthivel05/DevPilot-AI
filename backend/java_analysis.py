"""Tree-sitter Java extraction with conservative relationship resolution."""

from pathlib import PurePosixPath

import tree_sitter_java
from tree_sitter import Language, Parser

from .analysis import symbol_id

JAVA_LANGUAGE = Language(tree_sitter_java.language())
TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
}


def analyse_java(repo_id, files):
    symbols, edges, errors, unresolved, pending = [], [], [], [], []
    qualified = {}
    parser = Parser(JAVA_LANGUAGE)
    import_aliases, field_types, parameter_types = {}, {}, {}

    for path, content in sorted(files.items()):
        if not path.endswith(".java"):
            continue
        data = content.encode("utf-8")
        root = parser.parse(data).root_node
        if root.has_error:
            errors.append({"path": path, "error": "Java syntax contains parser errors"})
        package = ""
        for child in root.children:
            if child.type == "package_declaration":
                package = (
                    data[child.start_byte : child.end_byte]
                    .decode()
                    .removeprefix("package")
                    .strip(" ;")
                )
        aliases = {}
        for child in root.children:
            if child.type == "import_declaration":
                target = (
                    data[child.start_byte : child.end_byte]
                    .decode()
                    .removeprefix("import")
                    .strip(" ;")
                )
                target = target.removeprefix("static ").strip()
                if not target.endswith(".*"):
                    aliases[target.rsplit(".", 1)[-1]] = target
        import_aliases[path] = aliases
        module_name = (
            package + "." + PurePosixPath(path).stem if package else PurePosixPath(path).stem
        )
        mid = symbol_id(repo_id, path, module_name + "#module", 1)
        symbols.append(
            dict(
                id=mid,
                repo_id=repo_id,
                path=path,
                name=PurePosixPath(path).name,
                qualified=module_name,
                kind="module",
                start_line=1,
                end_line=max(1, len(content.splitlines())),
                source="\n".join(content.splitlines()),
                docstring="",
                parent_id=None,
            )
        )

        def visit(node, parent=mid, prefix=package, cls=None):
            kind = TYPES.get(node.type)
            if kind or node.type in ("method_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    return
                name = data[name_node.start_byte : name_node.end_byte].decode()
                qname = prefix + "." + name if prefix else name
                sid = symbol_id(
                    repo_id, path, qname + f"#byte{node.start_byte}", node.start_point.row + 1
                )
                actual_kind = kind or (
                    "constructor" if node.type == "constructor_declaration" else "method"
                )
                symbols.append(
                    dict(
                        id=sid,
                        repo_id=repo_id,
                        path=path,
                        name=name,
                        qualified=qname,
                        kind=actual_kind,
                        start_line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        source=data[node.start_byte : node.end_byte].decode(),
                        docstring="",
                        parent_id=parent,
                    )
                )
                qualified.setdefault(qname, []).append(sid)
                edges.append(
                    dict(
                        repo_id=repo_id,
                        source=parent,
                        target=sid,
                        kind="contains",
                        line=node.start_point.row + 1,
                        confidence="exact",
                        label=name,
                    )
                )
                if kind:
                    cls = qname
                    for field in ("superclass", "interfaces"):
                        base = node.child_by_field_name(field)
                        if base:
                            pending.append(
                                (
                                    sid,
                                    "inherits",
                                    data[base.start_byte : base.end_byte].decode(),
                                    package,
                                    cls,
                                    node.start_point.row + 1,
                                )
                            )
                if not kind:
                    parameters = node.child_by_field_name("parameters")
                    bindings = {}
                    if parameters:
                        for param in parameters.named_children:
                            pname, ptype = (
                                param.child_by_field_name("name"),
                                param.child_by_field_name("type"),
                            )
                            if pname and ptype:
                                bindings[data[pname.start_byte : pname.end_byte].decode()] = data[
                                    ptype.start_byte : ptype.end_byte
                                ].decode()
                    parameter_types[sid] = bindings
                parent, prefix = sid, qname
            elif node.type == "field_declaration" and cls:
                type_node = node.child_by_field_name("type")
                if type_node:
                    declared = data[type_node.start_byte : type_node.end_byte].decode()
                    for declarator in node.named_children:
                        if declarator.type == "variable_declarator":
                            name_node = declarator.child_by_field_name("name")
                            if name_node:
                                field_types[
                                    (cls, data[name_node.start_byte : name_node.end_byte].decode())
                                ] = declared
            elif node.type == "method_invocation":
                name = node.child_by_field_name("name")
                owner = node.child_by_field_name("object")
                if name and parent != mid:
                    call = data[name.start_byte : name.end_byte].decode()
                    label = (
                        data[owner.start_byte : owner.end_byte].decode() + "." + call
                        if owner
                        else call
                    )
                    pending.append((parent, "calls", label, package, cls, node.start_point.row + 1))
            elif node.type == "import_declaration":
                label = (
                    data[node.start_byte : node.end_byte]
                    .decode()
                    .removeprefix("import")
                    .strip(" ;")
                )
                pending.append(
                    (
                        mid,
                        "imports",
                        label.removeprefix("static "),
                        package,
                        cls,
                        node.start_point.row + 1,
                    )
                )
            for child in node.children:
                visit(child, parent, prefix, cls)

        visit(root)

    # Resolve only indexed, unambiguous direct superclass declarations. Never
    # interpret super as this; unknown/external parents remain unresolved.
    source_paths = {item["id"]: item["path"] for item in symbols}

    def qualify_type(value, package, aliases):
        value = value.split("<", 1)[0].strip().removesuffix("[]")
        return aliases.get(value, package + "." + value if "." not in value and package else value)

    bases = {}
    for source, kind, label, package, cls, _ in pending:
        if kind == "inherits" and label.startswith("extends "):
            base = label.removeprefix("extends ").split("<", 1)[0].strip()
            candidates = [
                qualify_type(base, package, import_aliases[source_paths[source]]),
                package + "." + base,
                base,
            ]
            resolved = next((c for c in candidates if len(qualified.get(c, [])) == 1), None)
            if resolved:
                bases[cls] = resolved

    for source, kind, label, package, cls, line in pending:
        cleaned = (
            label.removeprefix("extends ").removeprefix("implements ").split("<", 1)[0].strip()
        )
        aliases = import_aliases.get(source_paths[source], {})
        confidence = "static"
        if kind == "calls":
            if cls and "." not in cleaned:
                candidates = [cls + "." + cleaned]
                if cleaned in aliases:
                    candidates.append(aliases[cleaned])
            elif cls and cleaned.startswith("super."):
                parent = bases.get(cls)
                candidates = []
                seen = set()
                while parent and parent not in seen:
                    seen.add(parent)
                    candidate = parent + "." + cleaned.split(".", 1)[1]
                    candidates.append(candidate)
                    if candidate in qualified:
                        break
                    parent = bases.get(parent)
            elif cls and cleaned.startswith("this."):
                candidates = [cls + "." + cleaned.split(".", 1)[1]]
            else:
                head, separator, tail = cleaned.partition(".")
                declared = parameter_types.get(source, {}).get(head, field_types.get((cls, head)))
                if declared and separator:
                    candidates = [qualify_type(declared, package, aliases) + "." + tail]
                    confidence = "declared_type"
                elif head in aliases and separator:
                    candidates = [aliases[head] + "." + tail]
                else:
                    candidates = [package + "." + cleaned, cleaned]
        else:
            candidates = [package + "." + cleaned, cleaned]
        matches = []
        for candidate in candidates:
            if candidate in qualified:
                matches = qualified[candidate] if len(qualified[candidate]) == 1 else []
                break
        if matches:
            edges.append(
                dict(
                    repo_id=repo_id,
                    source=source,
                    target=matches[0],
                    kind=kind,
                    line=line,
                    confidence=confidence,
                    label=label,
                )
            )
        else:
            unresolved.append(dict(source=source, label=label, kind=kind, line=line))
    return symbols, edges, errors, unresolved
