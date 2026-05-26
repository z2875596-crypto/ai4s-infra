"""Feedback collector — manages human preference annotation lifecycle."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class FeedbackStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    ANNOTATED = "annotated"
    SKIPPED = "skipped"
    FLAGGED = "flagged"             # Needs review by senior annotator
    CONSENSUS = "consensus"


class AnnotationChoice(str, Enum):
    A = "A"
    B = "B"
    TIE = "tie"
    BOTH_BAD = "both_bad"
    BOTH_GOOD = "both_good"


@dataclass
class FeedbackItem:
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    prompt: str = ""
    response_a: str = ""
    response_b: str = ""
    status: FeedbackStatus = FeedbackStatus.PENDING
    annotation: AnnotationChoice | None = None
    annotator_id: str | None = None
    confidence: float = 1.0               # Annotator self-reported confidence
    annotated_at: str | None = None
    review_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_preference_pair(self) -> dict[str, Any] | None:
        """Convert annotation to (prompt, chosen, rejected) format."""
        if self.annotation == AnnotationChoice.A:
            return {"prompt": self.prompt, "chosen": self.response_a, "rejected": self.response_b}
        elif self.annotation == AnnotationChoice.B:
            return {"prompt": self.prompt, "chosen": self.response_b, "rejected": self.response_a}
        return None


# ---------------------------------------------------------------------------
# collector
# ---------------------------------------------------------------------------


class FeedbackCollector:
    """Manages the full feedback annotation lifecycle.

    Features:
      - Pool-based active learning (sample uncertain items for annotation)
      - Multi-annotator assignment
      - Priority queue for annotation
      - Export to training data format
    """

    def __init__(self, pool_size: int = 1000, persist_path: str | None = None) -> None:
        self.pool_size = pool_size
        self.persist_path = Path(persist_path) if persist_path else None
        self._items: dict[str, FeedbackItem] = {}
        self._annotator_assignments: dict[str, list[str]] = {}
        if self.persist_path and self.persist_path.exists():
            self._load()

    # -- add items ----------------------------------------------------------

    def add_items(self, items: list[FeedbackItem]) -> list[str]:
        ids: list[str] = []
        for item in items:
            self._items[item.item_id] = item
            ids.append(item.item_id)
        self._maybe_save()
        return ids

    def add_generated_pairs(
        self,
        prompts: list[str],
        responses_a: list[str],
        responses_b: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Batch-create feedback items from two model outputs."""
        ids: list[str] = []
        for p, ra, rb in zip(prompts, responses_a, responses_b):
            item = FeedbackItem(
                prompt=p,
                response_a=ra,
                response_b=rb,
                metadata=metadata or {},
            )
            self._items[item.item_id] = item
            ids.append(item.item_id)
        self._maybe_save()
        return ids

    # -- assignment ---------------------------------------------------------

    def assign_to_annotator(
        self, annotator_id: str, n: int = 5, strategy: str = "random"
    ) -> list[FeedbackItem]:
        """Assign n pending items to an annotator.

        Strategies:
          - random       : random sample from pending pool
          - uncertainty  : items where current consensus is least clear
          - priority     : highest metadata["priority"] first
        """
        pending = [item for item in self._items.values()
                   if item.status == FeedbackStatus.PENDING]

        if strategy == "priority":
            pending.sort(key=lambda x: x.metadata.get("priority", 0), reverse=True)
        elif strategy == "uncertainty":
            # Items with most annotator disagreement (if re-assigning)
            pending.sort(key=lambda x: x.metadata.get("disagreement_score", 0), reverse=True)
        else:
            import random
            random.shuffle(pending)

        assigned = pending[:n]
        for item in assigned:
            item.status = FeedbackStatus.ASSIGNED
            item.annotator_id = annotator_id
            self._annotator_assignments.setdefault(annotator_id, []).append(item.item_id)

        self._maybe_save()
        return assigned

    # -- annotation ---------------------------------------------------------

    def record_annotation(
        self,
        item_id: str,
        annotator_id: str,
        choice: AnnotationChoice,
        confidence: float = 1.0,
        notes: str = "",
    ) -> FeedbackItem:
        item = self._items.get(item_id)
        if not item:
            raise KeyError(f"Feedback item not found: {item_id}")

        item.annotation = choice
        item.confidence = confidence
        item.annotated_at = datetime.now(timezone.utc).isoformat()
        item.review_notes = notes
        item.status = FeedbackStatus.ANNOTATED

        self._maybe_save()
        return item

    # -- export -------------------------------------------------------------

    def get_preference_pairs(self) -> list[dict[str, Any]]:
        """Export all annotated items as (prompt, chosen, rejected) triples."""
        pairs: list[dict[str, Any]] = []
        for item in self._items.values():
            p = item.to_preference_pair()
            if p:
                p["metadata"] = item.metadata
                pairs.append(p)
        return pairs

    def get_annotated_count(self) -> int:
        return sum(1 for i in self._items.values()
                   if i.status in (FeedbackStatus.ANNOTATED, FeedbackStatus.CONSENSUS))

    def get_pending_count(self) -> int:
        return sum(1 for i in self._items.values()
                   if i.status == FeedbackStatus.PENDING)

    def stats(self) -> dict[str, Any]:
        items = list(self._items.values())
        statuses = {}
        for item in items:
            statuses[item.status.value] = statuses.get(item.status.value, 0) + 1

        choices = {}
        for item in items:
            if item.annotation:
                choices[item.annotation.value] = choices.get(item.annotation.value, 0) + 1

        return {
            "total": len(items),
            "by_status": statuses,
            "by_choice": choices,
            "annotators": len(self._annotator_assignments),
            "avg_confidence": sum(i.confidence for i in items if i.annotation) / max(
                sum(1 for i in items if i.annotation), 1
            ),
        }

    # -- active learning ----------------------------------------------------

    def get_uncertain_samples(self, n: int = 10) -> list[FeedbackItem]:
        """Return items where annotators disagree most (for re-annotation)."""
        candidates = [
            item for item in self._items.values()
            if item.status == FeedbackStatus.ANNOTATED
            and item.metadata.get("disagreement_score", 0) > 0
        ]
        candidates.sort(key=lambda x: x.metadata.get("disagreement_score", 0), reverse=True)
        return candidates[:n]

    # -- persistence --------------------------------------------------------

    def _maybe_save(self) -> None:
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for item in self._items.values():
            d = {
                "item_id": item.item_id,
                "prompt": item.prompt,
                "response_a": item.response_a,
                "response_b": item.response_b,
                "status": item.status.value,
                "annotation": item.annotation.value if item.annotation else None,
                "annotator_id": item.annotator_id,
                "confidence": item.confidence,
                "annotated_at": item.annotated_at,
                "review_notes": item.review_notes,
                "metadata": item.metadata,
                "tags": item.tags,
            }
            data.append(d)
        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _load(self) -> None:
        with open(self.persist_path, encoding="utf-8") as f:
            data = json.load(f)
        for d in data:
            d["status"] = FeedbackStatus(d["status"])
            d["annotation"] = AnnotationChoice(d["annotation"]) if d["annotation"] else None
            self._items[d["item_id"]] = FeedbackItem(**{k: v for k, v in d.items() if k != "item_id"})
            # Restore item_id
            self._items[d["item_id"]].item_id = d["item_id"]
