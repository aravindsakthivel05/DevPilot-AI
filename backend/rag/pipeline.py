import ast
import json
import os
import re
import textwrap
import time
from collections import Counter, defaultdict
from contextvars import ContextVar

from .. import db
from ..config import provider_settings
from ..evidence import excerpt
from ..providers import (
    ANSWER_PROMPT_VERSION,
    context_window,
    embedding_signature,
    generate,
)
from ..question_analysis import analyze_query, answer_aspects
from ..search import indexed_candidates
from ..test_links import is_test_path
from .context import role
from .embeddings import embed
from .fusion import fuse
from .graph_retrieval import relationship_weight
from .lexical import bm25
from .reranker import rerank, structural_score
from .settings import settings
from .vector_store import LocalVectorStore

TRACE = ContextVar("devpilot_retrieval_trace", default=None)
RETRIEVAL_VERSION = "2026-10-04-custom-modular-rag-v1"

SYMBOL_REFERENCE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")

EXTERNAL_STATE_PATTERNS = (
    re.compile(r"\b(?:tomorrow|next time)\b", re.I),
    re.compile(r"\bmy\b.{0,80}\b(?:running|deployed|private|laptop|shell|production)\b", re.I),
    re.compile(
        r"\b(?:current|currently|now)\b.{0,80}\b(?:deployment|deployed|database|shell|session|jvm|runtime|production)\b",
        re.I,
    ),
    re.compile(r"\bproduction\b.{0,80}\b(?:next|actual|currently|now)\b", re.I),
)


def asks_external_state(question):
    """Identify explicit live/private/future facts a source snapshot cannot establish."""
    return any(pattern.search(question) for pattern in EXTERNAL_STATE_PATTERNS)


STOP = {
    "the",
    "a",
    "an",
    "in",
    "is",
    "to",
    "of",
    "and",
    "for",
    "how",
    "what",
    "does",
    "this",
    "with",
    "where",
    "which",
    "it",
    "are",
    "from",
    "can",
    "i",
    "on",
    "that",
    "during",
    "happens",
    "first",
    "after",
    "before",
    "still",
    "then",
    "once",
    "if",
    "when",
    "while",
    "attempt",
    "into",
    "whose",
    "be",
    "was",
    "were",
    "as",
    "by",
}


def tokens(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    normalized = []
    for term in re.findall(r"[a-z0-9]+", text.lower()):
        if term in STOP or len(term) <= 1:
            continue
        if len(term) > 5 and term.endswith("ies"):
            term = term[:-3] + "y"
        for suffix in ("ing", "ed", "ion", "or", "er", "s"):
            if len(term) - len(suffix) >= 4 and term.endswith(suffix):
                if suffix == "s" and term.endswith("ss"):
                    continue
                term = term[: -len(suffix)]
                break
        if len(term) > 5 and term.endswith("e"):
            term = term[:-1]
        if len(term) > 1:
            normalized.append(term)
    return normalized


def explicit_symbol_references(question):
    """Find code identifiers the user actually named, rather than terms in snippets."""
    return {match.group().lower() for match in SYMBOL_REFERENCE.finditer(question)}


def is_multi_stage(question):
    """Investigate distinct obligations regardless of question length."""
    return len(answer_aspects(question)) > 1 or bool(
        re.search(
            r"\b(?:trace|walk through|hand off|delegate|delegates|delegation|progress|flows|flow)\b",
            question,
            re.I,
        )
    )


def check_citations(text, evidence_count):
    """Check citation placement and bounds; this does not establish factual support."""
    citations = [int(x) for x in re.findall(r"\[(\d+)\]", text)]
    invalid = sorted({i for i in citations if i < 1 or i > evidence_count})
    uncited = [
        paragraph[:160]
        for paragraph in re.split(r"\n\s*\n", text.strip())
        if paragraph.strip() and not re.search(r"\[\d+\]", paragraph)
    ]
    uncited_sentences = [
        sentence[:160]
        for paragraph in re.split(r"\n\s*\n", text.strip())
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph.strip())
        if sentence.strip() and not re.search(r"\[\d+\]", sentence)
    ]
    return {
        "invalid": invalid,
        "has_citations": bool(citations),
        "uncited_paragraphs": uncited,
        "uncited_sentences": uncited_sentences,
        "reference_section": bool(
            re.search(r"(?im)^\s*(references|sources)\s*:", text)
            or re.search(r"(?m)^\s*\[\d+\]\s+\w", text)
        ),
        "entailment_checked": False,
    }


