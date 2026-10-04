"""Bounded syntax and lexical-scope rules. Unknown resolution is never a bug."""

import ast
import builtins
import json
from pathlib import PurePosixPath


def candidates(files, parser_errors):
    found = []
    for error in parser_errors:
        if error.get("language") == "python":
            continue
        path = error["path"]
        if path.endswith(".py"):
            continue
        found.append(
            dict(
                kind="syntax_error",
                path=path,
                line=error.get("line", 1),
                end_line=error.get("end_line", error.get("line", 1)),
                message=error["error"],
                root_cause="The configured parser could not parse this source region. Grammar/dialect limitations can also produce this diagnostic.",
                fix="Inspect the indicated syntax and the language/dialect capability report.",
                confidence="medium",
                severity="error",
            )
        )
    for path, source in files.items():
        if PurePosixPath(path).name in ("package.json", "tsconfig.json"):
            try:
                json.loads(source)
            except json.JSONDecodeError as exc:
                # tsconfig permits comments, so do not call JSONC invalid JSON.
                if path.endswith("tsconfig.json"):
                    continue
                found.append(
                    dict(
                        kind="configuration_syntax",
                        path=path,
                        line=exc.lineno,
                        message=exc.msg,
                        root_cause="The dependency manifest is not valid JSON.",
                        fix="Correct the JSON token or delimiter at this location.",
                        confidence="high",
                        severity="error",
                    )
                )
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            found.append(
                dict(
                    kind="syntax_error",
                    path=path,
                    line=exc.lineno or 1,
                    message=exc.msg,
                    root_cause="Python's parser rejects this source syntax.",
                    fix="Correct the indicated Python syntax; inspect the preceding delimiter or indentation as well.",
                    confidence="high",
                    severity="error",
                )
            )
            continue
        except (ValueError, RecursionError):
            continue
        definitions = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in definitions:
                    found.append(
                        dict(
                            kind="duplicate_definition",
                            path=path,
                            line=node.lineno,
                            end_line=node.end_lineno,
                            message=f"Top-level definition {node.name} replaces an earlier definition at line {definitions[node.name].lineno}.",
                            root_cause="Two unconditional top-level definitions bind the same name in file order. Replacement can be intentional.",
                            fix="If replacement is unintended, rename or consolidate the definitions; otherwise document the override.",
                            confidence="medium",
                        )
                    )
                definitions[node.name] = node
        global_names = set(dir(builtins)) | {
            "__name__",
            "__file__",
            "__package__",
            "__doc__",
            "__annotations__",
            "__builtins__",
        }
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                global_names.add(n.id)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                global_names.add(n.name)
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                global_names.update(
                    a.asname or (a.name.split(".")[0] if isinstance(n, ast.Import) else a.name)
                    for a in n.names
                )
        dynamic = any(
            isinstance(n, ast.ImportFrom)
            and any(a.name == "*" for a in n.names)
            or isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("exec", "eval", "globals", "locals")
            for n in ast.walk(tree)
        )
        if not dynamic:
            for function in [
                n
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.decorator_list
            ]:
                local = {
                    a.arg
                    for a in [
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
                        *([function.args.vararg] if function.args.vararg else []),
                        *([function.args.kwarg] if function.args.kwarg else []),
                    ]
                }
                local.update(
                    n.id
                    for n in ast.walk(function)
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                )
                local.update(
                    n.name
                    for n in ast.walk(function)
                    if isinstance(n, ast.ExceptHandler) and n.name
                )
                local.update(
                    n.name
                    for n in ast.walk(function)
                    if isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name
                )
                local.update(
                    n.rest for n in ast.walk(function) if isinstance(n, ast.MatchMapping) and n.rest
                )
                # Complex nested scopes are explicitly excluded from this rule.
                if any(
                    isinstance(
                        n,
                        (
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef,
                            ast.Lambda,
                            ast.ListComp,
                            ast.SetComp,
                            ast.DictComp,
                            ast.GeneratorExp,
                        ),
                    )
                    for stmt in function.body
                    for n in ast.walk(stmt)
                ):
                    continue
                for n in ast.walk(function):
                    if (
                        isinstance(n, ast.Name)
                        and isinstance(n.ctx, ast.Load)
                        and n.id not in global_names | local
                    ):
                        found.append(
                            dict(
                                kind="undefined_symbol",
                                path=path,
                                line=n.lineno,
                                message=f"Name {n.id} has no declaration in the analyzed lexical/module scopes.",
                                root_cause="No parameter, local binding, explicit import, module declaration or builtin establishes this name. Runtime injection remains possible.",
                                fix=f"Declare or import {n.id}, check its spelling, or document how runtime injection supplies it.",
                                confidence="medium",
                            )
                        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                parts = list(PurePosixPath(path).parent.parts)
                if node.level > len(parts) + 1:
                    continue
                prefix = parts[: len(parts) - node.level + 1]
                if node.module:
                    target = "/".join(prefix + node.module.split("."))
                    if target + ".py" not in files and target + "/__init__.py" not in files:
                        found.append(
                            dict(
                                kind="missing_relative_import",
                                path=path,
                                line=node.lineno,
                                message=f"Relative import target {target} is not present in the indexed snapshot.",
                                root_cause="The explicitly relative module has no matching indexed .py file or package. It may be generated or excluded from indexing.",
                                fix=f"Check the relative import spelling and package location for {target}; also inspect indexing coverage and generated-file rules.",
                                confidence="medium",
                            )
                        )
            # Only straight-line siblings after a terminating statement.
            for field in ("body", "orelse", "finalbody"):
                body = getattr(node, field, None)
                if not isinstance(body, list):
                    continue
                terminated = False
                for statement in body:
                    if terminated and isinstance(statement, ast.stmt):
                        found.append(
                            dict(
                                kind="unreachable_statement",
                                path=path,
                                line=statement.lineno,
                                end_line=statement.end_lineno,
                                message="Statement follows an unconditional terminating statement in the same block.",
                                root_cause="The preceding return, raise, break or continue exits this block before this statement.",
                                fix="Remove the unreachable statement or move it before the terminator if it must execute.",
                                confidence="high",
                            )
                        )
                        break
                    if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                        terminated = True
        # Signature checks limited to direct top-level calls, no starred args,
        # decorators, reassigned names, methods or nested/dynamic receivers.
        reassigned = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
        }
        for statement in tree.body:
            for call in (
                ast.walk(statement)
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                else []
            ):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                target = definitions.get(call.func.id)
                if (
                    not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef))
                    or target.decorator_list
                    or call.func.id in reassigned
                ):
                    continue
                if any(isinstance(a, ast.Starred) for a in call.args) or any(
                    k.arg is None for k in call.keywords
                ):
                    continue
                args = target.args
                positional = args.posonlyargs + args.args
                if not args.vararg and len(call.args) > len(positional):
                    found.append(
                        dict(
                            kind="signature_mismatch",
                            path=path,
                            line=call.lineno,
                            end_line=call.end_lineno,
                            message=f"Call to {target.name} supplies {len(call.args)} positional arguments; its direct definition accepts at most {len(positional)}.",
                            root_cause="A direct, undecorated top-level function is called with too many positional arguments.",
                            fix=f"Adjust the arguments to match {target.name}'s declared signature, or update that signature if intentional.",
                            confidence="high",
                            severity="error",
                        )
                    )
    return found
