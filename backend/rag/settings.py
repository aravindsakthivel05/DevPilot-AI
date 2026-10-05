"""Validated configurable retrieval weights and bounded candidate budgets."""

import math
import os


def number(name, default):
    value = float(os.environ.get("DEVPILOT_" + name, default))
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f"Invalid retrieval setting {name}")
    return value


def settings():
    return {
        "lexical_weight": number("LEXICAL_WEIGHT", 2),
        "semantic_weight": number("SEMANTIC_WEIGHT", 0.5),
        "graph_weight": number("GRAPH_WEIGHT", 0.5),
        "structural_weight": number("STRUCTURAL_WEIGHT", 0.002),
        "exact_boost": number("EXACT_BOOST", 50),
        "candidate_limit": 50,
        "rerank": os.environ.get("DEVPILOT_RERANK", "1").lower() in ("1", "true", "yes"),
    }
