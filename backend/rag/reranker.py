"""Deterministic structural reranking; same-owner definitions beat homonyms."""

import re


def structural_score(item, question, references):
    language_names = {
        "python": r"\bpython\b",
        "java": r"\bjava\b",
        "javascript": r"\bjavascript\b",
        "typescript": r"\btypescript\b",
        "cpp": r"c\+\+",
        "csharp": r"c#|\bcsharp\b",
        "rust": r"\brust\b",
    }
    requested = {
        language
        for language, pattern in language_names.items()
        if re.search(pattern, question, re.I)
    }
    if re.search(r"\bGo\b|\bgo (?:language|package|module)\b", question):
        requested.add("go")
    if re.search(r"\bC (?:language|code|function)|\bthe C\b", question):
        requested.add("c")
    language_score = (
        3
        if item.get("language") in requested
        else -2
        if requested and item.get("language") not in requested | {"text"}
        else 0
    )
    metadata_penalty = (
        -2
        if item.get("kind") in ("parameter", "type_reference", "exception_reference", "dependency")
        and not re.search(
            r"\b(?:parameters?|annotations?|types?|dependencies|manifest|exceptions?)\b",
            question,
            re.I,
        )
        else 0
    )
    qualified = item["qualified"].lower()
    exact = any(qualified == r or qualified.endswith("." + r) for r in references)
    owner = qualified.rsplit(".", 1)[0].rsplit(".", 1)[-1]
    owner_match = bool(owner and re.search(r"\b" + re.escape(owner) + r"\b", question.lower()))
    scoped = any(("." + r + ".") in ("." + qualified + ".") for r in references)
    wrong_owner = (
        bool(references)
        and not exact
        and item["name"].lower() in {r.rsplit(".", 1)[-1] for r in references}
    )
    return (
        language_score
        + metadata_penalty
        + (
            (3 if exact else 0)
            + (2 if scoped else 0)
            + (1 if owner_match else 0)
            - (2 if wrong_owner else 0)
        )
    )


def rerank(ids, metadata, scores, question, references, weight):
    return sorted(
        ids,
        key=lambda sid: (
            -(scores.get(sid, 0) + weight * structural_score(metadata[sid], question, references)),
            metadata[sid]["qualified"],
            sid,
        ),
    )
