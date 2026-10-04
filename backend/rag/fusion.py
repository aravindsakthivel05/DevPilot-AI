"""Weighted reciprocal-rank fusion retains original per-channel scores."""

from collections import defaultdict


def fuse(rankings, weights, constant=60):
    scores = defaultdict(float)
    channels = defaultdict(dict)
    for name, ranking in rankings.items():
        for rank, sid in enumerate(ranking, 1):
            score = 1 / (constant + rank)
            scores[sid] += weights.get(name, 1) * score
            channels[sid][name] = {"rank": rank, "rrf_score": score}
    return scores, dict(channels)
