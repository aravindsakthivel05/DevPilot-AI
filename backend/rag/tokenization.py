"""Consistent English search stems with bounded caching and per-thread state."""

from functools import lru_cache
from threading import local

import snowballstemmer

_STATE = local()


@lru_cache(maxsize=50000)
def stem(word):
    if not hasattr(_STATE, "stemmer"):
        _STATE.stemmer = snowballstemmer.stemmer("english")
    return _STATE.stemmer.stemWord(word)
