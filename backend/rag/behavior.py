"""Python syntax tables, not symbolic execution or proof of runtime behavior."""

import ast
import textwrap

from ..evidence import _terms, source_lines


def behavior_table(record, visible=None, limit=10, question=None):
    """Extract guarded statements from a complete definition, retaining coordinates.

    Only emit rows whose statement and every enclosing guard are supplied to the
    model. Nested definitions have their own scope. No expressions are evaluated.
    Unsupported languages and malformed source return no table.
    """
    if not record.get("path", "").endswith(".py"):
        return []
    try:
        tree = ast.parse(textwrap.dedent(record["source"]))
    except (SyntaxError, ValueError, RecursionError):
        return []
    offset = record.get("start_line", 1) - 1
    available = set(source_lines(visible or record))
    rows = []
    original_lines = textwrap.dedent(record["source"]).splitlines()

    def span(node):
        return {"start_line": node.lineno + offset, "end_line": node.end_lineno + offset}

    def guard(node, branch, expression):
        # Headers can span multiple lines; preserve the complete expression.
        end = getattr(node, "end_lineno", node.lineno)
        return {
            "branch": branch,
            "expression": expression,
            "start_line": node.lineno + offset,
            "end_line": end + offset,
        }

    def emit(node, kind, scope, guards):
        location = span(node)
        required = [location, *guards]
        statement = ast.unparse(node)
        if (
            len(statement) > 200
            or len(guards) > 6
            or any(
                r["end_line"] - r["start_line"] >= 80
                or len(r.get("expression", "")) > 180
                or (r.get("branch_line") is not None and r["branch_line"] not in available)
                or not set(range(r["start_line"], r["end_line"] + 1)) <= available
                for r in required
            )
        ):
            return
        rows.append(
            {
                "kind": kind,
                "scope": scope,
                **location,
                "statement": statement,
                "guards": guards,
            }
        )

    def alternative_guard(node, body, branch, expression):
        result = guard(node, branch, expression)
        if isinstance(node, (ast.Try, ast.TryStar)):
            result["end_line"] = node.lineno + offset
        if body:
            line = body[0].lineno
            # elif is itself an If node; else can have comments before its body.
            if original_lines[line - 1].lstrip().startswith(("elif ", "else:")):
                result["branch_line"] = line + offset
            else:
                while line > node.lineno:
                    line -= 1
                    if original_lines[line - 1].lstrip().startswith("else:"):
                        result["branch_line"] = line + offset
                        break
        return result

    def walk(body, scope, guards):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(node.body, f"{scope}.{node.name}".strip("."), [])
            elif isinstance(node, ast.If):
                condition = ast.unparse(node.test)
                walk(node.body, scope, guards + [guard(node.test, "if_true", condition)])
                walk(
                    node.orelse,
                    scope,
                    guards + [alternative_guard(node.test, node.orelse, "if_false", condition)],
                )
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                expr = node.test if isinstance(node, ast.While) else node.iter
                walk(node.body, scope, guards + [guard(expr, "loop_body", ast.unparse(expr))])
                walk(
                    node.orelse,
                    scope,
                    guards
                    + [
                        alternative_guard(
                            expr, node.orelse, "loop_else_no_break", ast.unparse(expr)
                        )
                    ],
                )
            elif isinstance(node, (ast.Try, ast.TryStar)):
                # Entering try is not a predicate. Source statements and the
                # question prompt retain early-exception/order semantics without
                # repeating a fictitious condition on every row.
                walk(node.body, scope, guards)
                for handler in node.handlers:
                    h = {
                        "branch": "except_star" if isinstance(node, ast.TryStar) else "except",
                        "expression": ast.unparse(handler.type) if handler.type else "bare except",
                        "start_line": handler.lineno + offset,
                        "end_line": (handler.type.end_lineno if handler.type else handler.lineno)
                        + offset,
                    }
                    walk(handler.body, scope, guards + [h])
                walk(
                    node.orelse,
                    scope,
                    guards
                    + [
                        alternative_guard(
                            node,
                            node.orelse,
                            "try_else_no_exception",
                            "try body completed without exception",
                        )
                    ],
                )
                # The original finally header is the line before its first statement.
                if node.finalbody:
                    first = node.finalbody[0].lineno - 1
                    while first > node.lineno and not original_lines[first - 1].strip().startswith(
                        "finally:"
                    ):
                        first -= 1
                    walk(
                        node.finalbody,
                        scope,
                        guards
                        + [
                            {
                                "branch": "finally",
                                "expression": "on leaving try",
                                "start_line": first + offset,
                                "end_line": first + offset,
                            }
                        ],
                    )
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                walk(
                    node.body,
                    scope,
                    guards
                    + [
                        guard(item.context_expr, "with_body", ast.unparse(item.context_expr))
                        for item in node.items
                    ],
                )
            elif isinstance(
                node,
                (
                    ast.Return,
                    ast.Raise,
                    ast.Assign,
                    ast.AugAssign,
                    ast.AnnAssign,
                    ast.Break,
                    ast.Continue,
                ),
            ):
                emit(node, type(node).__name__.lower(), scope, guards)
            elif isinstance(node, ast.Expr) and isinstance(node.value, (ast.Call, ast.Await)):
                emit(node, "call", scope, guards)
            # Match and other unsupported compound statements are left to source
            # reading rather than emitting their bodies without the right guards.

    walk(tree.body, "", [])
    if question:
        terms = _terms(question)
        if "numeric" in terms or "integer" in terms:
            terms.update({"int", "index"})

        def score(row):
            words = _terms(
                row["statement"] + " " + " ".join(g["expression"] for g in row["guards"])
            )
            numeric_focus = (
                24 if "int(" in row["statement"] and ({"numeric", "integer"} & terms) else 0
            )
            return (
                numeric_focus
                + 8 * len(terms & words)
                + (6 if row["kind"] in ("return", "raise") else 0)
            )

        # Represent distinct guarded paths before extra statements from the same
        # path. Return/error rows and query-relevant conversions outrank setup.
        ranked = sorted(rows, key=lambda row: (-score(row), row["start_line"]))
        chosen, groups = [], set()
        for row in ranked:
            group = (
                row["scope"],
                tuple((g["branch"], g["start_line"], g["end_line"]) for g in row["guards"]),
            )
            if group not in groups:
                chosen.append(row)
                groups.add(group)
        chosen.extend(row for row in ranked if row not in chosen)
        return chosen[:limit]
    return rows[:limit]
