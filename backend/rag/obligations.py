"""Question obligations guide source reads; they never certify answer correctness."""

import re

from ..question_analysis import answer_aspects, symbol_references


def requirements(question):
    """Bounded reading/answer requirements, never facts or a completeness proof.

    Derived only from the user's question, without benchmark references. The
    generic dimensions spell out what to inspect; source-dependent alternatives
    remain a model reading task rather than fabricated repository facts.
    """
    rows = []
    for number, aspect in enumerate(answer_aspects(question), 1):
        details = [("core", aspect)]
        for key, pattern, detail in (
            (
                "conditions",
                r"\b(?:if|when|unless|otherwise|conditions?|versus)\b",
                "State exact conditions and alternatives; include negation and enclosing guards.",
            ),
            (
                "results",
                r"\b(?:yield\w*|return\w*|result|collection|type|orient\w*)\b",
                "State the actual yielded or returned value; explain only the result details requested in this aspect.",
            ),
            (
                "calls",
                r"\b(?:used|calls?|helper|algorithm|dispatch|delegat\w*)\b",
                "Name the actual calls with argument expressions; trace returned values through caller assignments and state updates to return or yield.",
            ),
            (
                "errors",
                r"\b(?:raise\w*|error\w*|exception\w*|invalid|failure|cleanup|finally)\b",
                "For each requested error or cleanup path, state its precise trigger and chaining; an error message is not the trigger.",
            ),
            (
                "state",
                r"\b(?:skip\w*|cache\w*|state|reuse\w*|publish\w*|update\w*)\b",
                "Explain the checks and state changes, including their order relative to the result or yield.",
            ),
            (
                "order",
                r"\b(?:before|after|first|order|precedence|priority)\b",
                "Explain the requested order and early exits using executable checks, not textual position alone.",
            ),
        ):
            if re.search(pattern, aspect, re.I):
                details.append((key, detail))
        # Enumerated cases should not disappear behind one generic claim.
        enumeration = re.search(r"\bfor\s+([^?;]{1,100}?)\s+cases\b", aspect, re.I)
        if enumeration:
            alternatives = re.split(r",\s*(?:and\s+)?|\s+and\s+", enumeration[1])
            if 2 <= len(alternatives) <= 4:
                details.extend(
                    (
                        f"case{i}",
                        f"Explain the {name.strip()} case separately, including its arguments and result.",
                    )
                    for i, name in enumerate(alternatives, 1)
                )
        for key, detail in details[:8]:
            rows.append({"id": f"a{number}.{key}", "aspect_id": number, "detail": detail})
    return rows


def reconcile(requirements, declared, claims):
    """Validate coverage references; coverage remains a fallible model judgment."""
    if declared is None:
        return {"status": "unavailable", "semantic_coverage": "unverified", "items": []}
    expected = {row["id"]: row for row in requirements}
    if not isinstance(declared, list) or len(declared) != len(expected):
        raise ValueError(
            "Requirement coverage must cover every requested requirement exactly once."
        )
    output, seen = [], set()
    for row in declared:
        if not isinstance(row, dict) or set(row) != {"requirement_id", "status", "claim_indices"}:
            raise ValueError("Invalid requirement coverage shape.")
        rid, status, indices = row["requirement_id"], row["status"], row["claim_indices"]
        if not isinstance(rid, str) or rid not in expected or rid in seen:
            raise ValueError("Unknown or duplicate requirement ID.")
        if status not in ("covered", "missing") or not isinstance(indices, list):
            raise ValueError("Invalid requirement coverage status.")
        if len(indices) > 6 or len({i for i in indices if type(i) is int}) != len(indices):
            raise ValueError("Requirement claim indices must be unique integers.")
        if any(
            type(i) is not int
            or not 0 <= i < len(claims)
            or claims[i]["aspect_id"] != expected[rid]["aspect_id"]
            for i in indices
        ):
            raise ValueError("Requirement must reference claims from its own aspect.")
        if status == "covered" and not indices:
            raise ValueError("Covered requirements need claim references.")
        if status == "covered" and any(claims[i]["status"] != "supported" for i in indices):
            status = "missing"
        output.append({**expected[rid], "status": status, "claim_indices": indices})
        seen.add(rid)
    return {"status": "model_reported", "semantic_coverage": "unverified", "items": output}


def checklist(question, evidence):
    identities = [e.get("qualified", "").lower() for e in evidence]
    rows = []
    for number, aspect in enumerate(answer_aspects(question), 1):
        references = sorted(symbol_references(aspect))
        missing = [
            r for r in references if not any(q == r or q.endswith("." + r) for q in identities)
        ]
        dimensions = []
        for name, pattern in (
            (
                "conditions_and_alternatives",
                r"\b(?:if|when|unless|otherwise|both|versus|compare|difference)\b",
            ),
            ("ordering", r"\b(?:before|after|first|order|precedence|priority)\b"),
            ("returns", r"\b(?:return|returns|result|value|none)\b"),
            ("errors_and_cleanup", r"\b(?:exception|error|raise|raises|cleanup|finally|failure)\b"),
            ("cache_and_state", r"\b(?:cache|cached|state|reuse|reused|publish)\b"),
        ):
            if re.search(pattern, aspect, re.I):
                dimensions.append(name)
        rows.append(
            {
                "aspect_id": number,
                "question": aspect,
                "inspect": dimensions,
                "missing_named_definitions": missing,
                "semantic_coverage": "unverified",
            }
        )
    return rows
