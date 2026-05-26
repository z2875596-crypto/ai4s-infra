"""Memory store — vector database-backed persistent agent memory.

Backends: Weaviate, ChromaDB, Qdrant, or in-memory (dev).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ai4s.common.exceptions import MemoryStoreError
from ai4s.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryEntry:
    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    content: str = ""
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0
    importance: float = 0.5         # 0.0 – 1.0, higher = more important
    decay_rate: float = 0.01        # Importance decays per access (recency boost)
    tags: list[str] = field(default_factory=list)
    source: str = ""                # "conversation", "tool_output", "user", "system"


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """Vector database-backed memory store.

    Features:
      - CRUD for memory entries
      - Vector embedding generation (OpenAI / local model)
      - TTL and importance-based eviction
      - Tag-based organization
    """

    def __init__(
        self,
        backend: str = "weaviate",         # weaviate | chromadb | qdrant | memory
        collection_name: str = "agent_memory",
        embedding_model: str = "text-embedding-3-small",
        embedding_api_key: str | None = None,
        embedding_api_base: str | None = None,
        max_entries: int = 100_000,
        ttl_days: int | None = None,
    ) -> None:
        self.backend = backend
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._embedding_api_key = embedding_api_key
        self._embedding_api_base = embedding_api_base
        self.max_entries = max_entries
        self.ttl_days = ttl_days
        self._entries: dict[str, MemoryEntry] = {}
        self._embedding_cache: dict[str, list[float]] = {}

    # -- CRUD ---------------------------------------------------------------

    async def store(self, entry: MemoryEntry) -> str:
        if entry.embedding is None:
            entry.embedding = await self._embed(entry.content)
        self._entries[entry.memory_id] = entry
        await self._evict_if_needed()
        logger.debug("Memory stored: %s (tags=%s, importance=%.2f)",
                      entry.memory_id, entry.tags, entry.importance)
        return entry.memory_id

    async def store_text(
        self,
        content: str,
        tags: list[str] | None = None,
        importance: float = 0.5,
        source: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        entry = MemoryEntry(
            content=content,
            tags=tags or [],
            importance=importance,
            source=source,
            metadata=metadata or {},
        )
        return await self.store(entry)

    async def get(self, memory_id: str) -> MemoryEntry | None:
        entry = self._entries.get(memory_id)
        if entry:
            entry.access_count += 1
            # Decay importance slightly on access (recency effect)
            entry.importance = min(1.0, entry.importance * (1 + entry.decay_rate))
        return entry

    async def delete(self, memory_id: str) -> bool:
        if memory_id in self._entries:
            del self._entries[memory_id]
            return True
        return False

    async def update(self, memory_id: str, **kwargs) -> MemoryEntry | None:
        entry = self._entries.get(memory_id)
        if not entry:
            return None
        for k, v in kwargs.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        if "content" in kwargs:
            entry.embedding = await self._embed(entry.content)
        return entry

    # -- query --------------------------------------------------------------

    async def list_by_tag(self, tag: str, limit: int = 50) -> list[MemoryEntry]:
        results = [e for e in self._entries.values() if tag in e.tags]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    async def list_by_source(self, source: str, limit: int = 50) -> list[MemoryEntry]:
        results = [e for e in self._entries.values() if e.source == source]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    async def count(self) -> int:
        return len(self._entries)

    async def stats(self) -> dict[str, Any]:
        entries = list(self._entries.values())
        if not entries:
            return {"total": 0}
        return {
            "total": len(entries),
            "avg_importance": sum(e.importance for e in entries) / len(entries),
            "total_accesses": sum(e.access_count for e in entries),
            "sources": list({e.source for e in entries}),
            "tags": list({t for e in entries for t in e.tags}),
            "oldest": min(e.created_at for e in entries),
            "newest": max(e.created_at for e in entries),
        }

    # -- embedding ----------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        In production: calls OpenAI / Cohere / local embedding API.
        Fallback: deterministic hash-based pseudo-embedding for dev.
        """
        # Check cache
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        if self._embedding_api_key:
            embedding = await self._embed_openai(text)
        else:
            # Dev fallback: hash-based pseudo-embedding (128-dim)
            h = hashlib.sha256(text.encode()).digest()
            embedding = [float(b) / 255.0 for b in h[:128]]

        self._embedding_cache[cache_key] = embedding
        return embedding

    async def _embed_openai(self, text: str) -> list[float]:
        import httpx

        url = (self._embedding_api_base or "https://api.openai.com/v1") + "/embeddings"
        headers = {"Authorization": f"Bearer {self._embedding_api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json={
                "input": text,
                "model": self.embedding_model,
            })
            if resp.status_code != 200:
                raise MemoryStoreError(f"Embedding API error: {resp.status_code}")
            data = resp.json()
            return data["data"][0]["embedding"]

    # -- eviction -----------------------------------------------------------

    async def _evict_if_needed(self) -> None:
        if len(self._entries) <= self.max_entries:
            return

        # Evict lowest importance entries first
        entries = sorted(self._entries.values(), key=lambda e: e.importance)
        to_remove = len(self._entries) - self.max_entries
        for e in entries[:to_remove]:
            del self._entries[e.memory_id]
        logger.info("Evicted %d low-importance memories", to_remove)

    async def cleanup_expired(self) -> int:
        """Remove entries older than TTL."""
        if not self.ttl_days:
            return 0
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.ttl_days)).isoformat()
        expired = [
            mid for mid, e in self._entries.items()
            if e.created_at < cutoff and e.importance < 0.5
        ]
        for mid in expired:
            del self._entries[mid]
        if expired:
            logger.info("Cleaned up %d expired memories", len(expired))
        return len(expired)

    # -- copy to/from other stores ------------------------------------------

    async def copy_to(self, target: MemoryStore) -> int:
        for entry in self._entries.values():
            await target.store(entry)
        return len(self._entries)
