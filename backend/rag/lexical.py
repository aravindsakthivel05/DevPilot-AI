"""Repository-local BM25 scoring, independently inspectable and configurable."""

import math


def bm25(query, terms, length, count, df, average_length, k1=1.2, b=0.75):
    score = 0.0
    for term in query:
        tf = terms[term]
        if tf:
            idf = math.log(1 + (count - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / max(1, average_length)))
    return score