def answer_focus_warning(question, text):
    """Reject obvious wrong-target and unsolicited-repair answers before display."""
    for reference in explicit_symbol_references(question):
        method = reference.rsplit(".", 1)[-1]
        if not re.search(rf"(?<!\w){re.escape(method)}(?!\w)", text, re.I):
            return f"Model answer did not address the named symbol {reference}."
    if not re.search(r"\b(?:fix|change|modify|patch|improve|implement)\b", question, re.I):
        if re.search(
            r"(?i)\b(?:to fix|the fix is|should (?:modify|change|add|remove)|"
            r"modification is needed|make sure .* is (?:imported|defined))\b",
            text,
        ):
            return "Model proposed a code change although the question requested an explanation."
    return None


def anchor_named_symbols(question, text):
    """Compatibility helper: never insert a symbol the model did not establish."""
    return text


def generation_context(repo_id, question, evidence):
    """Preserve per-aspect helpers with original line mappings and a token budget."""
    records = {r["id"]: r for r in db.symbols_by_ids(repo_id, [e["id"] for e in evidence])}
    with db.connection() as connection:
        ids = list(records)
        chunks = (
            {
                row["id"]: json.loads(row["metadata"])
                for row in connection.execute(
                    "SELECT id,metadata FROM chunks WHERE repo_id=? AND id IN ("
                    + ",".join("?" for _ in ids)
                    + ")",
                    (repo_id, *ids),
                )
            }
            if ids
            else {}
        )
    references = explicit_symbol_references(question)
    aspects = answer_aspects(question)
    indexed = list(enumerate(evidence, 1))
    selected = []

    def add(pair):
        if pair and pair[1]["id"] not in {item["id"] for _, item in selected}:
            selected.append(pair)

    for pair in indexed:
        if any(
            pair[1]["qualified"].lower().endswith("." + ref) or pair[1]["qualified"].lower() == ref
            for ref in references
        ):
            add(pair)

    def context_score(pair, aspect):
        record = records.get(pair[1]["id"], pair[1])
        terms = set(tokens(aspect))
        body_terms = set(tokens(executable_source(record)))
        name_hits = len(terms & set(tokens(pair[1]["qualified"])))
        score = 3 * name_hits + len(terms & body_terms) / max(1, len(body_terms) ** 0.4)
        if record.get("kind") in ("class", "interface", "module"):
            score *= 0.5
        if any(edge.get("kind") in ("calls", "aliases") for edge in pair[1].get("traversal", [])):
            score += 3
        return score

    for aspect in aspects:
        ranked = sorted(
            indexed, key=lambda pair: (context_score(pair, aspect), -pair[0]), reverse=True
        )
        if ranked:
            add(ranked[0])
    for pair in indexed:
        add(pair)
    selected = selected[:8]
    output_tokens = min(3072, max(768, 384 * len(aspects)))
    # Line-numbered JSON and metadata need substantial space beyond source text.
    budget = min(
        int(os.environ.get("DEVPILOT_SOURCE_TOKEN_BUDGET", "4096")),
        max(128, (context_window() - output_tokens - 1500) // 2),
    )
    context = []
    for index, (number, metadata) in enumerate(selected):
        record = records.get(metadata["id"], metadata)
        if not record.get("source"):
            continue
        allowance = max(1, budget // (len(selected) - index))
        item = excerpt(record, question, allowance)
        if not item["source"]:
            continue
        budget -= item["estimated_source_tokens"]
        context.append(
            {
                **metadata,
                **item,
                "citation_number": number,
                "evidence_role": role(metadata),
                "relationships": chunks.get(metadata["id"], {}).get("relationships", [])[:20],
                "public_aliases": metadata.get("public_aliases", []),
            }
        )
    return context


def executable_source(symbol):
    """Remove a Python symbol's leading docstring from generation context."""
    source = symbol["source"]
    if not symbol["path"].endswith(".py"):
        return source
    dedented = textwrap.dedent(source)
    try:
        tree = ast.parse(dedented)
    except SyntaxError:
        return source
    if not tree.body or not isinstance(
        tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    ):
        return source
    node = tree.body[0]
    if not node.body or not isinstance(node.body[0], ast.Expr):
        return source
    doc = node.body[0]
    if not isinstance(doc.value, ast.Constant) or not isinstance(doc.value.value, str):
        return source
    lines = dedented.splitlines(keepends=True)
    return "".join(lines[: doc.lineno - 1] + lines[doc.end_lineno :])


def retrieve(repo_id, question, mode="hybrid", limit=8, hops=2, overrides=None):
    started = time.perf_counter()
    cfg_weights = settings()
    if overrides:
        for key, value in overrides.items():
            if key not in cfg_weights:
                raise ValueError("Unknown retrieval setting")
            if key == "rerank":
                if not isinstance(value, bool):
                    raise ValueError("rerank must be boolean")
            elif key == "candidate_limit" and (
                not isinstance(value, int) or isinstance(value, bool) or not 10 <= value <= 100
            ):
                raise ValueError("candidate_limit must be an integer from 10 to 100")
            elif not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise ValueError("Invalid retrieval override")
            cfg_weights[key] = value
    candidate_ids, rows, graph, stats = indexed_candidates(repo_id, question, tokens)
    trace = {
        "question": question,
        "query_analysis": analyze_query(question),
        "mode": mode,
        "hops": hops,
        "settings": cfg_weights,
        "lexical_candidates": [],
        "semantic_candidates": [],
        "graph_seeds": [],
        "graph_expanded": [],
        "fused_candidates": [],
        "reranked_candidates": [],
        "timings_ms": {},
    }
    TRACE.set(trace)
    lookup = {row["id"]: row for row in rows}
    query = Counter(tokens(question))
    references = explicit_symbol_references(question)
    legacy_requested = bool(re.search(r"\b(?:v1|legacy|deprecated)\b", question, re.I))
    tests_requested = bool(
        re.search(r"\b(?:tests?|regression|behavior|behaviour|contract)\b", question, re.I)
    )
    exact_ids = {
        row["id"]
        for row in rows
        if any(
            row["qualified"].lower() == ref
            or row["qualified"].lower().endswith("." + ref)
            or any(alias.lower() == ref for alias in row.get("public_aliases", []))
            for ref in references
        )
    }
    # FTS supplies a bounded candidate set. Re-rank with repository-local
    # statistics so adding another repository does not change its BM25 scores.
    name_candidates = sorted(
        (row for row in rows if set(row["_name_tokens"]) & query.keys()),
        key=lambda row: len(set(row["_name_tokens"]) & query.keys()),
        reverse=True,
    )[:512]
    ids = list(
        dict.fromkeys([*candidate_ids, *sorted(exact_ids), *[row["id"] for row in name_candidates]])
    )
    records = {row["id"]: row for row in db.symbols_by_ids(repo_id, ids)}
    scores = {}
    for sid in ids:
        row = lookup[sid]
        record = records[sid]
        terms = Counter(
            tokens(record["qualified"] + " " + record["docstring"] + " " + record["source"])
        )
        length = row.get("length") or sum(terms.values())
        score = bm25(query, terms, length, len(rows), stats["df"], stats["average_length"])
        name_tokens = set(row["_name_tokens"])
        if name_tokens:
            score += 2.5 * len(name_tokens & query.keys()) / len(name_tokens)
        if re.search(r"(?<!\w)" + re.escape(row["name"]) + r"(?!\w)", question, re.I):
            score += 5
        owner = row["qualified"].rsplit(".", 1)[0].rsplit(".", 1)[-1]
        if len(owner) > 3 and re.search(r"\b" + re.escape(owner) + r"\b", question, re.I):
            score += 3
        if row["kind"] in ("parameter", "variable", "constant"):
            score *= 0.2
        if row["kind"] == "document" and not re.search(
            r"\b(?:config|configuration|document|readme|manifest)\b", question, re.I
        ):
            score *= 0.35
        elif row["kind"] == "module":
            score *= 0.65
        elif row["kind"] in ("class", "interface", "enum"):
            score *= 0.75
        if is_test_path(row["path"]) and not tests_requested:
            score *= 0.6
        if not legacy_requested and ("/v1/" in row["path"] or "/deprecated/" in row["path"]):
            score *= 0.25
        if sid in exact_ids:
            score += cfg_weights["exact_boost"]
        if score > 0:
            scores[sid] = score
    lexical_done = time.perf_counter()
    lexical = sorted(scores, key=lambda sid: (-scores[sid], lookup[sid]["qualified"], sid))
    semantic = []
    warning = None
    cfg = provider_settings()
    if (
        cfg["embedding_model"]
        and mode in ("hybrid", "semantic")
        and (mode == "semantic" or cfg_weights["semantic_weight"] > 0)
    ):
        with db.connection() as c:
            vectors = c.execute(
                "SELECT e.* FROM embeddings e JOIN symbols s ON e.symbol_id=s.id WHERE s.repo_id=? AND e.model=? AND e.signature=?",
                (repo_id, cfg["embedding_model"], embedding_signature()),
            ).fetchall()
        if len(vectors) != len(rows):
            warning = f"Embedding coverage is incomplete for the configured provider/model revision ({len(vectors)}/{len(rows)} symbols); using lexical/graph retrieval."
            vectors = []
        if vectors:
            try:
                vector = embed([question])[0]
                dimensions = {len(json.loads(v["vector"])) for v in vectors}
                if dimensions != {len(vector)}:
                    raise ValueError(
                        "Stored embedding dimensions do not match the query; rebuild embeddings."
                    )
                vector_results = LocalVectorStore(
                    [(v["symbol_id"], json.loads(v["vector"])) for v in vectors]
                ).search(vector, len(vectors))
                semantic = [sid for sid, _ in vector_results]
                trace["semantic_candidates"] = [
                    {"id": sid, "similarity": score} for sid, score in vector_results[:50]
                ]
            except Exception as e:
                warning = str(e)
    semantic_done = time.perf_counter()
    semantic_scores = dict(vector_results) if semantic else {}
    graph_scores = {}
    if mode == "semantic" and not semantic:
        raise ValueError(
            "Semantic mode requires configured embeddings and a successfully embedded repository."
        )
    if mode == "semantic":
        seeds = semantic[:limit]
        fused = {sid: 1 / (60 + i) for i, sid in enumerate(semantic)}
    else:
        fused, channels = fuse(
            {"lexical": lexical, "semantic": semantic},
            {"lexical": cfg_weights["lexical_weight"], "semantic": cfg_weights["semantic_weight"]},
        )
        for sid in list(fused):
            symbol = lookup[sid]
            if not legacy_requested and (
                "/v1/" in symbol["path"] or "/deprecated/" in symbol["path"]
            ):
                fused[sid] *= 0.25
        if cfg_weights["lexical_weight"] > 0:
            for sid in exact_ids:
                fused[sid] += 0.1
        direct_count = (
            max(3, limit // 2)
            if mode == "graph" or (mode == "hybrid" and is_multi_stage(question))
            else limit
        )
        pool = sorted(fused, key=fused.get, reverse=True)[: cfg_weights["candidate_limit"]]
        if cfg_weights["rerank"]:
            pool = rerank(
                pool, lookup, fused, question, references, cfg_weights["structural_weight"]
            )
        seeds = pool[:direct_count]
    fusion_done = time.perf_counter()
    reasons = {
        sid: "semantic match" if mode == "semantic" else "symbol / text match" for sid in seeds
    }
    paths = {sid: [] for sid in seeds}
    selected = set(seeds)
    if mode in ("hybrid", "graph") and cfg_weights["graph_weight"] > 0:
        adjacent = defaultdict(list)
        for e in graph:
            adjacent[e["source"]].append((e["target"], e))
            adjacent[e["target"]].append((e["source"], e))
        frontier = list(seeds)
        for depth in range(hops):
            candidates = {}
            for sid in frontier:
                for target, edge in adjacent[sid]:
                    if target in selected or target not in lookup:
                        continue
                    # Containment fan-out is bounded. Prefer call/import/inheritance evidence.
                    weight = relationship_weight(edge, sid) * cfg_weights["graph_weight"]
                    score = fused.get(sid, 0.01) * weight / (depth + 1) + fused.get(target, 0) * 0.3
                    if target not in candidates or score > candidates[target][0]:
                        candidates[target] = (score, sid, edge)
            frontier = []
            for target, (score, sid, edge) in sorted(
                candidates.items(), key=lambda kv: kv[1][0], reverse=True
            )[:limit]:
                selected.add(target)
                frontier.append(target)
                graph_scores[target] = score
                fused[target] = max(fused.get(target, 0), score)
                reasons[target] = f"{edge['kind']} relationship with {lookup[sid]['name']}"
                paths[target] = paths[sid] + [edge]
    graph_done = time.perf_counter()
    pool = list(
        dict.fromkeys(
            [
                *seeds,
                *sorted(selected - set(seeds), key=lambda sid: fused.get(sid, 0), reverse=True),
                *(pool if mode != "semantic" else []),
            ]
        )
    )[: cfg_weights["candidate_limit"]]
    ranked = (
        rerank(pool, lookup, fused, question, references, cfg_weights["structural_weight"])
        if cfg_weights["rerank"] and mode != "semantic"
        else pool
    )[:limit]
    for sid in ranked:
        reasons.setdefault(sid, "fused lexical / semantic candidate")
        paths.setdefault(sid, [])
    rerank_done = time.perf_counter()
    trace["lexical_candidates"] = [{"id": sid, "score": scores[sid]} for sid in lexical[:50]]
    trace["graph_seeds"] = seeds
    trace["graph_expanded"] = [
        {"id": sid, "path": paths.get(sid, [])} for sid in selected - set(seeds)
    ]
    trace["fused_candidates"] = [{"id": sid, "score": fused.get(sid, 0)} for sid in pool]
    trace["reranked_candidates"] = ranked
    trace["timings_ms"] = {
        "lexical": round((lexical_done - started) * 1000, 3),
        "semantic": round((semantic_done - lexical_done) * 1000, 3),
        "fusion_and_seed_reranking": round((fusion_done - semantic_done) * 1000, 3),
        "graph": round((graph_done - fusion_done) * 1000, 3),
        "reranking": round((rerank_done - graph_done) * 1000, 3),
    }
    evidence = []
    budget = 24000
    full_records = {s["id"]: s for s in db.symbols_by_ids(repo_id, ranked)}
    for sid in ranked:
        s = dict(full_records[sid])
        s["public_aliases"] = lookup[sid].get("public_aliases", [])
        source = s["source"][: min(5000, budget)]
        if not source:
            break
        budget -= len(source)
        s["source"] = source
        s.update(
            score=round(fused.get(sid, 0), 5),
            component_scores={
                "lexical": scores.get(sid, 0),
                "semantic": semantic_scores.get(sid, 0),
                "graph": graph_scores.get(sid, 0),
                "structural": structural_score(s, question, references),
                "final": fused.get(sid, 0)
                + (
                    cfg_weights["structural_weight"] * structural_score(s, question, references)
                    if cfg_weights["rerank"] and mode != "semantic"
                    else 0
                ),
            },
            retrieval_sources=(
                ["lexical"]
                if mode != "semantic" and cfg_weights["lexical_weight"] > 0 and sid in scores
                else []
            )
            + (["semantic"] if sid in semantic_scores else [])
            + (["graph"] if paths[sid] else []),
            reason=reasons[sid],
            traversal=paths[sid],
            truncated=len(source) < len(full_records[sid]["source"]),
        )
        evidence.append(s)
    trace["timings_ms"]["context_records"] = round((time.perf_counter() - rerank_done) * 1000, 3)
    trace["timings_ms"]["retrieval"] = round((time.perf_counter() - started) * 1000, 3)
    return evidence, warning, bool(semantic)


def answer(repo_id, question, mode="hybrid", limit=8, hops=2, use_model=True):
    TRACE.set(None)
    start = time.perf_counter()
    if asks_external_state(question):
        return dict(
            answer="The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.",
            evidence=[],
            mode=mode,
            semantic_used=False,
            generated=False,
            abstained=True,
            claims=[],
            confidence="insufficient",
            missing_information=["Live/private/future state is outside the source snapshot."],
            related_symbols=[],
            verification="not_executed",
            citation_check=check_citations("", 0),
            warning=None,
            usage={},
            elapsed_ms=round((time.perf_counter() - start) * 1000),
            snapshot=db.repository(repo_id)["fingerprint"],
            model=provider_settings()["model"] or None,
            answer_prompt_version=ANSWER_PROMPT_VERSION,
            retrieval_version=RETRIEVAL_VERSION,
        )
    evidence, warning, semantic = retrieve(repo_id, question, mode, limit, hops)
    return answer_from_evidence(
        repo_id, question, evidence, warning, semantic, mode, use_model, start
    )


def answer_from_evidence(
    repo_id, question, evidence, warning, semantic, mode, use_model=True, start=None
):
    """Apply the same answer and citation policy to direct or orchestrated retrieval."""
    if start is None:
        start = time.perf_counter()
    original_warning = warning
    usage = {}
    generation_diagnostics = {"attempt_count": 0, "total_request_ms": 0, "attempts": []}
    generated = False
    focus_warning = None
    aspect_statuses = []
    context = []
    if evidence and use_model and provider_settings()["model"]:
        try:
            text = ""
            context = generation_context(repo_id, question, evidence)
            allowed = {item["citation_number"] for item in context}
            retry_feedback = None
            for attempt in range(2):
                generation_diagnostics["attempt_count"] += 1
                attempt_started = time.perf_counter()
                try:
                    generated_result = generate(
                        question,
                        context,
                        citation_feedback=retry_feedback,
                    )
                    if len(generated_result) == 2:
                        candidate, attempt_usage = generated_result
                        attempt_metrics = {}
                    else:
                        candidate, attempt_usage, attempt_metrics = generated_result
                except ValueError as exc:
                    text = str(exc)
                    attempt_metrics = getattr(exc, "metrics", {})
                    for key, value in attempt_metrics.get("usage", {}).items():
                        if isinstance(value, (int, float)):
                            usage[key] = usage.get(key, 0) + value
                    duration_ms = attempt_metrics.get(
                        "request_ms", round((time.perf_counter() - attempt_started) * 1000)
                    )
                    generation_diagnostics["total_request_ms"] += duration_ms
                    retryable = getattr(exc, "retryable", False)
                    generation_diagnostics["attempts"].append(
                        {
                            **attempt_metrics,
                            "request_ms": duration_ms,
                            "outcome": "invalid_model_output" if retryable else "provider_failure",
                            "reason": str(exc),
                        }
                    )
                    if attempt == 0 and retryable:
                        retry_feedback = (
                            f"{text} Return valid claims or explicit missing-evidence statuses."
                        )
                        # Broaden the evidence on a rejected attempt; repeating the
                        # same incomplete prompt cannot establish a missing helper.
                        extra, extra_warning, used = retrieve(repo_id, question, mode, 15, 2)
                        known = {item["id"] for item in evidence}
                        evidence = [
                            *evidence,
                            *[item for item in extra if item["id"] not in known],
                        ][:15]
                        semantic = semantic or used
                        original_warning = original_warning or extra_warning
                        context = generation_context(repo_id, question, evidence)
                        allowed = {item["citation_number"] for item in context}
                        continue
                    warning = str(exc)
                    break
                duration_ms = attempt_metrics.get(
                    "request_ms", round((time.perf_counter() - attempt_started) * 1000)
                )
                generation_diagnostics["total_request_ms"] += duration_ms
                outcome = "candidate_received"
                generation_diagnostics["attempts"].append(
                    {**attempt_metrics, "request_ms": duration_ms, "outcome": outcome}
                )
                for key, value in attempt_usage.items():
                    if isinstance(value, (int, float)):
                        usage[key] = usage.get(key, 0) + value
                statuses = attempt_metrics.get("aspect_statuses", [])
                supported_text = candidate
                if statuses:
                    supported_text = "\n\n".join(
                        p
                        for p in candidate.split("\n\n")
                        if not any(
                            p == f"Aspect {i['aspect_id']}: {i['text'].strip()}"
                            for i in attempt_metrics.get("claims", [])
                            if i["status"] != "supported"
                        )
                    )
                citation_check = check_citations(supported_text, len(evidence))
                focus_warning = None if statuses else answer_focus_warning(question, candidate)
                cited = {int(number) for number in re.findall(r"\[(\d+)\]", candidate)}
                if (
                    (citation_check["has_citations"] or (statuses and not supported_text))
                    and not citation_check["invalid"]
                    and not citation_check["uncited_paragraphs"]
                    and not citation_check["uncited_sentences"]
                    and not citation_check["reference_section"]
                    and cited <= allowed
                    and not focus_warning
                ):
                    text = candidate
                    aspect_statuses = statuses
                    generated = True
                    generation_diagnostics["attempts"][-1]["outcome"] = "accepted"
                    warning = original_warning
                    break
                issues = []
                if not citation_check["has_citations"] or citation_check["invalid"]:
                    issues.append("Use valid citation numbers from the supplied evidence.")
                if citation_check["uncited_paragraphs"] or citation_check["uncited_sentences"]:
                    issues.append("Cite every factual sentence.")
                if citation_check["reference_section"] or not cited <= allowed:
                    issues.append("Cite only source IDs included in the supplied excerpts.")
                if focus_warning:
                    issues.append(focus_warning)
                retry_feedback = (
                    " ".join(issues) or "Correct the answer to satisfy the citation checks."
                )
                generation_diagnostics["attempts"][-1]["outcome"] = "citation_or_focus_rejected"
                generation_diagnostics["attempts"][-1]["reason"] = retry_feedback
                warning = retry_feedback
                text = ""
                if attempt == 1:
                    break
            if not generated:
                warning = (
                    focus_warning
                    or warning
                    or "Model answer omitted valid source citations; showing source locations."
                )
                text = ""
        except Exception as e:
            warning = str(e)
            text = ""
    else:
        text = ""
    if not text:
        if not evidence:
            text = "No matching evidence was found in this snapshot. Try a function name, file path, or a more specific behaviour."
        else:
            text = "No validated explanation is available. These retrieved source locations may help you investigate; their relevance does not establish an answer.\n\n"
            text += "\n\n".join(
                f"[{i + 1}] {s['qualified']} — {s['path']}:{s['start_line']}–{s['end_line']}\nRetrieved through {s['reason']}."
                for i, s in enumerate(evidence)
            )
    generation_diagnostics["provider_calls"] = sum(
        m.get("provider_calls", 1) for m in generation_diagnostics["attempts"]
    )
    from .abstention import sufficiency
    from .citations import evidence_reference

    provenance = []
    by_number = {item["citation_number"]: item for item in context}
    for attempt in generation_diagnostics["attempts"]:
        if attempt.get("outcome") != "accepted":
            continue
        for span in attempt.get("supporting_lines", []):
            number = span.get("source_id")
            if number in by_number:
                try:
                    provenance.append(
                        evidence_reference(by_number[number], span["start_line"], span["end_line"])
                    )
                except (ValueError, KeyError):
                    continue
    result = dict(
        answer=text,
        citation_provenance=provenance,
        claims=[
            c
            for attempt in generation_diagnostics["attempts"]
            if attempt.get("outcome") == "accepted"
            for c in attempt.get("claims", [])
        ],
        missing_information=[s["question"] for s in aspect_statuses if s["status"] != "supported"],
        confidence="insufficient"
        if not generated
        else "partial"
        if any(s["status"] != "supported" for s in aspect_statuses)
        else "model_supported",
        related_symbols=[s["qualified"] for s in evidence],
        retrieval_trace=TRACE.get(),
        evidence=evidence,
        mode=mode,
        semantic_used=semantic,
        generated=generated,
        abstained=not evidence
        or (bool(aspect_statuses) and all(s["status"] != "supported" for s in aspect_statuses)),
        partial=bool(aspect_statuses)
        and any(s["status"] != "supported" for s in aspect_statuses)
        and any(s["status"] == "supported" for s in aspect_statuses),
        aspect_statuses=aspect_statuses,
        generation_context=[
            {
                "source_id": item["citation_number"],
                "id": item["id"],
                "qualified": item["qualified"],
                "path": item["path"],
                "source_line_numbers": item["source_line_numbers"],
                "source": item["source"],
                "truncated": item["truncated"],
            }
            for item in context
        ],
        verification="not_executed",
        citation_check={
            **check_citations(
                supported_text if generated and aspect_statuses else text, len(evidence)
            ),
            "source_identity_checked": bool(generated and aspect_statuses),
        },
        warning=warning,
        usage=usage,
        generation_diagnostics=generation_diagnostics,
        elapsed_ms=round((time.perf_counter() - start) * 1000),
        snapshot=db.repository(repo_id)["fingerprint"],
        model=provider_settings()["model"] or None,
        answer_prompt_version=ANSWER_PROMPT_VERSION,
        retrieval_version=RETRIEVAL_VERSION,
    )
    result["evidence_sufficiency"] = sufficiency(result)
    return result
