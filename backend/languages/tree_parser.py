"""Common Tree-sitter extraction; resolution is delegated to language policies.

No compilation, macro expansion, runtime type inference or repository execution.
"""

import importlib
from pathlib import PurePosixPath

from tree_sitter import Language, Parser

from ..analysis import symbol_id
from ..models import normalize_symbol
from .base import AnalysisResult


def parser_for(language, path=""):
    module = importlib.import_module("tree_sitter_" + {"csharp": "c_sharp"}.get(language, language))
    factory = (
        (module.language_tsx if path.endswith(".tsx") else module.language_typescript)
        if language == "typescript"
        else module.language
    )
    return Parser(Language(factory()))


def walk(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))


class TreeAdapter:
    def __init__(self, language, extensions, declarations, resolver):
        self.language, self.extensions = language, extensions
        self.declarations, self.resolver = declarations, resolver

    def capabilities(self):
        return {
            "language": self.language,
            "extensions": self.extensions,
            "parser": "Tree-sitter",
            "symbols": sorted(set(self.declarations.values())),
            "relationships": "containment, literal imports, uniquely resolved lexical/static calls, syntactic parameter/return/raise references",
            "limitations": [
                "No compiler type checking or runtime dispatch",
                "Overloads, computed imports, macros and ambiguous receivers remain unresolved",
            ],
        }

    def analyze(self, repo_id, files):
        result = AnalysisResult()
        pending_calls = []
        for path, source in sorted(files.items()):
            data = source.encode()
            root = parser_for(self.language, path).parse(data).root_node

            def text(node):
                return data[node.start_byte : node.end_byte].decode() if node else ""

            prefix = str(PurePosixPath(path).with_suffix("")).replace("/", ".")
            mid = symbol_id(repo_id, path, prefix + "#module", 1)
            module = dict(
                id=mid,
                repo_id=repo_id,
                path=path,
                name=PurePosixPath(path).name,
                qualified=prefix,
                kind="module",
                start_line=1,
                end_line=max(1, len(source.splitlines())),
                source=source,
                docstring="",
                parent_id=None,
            )
            result.symbols.append(normalize_symbol(module, self.language))
            if root.has_error:
                failures = [n for n in walk(root) if n.type == "ERROR" or n.is_missing]
                for node in failures[:30]:
                    result.errors.append(
                        {
                            "path": path,
                            "line": node.start_point.row + 1,
                            "end_line": node.end_point.row + 1,
                            "error": "Tree-sitter syntax error or missing token",
                            "language": self.language,
                        }
                    )

            def edge(parent, target, kind, line, label):
                result.relationships.append(
                    dict(
                        repo_id=repo_id,
                        source=parent,
                        target=target,
                        kind=kind,
                        line=line,
                        confidence="exact",
                        label=label,
                    )
                )

            def visit(node, parent=mid, scope=prefix, parent_kind="module", shadowed=frozenset()):
                kind = self.declarations.get(node.type)
                if self.language in ("c", "cpp") and node.type == "declaration":
                    declared = node.child_by_field_name("declarator")
                    if declared and declared.type == "function_declarator":
                        kind = "function"
                if self.language == "go" and node.type == "type_spec":
                    declared = node.child_by_field_name("type")
                    if declared and declared.type in ("struct_type", "interface_type"):
                        kind = "struct" if declared.type == "struct_type" else "interface"
                name_node = node.child_by_field_name("name")
                if kind == "function" and name_node is None:
                    declarator = node.child_by_field_name("declarator")
                    while declarator and declarator.type not in (
                        "identifier",
                        "field_identifier",
                        "qualified_identifier",
                    ):
                        declarator = declarator.child_by_field_name("declarator")
                    name_node = declarator
                # JS arrow functions are named by the containing variable.
                if node.type == "variable_declarator":
                    value = node.child_by_field_name("value")
                    if value and value.type in ("arrow_function", "function_expression"):
                        kind = "function"
                if node.type == "impl_item":
                    owner = text(node.child_by_field_name("type"))
                    for child in node.named_children:
                        visit(child, parent, prefix + "." + owner, "class", shadowed)
                    return
                if kind and name_node:
                    name = text(name_node).replace("::", ".")
                    qualified = scope + "." + name
                    if node.type == "method_declaration" and self.language == "go":
                        receiver = node.child_by_field_name("receiver")
                        types = (
                            [n for n in walk(receiver) if n.type == "type_identifier"]
                            if receiver
                            else []
                        )
                        if types:
                            qualified = prefix + "." + text(types[-1]) + "." + name
                    if kind == "function" and parent_kind in ("class", "struct", "interface"):
                        kind = "method"
                    start, end = node.start_point.row + 1, node.end_point.row + 1
                    sid = symbol_id(repo_id, path, qualified + f"#byte{node.start_byte}", start)
                    # Store full original lines rather than byte fragments; the
                    # excerpt coordinates must always map to the original file.
                    body = "\n".join(source.splitlines()[start - 1 : end])
                    signature = text(node).split("{", 1)[0].split("\n", 1)[0][:500]
                    item = dict(
                        id=sid,
                        repo_id=repo_id,
                        path=path,
                        name=name,
                        qualified=qualified,
                        kind=kind,
                        start_line=start,
                        end_line=end,
                        source=body,
                        signature=signature,
                        docstring="",
                        parent_id=parent,
                    )
                    result.symbols.append(normalize_symbol(item, self.language))
                    edge(parent, sid, "contains", start, name)
                    params = node.child_by_field_name("parameters")
                    if not params:
                        decl = node.child_by_field_name("declarator")
                        params = decl.child_by_field_name("parameters") if decl else None
                    if not params and node.type == "variable_declarator":
                        value = node.child_by_field_name("value")
                        params = value.child_by_field_name("parameters") if value else None
                    names = set(shadowed)
                    if params:
                        for param in params.named_children:
                            pn = (
                                param.child_by_field_name("name")
                                or param.child_by_field_name("pattern")
                                or param.child_by_field_name("declarator")
                            )
                            if param.type == "identifier":
                                pn = param
                            if pn:
                                param_name = text(pn)
                                names.add(param_name)
                                pid = symbol_id(
                                    repo_id,
                                    path,
                                    qualified + "." + param_name + "#parameter",
                                    param.start_point.row + 1,
                                )
                                result.symbols.append(
                                    normalize_symbol(
                                        dict(
                                            id=pid,
                                            repo_id=repo_id,
                                            path=path,
                                            name=param_name,
                                            qualified=qualified + "." + param_name,
                                            kind="parameter",
                                            start_line=param.start_point.row + 1,
                                            end_line=param.end_point.row + 1,
                                            source="\n".join(
                                                source.splitlines()[
                                                    param.start_point.row : param.end_point.row + 1
                                                ]
                                            ),
                                            docstring="",
                                            parent_id=sid,
                                        ),
                                        self.language,
                                    )
                                )
                                edge(sid, pid, "accepts", param.start_point.row + 1, param_name)
                    if kind in ("function", "method", "constructor"):
                        for binding in walk(node):
                            if binding == node:
                                continue
                            if binding.type in (
                                "variable_declarator",
                                "let_declaration",
                                "var_spec",
                                "const_spec",
                            ):
                                bound = binding.child_by_field_name(
                                    "name"
                                ) or binding.child_by_field_name("pattern")
                                if bound and bound.type == "identifier":
                                    names.add(text(bound))
                            elif binding.type == "short_var_declaration":
                                left = binding.child_by_field_name("left")
                                if left:
                                    names.update(
                                        text(n)
                                        for n in left.named_children
                                        if n.type == "identifier"
                                    )
                    for child in node.named_children:
                        visit(child, sid, qualified, kind, frozenset(names))
                    return
                if node.type in ("call_expression", "invocation_expression"):
                    callee = node.child_by_field_name("function") or node.child_by_field_name(
                        "expression"
                    )
                    if callee:
                        pending_calls.append(
                            {
                                "source": parent,
                                "path": path,
                                "label": text(callee).replace("::", "."),
                                "line": node.start_point.row + 1,
                                "shadowed": shadowed,
                            }
                        )
                for child in node.named_children:
                    visit(child, parent, scope, parent_kind, shadowed)

            visit(root)
        edges, unresolved = self.resolver(
            repo_id, files, result.symbols, pending_calls, self.language
        )
        result.relationships.extend(edges)
        result.unresolved.extend(unresolved)
        return result
