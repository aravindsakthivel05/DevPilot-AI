import ast
import json
import math
import re
import textwrap
import time
from collections import Counter, defaultdict

from . import db
from .config import provider_settings
from .providers import (
    ANSWER_PROMPT_VERSION,
    cosine,
    embed,
    generate,
)

RETRIEVAL_VERSION = "2026-09-29-multistage-relevance-order"

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
    """Reserve relationship evidence for questions asking about more than one step."""
    cues = re.findall(
        r"\b(?:how|where|what|when|trace|through|after|before|then)\b", question, re.I
    )
    return len(tokens(question)) >= 18 and len(cues) >= 2


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
    """Name a requested symbol when a grounded answer omits its question context."""
    missing = []
    for match in SYMBOL_REFERENCE.finditer(question):
        reference = match.group()
        method = reference.rsplit(".", 1)[-1]
        if re.search(rf"(?<!\w){re.escape(method)}(?!\w)", text, re.I):
            continue
        # Never relabel a response that explicitly names a similar but different method.
        if re.search(rf"(?<!\w){re.escape(method)}\w+", text, re.I):
            continue
        missing.append(reference)
    if not missing or not text:
        return text
    labels = " and ".join(f"`{reference}`" for reference in missing)
    return f"In {labels}, {text[0].lower()}{text[1:]}"


def generation_context(repo_id, question, evidence):
    """Use a small, source-backed context while keeping public citation numbers stable."""
    references = explicit_symbol_references(question)
    if references:
        exact = [
            (number, item)
            for number, item in enumerate(evidence, 1)
            if any(
                item["qualified"].lower() == ref or item["qualified"].lower().endswith("." + ref)
                for ref in references
            )
        ]
        if is_multi_stage(question):
            names = {item["name"] for _, item in exact}
            related = [
                (number, item)
                for number, item in enumerate(evidence, 1)
                if item["id"] not in {match["id"] for _, match in exact}
            ]
            related.sort(key=lambda pair: (pair[1]["name"] not in names, pair[0]))
            selected = (exact + related)[:3]
        else:
            selected = exact
    else:
        # Investigation already keeps its full evidence list for citations and
        # recall metrics. Generation gets a smaller first-page context to keep
        # long multi-hop traces within the local model's useful prompt budget.
        selected = list(enumerate(evidence[:6], 1))
    if not selected:
        selected = list(enumerate(evidence[:4], 1))
    records = {
        item["id"]: item
        for item in db.symbols_by_ids(repo_id, [item["id"] for _, item in selected])
    }
    budget = 12000
    context = []
    for number, item in selected:
        source = executable_source(records[item["id"]])[: min(4000, budget)]
        if not source:
            break
        context.append({**item, "source": source, "citation_number": number})
        budget -= len(source)
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


