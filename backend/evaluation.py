"""Retrieval experiments with explicit unavailable modes and real ranking metrics."""

import math
import time

from . import db
from .retrieval import retrieve


def metrics(actual, expected, k):
    expected = set(expected)
    ranked = list(dict.fromkeys(actual))[:k]
    gains = [1 if sid in expected else 0 for sid in ranked]
    hits = sum(gains)
    first = next((i + 1 for i, gain in enumerate(gains) if gain), None)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(expected))))
    dcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(gains))
    return {
        "recall": hits / len(expected) if expected else None,
        "precision": hits / len(ranked) if ranked else 0,
        "mrr": 1 / first if first else 0,
        "ndcg": dcg / ideal if ideal else None,
        "all_required_evidence": bool(expected) and expected.issubset(ranked),
    }


def experiment(repo_id, cases, variants=None):
    variants = variants or [
        {"name": "lexical", "mode": "lexical", "hops": 0, "settings": {"rerank": False}},
        {"name": "lexical_structured", "mode": "lexical", "hops": 0},
        {"name": "semantic", "mode": "semantic", "hops": 0},
        {"name": "graph", "mode": "graph", "hops": 2},
        {"name": "hybrid", "mode": "hybrid", "hops": 2},
        {"name": "hybrid_no_reranking", "mode": "hybrid", "hops": 2, "settings": {"rerank": False}},
        {"name": "hybrid_no_graph", "mode": "hybrid", "hops": 0},
        {"name": "hybrid_1hop", "mode": "hybrid", "hops": 1},
        {"name": "hybrid_3hop", "mode": "hybrid", "hops": 3},
        {
            "name": "hybrid_no_semantic",
            "mode": "hybrid",
            "hops": 2,
            "settings": {"semantic_weight": 0},
        },
        {
            "name": "hybrid_no_lexical",
            "mode": "hybrid",
            "hops": 2,
            "settings": {"lexical_weight": 0},
        },
        {
            "name": "hybrid_graph_half",
            "mode": "hybrid",
            "hops": 2,
            "settings": {"graph_weight": 0.5},
        },
        {
            "name": "hybrid_graph_double",
            "mode": "hybrid",
            "hops": 2,
            "settings": {"graph_weight": 2},
        },
        {
            "name": "hybrid_no_structure",
            "mode": "hybrid",
            "hops": 2,
            "settings": {"structural_weight": 0},
        },
    ]
    available = {s["id"] for s in db.symbols(repo_id)}
    for case in cases:
        if not case["expected_ids"] or not set(case["expected_ids"]) <= available:
            raise ValueError("Labels must reference indexed symbol IDs in this snapshot")
    results = []
    for variant in variants:
        rows = []
        for case in cases:
            started = time.perf_counter()
            try:
                if (
                    variant["name"] == "hybrid_no_lexical"
                    and not db.repository(repo_id)["stats"].get("embedding_status") == "ready"
                ):
                    raise ValueError(
                        "No-lexical ablation requires a complete embedding corpus for seed retrieval"
                    )
                evidence, warning, semantic = retrieve(
                    repo_id,
                    case["question"],
                    variant["mode"],
                    limit=10,
                    hops=variant["hops"],
                    overrides=variant.get("settings"),
                )
                actual = [s["id"] for s in evidence]
                rows.append(
                    {
                        "question": case["question"],
                        "available": True,
                        "at_5": metrics(actual, case["expected_ids"], 5),
                        "at_10": metrics(actual, case["expected_ids"], 10),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "retrieved": actual,
                        "semantic_used": semantic,
                        "warning": warning,
                    }
                )
            except ValueError as exc:
                rows.append({"question": case["question"], "available": False, "reason": str(exc)})
        results.append({"variant": variant, "cases": rows})
    return {
        "snapshot": db.repository(repo_id)["fingerprint"],
        "results": results,
        "answer_scores": None,
        "notice": "Retrieval metrics only. Graph mode uses lexical seeds; hybrid can use lexical/semantic seeds. Answer, error and suggestion correctness require separate reviewed labels.",
    }


def detection_metrics(actual, expected):
    """Exact type/file/line labels; never grade causes or fixes implicitly."""

    def key(row):
        return row["type"], row["file"], row["line"]

    observed, truth = {key(r) for r in actual}, {key(r) for r in expected}
    tp = len(observed & truth)
    fp, fn = len(observed - truth), len(truth - observed)
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": None,
        "precision": tp / len(observed) if observed else None,
        "recall": tp / len(truth) if truth else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if observed or truth else None,
        "matching": "exact type/file/line",
        "notice": "Scores depend on complete reviewed labels; static candidates are not execution-confirmed bugs. True negatives require a labelled negative population and are not inferred from unflagged lines.",
    }
