"""Small deterministic helpers for splitting compound repository questions."""

import re

_ASK = re.compile(
    r"\b(?:how|where|which|what|why)\b|\bwhen\s+(?:does|did|is|was|will|should|can|do|has|have|would)\b",
    re.I,
)
_TRACE = re.compile(r"\b(?:trace|explain|walk through)\b", re.I)


def question_aspects(question, limit=8):
    """Return the distinct requested parts of a question in their original order.

    This is intentionally a light parser: it preserves code identifiers and uses
    interrogative boundaries rather than splitting on periods, which occur in
    qualified Python names.
    """
    asks = list(_ASK.finditer(question))
    aspects = []

    if asks:
        first_ask = asks[0].start()
        prefix = question[:first_ask]
        trace = _TRACE.search(prefix)
        if trace:
            traced = prefix[trace.end() :].strip(" ,:.-")
            if len(re.findall(r"[A-Za-z0-9_]+", traced)) >= 3:
                aspects.append(traced)

        for index, match in enumerate(asks):
            end = asks[index + 1].start() if index + 1 < len(asks) else len(question)
            aspect = question[match.start() : end].strip(" ,:;.!?-")
            aspect = re.sub(r"\s+", " ", aspect)
            aspect = re.sub(r",?\s+and\s*$", "", aspect, flags=re.I)
            steps = re.split(r"\band\s+(?=(?:then|after|before|on|when)\b)", aspect, flags=re.I)
            for step in steps:
                step = step.strip(" ,:;.!?-")
                if step and step.lower() not in {a.lower() for a in aspects}:
                    aspects.append(step)

    if not aspects:
        aspects = [question.strip()]
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
