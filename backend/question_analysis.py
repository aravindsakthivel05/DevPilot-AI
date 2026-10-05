"""Small deterministic helpers for splitting compound repository questions."""

import re

_ASK = re.compile(
    r"\b(?:how|where|which|what|why)\b|\bwhen\s+(?:does|did|is|was|will|should|can|do|has|have|would)\b",
    re.I,
)
_TRACE = re.compile(r"\b(?:trace|explain|walk through)\b", re.I)


def symbol_references(question):
    """Identifiers explicitly written by the user, including unqualified methods."""
    references = set(re.findall(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b", question))
    references.update(re.findall(r"`([A-Za-z_]\w*)`", question))
    for word in re.findall(r"\b[A-Za-z_]\w*\b", question):
        if "_" in word or re.search(r"[a-z][A-Z]", word):
            references.add(word)
    return {r.lower() for r in references}


def code_query(question):
    """Small language-independent vocabulary bridges; never repository facts."""
    concepts = {
        r"\basynchronous\b": "async",
        r"\b(?:stop|stops|stopping)\b": "break cascade",
        r"\b(?:oversized|too large)\b": "max bytes limit",
        r"\b(?:clean.?up|cleaned up)\b": "finally delete remove",
        r"\b(?:reject|rejection)\b": "reject error",
        r"\bfallible\b": "try result error non panicking",
        r"\bsingle[- ]value\b": "one value",
        r"\blookup\b": "get access",
        r"\b(?:supplied|explicit)\b.{0,30}\b(?:CLI\s+)?arguments\b": "from args",
    }
    additions = [value for pattern, value in concepts.items() if re.search(pattern, question, re.I)]
    return question + (" " + " ".join(additions) if additions else "")


def question_aspects(question, limit=8):
    """Return the distinct requested parts of a question in their original order.

    This is intentionally a light parser: it preserves code identifiers and uses
    interrogative boundaries rather than splitting on periods, which occur in
    qualified Python names.
    """
    asks = list(_ASK.finditer(question))
    aspects = []
    scope = ""

    if asks:
        first_ask = asks[0].start()
        prefix = question[:first_ask]
        trace = _TRACE.search(prefix)
        if trace:
            traced = prefix[trace.end() :].strip(" ,:.-")
            if len(re.findall(r"[A-Za-z0-9_]+", traced)) >= 3:
                aspects.append(traced)
        elif re.match(r"\s*(?:for|in|within|when|at|regarding|given|using|with)\b", prefix, re.I):
            # Retain caller-supplied scope in every obligation. Dropping it can
            # turn explicit-argument questions into environment-argument ones.
            scope = re.sub(r"\s+", " ", prefix).strip(" ,:;.!?-")

        for index, match in enumerate(asks):
            end = asks[index + 1].start() if index + 1 < len(asks) else len(question)
            aspect = question[match.start() : end].strip(" ,:;.!?-")
            aspect = re.sub(r"\s+", " ", aspect)
            aspect = re.sub(r",?\s+and\s*$", "", aspect, flags=re.I)
            # Preserve coordinated noun obligations, not only verb phrases.
            # "arguments, options, priority and queue" must not collapse into
            # one aspect with a three-claim limit.
            listing = re.match(
                r"(how\s+(?:are|do|does|will|can)\s+)(.+?,.+?)(\s+(?:carried|configured|handled|passed|restored|change|affect|influence|control|work|behave)\b.*)",
                aspect,
                re.I,
            )
            categories = re.match(r"(.*\bdistinguish\s+)(.+?,.+?)(\s+exceptions)$", aspect, re.I)
            if listing or categories:
                parts = re.split(r",\s*|\s+and\s+", (listing or categories).group(2))
                if 2 <= len(parts) <= 6:
                    header, _, tail = (listing or categories).groups()
                    aspects.extend(header + part.strip() + tail for part in parts if part.strip())
                    continue
            objects = re.match(
                r"(.+?\b(?:control|handle|affect|manage|implement|support)\s+)([^,;?]+,[^;?]+)$",
                aspect,
                re.I,
            )
            if objects:
                parts = re.split(r",\s*|\s+and\s+", objects[2])
                if 2 <= len(parts) <= 6:
                    aspects.extend(objects[1] + part.strip() for part in parts if part.strip())
                    continue
            steps = re.split(r"\band\s+(?=(?:then|after|before|on|when)\b)", aspect, flags=re.I)
            for step in steps:
                step = step.strip(" ,:;.!?-")
                # Split coordinated actions, not arbitrary nouns or code names.
                # "fetch and cache results and hand off SQL" has three obligations
                # even though it has only one interrogative and is a short question.
                actions = re.split(
                    r",\s*(?=(?:call|run|fetch|cache|hand|populate|assemble|return|validate|install|rebuild|prepare|reach|construct|send|select|create|configure|clean|finish|obtain|handle|delegate)\b)"
                    r"|\s+and\s+(?=(?:call|run|fetch|cache|hand|populate|assemble|return|validate|install|rebuild|prepare|reach|construct|send|select|create|configure|clean|finish|obtain|handle|delegate)\b)",
                    step,
                    flags=re.I,
                )
                for action in actions:
                    if action and action.lower() not in {a.lower() for a in aspects}:
                        aspects.append(action)

    if not aspects:
        aspects = [question.strip()]
    if _TRACE.search(question) and len(aspects) == 1:
        steps = re.split(r"\s+(?:through|into|then|to)\s+", aspects[0], flags=re.I)
        if len(steps) > 1 and all(len(re.findall(r"[A-Za-z0-9_]+", step)) >= 3 for step in steps):
            aspects = steps
    if scope:
        aspects = [scope + ", " + aspect for aspect in aspects]
    return aspects[:limit]


def answer_aspects(question, limit=6):
    """Keep distinct answer obligations for multi-stage questions when feasible."""
    aspects = question_aspects(question)
    if len(aspects) <= limit:
        return aspects
    group_size = (len(aspects) + limit - 1) // limit
    return [
        "; ".join(aspects[start : start + group_size])
        for start in range(0, len(aspects), group_size)
    ]


def analyze_query(question):
    patterns = [
        ("test_suggestion", r"regression|test.*(?:add|suggest|generate)"),
        ("fix_suggestion", r"\bfix|patch|repair"),
        ("root_cause", r"root.cause|why.*fail"),
        ("error", r"\bbug|error|exception|failing"),
        ("call_flow", r"\btrace|flow|reach|callers|callees|calls"),
        ("dependency", r"depend|import|inherit"),
        ("architecture", r"architecture|structure|overview"),
        ("comparison", r"compare|difference|versus"),
        ("symbol_lookup", r"where.*(?:defined|implemented)|definition"),
        ("repository_summary", r"summar|purpose"),
    ]
    return {
        "type": next(
            (name for name, pattern in patterns if re.search(pattern, question, re.I)),
            "implementation",
        ),
        "entities": sorted(symbol_references(question)),
        "aspects": answer_aspects(question),
    }
