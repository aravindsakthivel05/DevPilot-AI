"""Bounded, aspect-aware LangGraph repository investigation.

Coverage is a retrieval heuristic, never a factual-support verdict. Generation
still validates source identity and coordinates and can abstain per aspect.
"""

import re
import time
from copy import deepcopy
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import db
from .question_analysis import answer_aspects
from .retrieval import (
    TRACE,
    answer,
    answer_from_evidence,
    asks_external_state,
    explicit_symbol_references,
    is_multi_stage,
    retrieve,
    tokens,
)
from .search import indexed_candidates
from .test_links import is_test_path


class InvestigationState(TypedDict, total=False):
    repo_id: str
    snapshot: str
    question: str
    mode: str
    limit: int
    hops: int
    use_model: bool
    selected: list[dict]
    primary: list[dict]
    variants: list[str]
    coverage: list[dict]
    warning: str | None
    semantic_used: bool
    passes: int
    rounds: int
    novelty: int
    steps: list[str]
    result: dict
    retrieval_traces: list[dict]


def _small(items):
    return [
        {
            key: item.get(key, []) if key == "public_aliases" else item[key]
            for key in ("id", "name", "qualified", "score", "reason", "traversal", "public_aliases")
        }
        for item in items
    ]


def _relevance(item, aspect, question):
    terms = set(tokens(aspect))
    names = set(tokens(item["qualified"]))
    source = set(tokens(item.get("source", "")))
    score = (3 * len(terms & names) + 0.2 * len(terms & source)) / max(1, len(terms) ** 0.5)
    score += len(terms & names) / max(1, len(names))
    named_owners = re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", question)
    if set(named_owners) & set(item["qualified"].split(".")):
        score += 2
    if item.get("kind") in ("class", "interface", "module"):
        score *= 0.65
    if is_test_path(item["path"]) and not re.search(
        r"\b(?:tests?|behavior|behaviour|contract)\b", question, re.I
    ):
        score *= 0.5
    return score


def _guard(state):
    if asks_external_state(state["question"]):
        return {
            "result": answer(
                state["repo_id"], state["question"], mode=state["mode"], use_model=False
            ),
            "steps": ["external-state guard"],
            "passes": 0,
            "coverage": [],
        }
    return {"steps": ["snapshot check"], "rounds": 0}


def _primary(state):
    evidence, warning, semantic = retrieve(
        state["repo_id"], state["question"], state["mode"], state["limit"], state["hops"]
    )
    return {
        "retrieval_traces": [deepcopy(TRACE.get())],
        "selected": _small(evidence),
        "primary": _small(evidence),
        "warning": warning,
        "semantic_used": semantic,
        "passes": 1,
        "steps": state["steps"] + ["primary retrieval"],
    }


def _assess(state):
    records = db.symbols_by_ids(state["repo_id"], [item["id"] for item in state["selected"]])
    coverage = []
    for i, aspect in enumerate(answer_aspects(state["question"]), 1):
        ranked = sorted(
            records, key=lambda item: _relevance(item, aspect, state["question"]), reverse=True
        )
        candidates = [
            item for item in ranked[:2] if _relevance(item, aspect, state["question"]) >= 0.75
        ]
        coverage.append(
            {
                "aspect_id": i,
                "question": aspect,
                "status": "candidate_evidence" if candidates else "missing_candidate_evidence",
                "candidate_ids": [item["id"] for item in candidates],
                "factual_support_verified": False,
            }
        )
    # A first focused pass for compound questions ensures that a large entry
    # function's lexical overlap doesn't suppress helper investigation.
    if state["rounds"] == 0 and is_multi_stage(state["question"]):
        variants = [item["question"] for item in coverage]
    else:
        variants = [item["question"] for item in coverage if not item["candidate_ids"]]
    if state["rounds"] >= 2 or (state["rounds"] and state.get("novelty", 0) == 0):
        variants = []
    return {
        "coverage": coverage,
        "variants": variants[:6],
        "steps": state["steps"] + ["aspect candidate coverage"],
    }


