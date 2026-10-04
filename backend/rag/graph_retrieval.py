"""Direction-aware relationship weights for bounded structural expansion."""


def relationship_weight(edge, current):
    weight = {
        "contains": 0.25,
        "accepts": 0.08,
        "returns": 0.08,
        "raises": 0.12,
        "defines": 0.2,
        "depends_on": 0.2,
    }.get(edge["kind"], 0.85)
    weight *= 1 if edge["confidence"] == "exact" else 0.6
    if edge["kind"] == "calls" and edge["source"] != current:
        weight *= 0.65
    if edge["kind"] in ("inherits", "implements") and edge["source"] != current:
        weight *= 0.15
    return weight
