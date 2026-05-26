"""Memory retriever — semantic search, hybrid retrieval, and memory ranking."""

from __future__ import annotations

from typing import Any

import numpy as np

from ai4s.common.logging import get_logger
from ai4s.agent_runtime.memory.store import MemoryEntry, MemoryStore

logger = get_logger(__name__)


class MemoryRetriever:
    """Retrieves relevant memories using semantic and hybrid search.

    Retrieval strategies:
      - semantic  : cosine similarity of embeddings
      - hybrid    : semantic + keyword (BM25-like) combined
      - recency   : most recent first
      - importance: highest importance first
      - fusion    : weighted combination of all above (Reciprocal Rank Fusion)

    Usage::

        store = MemoryStore()
        retriever = MemoryRetriever(store, top_k=10)

        results = await retriever.semantic_search("What did we discuss about GPU quotas?")
        results = await retriever.hybrid_search("GPU quota", semantic_weight=0.7)
        context_str = retriever.format_context(results, max_tokens=4000)
    """

    def __init__(
        self,
        store: MemoryStore,
        top_k: int = 10,
        similarity_threshold: float = 0.5,
    ) -> None:
        self.store = store
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    # -- semantic search ----------------------------------------------------

    async def semantic_search(
        self,
        query: str,
        top_k: int | None = None,
        filter_tags: list[str] | None = None,
        filter_source: str | None = None,
    ) -> list[MemoryEntry]:
        """Retrieve top-K semantically similar memories."""
        k = top_k or self.top_k
        query_emb = await self.store._embed(query)

        candidates = list(self.store._entries.values())

        # Filters
        if filter_tags:
            candidates = [e for e in candidates if any(t in e.tags for t in filter_tags)]
        if filter_source:
            candidates = [e for e in candidates if e.source == filter_source]

        if not candidates:
            return []

        # Compute cosine similarity
        scored: list[tuple[MemoryEntry, float]] = []
        for entry in candidates:
            if entry.embedding is None:
                continue
            sim = self._cosine_similarity(query_emb, entry.embedding)
            if sim >= self.similarity_threshold:
                # Blend in importance and recency
                combined = (0.7 * sim + 0.2 * entry.importance + 0.1 * self._recency_score(entry))
                scored.append((entry, combined))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = [e for e, _ in scored[:k]]

        for e in results:
            e.access_count += 1

        logger.info("Semantic search: %d results for query (len=%d)", len(results), len(query))
        return results

    # -- hybrid search ------------------------------------------------------

    async def hybrid_search(
        self,
        query: str,
        top_k: int | None = None,
        semantic_weight: float = 0.7,
        filter_tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Combine semantic search with keyword matching using weighted fusion."""
        k = top_k or self.top_k

        semantic_results = await self.semantic_search(
            query, top_k=k * 2, filter_tags=filter_tags
        )
        keyword_results = self._keyword_search(query, top_k=k * 2, filter_tags=filter_tags)

        # Reciprocal Rank Fusion (RRF)
        scores: dict[str, float] = {}
        for rank, entry in enumerate(semantic_results):
            scores[entry.memory_id] = scores.get(entry.memory_id, 0) + semantic_weight / (60 + rank)
        for rank, entry in enumerate(keyword_results):
            scores[entry.memory_id] = scores.get(entry.memory_id, 0) + (1 - semantic_weight) / (60 + rank)

        # Sort and take top-K
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:k]
        id_to_entry = {e.memory_id: e for e in semantic_results + keyword_results}
        return [id_to_entry[mid] for mid in sorted_ids if mid in id_to_entry]

    # -- keyword search -----------------------------------------------------

    def _keyword_search(
        self,
        query: str,
        top_k: int = 10,
        filter_tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Simple TF-IDF-like keyword matching."""
        query_terms = set(query.lower().split())
        candidates = list(self.store._entries.values())

        if filter_tags:
            candidates = [e for e in candidates if any(t in e.tags for t in filter_tags)]

        scored: list[tuple[MemoryEntry, float]] = []
        for entry in candidates:
            content_lower = entry.content.lower()
            # Term frequency
            score = sum(content_lower.count(term) for term in query_terms)
            # Boost exact phrase match
            if query.lower() in content_lower:
                score += 10
            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:top_k]]

    # -- static retrievers --------------------------------------------------

    async def recent_memories(self, n: int = 20) -> list[MemoryEntry]:
        entries = sorted(
            self.store._entries.values(),
            key=lambda e: e.created_at,
            reverse=True,
        )
        return entries[:n]

    async def important_memories(self, threshold: float = 0.7, n: int = 20) -> list[MemoryEntry]:
        entries = [e for e in self.store._entries.values() if e.importance >= threshold]
        entries.sort(key=lambda e: e.importance, reverse=True)
        return entries[:n]

    async def memories_by_tag(self, tag: str, n: int = 20) -> list[MemoryEntry]:
        return await self.store.list_by_tag(tag, limit=n)

    # -- context formatting -------------------------------------------------

    def format_context(
        self,
        entries: list[MemoryEntry],
        max_tokens: int = 4000,
        template: str = "[Memory {id}] ({tags}) {content}",
    ) -> str:
        """Format retrieved memories as context string for an LLM prompt."""
        parts: list[str] = []
        token_estimate = 0

        for entry in entries:
            text = template.format(
                id=entry.memory_id[:8],
                tags=", ".join(entry.tags) if entry.tags else "general",
                content=entry.content,
            )
            # Rough token estimate: ~4 chars per token
            token_estimate += len(text) // 4
            if token_estimate > max_tokens:
                break
            parts.append(text)

        return "\n\n".join(parts)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        a_arr = np.array(a[:n])
        b_arr = np.array(b[:n])
        dot = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    @staticmethod
    def _recency_score(entry: MemoryEntry) -> float:
        from datetime import datetime, timezone

        try:
            created = datetime.fromisoformat(entry.created_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            return 1.0 / (1.0 + age_hours / 24.0)  # Decay over days
        except Exception:
            return 0.5