def _followup(state):
    selected_ids = {item["id"] for item in state["selected"]}
    pool = {item["id"]: item for item in state["selected"]}
    warnings = [state["warning"]] if state.get("warning") else []
    passes = state["passes"]
    traces = list(state.get("retrieval_traces", []))
    for variant in state["variants"]:
        evidence, warning, _ = retrieve(state["repo_id"], variant, "lexical", 24, 0)
        passes += 1
        traces.append(deepcopy(TRACE.get()))
        for item in evidence:
            pool.setdefault(item["id"], item)
        if warning:
            warnings.append(warning)
    _, metadata, graph, _ = indexed_candidates(state["repo_id"], state["question"], tokens)
    lookup = {item["id"]: item for item in metadata}
    # Prefer direct outgoing calls; containment siblings are considered only
    # when the question explicitly names their class or symbol.
    roots = set(selected_ids)
    related = {}
    for _ in range(min(2, state["hops"])):
        next_roots = set()
        for edge in graph:
            if edge["kind"] not in (
                "calls",
                "inherits",
                "decorated_by",
                "type_stub_for",
                "aliases",
            ):
                continue
            if edge["source"] in roots and edge["target"] in lookup:
                related[edge["target"]] = edge
                next_roots.add(edge["target"])
        roots = next_roots - selected_ids
    for record in db.symbols_by_ids(state["repo_id"], sorted(related)):
        edge = related[record["id"]]
        pool.setdefault(
            record["id"],
            {
                **record,
                "score": 0,
                "reason": f"{edge['kind']} relationship with {lookup[edge['source']]['name']}",
                "traversal": [edge],
            },
        )
    records = {r["id"]: r for r in db.symbols_by_ids(state["repo_id"], list(pool))}
    pool = {sid: {**item, **records[sid]} for sid, item in pool.items() if sid in records}
    aspects = answer_aspects(state["question"])
    refs = explicit_symbol_references(state["question"])
    chosen = []

    def add(item):
        if len(chosen) < state["limit"] and item["id"] not in {r["id"] for r in chosen}:
            chosen.append(item)

    exact = [
        item
        for item in pool.values()
        if any(
            item["qualified"].lower() == ref or item["qualified"].lower().endswith("." + ref)
            for ref in refs
        )
    ]
    for item in exact:
        add(item)
    for primary in state["selected"][: max(1, state["limit"] // 2)]:
        if primary["id"] in pool:
            add(pool[primary["id"]])
    # Give every obligation a slot before filling the remaining slots globally.
    for aspect in aspects:
        ranked = sorted(
            pool.values(),
            key=lambda item: (
                _relevance(item, aspect, state["question"]) + (1.0 if item["id"] in related else 0),
                item["qualified"],
            ),
            reverse=True,
        )
        best = next((item for item in ranked if item["id"] not in {r["id"] for r in chosen}), None)
        if best:
            add(best)
    ranked = sorted(
        pool.values(),
        key=lambda item: (
            max((_relevance(item, a, state["question"]) for a in aspects), default=0)
            + (1.0 if item["id"] in related else 0),
            item["qualified"],
        ),
        reverse=True,
    )
    for item in ranked:
        add(item)
    # Preserve the original ranked evidence. Focused investigation adds a
    # bounded supplement instead of displacing useful baseline sources.
    combined = list(state["primary"])
    primary_ids = {item["id"] for item in combined}
    combined.extend(item for item in _small(chosen) if item["id"] not in primary_ids)
    combined = combined[:15]
    return {
        "retrieval_traces": traces,
        "selected": combined,
        "novelty": len({i["id"] for i in chosen} - selected_ids),
        "rounds": state["rounds"] + 1,
        "passes": passes,
        "warning": "; ".join(dict.fromkeys(warnings)) or None,
        "steps": state["steps"] + ["targeted aspect and outgoing-relationship retrieval"],
    }


def _compose(state):
    records = db.symbols_by_ids(state["repo_id"], [item["id"] for item in state["selected"]])
    metadata = {item["id"]: item for item in state["selected"]}
    _, all_metadata, _, _ = indexed_candidates(state["repo_id"], state["question"], tokens)
    alias_lookup = {r["id"]: r.get("public_aliases", []) for r in all_metadata}
    evidence = [
        {
            **record,
            **metadata[record["id"]],
            "truncated": False,
            "public_aliases": alias_lookup.get(record["id"], []),
        }
        for record in records
    ]
    result = answer_from_evidence(
        state["repo_id"],
        state["question"],
        evidence,
        state["warning"],
        state["semantic_used"],
        state["mode"],
        state["use_model"],
    )
    result["retrieval_trace"] = {
        "question": state["question"],
        "workflow": "optional_langgraph",
        "passes": state.get("retrieval_traces", []),
        "generation_pass": result.get("retrieval_trace"),
    }
    return {"result": result, "steps": state["steps"] + ["answer provenance and citation checks"]}


def build_graph():
    builder = StateGraph(InvestigationState)
    for name, node in [
        ("guard", _guard),
        ("primary", _primary),
        ("assess", _assess),
        ("followup", _followup),
        ("compose", _compose),
    ]:
        builder.add_node(name, node)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges(
        "guard",
        lambda s: "done" if "result" in s else "primary",
        {"done": END, "primary": "primary"},
    )
    builder.add_edge("primary", "assess")
    builder.add_conditional_edges(
        "assess",
        lambda s: "followup" if s["variants"] else "compose",
        {"followup": "followup", "compose": "compose"},
    )
    builder.add_edge("followup", "assess")
    builder.add_edge("compose", END)
    return builder.compile()


GRAPH = build_graph()


def investigate(repo_id, question, mode="hybrid", limit=8, hops=2, use_model=True):
    TRACE.set(None)
    started = time.perf_counter()
    repo = db.repository(repo_id)
    if not repo or repo["status"] != "ready":
        raise ValueError("Repository is not ready.")
    state = GRAPH.invoke(
        {
            "repo_id": repo_id,
            "snapshot": repo["fingerprint"],
            "question": question,
            "mode": mode,
            "limit": limit,
            "hops": hops,
            "use_model": use_model,
        }
    )
    if db.repository(repo_id)["fingerprint"] != repo["fingerprint"]:
        raise ValueError("Repository snapshot changed during investigation.")
    result = state["result"]
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    result["workflow"] = {
        "engine": "langgraph",
        "steps": state["steps"],
        "retrieval_passes": state["passes"],
        "investigation_rounds": state.get("rounds", 0),
        "candidate_coverage": state["coverage"],
    }
    return result
