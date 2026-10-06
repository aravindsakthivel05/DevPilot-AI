"""Small process-local lexical cache; derived evidence, never cached AI answers."""

import copy
from collections import OrderedDict
from threading import RLock

from .. import db

_LOCK = RLock()
_CACHE = OrderedDict()


def identity(repo_id):
    repo = db.repository(repo_id)
    if not repo or repo["status"] != "ready":
        return None
    # Include database/WAL stamps as well as snapshot and index revision: edits
    # to chunk metadata cannot accidentally reuse older source evidence.
    stamps = []
    for path in (db.DB_PATH, db.DB_PATH.with_name(db.DB_PATH.name + "-wal")):
        try:
            stat = path.stat()
            stamps.append((stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            stamps.append(None)
    with db.connection() as connection:
        row = connection.execute(
            "SELECT revision FROM search_revisions WHERE repo_id=?", (repo_id,)
        ).fetchone()
    return (str(db.DB_PATH), repo_id, repo["fingerprint"], row[0] if row else 0, tuple(stamps))


def get(key):
    with _LOCK:
        if key not in _CACHE:
            return None
        _CACHE.move_to_end(key)
        return copy.deepcopy(_CACHE[key])


def put(key, value):
    with _LOCK:
        _CACHE[key] = copy.deepcopy(value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > 32:
            _CACHE.popitem(last=False)
