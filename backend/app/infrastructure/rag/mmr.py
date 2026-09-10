"""Maximal Marginal Relevance — diversity-aware re-ranking."""
from __future__ import annotations

import numpy as np


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)


def mmr_rerank(
    query_vec: list[float],
    doc_vecs: list[list[float]],
    doc_scores: list[float],
    *,
    k: int = 5,
    lambda_: float = 0.7,
) -> list[int]:
    """Return indices of the top-k documents under MMR."""
    if not doc_vecs:
        return []
    q = np.asarray(query_vec)
    docs = [np.asarray(v) for v in doc_vecs]
    selected: list[int] = []
    remaining = set(range(len(docs)))
    while remaining and len(selected) < k:
        best = None
        best_val = -1e9
        for i in remaining:
            rel = doc_scores[i] if doc_scores else cosine(q, docs[i])
            div = max((cosine(docs[i], docs[j]) for j in selected), default=0.0)
            val = lambda_ * rel - (1 - lambda_) * div
            if val > best_val:
                best_val = val
                best = i
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)
    return selected