def retrieve(repo_id, question, mode="hybrid", limit=8, hops=2):
    rows = db.symbols(repo_id)
    graph = db.edges(repo_id)
    lookup = {s["id"]: s for s in rows}
    query = Counter(tokens(question))
    references = explicit_symbol_references(question)
    legacy_requested = bool(re.search(r"\b(?:v1|legacy|deprecated)\b", question, re.I))
    tests_requested = bool(re.search(r"\btests?\b", question, re.I))
    df = Counter()
    counts = {}
    for s in rows:
        terms = Counter(tokens(s["qualified"] + " " + s["docstring"] + " " + s["source"]))
        counts[s["id"]] = terms
        df.update(terms.keys())
    scores = {}
    exact_ids = set()
    avg = sum(sum(c.values()) for c in counts.values()) / max(len(rows), 1)
    for s in rows:
        terms = counts[s["id"]]
        length = sum(terms.values())
        score = 0.0
        for t in query:
            tf = terms[t]
            if tf:
                idf = math.log(1 + (len(rows) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / max(avg, 1)))
        name_tokens = set(tokens(s["name"]))
        if name_tokens:
            score += 2.5 * len(name_tokens & query.keys()) / len(name_tokens)
        if s["name"].lower() in question.lower() and len(s["name"]) > 2:
            score += 5
        owner = s["qualified"].rsplit(".", 1)[0].rsplit(".", 1)[-1]
        if owner.lower() in question.lower() and len(owner) > 3:
            score += 3
        if s["kind"] == "document":
            score *= 0.35
        elif s["kind"] == "module":
            score *= 0.65
        elif s["kind"] in ("class", "interface", "enum"):
            score *= 0.75
        if ("/test" in s["path"] or s["path"].startswith("tests/")) and "test" not in query:
            score *= 0.45
        if not legacy_requested and ("/v1/" in s["path"] or "/deprecated/" in s["path"]):
            score *= 0.25
        if any(
            s["qualified"].lower() == ref or s["qualified"].lower().endswith("." + ref)
            for ref in references
        ):
            score += 50
            exact_ids.add(s["id"])
        if score > 0:
            scores[s["id"]] = score
    lexical = sorted(scores, key=scores.get, reverse=True)
    semantic = []
    warning = None
    cfg = provider_settings()
    if cfg["embedding_model"] and mode in ("hybrid", "semantic"):
        with db.connection() as c:
            vectors = c.execute(
                "SELECT e.* FROM embeddings e JOIN symbols s ON e.symbol_id=s.id WHERE s.repo_id=? AND e.model=?",
                (repo_id, cfg["embedding_model"]),
            ).fetchall()
        if vectors:
            try:
                vector = embed([question])[0]
                semantic = [
                    r[0]
                    for r in sorted(
                        [
                            (v["symbol_id"], cosine(vector, json.loads(v["vector"])))
                            for v in vectors
                        ],
                        key=lambda r: r[1],
                        reverse=True,
                    )
                ]
            except Exception as e:
                warning = str(e)
    if mode == "semantic" and not semantic:
        raise ValueError(
            "Semantic mode requires configured embeddings and a successfully embedded repository."
        )
    if mode == "semantic":
        seeds = semantic[:limit]
        fused = {sid: 1 / (60 + i) for i, sid in enumerate(semantic)}
    else:
        fused = defaultdict(float)
        for ranking in [lexical, semantic] if semantic else [lexical]:
            for i, sid in enumerate(ranking):
                fused[sid] += 1 / (60 + i)
        for sid in list(fused):
            symbol = lookup[sid]
            if not tests_requested and (
                "/test" in symbol["path"] or symbol["path"].startswith("tests/")
            ):
                fused[sid] *= 0.45
            if not legacy_requested and (
                "/v1/" in symbol["path"] or "/deprecated/" in symbol["path"]
            ):
                fused[sid] *= 0.25
        for sid in exact_ids:
            fused[sid] += 0.1
        direct_count = (
            max(3, limit // 2)
            if mode == "graph" or (mode == "hybrid" and is_multi_stage(question))
            else limit
        )
        seeds = sorted(fused, key=fused.get, reverse=True)[:direct_count]
    reasons = {
        sid: "semantic match" if mode == "semantic" else "symbol / text match" for sid in seeds
    }
    paths = {sid: [] for sid in seeds}
    selected = set(seeds)
    if mode in ("hybrid", "graph"):
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
                    weight = 0.35 if edge["kind"] == "contains" else 0.85
                    score = fused.get(sid, 0.01) * weight / (depth + 1) + fused.get(target, 0) * 0.3
                    if target not in candidates or score > candidates[target][0]:
                        candidates[target] = (score, sid, edge)
            frontier = []
            for target, (score, sid, edge) in sorted(
                candidates.items(), key=lambda kv: kv[1][0], reverse=True
            )[:limit]:
                selected.add(target)
                frontier.append(target)
                fused[target] = max(fused.get(target, 0), score)
                reasons[target] = f"{edge['kind']} relationship with {lookup[sid]['name']}"
                paths[target] = paths[sid] + [edge]
    # Graph neighbors add context; they must not displace stronger direct matches.
    ranked = (
        seeds
        + [
            sid
            for sid in sorted(selected - set(seeds), key=lambda x: fused.get(x, 0), reverse=True)
        ]
    )[:limit]
    evidence = []
    budget = 24000
    for sid in ranked:
        s = dict(lookup[sid])
        source = s["source"][: min(5000, budget)]
        if not source:
            break
        budget -= len(source)
        s["source"] = source
        s.update(
            score=round(fused.get(sid, 0), 5),
            reason=reasons[sid],
            traversal=paths[sid],
            truncated=len(source) < len(lookup[sid]["source"]),
        )
        evidence.append(s)
    return evidence, warning, bool(semantic)


def answer(repo_id, question, mode="hybrid", limit=8, hops=2, use_model=True):
    start = time.perf_counter()
    if asks_external_state(question):
        return dict(
            answer="The indexed source snapshot cannot establish that live, private, or future value. Check the running system, its configuration, or its logs for the actual result.",
            evidence=[],
            mode=mode,
            semantic_used=False,
            generated=False,
            abstained=True,
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
                        retry_feedback = f"{text} Return the required JSON shape with one quoted claim for each aspect."
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
                candidate = anchor_named_symbols(question, candidate)
                citation_check = check_citations(candidate, len(evidence))
                focus_warning = answer_focus_warning(question, candidate)
                cited = {int(number) for number in re.findall(r"\[(\d+)\]", candidate)}
                if (
                    citation_check["has_citations"]
                    and not citation_check["invalid"]
                    and not citation_check["uncited_paragraphs"]
                    and not citation_check["uncited_sentences"]
                    and not citation_check["reference_section"]
                    and cited <= allowed
                    and not focus_warning
                ):
                    text = candidate
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
            text = "The following source locations are relevant to your question. This is a retrieval report; connect a model provider for a synthesised explanation.\n\n"
            text += "\n\n".join(
                f"[{i + 1}] {s['qualified']} — {s['path']}:{s['start_line']}–{s['end_line']}\nRetrieved through {s['reason']}."
                for i, s in enumerate(evidence)
            )
    return dict(
        answer=text,
        evidence=evidence,
        mode=mode,
        semantic_used=semantic,
        generated=generated,
        abstained=False,
        verification="not_executed",
        citation_check=check_citations(text, len(evidence)),
        warning=warning,
        usage=usage,
        generation_diagnostics=generation_diagnostics,
        elapsed_ms=round((time.perf_counter() - start) * 1000),
        snapshot=db.repository(repo_id)["fingerprint"],
        model=provider_settings()["model"] or None,
        answer_prompt_version=ANSWER_PROMPT_VERSION,
        retrieval_version=RETRIEVAL_VERSION,
    )
