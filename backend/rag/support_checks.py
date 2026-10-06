"""Conservative necessary-support checks, not a general correctness prover."""

import re


def _captured_getter_cache(text):
    # Only the narrow lexical shape of a captured JS/TS getter cache. A local
    # variable inside the getter or an unconditional reassignment is excluded.
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    pattern = (
        r"\b(?:let|var)\s+(\w+)[^;]*;[\s\S]*?\bget\s+\w+\s*\(\s*\)\s*\{\s*"
        r"if\s*\(\s*!\s*\1\s*\)\s*\{([^{}]*)\}\s*return\s+\1\s*;"
    )
    for match in re.finditer(pattern, code):
        name, body = match.groups()
        if (
            re.match(r"\s*" + re.escape(name) + r"\s*=\s*new\b", body)
            and len(re.findall(r"\b" + re.escape(name) + r"\s*=(?!=)", body)) == 1
        ):
            return name
    return None


def support_warning(claim, sources, contextual_names=()):
    sentence = claim["text"]
    text = "\n".join(line["text"] for s in sources for line in s.get("lines", []))
    identities = "\n".join(s.get("qualified", "") for s in sources)
    named = set(re.findall(r"\b[A-Za-z_]\w*\b", sentence))
    code_names = {
        name
        for name in named
        if ("_" in name or re.search(r"[a-z][A-Z]", name))
        and name
        not in ("JavaScript", "TypeScript", "OpenAPI", "GraphQL", "PostgreSQL", "SQLite", "NaN")
    }
    for name in sorted(code_names):
        if name in contextual_names:
            continue
        if not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text + "\n" + identities, re.I):
            # Ordinary terminology can be a component of a snake-case symbol,
            # e.g. WebSocket in websocket_mismatch. Exact configuration names
            # still have to appear in full.
            words = re.findall(
                r"[A-Za-z][A-Za-z0-9]*", (text + "\n" + identities).replace("_", " ")
            )
            if "_" not in name and name.lower() in {word.lower() for word in words}:
                continue
            return f"Named identifier {name} is not established by the cited source."
    if re.search(
        r"\b(?:not reused|never reused|does not cache)\b|\bnew\b.*\beach\b", sentence, re.I
    ):
        cache = _captured_getter_cache(text)
        if cache and re.search(r"\b" + re.escape(cache) + r"\b", sentence, re.I):
            return "A captured getter constructs only on a falsy cache, then returns the cached value; unconditional reconstruction is not established."
    for macro in re.findall(r"^\s*#\s*(?:if|elif)\s+([A-Za-z_]\w*)\s*$", text, re.M):
        if re.search(r"\b" + re.escape(macro) + r"\b", sentence) and re.search(
            r"\b(?:un)?defined\b", sentence, re.I
        ):
            return "A #if/#elif MACRO condition tests its value, not whether it is defined."
    if re.search(r"\b(?:does not|doesn't|never|no explicit)\b", sentence, re.I):
        if any(not s.get("executable_complete", s.get("excerpt_complete", False)) for s in sources):
            return "An incomplete excerpt cannot establish an absence claim."
        identities = [s.get("qualified", "").split(".")[-1] for s in sources]
        if not any(
            name and re.search(r"\b" + re.escape(name) + r"\b", sentence, re.I)
            for name in identities
        ):
            return "Absence must be limited to a named complete implementation, not the whole repository."
    # Preserve the exact type in explicitly contrasted documentation/code facts.
    # Merely mentioning one type from a contrast is not an adequate explanation.
    for left, right in re.findall(
        r"\bas\s+(?:an?\s+)?([A-Za-z_]\w*)\s+(?:instead|rather)\s+(?:of|than)\s+(?:as\s+)?(?:an?\s+)?([A-Za-z_]\w*)",
        text,
    ):
        if re.search(r"\b(?:instead|rather)\b", sentence, re.I) and re.search(
            r"\b" + re.escape(right) + r"\b", sentence
        ):
            if not re.search(r"\b" + re.escape(left) + r"\b", sentence):
                return "The explanation omits the source's exact contrasting data type."
    if re.search(r"\bno\s+(?:failures|errors)\b", sentence, re.I) and not re.search(
        r"\b(?:new|additional|relative|since)\b", sentence, re.I
    ):
        if re.search(r"(?:Count|count|length|size)\s*<=?\s*[A-Za-z_]\w*", text):
            return "A comparison with a baseline does not establish zero total failures."
    if (
        re.search(r"\b(?:stopping|stops?|breaks?)\b", sentence, re.I)
        and re.search(r"\b(?:when|if|whenever|occurs)\b", sentence, re.I)
        and not re.search(r"\b(?:failures?|errors?)\b", sentence, re.I)
    ):
        for condition in re.findall(r"\bif\s*\(([^()\n]{1,300})\)", text):
            if (
                "&&" in condition
                and re.search(r"\bStop\b", condition)
                and re.search(r"(?:Failures|Errors)\.(?:Count|count)\s*>\s*\w+", condition)
            ):
                return "The Stop setting alone is insufficient: the branch also requires an increase in failures."
    return None
