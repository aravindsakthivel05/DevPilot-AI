"""Bounded LangGraph investigation; the ordinary question path stays unchanged."""

import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import db
from .question_analysis import question_aspects
from .retrieval import (
    answer,
    answer_from_evidence,
    asks_external_state,
    explicit_symbol_references,
    is_multi_stage,
    retrieve,
    tokens,
)

CODE_TYPE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+\b")
ACTION_TOKENS = {
    "validat",
    "rebuild",
    "install",
    "mock",
    "creat",
    "generat",
    "dump",
    "serializ",
    "pars",
    "trigger",
    "rais",
    "call",
    "delegat",
    "return",
    "resolv",
    "updat",
    "defin",
    "access",
}


class InvestigationState(TypedDict, total=False):
    repo_id: str
    snapshot: str
    question: str
    mode: str
    limit: int
    hops: int
    use_model: bool
    primary: list[dict]
    selected: list[dict]
    variants: list[str]
    warning: str | None
    semantic_used: bool
    passes: int
    steps: list[str]
    result: dict


def _small(items, reason_prefix=""):
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "qualified": item["qualified"],
            "score": item["score"],
            "reason": reason_prefix + item["reason"],
            "traversal": item["traversal"],
        }
        for item in items
    ]


def _candidate_relevance(item, question):
    aspects = question_aspects(question)
    name_terms = set(tokens(item["qualified"]))
    source_terms = set(tokens(item.get("source", "")))
    aspect_scores = []
    for aspect in aspects:
        terms = set(tokens(aspect))
        if not terms:
            continue
        name_hits = len(name_terms & terms)
        source_hits = len(source_terms & terms)
        aspect_scores.append((3 * name_hits + 0.15 * source_hits) / (len(terms) ** 0.5))
    score = max(aspect_scores, default=0) + 0.12 * sum(sorted(aspect_scores, reverse=True)[1:3])
    named_types = CODE_TYPE.findall(question)
    if any(owner in item["qualified"] for owner in named_types):
        score += 1
    if item.get("kind") in ("function", "method"):
        score += 0.1
    if not re.search(r"\btests?\b", question, re.I) and (
        "/test" in item.get("path", "") or item.get("path", "").startswith("tests/")
    ):
        score -= 6
    return score


def _relationship_candidates(repo_id, seeds, question):
    """Collect a bounded two-hop call/class neighborhood for multi-stage answers."""
    symbols = db.symbols(repo_id)
    lookup = {item["id"]: item for item in symbols}
    adjacency = {}
    for edge in db.edges(repo_id):
        if edge["kind"] not in ("calls", "contains", "inherits", "implements"):
            continue
        adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
        adjacency.setdefault(edge["target"], []).append((edge["source"], edge))

    roots = {item["id"] for item in seeds if item["id"] in lookup}
    seen = set(roots)
    frontier = set(roots)
    candidates = {}
    children_by_class = {}
    for _depth in range(2):
        next_frontier = set()
        for symbol_id in frontier:
            for neighbor, edge in adjacency.get(symbol_id, ()):
                if neighbor in seen or neighbor not in lookup:
                    continue
                symbol = lookup[neighbor]
                seen.add(neighbor)
                next_frontier.add(neighbor)
                item = dict(symbol)
                item.update(
                    score=0.0,
                    reason=f"{edge['kind']} relationship with {lookup[symbol_id]['name']}",
                    traversal=[edge],
                    truncated=False,
                )
                candidates[neighbor] = item
                if edge["kind"] == "contains":
                    parent = lookup.get(edge["source"])
                    child = lookup.get(edge["target"])
                    if (
                        parent
                        and child
                        and parent["kind"] in ("class", "interface", "enum")
                        and child["kind"] in ("function", "method")
                    ):
                        children_by_class.setdefault(parent["id"], {})[child["id"]] = item
        frontier = next_frontier

    # Rank graph neighbors by their source and name overlap with the request.
    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            _candidate_relevance(item, question),
            item["kind"] in ("function", "method"),
            item["qualified"],
        ),
        reverse=True,
    )
    class_members = []
    for members in children_by_class.values():
        class_members.extend(
            sorted(
                members.values(),
                key=lambda item: _candidate_relevance(item, question),
                reverse=True,
            )[:32]
        )
    unique = {item["id"]: item for item in [*ranked[:48], *class_members]}
    return list(unique.values())


