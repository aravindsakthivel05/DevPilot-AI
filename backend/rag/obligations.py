"""Question obligations guide source reads; they never certify answer correctness."""

import re

from ..question_analysis import answer_aspects, symbol_references


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
