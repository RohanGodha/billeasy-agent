"""Hybrid retriever: dense (Chroma) + lexical (BM25) + MMR re-rank.

Index = counter field-visit notes and support tickets. Each chunk carries the
counter_id so the agent can ground messages with citations like [FN-CTR-0001-3a9f21].
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.infrastructure.datasource import get_datasource
from app.infrastructure.llm import get_llm_router
from app.observability import get_logger
from app.settings import get_settings

from .mmr import mmr_rerank

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-zA-Z]+")


def _tokenize(s: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s)]


class HybridRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._chroma = None
        self._collection = None
        self._bm25: BM25Okapi | None = None
        self._corpus_tokens: list[list[str]] = []
        self._chunks: list[dict[str, Any]] = []
        self._ready = False

    async def initialise(self) -> None:
        if self._ready:
            return
        ds = get_datasource()
        notes_result = await ds.get_field_notes()
        field_notes = notes_result.data or []
        if not field_notes:
            logger.info("No field notes available — RAG index will be empty.")
            self._ready = True
            return

        # Build chunk records
        chunks: list[dict[str, Any]] = []
        for note in field_notes:
            chunks.append(
                {
                    "id": f"FN-{note['counter_id']}-{note['id'][:6]}",
                    "counter_id": note["counter_id"],
                    "channel": note.get("channel"),
                    "ts": note.get("ts"),
                    "text": note["summary"],
                }
            )
        self._chunks = chunks

        # BM25 index
        self._corpus_tokens = [_tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens)

        # Chroma index
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._chroma = chromadb.PersistentClient(
                path=str(self.settings.chroma_abs_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._chroma.get_or_create_collection(
                name="field_notes",
                metadata={"hnsw:space": "cosine"},
            )
            existing = set(self._collection.get(include=[])["ids"])
            new_chunks = [c for c in chunks if c["id"] not in existing]
            if new_chunks:
                logger.info("Embedding %d new chunks into Chroma...", len(new_chunks))
                router = get_llm_router()
                vecs = await router.embed([c["text"] for c in new_chunks])
                self._collection.add(
                    ids=[c["id"] for c in new_chunks],
                    documents=[c["text"] for c in new_chunks],
                    embeddings=vecs,
                    metadatas=[{"counter_id": c["counter_id"], "channel": c.get("channel") or ""} for c in new_chunks],
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Chroma unavailable (%s) — RAG will use BM25 only.", e)
            self._chroma = None
            self._collection = None

        self._ready = True
        logger.info("HybridRetriever ready with %d chunks.", len(chunks))

    @property
    def mode(self) -> str:
        """Actual retrieval mode: dense+lexical when Chroma is loaded, else lexical only."""
        return "chroma+bm25" if self._collection is not None else "bm25"

    async def search(self, query: str, *, k: int = 5, counter_id: str | None = None) -> list[dict[str, Any]]:
        if not self._ready:
            await self.initialise()
        if not self._chunks:
            return []

        # Optional filter by counter
        idx_pool = list(range(len(self._chunks)))
        if counter_id:
            idx_pool = [i for i, c in enumerate(self._chunks) if c["counter_id"] == counter_id]
            if not idx_pool:
                return []

        # --- Dense scores ---
        dense_scores = dict.fromkeys(idx_pool, 0.0)
        if self._collection is not None:
            try:
                router = get_llm_router()
                qvec = (await router.embed([query]))[0]
                qres = self._collection.query(
                    query_embeddings=[qvec],
                    n_results=min(len(idx_pool), 30),
                )
                ids_returned = qres["ids"][0]
                dists = qres["distances"][0]
                id_to_idx = {c["id"]: i for i, c in enumerate(self._chunks)}
                for cid, dist in zip(ids_returned, dists, strict=False):
                    if cid in id_to_idx:
                        idx = id_to_idx[cid]
                        if idx in dense_scores:
                            dense_scores[idx] = 1.0 / (1.0 + dist)  # convert distance → similarity
            except Exception as e:  # noqa: BLE001
                logger.warning("Dense retrieval failed (%s) — using BM25 only.", e)

        # --- BM25 scores ---
        q_tokens = _tokenize(query)
        bm25_raw = self._bm25.get_scores(q_tokens) if self._bm25 else np.zeros(len(self._chunks))
        bm25_max = float(bm25_raw.max()) or 1.0
        bm25_norm = {i: float(bm25_raw[i] / bm25_max) for i in idx_pool}

        # --- Reciprocal rank fusion ---
        dense_rank = sorted(idx_pool, key=lambda i: dense_scores.get(i, 0.0), reverse=True)
        bm25_rank = sorted(idx_pool, key=lambda i: bm25_norm.get(i, 0.0), reverse=True)

        K = 60  # standard RRF
        fused: dict[int, float] = dict.fromkeys(idx_pool, 0.0)
        for r, idx in enumerate(dense_rank):
            fused[idx] += 1.0 / (K + r)
        for r, idx in enumerate(bm25_rank):
            fused[idx] += 1.0 / (K + r)

        # --- MMR over top-N fused ---
        top_n = sorted(idx_pool, key=lambda i: fused[i], reverse=True)[: max(k * 4, 8)]
        # Build vectors for MMR — use BM25 vec proxy if no dense
        if self._collection is not None:
            try:
                # Fetch embeddings for the top_n chunks
                chunk_ids = [self._chunks[i]["id"] for i in top_n]
                got = self._collection.get(ids=chunk_ids, include=["embeddings"])
                emb_map = dict(zip(got["ids"], got["embeddings"], strict=False))
                doc_vecs = [emb_map.get(self._chunks[i]["id"], [0.0]) for i in top_n]
                router = get_llm_router()
                q_vec = (await router.embed([query]))[0]
                mmr_idx = mmr_rerank(q_vec, doc_vecs, [fused[i] for i in top_n], k=k, lambda_=0.7)
                selected = [top_n[i] for i in mmr_idx]
            except Exception:  # noqa: BLE001
                selected = top_n[:k]
        else:
            selected = top_n[:k]

        results = []
        for i in selected:
            c = self._chunks[i]
            results.append(
                {
                    "id": c["id"],
                    "counter_id": c["counter_id"],
                    "channel": c.get("channel"),
                    "ts": c.get("ts"),
                    "text": c["text"],
                    "fused_score": round(fused[i], 4),
                    "bm25": round(bm25_norm[i], 4),
                    "dense": round(dense_scores.get(i, 0.0), 4),
                }
            )
        return results


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    return HybridRetriever()


async def init_retriever_async() -> None:
    """Used by startup hooks."""
    try:
        await get_retriever().initialise()
    except Exception as e:  # noqa: BLE001
        logger.warning("RAG init deferred: %s", e)
