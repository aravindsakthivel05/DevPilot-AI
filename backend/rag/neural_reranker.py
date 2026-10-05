"""Optional locally executed cross-encoder; no repository text leaves the Mac."""

import math
import os
from threading import RLock

from ..config import DATA
from ..evidence import excerpt

_LOCK = RLock()
_MODELS = {}


def rank(question, records, model_name=None):
    name = model_name or os.environ.get("DEVPILOT_NEURAL_RERANKER")
    if not name:
        return None
    with _LOCK:
        if name not in _MODELS:
            import torch
            from sentence_transformers import CrossEncoder

            torch.set_num_threads(2)
            _MODELS[name] = CrossEncoder(
                name,
                device="cpu",
                max_length=512,
                cache_folder=str(DATA / "reranker-models"),
                trust_remote_code=False,
            )
        model = _MODELS[name]
        passages = [
            r["path"]
            + "\n"
            + r["qualified"]
            + "\n"
            + r.get("docstring", "")[:800]
            + "\n"
            + excerpt(r, question, 320)["source"]
            for r in records
        ]
        values = model.predict(
            [(question, p) for p in passages], batch_size=8, show_progress_bar=False
        )
    scores = [float(v) for v in values]
    if len(scores) != len(records) or not all(math.isfinite(v) for v in scores):
        raise ValueError("Local reranker returned invalid scores")
    return dict(zip((r["id"] for r in records), scores))
