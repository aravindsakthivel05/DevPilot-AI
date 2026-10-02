"""Tree-sitter Java extraction with conservative relationship resolution."""

from pathlib import PurePosixPath

import tree_sitter_java
from tree_sitter import Language, Parser

from .analysis import symbol_id

PARSER = Parser(Language(tree_sitter_java.language()))
TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
}


def analyse_java(repo_id, files):
    symbols, edges, errors, unresolved, pending = [], [], [], [], []
    qualified = {}

    for path, content in sorted(files.items()):
        if not path.endswith(".java"):
            continue
        data = content.encode("utf-8")
        root = PARSER.parse(data).root_node
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
        module_name = (
            package + "." + PurePosixPath(path).stem if package else PurePosixPath(path).stem
        )
        mid = symbol_id(repo_id, path, module_name, 1)
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
                source=content[:5000],
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
                sid = symbol_id(repo_id, path, qname, node.start_point.row + 1)
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
                parent, prefix = sid, qname
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

    for source, kind, label, package, cls, line in pending:
        cleaned = (
            label.removeprefix("extends ").removeprefix("implements ").split("<", 1)[0].strip()
        )
        if kind == "calls":
            if cls and "." not in cleaned:
                candidates = [cls + "." + cleaned]
            elif cls and cleaned.startswith(("this.", "super.")):
                candidates = [cls + "." + cleaned.split(".", 1)[1]]
            else:
                candidates = [package + "." + cleaned, cleaned]
        else:
            candidates = [package + "." + cleaned, cleaned]
        matches = next((qualified[c] for c in candidates if len(qualified.get(c, [])) == 1), [])
        if matches:
            edges.append(
                dict(
                    repo_id=repo_id,
                    source=source,
                    target=matches[0],
                    kind=kind,
                    line=line,
                    confidence="static",
                    label=label,
                )
            )
        else:
            unresolved.append(dict(source=source, label=label, kind=kind, line=line))
    return symbols, edges, errors, unresolved
