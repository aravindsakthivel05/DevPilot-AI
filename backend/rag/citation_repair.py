"""Expand valid citations within evidence already supplied to the model.

This repairs provenance, not factual content. Expanded claims still go through
identity checks and the fallible reviewer. Missing lines are never invented.
"""

import ast
import re
import textwrap

from ..evidence import REFERENCE, identity_supported, source_lines


def _tree(item):
    lines = source_lines(item)
    if not lines or not item["path"].endswith(".py"):
        return None, lines, 0
    first = min(lines)
    source = "\n".join(lines.get(n, "") for n in range(first, max(lines) + 1))
    try:
        return ast.parse(textwrap.dedent(source)), lines, first - 1
    except (SyntaxError, ValueError):
        return None, lines, first - 1


def _ranges(numbers, sid):
    result = []
    for number in sorted(numbers):
        if (
            result
            and number == result[-1]["end_line"] + 1
            and (number - result[-1]["start_line"] < 80)
        ):
            result[-1]["end_line"] = number
        else:
            result.append({"source_id": sid, "start_line": number, "end_line": number})
    return result


def repair(claim, sources):
    """Return an expanded copy and an auditable record, or keep the original."""
    if claim["status"] != "supported" or not claim["citations"]:
        return claim, []
    selected = {}
    for citation in claim["citations"]:
        sid, first, last = (citation.get(k) for k in ("source_id", "start_line", "end_line"))
        if (
            any(type(n) is not int for n in (sid, first, last))
            or sid not in sources
            or not 1 <= first <= last
            or last - first >= 80
        ):
            return claim, []
        available = source_lines(sources[sid])
        if any(n not in available for n in range(first, last + 1)):
            return claim, []
        selected.setdefault(sid, set()).update(range(first, last + 1))
    original = {sid: set(numbers) for sid, numbers in selected.items()}
    # A workflow claim may name both caller and callee while citing only one.
    # Add an exact supplied implementation identity, never a guessed alias.
    for reference in REFERENCE.findall(claim["text"]):
        if identity_supported(reference, [sources[sid] for sid in selected]):
            continue
        matches = [
            (sid, item)
            for sid, item in sources.items()
            if item["qualified"].lower().endswith("." + reference.lower())
            or item["qualified"].lower() == reference.lower()
        ]
        if len(matches) == 1:
            sid, item = matches[0]
            available = source_lines(item)
            if available:
                selected.setdefault(sid, set()).add(min(available))
    for sid, numbers in selected.items():
        item = sources[sid]
        tree, lines, offset = _tree(item)
        if tree is None:
            continue
        cited = set(numbers)
        for node in ast.walk(tree):
            if not hasattr(node, "lineno"):
                continue
            start, end = offset + node.lineno, offset + node.end_lineno
            if not any(start <= n <= end for n in cited):
                continue
            if isinstance(
                node,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.ExceptHandler,
                ),
            ):
                body = node.body
                header_end = offset + body[0].lineno - 1 if body else start
                numbers.update(n for n in range(start, header_end + 1) if n in lines)
                if (
                    isinstance(node, ast.If)
                    and node.orelse
                    and any(offset + node.orelse[0].lineno <= n <= end for n in cited)
                ):
                    numbers.update(
                        n
                        for n in range(
                            offset + body[-1].end_lineno + 1, offset + node.orelse[0].lineno
                        )
                        if n in lines
                    )
            if isinstance(node, ast.Try):
                # Keep cleanup/handler keywords that explain exceptional control flow.
                for n in range(start, end + 1):
                    if n in lines and re.match(r"\s*(?:except\b|finally\s*:|try\s*:)", lines[n]):
                        numbers.add(n)
        if re.search(r"\breturns?\b", claim["text"], re.I):
            # Include actual return sites for assigned values. For an implicit
            # return, retain a complete small implementation for review.
            returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
            numbers.update(
                offset + line
                for n in returns
                for line in range(n.lineno, n.end_lineno + 1)
                if offset + line in lines
            )
            if not returns and item.get("executable_complete", not item.get("truncated", False)):
                if len(lines) <= 80:
                    numbers.update(lines)
        # Fill only short, available gaps; omitted source stays omitted.
        low, high = min(numbers), max(numbers)
        if high - low < 80 and all(n in lines for n in range(low, high + 1)):
            numbers.update(range(low, high + 1))
    citations = [c for sid, ns in selected.items() for c in _ranges(ns, sid)]
    if len(citations) > 4 or citations == claim["citations"]:
        return claim, []
    return {**claim, "citations": citations}, [
        {"source_id": sid, "added_lines": sorted(ns - original.get(sid, set()))}
        for sid, ns in selected.items()
        if ns != original.get(sid, set())
    ]


def return_evidence(claim, items, cited_text):
    """Allow implicit Python returns only with a complete supplied body."""
    if re.search(r"\breturn\b|=>|\blambda\b", cited_text):
        return True
    for item in items:
        tree, _, _ = _tree(item)
        if tree and item.get("executable_complete", not item.get("truncated", False)):
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in tree.body):
                if not any(isinstance(n, ast.Return) for n in ast.walk(tree)) and re.search(
                    r"\b(?:None|null|nothing|immediately)\b", claim["text"], re.I
                ):
                    return True
    return False
