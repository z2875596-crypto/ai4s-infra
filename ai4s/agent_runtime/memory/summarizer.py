"""Memory summarizer — compresses long conversations into compact, retrievable memories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ai4s.common.logging import get_logger
from ai4s.agent_runtime.memory.store import MemoryEntry, MemoryStore

logger = get_logger(__name__)


class MemorySummarizer:
    """Summarizes large context windows into concise, important-memory entries.

    Triggers:
      - Context exceeds token budget (automatic trunction/summarization)
      - Periodic background compression of old, low-importance memories
      - Explicit user request

    Summarization strategies:
      - extractive  : select most important sentences (fast, local)
      - abstractive : call LLM to generate summary (better, slower)
      - hierarchical: summarize chunks, then summarize summaries
    """

    def __init__(
        self,
        store: MemoryStore,
        max_context_tokens: int = 128000,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        llm_summarize_fn: callable | None = None,
    ) -> None:
        self.store = store
        self.max_context_tokens = max_context_tokens
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._llm_summarize = llm_summarize_fn   # async fn(text: str) -> str

    # -- conversation summarization -----------------------------------------

    async def summarize_conversation(
        self,
        messages: list[dict[str, str]],
        tags: list[str] | None = None,
        use_llm: bool = True,
    ) -> MemoryEntry:
        """Summarize a full conversation into a single memory entry."""
        full_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in messages
        )

        summary = await self._generate_summary(full_text, use_llm)
        import uuid

        entry = MemoryEntry(
            memory_id=f"conv-summary-{uuid.uuid4().hex[:8]}",
            content=summary,
            tags=tags or ["conversation_summary"],
            importance=0.7,
            source="summarizer",
            metadata={
                "message_count": len(messages),
                "original_length_chars": len(full_text),
                "summary_length_chars": len(summary),
                "compression_ratio": len(summary) / max(len(full_text), 1),
            },
        )

        await self.store.store(entry)
        logger.info("Conversation summarized: %d messages → %d chars (%.1f%% compression)",
                     len(messages), len(summary), entry.metadata["compression_ratio"] * 100)
        return entry

    # -- progressive summarization ------------------------------------------

    async def progressive_summarize(
        self,
        text: str,
        max_chunk_tokens: int = 2000,
    ) -> str:
        """Hierarchical summarization: chunk → summarize each → summarize summaries."""
        chunks = self._chunk_text(text, max_chunk_tokens * 4)  # ~4 chars/token

        if len(chunks) <= 1:
            return await self._generate_summary(text, use_llm=True)

        # First level: summarize each chunk
        chunk_summaries: list[str] = []
        for chunk in chunks:
            summary = await self._generate_summary(chunk, use_llm=True)
            chunk_summaries.append(summary)

        # Second level: summarize the concatenated summaries
        combined = "\n\n".join(chunk_summaries)
        return await self._generate_summary(combined, use_llm=True)

    # -- memory compression -------------------------------------------------

    async def compress_old_memories(self, older_than_days: int = 30) -> int:
        """Compress low-importance memories older than threshold."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        compressed = 0

        for mid, entry in list(self.store._entries.items()):
            if entry.created_at < cutoff and entry.importance < 0.3:
                if len(entry.content) > 500:
                    entry.content = await self._generate_summary(entry.content, use_llm=False)
                    entry.metadata["compressed"] = True
                    entry.metadata["original_length"] = len(entry.content)
                    compressed += 1

        if compressed:
            logger.info("Compressed %d old memories", compressed)
        return compressed

    async def deduplicate_memories(self, similarity_threshold: float = 0.9) -> int:
        """Remove near-duplicate memories based on embedding similarity."""
        from ai4s.agent_runtime.memory.retrieval import MemoryRetriever

        retriever = MemoryRetriever(self.store)
        removed = 0

        entries = sorted(self.store._entries.values(), key=lambda e: e.created_at)
        for i, entry in enumerate(entries):
            if entry.memory_id not in self.store._entries:
                continue
            # Search for near-duplicates among older entries
            similar = await retriever.semantic_search(
                entry.content, top_k=3, similar_threshold=similarity_threshold
            )
            for dup in similar:
                if dup.memory_id != entry.memory_id and dup.created_at < entry.created_at:
                    await self.store.delete(entry.memory_id)
                    removed += 1
                    break

        logger.info("Deduplication removed %d entries", removed)
        return removed

    # -- token budget -------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (~4 chars per token)."""
        return len(text) // 4

    async def should_summarize(self, context_text: str) -> bool:
        """Check if context exceeds 80% of token budget."""
        return self.estimate_tokens(context_text) > (self.max_context_tokens * 0.8)

    # -- summarization ------------------------------------------------------

    async def _generate_summary(self, text: str, use_llm: bool = True) -> str:
        """Generate a summary of the given text."""
        if use_llm and self._llm_summarize:
            try:
                prompt = (
                    "Summarize the following text concisely, preserving key facts, "
                    "decisions, and action items.\n\nText:\n" + text
                )
                return await self._llm_summarize(prompt)
            except Exception as exc:
                logger.warning("LLM summarization failed, falling back to extractive: %s", exc)

        # Extractive fallback
        return self._extractive_summary(text)

    @staticmethod
    def _extractive_summary(text: str, max_sentences: int = 10) -> str:
        """Select the most informative sentences (extractive, no LLM needed)."""
        sentences = [s.strip() for s in text.replace("\n", ". ").split(". ") if len(s.strip()) > 20]

        if len(sentences) <= max_sentences:
            return ". ".join(sentences) + "."

        # Score sentences by: length (medium is good), position (early is important),
        # keyword presence (numbers, proper nouns)
        def score(s: str, idx: int) -> float:
            s_len = len(s)
            len_score = 1.0 - abs(s_len - 100) / 100  # Prefer ~100 char sentences
            pos_score = 1.0 - (idx / len(sentences))
            keyword_score = sum(1 for c in s if c.isupper()) / max(s_len, 1) * 10
            return len_score * 0.3 + pos_score * 0.4 + keyword_score * 0.3

        scored = [(s, score(s, i)) for i, s in enumerate(sentences)]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = sorted(scored[:max_sentences], key=lambda x: sentences.index(x[0]))

        return ". ".join(s for s, _ in top) + "."

    @staticmethod
    def _chunk_text(text: str, chunk_chars: int) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_chars, len(text))
            # Try to break at a sentence boundary
            if end < len(text):
                for delimiter in [". ", "\n", " "]:
                    last = text.rfind(delimiter, start, end)
                    if last > start + chunk_chars // 2:
                        end = last + len(delimiter)
                        break
            chunks.append(text[start:end].strip())
            start = end
        return chunks
