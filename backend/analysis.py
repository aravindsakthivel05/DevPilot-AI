"""Conservative Python structure extraction; unresolved calls remain explicit."""

import ast
import hashlib
from pathlib import PurePosixPath


def symbol_id(repo_id, path, qualified, line):
    return hashlib.sha256(f"{repo_id}:{path}:{qualified}:{line}".encode()).hexdigest()[:24]


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else ""
    return ""


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def local_bindings(node):
    """Names bound in a function; nested bodies have their own lexical scope."""
    names = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)

    class Collector(ast.NodeVisitor):
        def visit_Name(self, item):
            if isinstance(item.ctx, (ast.Store, ast.Del)):
                names.add(item.id)

        def visit_FunctionDef(self, item):
            names.add(item.name)

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Import(self, item):
            names.update(alias.asname or alias.name.split(".")[0] for alias in item.names)

        def visit_ImportFrom(self, item):
            names.update(alias.asname or alias.name for alias in item.names)

    collector = Collector()
    for child in node.body:
        collector.visit(child)
    return names


def analyse(repo_id, files):
    symbols, edges, pending, errors = [], [], [], []
    modules, by_qualified, imports, bindings = {}, {}, {}, {}
    for path, content in sorted(files.items()):
        lines = content.splitlines()
        mod = module_name(path) if path.endswith(".py") else path
        mid = symbol_id(repo_id, path, mod, 1)
        module = dict(
            id=mid,
            repo_id=repo_id,
            path=path,
            name=PurePosixPath(path).name,
            qualified=mod,
            kind="module" if path.endswith(".py") else "document",
            start_line=1,
            end_line=max(1, len(lines)),
            source="\n".join(lines[:100]),
            docstring="",
            parent_id=None,
        )
        symbols.append(module)
        if not path.endswith(".py"):
            continue
        modules[mod] = mid
        by_qualified.setdefault(mod, []).append(mid)
        imports[mid] = {}
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError, RecursionError) as e:
            errors.append({"path": path, "error": str(e)})
            continue
        module["docstring"] = ast.get_docstring(tree) or ""

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = [(mid, mod, "module")]

            def definition(self, node, kind):
                parent, prefix, parent_kind = self.stack[-1]
                qualified = f"{prefix}.{node.name}" if prefix else node.name
                sid = symbol_id(repo_id, path, qualified, node.lineno)
                start = min([node.lineno] + [x.lineno for x in node.decorator_list])
                actual_kind = "method" if kind == "function" and parent_kind == "class" else kind
                symbols.append(
                    dict(
                        id=sid,
                        repo_id=repo_id,
                        path=path,
                        name=node.name,
                        qualified=qualified,
                        kind=actual_kind,
                        start_line=start,
                        end_line=node.end_lineno,
                        source="\n".join(lines[start - 1 : node.end_lineno]),
                        docstring=ast.get_docstring(node) or "",
                        parent_id=parent,
                    )
                )
                by_qualified.setdefault(qualified, []).append(sid)
                edges.append(
                    dict(
                        repo_id=repo_id,
                        source=parent,
                        target=sid,
                        kind="contains",
                        line=start,
                        confidence="exact",
                        label=node.name,
                    )
                )
                if kind == "class":
                    for base in node.bases:
                        pending.append(
                            (sid, mid, prefix, dotted(base), "inherits", node.lineno, None)
                        )
                if kind == "function":
                    bindings[sid] = local_bindings(node)
                    imports[sid] = {}
                self.stack.append((sid, qualified, kind))
                # Decorators/default expressions run in the surrounding scope; don't invent body-call edges for them.
                for child in node.body:
                    self.visit(child)
                self.stack.pop()

            def visit_ClassDef(self, node):
                self.definition(node, "class")

            def visit_FunctionDef(self, node):
                self.definition(node, "function")

            def visit_AsyncFunctionDef(self, node):
                self.definition(node, "function")

            def visit_Import(self, node):
                for alias in node.names:
                    owner = self.stack[-1][0]
                    imports.setdefault(owner, {})[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
                    pending.append(
                        (self.stack[-1][0], mid, mod, alias.name, "imports", node.lineno, None)
                    )

            def visit_ImportFrom(self, node):
                package = mod.split(".") if path.endswith("/__init__.py") else mod.split(".")[:-1]
                if node.level:
                    prefix = package[: max(0, len(package) - node.level + 1)]
                    base = ".".join(prefix + ([node.module] if node.module else []))
                else:
                    base = node.module or ""
                for alias in node.names:
                    full = ".".join(x for x in [base, alias.name] if x)
                    imports.setdefault(self.stack[-1][0], {})[alias.asname or alias.name] = full
                    pending.append(
                        (self.stack[-1][0], mid, mod, full, "imports", node.lineno, base)
                    )

            def visit_Call(self, node):
                label = dotted(node.func)
                cls = next((q for _, q, k in reversed(self.stack) if k == "class"), None)
                if label:
                    pending.append(
                        (
                            self.stack[-1][0],
                            mid,
                            self.stack[-1][1],
                            label,
                            "calls",
                            node.lineno,
                            cls,
                        )
                    )
                self.generic_visit(node)

        Visitor().visit(tree)

    unresolved = []
    for source, mid, scope, label, kind, line, extra in pending:
        candidates = []
        confidence = "static"
        if kind == "imports":
            candidates = [label] + ([extra] if extra else [])
        else:
            head, _, tail = label.partition(".")
            if head in ("self", "cls") and extra:
                candidates = [extra + ("." + tail if tail else "")]
                confidence = "inferred"
            elif head in imports.get(source, {}):
                candidates = [imports[source][head] + ("." + tail if tail else "")]
            elif head in bindings.get(source, {}):
                candidates = []
            elif head in imports[mid]:
                candidates = [imports[mid][head] + ("." + tail if tail else "")]
            else:
                parts = scope.split(".")
                candidates = [".".join(parts[:i] + [label]) for i in range(len(parts), 0, -1)] + [
                    label
                ]
        target = None
        for candidate in candidates:
            matches = by_qualified.get(candidate, [])
            if len(matches) == 1:
                target = matches[0]
                break
        if target:
            edges.append(
                dict(
                    repo_id=repo_id,
                    source=source,
                    target=target,
                    kind=kind,
                    line=line,
                    confidence=confidence,
                    label=label,
                )
            )
        else:
            unresolved.append(dict(source=source, label=label, kind=kind, line=line))
    return symbols, edges, errors, unresolved
