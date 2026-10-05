"""Persistent FTS candidates and bounded, revision-aware graph metadata caches."""

from collections import Counter, OrderedDict
from threading import RLock

from . import db
from .namespaces import declared_aliases, scoped_package_prefix

VERSION = "2026-10-04-normalized-fts5-v5"
_LOCK = RLock()
_CACHE = OrderedDict()


def indexed_candidates(repo_id, question, tokenize, limit=256):
    with _LOCK, db.connection() as c:
        revision_row = c.execute(
            "SELECT revision FROM search_revisions WHERE repo_id=?", (repo_id,)
        ).fetchone()
        revision = revision_row[0] if revision_row else 0
        state = c.execute(
            "SELECT revision,version FROM search_state WHERE repo_id=?", (repo_id,)
        ).fetchone()
        if state is None or tuple(state) != (revision, VERSION):
            rows = c.execute(
                "SELECT id,qualified,source,docstring FROM symbols WHERE repo_id=?", (repo_id,)
            ).fetchall()
            c.execute("DELETE FROM symbols_fts WHERE repo_id=?", (repo_id,))
            documents, lengths, frequencies = [], [], Counter()
            for row in rows:
                names = tokenize(row["qualified"])
                body = tokenize(row["source"] + " " + row["docstring"])
                frequencies.update(set(names + body))
                lengths.append((row["id"], len(names) + len(body)))
                documents.append((row["id"], repo_id, " ".join(names), " ".join(body)))
            c.executemany("INSERT INTO symbols_fts VALUES (?,?,?,?)", documents)
            c.execute("DELETE FROM search_terms WHERE repo_id=?", (repo_id,))
            c.executemany(
                "INSERT INTO search_terms VALUES (?,?,?)",
                [(repo_id, term, count) for term, count in frequencies.items()],
            )
            c.executemany("INSERT OR REPLACE INTO search_lengths VALUES (?,?)", lengths)
            c.execute(
                "INSERT OR REPLACE INTO search_state VALUES (?,?,?)", (repo_id, revision, VERSION)
            )
        terms = list(dict.fromkeys(tokenize(question)))[:64]
        matches = []
        if terms:
            expression = " OR ".join('"' + t + '"' for t in terms)
            matches = c.execute(
                "SELECT symbol_id FROM symbols_fts WHERE symbols_fts MATCH ? AND repo_id=? "
                "ORDER BY bm25(symbols_fts,0,0,4,1) LIMIT ?",
                (expression, repo_id, limit),
            ).fetchall()
        key = (str(db.DB_PATH), repo_id, revision, VERSION)
        if key not in _CACHE:
            metadata = [
                dict(r)
                for r in c.execute(
                    "SELECT s.id,s.repo_id,path,name,qualified,kind,start_line,end_line,parent_id,language,role,length FROM symbols s LEFT JOIN search_lengths l ON l.symbol_id=s.id WHERE repo_id=? ORDER BY path,start_line,s.id",
                    (repo_id,),
                )
            ]
            for item in metadata:
                item["_name_tokens"] = tuple(tokenize(item["name"]))
            files = {
                r["path"]: r["content"]
                for r in c.execute(
                    "SELECT path,content FROM files WHERE repo_id=? AND (path='__init__.py' OR path LIKE '%/__init__.py')",
                    (repo_id,),
                )
            }
            repo = c.execute("SELECT source FROM repositories WHERE id=?", (repo_id,)).fetchone()
            aliases = (
                declared_aliases(metadata, files, scoped_package_prefix(dict(repo), files))
                if repo
                else {}
            )
            for item in metadata:
                item["public_aliases"] = aliases.get(item["id"], [])
            graph = [dict(r) for r in c.execute("SELECT * FROM edges WHERE repo_id=?", (repo_id,))]
            _CACHE[key] = (metadata, graph)
            while len(_CACHE) > 3:
                _CACHE.popitem(last=False)
        _CACHE.move_to_end(key)
        metadata, graph = _CACHE[key]
        placeholders = ",".join("?" for _ in terms)
        frequencies = (
            {
                r["term"]: r["frequency"]
                for r in c.execute(
                    f"SELECT term,frequency FROM search_terms WHERE repo_id=? AND term IN ({placeholders})",
                    (repo_id, *terms),
                )
            }
            if terms
            else {}
        )
        lengths = [item.get("length") or 0 for item in metadata]
    return (
        [r["symbol_id"] for r in matches],
        metadata,
        graph,
        {"df": frequencies, "average_length": sum(lengths) / max(1, len(lengths))},
    )
