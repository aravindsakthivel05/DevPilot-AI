"""Bounded excerpts with stable original-file coordinates and identity checks.

These checks establish provenance and lexical relevance, not semantic entailment.
"""

import ast
import math
import re
import textwrap

from .question_analysis import answer_aspects

REFERENCE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")


def estimated_tokens(text):
    """Conservative planning estimate; provider usage remains the measured value."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def _terms(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return {
        t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 1
    }


def excerpt(record, question, token_budget):
    lines = record["source"].splitlines()
    excluded = set()
    returned_calls = []
    if record.get("path", "").endswith(".py"):
        try:
            tree = ast.parse(textwrap.dedent(record["source"]))
            if tree.body and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
                pending = [tree.body[0]]
                while pending:
                    for child in ast.iter_child_nodes(pending.pop()):
                        if isinstance(
                            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
                        ):
                            continue
                        if isinstance(child, ast.Return) and isinstance(child.value, ast.Call):
                            returned_calls.append(child.value)
                        pending.append(child)
                returned_calls.sort(key=lambda call: call.lineno)
            for node in ast.walk(tree):
                if (
                    isinstance(
                        node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                    )
                    and node.body
                ):
                    first = node.body[0]
                    if (
                        isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)
                    ):
                        excluded.update(range(first.lineno - 1, first.end_lineno))
            excluded.update(i for i, line in enumerate(lines) if line.lstrip().startswith("#"))
        except SyntaxError:
            pass
    terms = _terms(question)
    ranked = sorted(
        (i for i in range(len(lines)) if i not in excluded),
        key=lambda i: (len(terms & _terms(lines[i])), -i),
        reverse=True,
    )
    selected = set()
    used = 0
    # Preserve the declaration and neighborhoods of relevant calls/conditions,
    # rather than always retaining only the beginning of a large function.
    windows = [range(min(3, len(lines)))]
    # Argument-only fragments cannot establish which function is invoked.
    # Reserve the callee and requested keyword values before declaration windows.
    for call in returned_calls[:2]:
        windows.append(range(max(0, call.lineno - 2), min(len(lines), call.lineno + 3)))
        relevant_keywords = sorted(
            (keyword for keyword in call.keywords if keyword.arg and terms & _terms(keyword.arg)),
            key=lambda keyword: (len(terms & _terms(keyword.arg)), -keyword.lineno),
            reverse=True,
        )[:3]
        for keyword in relevant_keywords:
            windows.append(range(max(0, keyword.lineno - 2), min(len(lines), keyword.lineno + 2)))
    # Reserve neighborhoods for distinct obligations before filling by global
    # overlap. Snake-case names match ordinary words such as forward hooks.
    for aspect in answer_aspects(question):
        focus = _terms(aspect)
        candidates = sorted(
            (i for i in ranked if focus & _terms(lines[i])),
            key=lambda i: (len(focus & _terms(lines[i])), "(" in lines[i], -i),
            reverse=True,
        )
        anchors = []
        for i in candidates:
            if all(abs(i - previous) >= 5 for previous in anchors):
                anchors.append(i)
            if len(anchors) == 2:
                break
        windows.extend(range(max(0, i - 2), min(len(lines), i + 4)) for i in anchors)
    windows += [range(max(0, i - 2), min(len(lines), i + 4)) for i in ranked]
    for window in windows:
        missing = [i for i in window if i not in selected and i not in excluded]
        cost = sum(estimated_tokens(lines[i] + "\n") for i in missing)
        if used + cost <= token_budget:
            selected.update(missing)
            used += cost
    indices = sorted(selected)
    while indices and not lines[indices[-1]].strip():
        indices.pop()
    start = record.get("start_line", 1)
    return {
        **record,
        "source": "\n".join(lines[i] for i in indices),
        "source_line_numbers": [start + i for i in indices],
        "truncated": len(indices) < len(lines),
        "estimated_source_tokens": used,
    }


def source_lines(item):
    lines = item["source"].splitlines()
    numbers = item.get("source_line_numbers")
    if numbers is None:
        numbers = list(range(item.get("start_line", 1), item.get("start_line", 1) + len(lines)))
    if len(numbers) != len(lines) or len(set(numbers)) != len(numbers):
        raise ValueError("Excerpt line mapping is invalid.")
    return dict(zip(numbers, lines))


def identity_supported(reference, items):
    """Require named owners to match a source identity or an explicit code reference."""
    reference = reference.lower()
    for item in items:
        if reference.endswith((".py", ".java", ".md", ".toml", ".json", ".yaml", ".yml")) and (
            item["path"].lower() == reference or item["path"].lower().endswith("/" + reference)
        ):
            return True
        for alias in item.get("public_aliases", []):
            if alias.lower() == reference or alias.lower().startswith(reference + "."):
                return True
        qualified = item["qualified"].lower()
        if qualified == reference or qualified.endswith("." + reference):
            return True
        if "." not in reference and reference in qualified.split("."):
            return True
        if "." not in reference and re.search(
            r"\b(?:except|raise|catch|throws|new)\s*(?:\(\s*)?(?:[A-Za-z_]\w*\.)*"
            + re.escape(reference)
            + r"\b",
            item["source"],
            re.I,
        ):
            return True
        # A caller can establish that a named method is called, but bare method
        # declarations in a similarly named class cannot establish that identity.
        if re.search(r"(?<![\w.])" + re.escape(reference) + r"(?!\w)", item["source"], re.I):
            return True
        if re.search(
            r"(?<![\w.])(?:self|cls|this)\." + re.escape(reference) + r"(?!\w)",
            item["source"],
            re.I,
        ):
            return True
    return False
