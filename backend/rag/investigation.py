"""Bounded source reads that recover helpers without inventing call relationships."""

import re

from .. import db
from ..question_analysis import answer_aspects, symbol_references
from ..test_links import is_test_path
from .obligations import checklist
from .tokenization import stem

CALLABLE = {"function", "method", "constructor", "macro"}


def recover(repo_id, question, evidence, search, *, limit=16, followups=2):
    """Read primary definitions, then unique named helpers and missing aspects.

    Lookup is not proof of dispatch. Every recovered item retains a precise
    source identity and the reason it was read. No target code is executed.
    """
    explicit = symbol_references(question)
    exact = [
        e
        for e in evidence
        if e.get("kind") in CALLABLE
        and any(
            e["qualified"].lower() == ref or e["qualified"].lower().endswith("." + ref)
            for ref in explicit
        )
    ]
    seeds = exact[:4] + [e for e in evidence if e not in exact][:1] if exact else evidence[:4]
    output = list(seeds[:limit])
    seen = {e["id"] for e in output}
    trace = []
    records = db.symbols_by_ids(repo_id, [e["id"] for e in output])
    with db.connection() as c:
        metadata = [
            dict(r)
            for r in c.execute(
                "SELECT id,path,name,qualified,kind,start_line,end_line,parent_id,source,docstring FROM symbols WHERE repo_id=?",
                (repo_id,),
            )
        ]
    by_name = {}
    globals_by_name = {}
    owners = {item["id"]: item["kind"] for item in metadata}
    for item in metadata:
        implementation = (
            item["kind"] == "macro" or "{" in item["source"] or item["path"].endswith(".py")
        )
        if item["kind"] in CALLABLE and implementation and not is_test_path(item["path"]):
            by_name.setdefault(item["name"], []).append(item)
        if item["kind"] in ("variable", "constant") and owners.get(item["parent_id"]) == "module":
            globals_by_name.setdefault((item["path"], item["name"]), []).append(item)

    def add(item, reason):
        if item["id"] in seen or len(output) >= limit:
            return
        seen.add(item["id"])
        output.append(
            {**item, "reason": reason, "traversal": [], "public_aliases": [], "recovered": True}
        )
        trace.append({"id": item["id"], "reason": reason})

    if re.search(r"\b(?:ordinary|compare|difference|versus)\b", question, re.I):
        for caller in records:
            name = caller["name"]
            counterpart = name[4:] if name.startswith("try_") else "try_" + name
            paired = [
                x
                for x in by_name.get(counterpart, [])
                if x["path"] == caller["path"] and x["parent_id"] == caller["parent_id"]
            ]
            if len(paired) == 1:
                add(
                    db.symbols_by_ids(repo_id, [paired[0]["id"]])[0],
                    "paired ordinary/fallible API definition read",
                )

    # Read referenced same-file global definitions and adjacent comments with
    # original coordinates. These are defaults/documented semantics, not proof
    # of the live value. Duplicate metadata entities describe the same span.
    primary_records = db.symbols_by_ids(repo_id, [e["id"] for e in output[:4]])
    for caller in primary_records:
        identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", caller["source"]))
        for (path, name), candidates in globals_by_name.items():
            if path != caller["path"] or name not in identifiers or len(output) >= limit:
                continue
            unique = {(x["start_line"], x["end_line"]): x for x in candidates}
            if len(unique) != 1:
                continue
            item = db.symbols_by_ids(repo_id, [next(iter(unique.values()))["id"]])[0]
            with db.connection() as connection:
                row = connection.execute(
                    "SELECT content FROM files WHERE repo_id=? AND path=?", (repo_id, path)
                ).fetchone()
            if row:
                lines = row[0].splitlines()
                start = item["start_line"] - 1
                while (
                    start > 0
                    and item["start_line"] - start <= 16
                    and lines[start - 1].lstrip().startswith(("//", "#", "*", "/*"))
                ):
                    start -= 1
                item.update(
                    start_line=start + 1,
                    source="\n".join(lines[start : item["end_line"]]),
                    read_extended=True,
                )
            item["helper_for"] = [caller["id"]]
            add(item, "referenced same-file global default and adjacent documentation")
    # Two rounds cover a primary -> helper -> helper chain. Keep reads bounded,
    # avoid common-name fan-out and prefer the caller's declared lexical owner.
    for _ in range(2):
        recovered = []
        additions = 0
        for caller in records:
            if caller["kind"] not in CALLABLE:
                continue
            source = re.sub(r"\b(\w+)\.(?:call|apply|bind)\s*\(", r"\1(", caller["source"])
            calls = set(
                re.findall(
                    r"(?<![\w.])(?:([A-Za-z_]\w*)\s*(?:\.|::)\s*)?([A-Za-z_]\w*)\s*(?:::\s*<[^;\n()]+>)?\(",
                    source,
                )
            )
            receiver = re.search(r"\bfunc\s*\(\s*(\w+)\s", caller["source"])
            own_receivers = {"self", "this", "cls", receiver[1] if receiver else ""}

            def query_hits(name):
                split = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
                words = {stem(x) for x in re.findall(r"[a-z0-9]+", split.lower())}
                query_words = {stem(x) for x in re.findall(r"[a-z0-9]+", question.lower())}
                return len(words & query_words)

            for owner, name in sorted(
                calls,
                key=lambda x: (x[1].lower() not in explicit, -query_hits(x[1]), -len(x[1]), x),
            ):
                candidates = by_name.get(name, [])
                local = [
                    x
                    for x in candidates
                    if x["path"] == caller["path"] and x["parent_id"] == caller["parent_id"]
                ]
                chosen = local if len(local) == 1 and owner in own_receivers else candidates
                # Alternate macro definitions may share one complete guard.
                chosen = list(
                    {(x["path"], x["start_line"], x["end_line"]): x for x in chosen}.values()
                )
                if len(chosen) > 1 and len({x["source"] for x in chosen}) == 1:
                    chosen = chosen[:1]
                if len(chosen) > 1 and len(name) >= 4:

                    def terms(text):
                        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
                        return {
                            stem(x) for x in re.findall(r"[a-z0-9]+", text.lower()) if len(x) > 2
                        }

                    query_terms = terms(question)

                    def relevance(item):
                        return 3 * len(query_terms & terms(item["qualified"])) + 0.25 * len(
                            query_terms & terms(item["docstring"])
                        )

                    ranked = sorted(
                        chosen,
                        key=relevance,
                        reverse=True,
                    )
                    best = relevance(ranked[0])
                    second = relevance(ranked[1])
                    chosen = ranked[:1] if best >= 2 and best > second else []
                if len(chosen) == 1:
                    if (
                        chosen[0]["path"] == caller["path"]
                        and caller["start_line"]
                        <= chosen[0]["start_line"]
                        <= chosen[0]["end_line"]
                        <= caller["end_line"]
                    ):
                        continue
                    for existing in output:
                        if existing["id"] == chosen[0]["id"]:
                            existing.setdefault("helper_for", []).append(caller["id"])
                    if chosen[0]["id"] in seen:
                        if chosen[0]["id"] != caller["id"]:
                            recovered.extend(db.symbols_by_ids(repo_id, [chosen[0]["id"]]))
                        continue
                    if additions >= 2:
                        continue
                    item = db.symbols_by_ids(repo_id, [chosen[0]["id"]])[0]
                    item["helper_for"] = [caller["id"]]
                    before = len(output)
                    add(item, "candidate helper identifier read; dispatch not proven")
                    if len(output) > before:
                        additions += 1
                        recovered.append(item)
        records = recovered[:2]
        if not records:
            break
    # Exact identifiers get their own lookup. Aspect searches are independent
    # of the full question, so a generic clause cannot crowd out a small helper.
    obligations = checklist(question, output)
    missing = [name for row in obligations for name in row["missing_named_definitions"]]
    queries = list(dict.fromkeys(missing + list(sorted(explicit)) + answer_aspects(question)))
    for query in list(dict.fromkeys(queries))[:followups]:
        found, _, _ = search(repo_id, query, mode="lexical", limit=4, hops=0)
        for item in found:
            add(item, "follow-up lexical source read")
    return output, {
        "source_reads": trace,
        "followup_queries": queries[:followups],
        "limit": limit,
        "obligation_checklist": checklist(question, output),
    }