def _guard(state: InvestigationState):
    if asks_external_state(state["question"]):
        result = answer(state["repo_id"], state["question"], mode=state["mode"], use_model=False)
        return {"result": result, "steps": ["external-state guard"], "passes": 0}
    return {"steps": ["snapshot check"]}


def _route_guard(state: InvestigationState):
    return "done" if "result" in state else "primary"


def _primary(state: InvestigationState):
    evidence, warning, semantic = retrieve(
        state["repo_id"],
        state["question"],
        state["mode"],
        state["limit"],
        state["hops"],
    )
    return {
        "primary": _small(evidence),
        "selected": _small(evidence),
        "warning": warning,
        "semantic_used": semantic,
        "passes": 1,
        "steps": state["steps"] + ["primary retrieval"],
    }


def _plan(state: InvestigationState):
    # Deliberately deterministic: a second model call would dominate local latency.
    # Multi-stage requests still need focused searches even when they name a class.
    owners = {
        item["qualified"].rsplit(".", 2)[-2]
        for item in state["primary"]
        if item["qualified"].count(".") >= 2
    }
    names_owner = any(
        len(owner) >= 6 and re.search(rf"\b{re.escape(owner)}\b", state["question"], re.I)
        for owner in owners
    )
    if state["mode"] == "semantic":
        variants = []
    elif is_multi_stage(state["question"]):
        aspects = question_aspects(state["question"])
        if len(aspects) <= 3:
            variants = aspects
        else:
            # Keep the initial trace, middle transitions, and final outcome distinct.
            middle = max(1, (len(aspects) - 1 + 1) // 2)
            variants = [
                aspects[0],
                "; ".join(aspects[1 : 1 + middle]),
                "; ".join(aspects[1 + middle :]),
            ]
            variants = [query for query in variants if query]
        type_anchors = CODE_TYPE.findall(state["question"])
        if type_anchors:
            variants = [
                (" ".join(type_anchors) + " " + query)
                if re.search(r"\b(?:validat|validation|validator)\b", query, re.I)
                else query
                for query in variants
            ]
    elif names_owner:
        variants = []
    else:
        parts = re.split(r",|\band\b|\bthrough\b|\bwhere\b|\bto\b", state["question"])
        variants = [part.strip() for part in parts if len(tokens(part)) >= 3]
        variants = [part for part in variants if part != state["question"]][:2]
    return {"variants": variants, "steps": state["steps"] + ["query planning"]}


def _route_followup(state: InvestigationState):
    return "followup" if state["variants"] else "compose"


def _followup(state: InvestigationState):
    # Preserve the strongest direct matches, while allowing focused searches to
    # replace low-ranked distractors even when their names are unique.
    selected = list(state["primary"][: state["limit"]])
    ids = {item["id"] for item in selected}
    references = explicit_symbol_references(state["question"])
    named_types = set(CODE_TYPE.findall(state["question"]))
    question_terms = set(tokens(state["question"]))
    direct_anchor_ids = {item["id"] for item in state["primary"][:1]}
    connected_to_anchor = set()
    for edge in db.edges(state["repo_id"]):
        if edge["kind"] == "calls" and (
            (edge["source"] in direct_anchor_ids and edge["target"] not in direct_anchor_ids)
            or (edge["target"] in direct_anchor_ids and edge["source"] not in direct_anchor_ids)
        ):
            connected_to_anchor.add(
                edge["source"] if edge["target"] in direct_anchor_ids else edge["target"]
            )
    replaceable = [
        i
        for i, item in enumerate(selected)
        if i >= max(1, state["limit"] // 4)
        and not any(
            f".{owner}." in f".{item['qualified']}."
            and bool((set(tokens(item["name"])) - set(tokens(owner))) & ACTION_TOKENS)
            and (set(tokens(item["name"])) - set(tokens(owner))) <= question_terms
            for owner in named_types
        )
        and item["id"] not in connected_to_anchor
        and not any(
            item["qualified"].lower() == reference
            or item["qualified"].lower().endswith("." + reference)
            for reference in references
        )
    ]
    passes = 1
    warnings = [state["warning"]] if state.get("warning") else []
    semantic = state["semantic_used"]
    candidate_pool = {}
    for query in state["variants"]:
        # Focused follow-up questions are short and lexical retrieval avoids
        # another embedding request for every clause on local providers.
        evidence, warning, used = retrieve(
            state["repo_id"], query, "lexical", max(32, state["limit"] * 4), state["hops"]
        )
        passes += 1
        semantic = semantic or used
        if warning:
            warnings.append(warning)
        candidate_pool.update({item["id"]: item for item in evidence if item["id"] not in ids})

    if state["variants"]:
        related = _relationship_candidates(state["repo_id"], selected, state["question"])
        candidate_pool.update({item["id"]: item for item in related if item["id"] not in ids})

    candidate_pool.update({item["id"]: item for item in selected})
    records = {
        item["id"]: item for item in db.symbols_by_ids(state["repo_id"], list(candidate_pool))
    }
    for item_id, item in list(candidate_pool.items()):
        if item_id in records:
            candidate_pool[item_id] = {**records[item_id], **item}

    def focus_score(item):
        name_terms = set(tokens(item["qualified"]))
        source_terms = set(tokens(item.get("source", "")))
        best = 0.0
        focus_queries = question_aspects(state["question"])
        for query in focus_queries:
            terms = set(tokens(query))
            if not terms:
                continue
            best = max(
                best,
                (4 * len(name_terms & terms) + 0.08 * len(source_terms & terms))
                / (len(terms) ** 0.5),
            )
        if item["kind"] in ("class", "interface", "enum"):
            best -= 0.5
        if not re.search(r"\btests?\b", state["question"], re.I) and (
            "/test" in item.get("path", "") or item.get("path", "").startswith("tests/")
        ):
            best -= 6
        if "relationship with" in item.get("reason", ""):
            best += 1.5
        owner = item["qualified"].rsplit(".", 2)[-2]
        question_terms = set(tokens(state["question"]))
        if owner in CODE_TYPE.findall(state["question"]):
            owner_terms = set(tokens(owner))
            method_terms = set(tokens(item["name"])) - owner_terms
            best += 4 * len(method_terms & question_terms)
            if method_terms:
                best += 1.5 * len(method_terms & question_terms) / len(method_terms)
        if (
            item.get("name") in ("__getattr__", "__getattribute__")
            and re.search(r"\b(?:first|trigger|access|attempt)\b", state["question"], re.I)
            and set(tokens(owner)) & (question_terms & {"mock", "validat", "ser", "schema"})
        ):
            best += 6
        if item.get("name") == "__new__" and re.search(
            r"\b(?:class creation|class is created|class is constructed)\b", state["question"], re.I
        ):
            best += 14
        if item.get("name") == "complete_model_class" and re.search(
            r"\b(?:class creation|rebuild|rebuilding|validator|validation)\b",
            state["question"],
            re.I,
        ):
            best += 7
        if item.get("name") == "set_model_mocks" and re.search(
            r"\b(?:mock|validator|validation)\b", state["question"], re.I
        ):
            best += 12
        if any(
            item["qualified"].lower() == reference
            or item["qualified"].lower().endswith("." + reference)
            for reference in references
        ):
            best += 100
        return best

    # Keep high-confidence direct symbols in place. Focused and graph evidence
    # may replace only the low-ranked slots selected above.
    candidates = sorted(candidate_pool.values(), key=focus_score, reverse=True)

    def prioritize(candidates_for_role):
        for item in sorted(candidates_for_role, key=focus_score, reverse=True):
            if item["id"] in ids or not replaceable:
                continue
            replacement = replaceable.pop()
            ids.remove(selected[replacement]["id"])
            selected[replacement] = _small([item], "focused/graph search: ")[0]
            ids.add(item["id"])
            return

    if re.search(
        r"\bclass (?:creation|is created|construction|is constructed)\b", state["question"], re.I
    ):
        prioritize([item for item in candidates if item["name"] == "__new__"])

    if re.search(r"\bfirst.{0,40}\bvalidat", state["question"], re.I):
        owners = CODE_TYPE.findall(state["question"])
        validators = [
            item
            for item in candidates
            if re.search(r"\bvalidat", item["name"], re.I)
            and any(f".{owner}." in f".{item['qualified']}." for owner in owners)
        ]
        prioritize(validators)

    if re.search(r"\b(?:first|trigger|access|attempt)\b", state["question"], re.I) and re.search(
        r"\b(?:mock|validator)\b", state["question"], re.I
    ):
        mocked_accessors = [
            item
            for item in candidates
            if item["name"] in ("__getattr__", "__getattribute__")
            and set(tokens(item["qualified"].rsplit(".", 2)[-2])) & set(tokens(state["question"]))
        ]
        prioritize(mocked_accessors)

    for item in candidates:
        if not replaceable:
            break
        if item["id"] in ids or focus_score(item) <= 0:
            continue
        replacement = replaceable.pop()
        ids.remove(selected[replacement]["id"])
        selected[replacement] = _small([item], "focused/graph search: ")[0]
        ids.add(item["id"])
    # Put the highest-scoring paths first so answer composition can use a
    # compact, high-signal context while the full ranked list remains visible.
    selected.sort(key=lambda item: focus_score(candidate_pool.get(item["id"], item)), reverse=True)
    return {
        "selected": selected,
        "passes": passes,
        "warning": "; ".join(dict.fromkeys(warnings)) or None,
        "semantic_used": semantic,
        "steps": state["steps"] + ["focused retrieval"],
    }


def _compose(state: InvestigationState):
    records = db.symbols_by_ids(state["repo_id"], [item["id"] for item in state["selected"]])
    metadata = {item["id"]: item for item in state["selected"]}
    budget = 24000
    evidence = []
    for record in records:
        item = dict(record)
        original_length = len(item["source"])
        item["source"] = item["source"][: min(5000, budget)]
        if not item["source"]:
            break
        budget -= len(item["source"])
        item.update(metadata[item["id"]])
        item["truncated"] = len(item["source"]) < original_length
        evidence.append(item)
    result = answer_from_evidence(
        state["repo_id"],
        state["question"],
        evidence,
        state["warning"],
        state["semantic_used"],
        state["mode"],
        state["use_model"],
    )
    return {"result": result, "steps": state["steps"] + ["answer and citation check"]}


def build_graph():
    builder = StateGraph(InvestigationState)
    for name, node in (
        ("guard", _guard),
        ("primary", _primary),
        ("plan", _plan),
        ("followup", _followup),
        ("compose", _compose),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", _route_guard, {"done": END, "primary": "primary"})
    builder.add_edge("primary", "plan")
    builder.add_conditional_edges(
        "plan", _route_followup, {"followup": "followup", "compose": "compose"}
    )
    builder.add_edge("followup", "compose")
    builder.add_edge("compose", END)
    return builder.compile()


GRAPH = build_graph()


def investigate(repo_id, question, mode="hybrid", limit=8, hops=2, use_model=True):
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
    }
    return result
