"""Literal declarations and type references, without inferring runtime semantics."""

import json
import re
import tomllib
from collections import defaultdict
from pathlib import PurePosixPath
from xml.etree import ElementTree

from .analysis import symbol_id
from .languages.registry import detect_language
from .languages.tree_parser import parser_for, walk
from .models import normalize_symbol


def declared_metadata(repo_id, files, symbols):
    additions, edges = [], []
    by_path = {}
    for symbol in symbols:
        by_path.setdefault(symbol["path"], []).append(symbol)
    used = {s["id"] for s in symbols}

    def entity(path, owner, name, kind, start, end, source, relation):
        sid = symbol_id(repo_id, path, owner["qualified"] + "." + name + "#" + kind, start)
        if sid in used:
            return
        used.add(sid)
        additions.append(
            normalize_symbol(
                dict(
                    id=sid,
                    repo_id=repo_id,
                    path=path,
                    name=name,
                    qualified=owner["qualified"] + "." + name,
                    kind=kind,
                    start_line=start,
                    end_line=end,
                    source=source,
                    docstring="",
                    parent_id=owner["id"],
                ),
                detect_language(path, files[path]),
            )
        )
        edges.append(
            dict(
                repo_id=repo_id,
                source=owner["id"],
                target=sid,
                kind=relation,
                line=start,
                confidence="declared",
                label=name,
            )
        )

    for path, source in files.items():
        entries = by_path.get(path, [])
        language = detect_language(path, source)
        if not entries:
            continue
        if language != "text":
            data = source.encode()
            root = parser_for(language, path).parse(data).root_node
            lines = source.splitlines()
            # Smallest enclosing definition retains lexical scope. A declared
            # type is a reference node, not a guessed resolved implementation.
            definitions = [
                s
                for s in entries
                if s["kind"]
                in ("function", "method", "constructor", "class", "interface", "struct", "module")
            ]
            starts, ends = defaultdict(list), defaultdict(list)
            for definition in definitions:
                starts[definition["start_line"]].append(definition)
                ends[definition["end_line"] + 1].append(definition["id"])
            active, owners = {}, {}
            for number in range(1, len(lines) + 1):
                for sid in ends[number]:
                    active.pop(sid, None)
                for definition in starts[number]:
                    active[definition["id"]] = definition
                owners[number] = sorted(
                    active.values(),
                    key=lambda s: (
                        s["end_line"] - s["start_line"],
                        s["kind"] == "module",
                        s["kind"] in ("class", "interface", "struct"),
                    ),
                )
            for node in walk(root):
                start, end = node.start_point.row + 1, node.end_point.row + 1
                enclosing = node.parent
                owner = None
                while enclosing:
                    declared_name = enclosing.child_by_field_name("name")
                    if declared_name:
                        named = data[declared_name.start_byte : declared_name.end_byte].decode()
                        matches = [
                            s
                            for s in owners.get(start, [])
                            if s["name"] == named and end <= s["end_line"]
                        ]
                        if len(matches) == 1:
                            owner = matches[0]
                            break
                    enclosing = enclosing.parent
                if owner is None:
                    owner = next((s for s in owners.get(start, []) if end <= s["end_line"]), None)
                if not owner:
                    continue
                text = data[node.start_byte : node.end_byte].decode()
                snippet = "\n".join(lines[start - 1 : end])
                if language == "java" and node.type in ("formal_parameter", "spread_parameter"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        entity(
                            path,
                            owner,
                            data[name_node.start_byte : name_node.end_byte].decode(),
                            "parameter",
                            start,
                            end,
                            snippet,
                            "accepts",
                        )
                elif node.type in ("return_type", "type_annotation"):
                    # TypeScript/JS type annotations include locals/parameters;
                    # only return annotations belong to the function directly.
                    if (
                        node.type == "type_annotation"
                        and node.parent.child_by_field_name("return_type") != node
                    ):
                        continue
                    entity(
                        path,
                        owner,
                        text.strip(": "),
                        "type_reference",
                        start,
                        end,
                        snippet,
                        "returns",
                    )
                elif node.type in ("raise_statement", "throw_statement", "throws"):
                    entity(
                        path,
                        owner,
                        text[:200],
                        "exception_reference",
                        start,
                        end,
                        snippet,
                        "raises",
                    )
                elif node.type in (
                    "superclass",
                    "super_interfaces",
                    "base_list",
                    "extends_type_clause",
                    "class_heritage",
                ):
                    entity(
                        path, owner, text[:200], "type_reference", start, end, snippet, "inherits"
                    )
                elif node.type in (
                    "variable_declarator",
                    "const_item",
                    "static_item",
                    "var_spec",
                    "const_spec",
                ):
                    name = node.child_by_field_name("name")
                    if name:
                        value = node.child_by_field_name("value")
                        if value and value.type in ("arrow_function", "function_expression"):
                            continue
                        name_text = data[name.start_byte : name.end_byte].decode()
                        if not re.fullmatch(r"[A-Za-z_]\w*", name_text):
                            continue
                        entity(
                            path,
                            owner,
                            name_text,
                            "constant" if node.type in ("const_item", "const_spec") else "variable",
                            start,
                            end,
                            snippet,
                            "defines",
                        )
        else:
            owner = entries[0]
            name = PurePosixPath(path).name
            dependencies = []
            try:
                if name == "package.json":
                    manifest = json.loads(source)
                    dependencies = [
                        (key, value)
                        for section in (
                            "dependencies",
                            "devDependencies",
                            "peerDependencies",
                            "optionalDependencies",
                        )
                        for key, value in manifest.get(section, {}).items()
                    ]
                elif name in ("Cargo.toml", "pyproject.toml"):
                    manifest = tomllib.loads(source)
                    if name == "Cargo.toml":
                        dependencies = [
                            (key, str(value))
                            for section in (
                                "dependencies",
                                "dev-dependencies",
                                "build-dependencies",
                            )
                            for key, value in manifest.get(section, {}).items()
                        ]
                    else:
                        dependencies = [
                            (str(value), "")
                            for value in manifest.get("project", {}).get("dependencies", [])
                        ]
                elif name == "requirements.txt":
                    dependencies = [
                        (line.strip(), "")
                        for line in source.splitlines()
                        if line.strip() and not line.lstrip().startswith(("#", "-"))
                    ]
                elif name == "go.mod":
                    dependencies = re.findall(r"^\s*([\w.\-/]+)\s+(v[\w.\-+]+)", source, re.M)
                elif name == "pom.xml" or name.endswith(".csproj"):
                    root = ElementTree.fromstring(source)
                    if name.endswith(".csproj"):
                        dependencies = [
                            (n.attrib["Include"], n.attrib.get("Version", ""))
                            for n in root.iter()
                            if n.tag.rsplit("}", 1)[-1] == "PackageReference"
                            and "Include" in n.attrib
                        ]
                    else:
                        for n in root.iter():
                            if n.tag.rsplit("}", 1)[-1] != "dependency":
                                continue
                            fields = {c.tag.rsplit("}", 1)[-1]: c.text or "" for c in n}
                            if fields.get("artifactId"):
                                dependencies.append(
                                    (
                                        fields.get("groupId", "") + ":" + fields["artifactId"],
                                        fields.get("version", ""),
                                    )
                                )
            except (ValueError, TypeError, AttributeError, ElementTree.ParseError):
                dependencies = []
            for dependency, version in dependencies[:1000]:
                # Literal manifest declaration; never imply the library source is indexed.
                start = next(
                    (
                        i + 1
                        for i, line in enumerate(source.splitlines())
                        if dependency.split(":")[-1].split(">=")[0] in line
                    ),
                    1,
                )
                entity(
                    path,
                    owner,
                    f"{dependency} {version}".strip(),
                    "dependency",
                    start,
                    start,
                    source.splitlines()[start - 1] if source.splitlines() else "",
                    "depends_on",
                )
    return additions, edges
