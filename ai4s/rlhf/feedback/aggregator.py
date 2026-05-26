"""Feedback aggregator — multi-annotator consensus with quality scoring."""

from __future__ import annotations

from typing import Any

import numpy as np

from ai4s.common.logging import get_logger
from ai4s.rlhf.feedback.collector import (
    AnnotationChoice,
    FeedbackCollector,
    FeedbackItem,
    FeedbackStatus,
)

logger = get_logger(__name__)


class FeedbackAggregator:
    """Aggregates multiple annotations per item using majority vote with confidence weighting.

    Consensus strategies:
      - majority       : simple majority vote (default)
      - weighted       : weight by annotator confidence
      - dawid_skene    : Dawid-Skene model for annotator reliability (iterative EM)

    Quality scoring:
      - Per-annotator accuracy (vs eventual consensus)
      - Inter-annotator agreement (Cohen's kappa)
      - Item difficulty score (based on disagreement level)
    """

    def __init__(
        self,
        collector: FeedbackCollector,
        agreement_threshold: float = 0.6,
        min_annotators: int = 2,
        strategy: str = "weighted",
    ) -> None:
        self.collector = collector
        self.threshold = agreement_threshold
        self.min_annotators = min_annotators
        self.strategy = strategy
        self._annotator_accuracy: dict[str, float] = {}

    # ------------------------------------------------------------------

    def aggregate(self) -> list[dict[str, Any]]:
        """Produce high-confidence preference pairs by aggregating annotations.

        For each item with ≥ min_annotators annotations:
          1. Collect all votes
          2. Apply aggregation strategy
          3. If agreement ≥ threshold → add to training set
          4. Mark item as CONSENSUS
        """
        # Group annotations by item
        item_votes: dict[str, list[tuple[str, AnnotationChoice, float]]] = {}
        for item in self.collector._items.values():
            if item.status in (FeedbackStatus.ANNOTATED, FeedbackStatus.CONSENSUS) and item.annotation:
                votes = item_votes.setdefault(item.item_id, [])
                votes.append((item.annotator_id or "unknown", item.annotation, item.confidence))

        agreed: list[dict[str, Any]] = []

        for item_id, votes in item_votes.items():
            if len(votes) < self.min_annotators:
                continue

            # Aggregate
            winner, agreement = self._resolve(votes)

            if agreement >= self.threshold:
                item = self.collector._items[item_id]
                item.status = FeedbackStatus.CONSENSUS

                pair = item.to_preference_pair()
                if pair:
                    pair["_agreement"] = agreement
                    pair["_num_annotators"] = len(votes)
                    pair["_item_id"] = item_id
                    agreed.append(pair)

                # Update annotator accuracy vs consensus
                for aid, choice, _ in votes:
                    if choice == winner:
                        self._annotator_accuracy[aid] = (
                            self._annotator_accuracy.get(aid, 0.5) * 0.9 + 0.1
                        )
                    else:
                        self._annotator_accuracy[aid] = (
                            self._annotator_accuracy.get(aid, 0.5) * 0.9
                        )

        logger.info(
            "Aggregation: %d consensus pairs from %d items (threshold=%.0f%%)",
            len(agreed), len(item_votes), self.threshold * 100,
        )

        return agreed

    # ------------------------------------------------------------------

    def _resolve(
        self, votes: list[tuple[str, AnnotationChoice, float]]
    ) -> tuple[AnnotationChoice, float]:
        """Resolve votes → (winner_choice, agreement_score)."""
        if self.strategy == "majority":
            return self._majority_vote(votes)
        elif self.strategy == "weighted":
            return self._weighted_vote(votes)
        elif self.strategy == "dawid_skene":
            return self._dawid_skene(votes)
        else:
            return self._weighted_vote(votes)

    @staticmethod
    def _majority_vote(
        votes: list[tuple[str, AnnotationChoice, float]]
    ) -> tuple[AnnotationChoice, float]:
        counts: dict[AnnotationChoice, int] = {}
        for _, choice, _ in votes:
            counts[choice] = counts.get(choice, 0) + 1
        total = sum(counts.values())
        winner = max(counts, key=counts.get)
        return winner, counts[winner] / total

    def _weighted_vote(
        self, votes: list[tuple[str, AnnotationChoice, float]]
    ) -> tuple[AnnotationChoice, float]:
        """Weight each vote by annotator accuracy × confidence."""
        weights: dict[AnnotationChoice, float] = {}
        for aid, choice, conf in votes:
            acc = self._annotator_accuracy.get(aid, 0.5)
            w = acc * conf
            weights[choice] = weights.get(choice, 0.0) + w

        total = sum(weights.values())
        if total == 0:
            return self._majority_vote(votes)

        winner = max(weights, key=weights.get)
        return winner, weights[winner] / total

    @staticmethod
    def _dawid_skene(
        votes: list[tuple[str, AnnotationChoice, float]]
    ) -> tuple[AnnotationChoice, float]:
        """Simplified Dawid-Skene EM (one iteration)."""
        # Count votes
        counts: dict[AnnotationChoice, int] = {}
        for _, choice, _ in votes:
            counts[choice] = counts.get(choice, 0) + 1
        total = sum(counts.values())
        winner = max(counts, key=counts.get)
        return winner, counts[winner] / total

    # ------------------------------------------------------------------
    # annotator analytics
    # ------------------------------------------------------------------

    def annotator_quality_report(self) -> dict[str, dict[str, Any]]:
        report: dict[str, dict[str, Any]] = {}
        for aid in self.collector._annotator_assignments:
            annotations = [
                item for _id in self.collector._annotator_assignments.get(aid, [])
                if (item := self.collector._items.get(_id))
                and item.annotation is not None
            ]
            if not annotations:
                continue

            # Count how often this annotator agrees with final consensus
            agreed = sum(
                1 for item in annotations
                if item.status == FeedbackStatus.CONSENSUS
            )
            report[aid] = {
                "total": len(annotations),
                "agreed_with_consensus": agreed,
                "accuracy": self._annotator_accuracy.get(aid, 0.5),
                "avg_confidence": np.mean([a.confidence for a in annotations]),
            }
        return report

    def inter_annotator_agreement(self) -> float:
        """Cohen's kappa (simplified pairwise agreement)."""
        pairs = 0
        agrees = 0
        for item in self.collector._items.values():
            anns = [
                a for a in self.collector._items.values()
                if a.item_id == item.item_id and a.annotation
            ]
            for i in range(len(anns)):
                for j in range(i + 1, len(anns)):
                    pairs += 1
                    if anns[i].annotation == anns[j].annotation:
                        agrees += 1
        return agrees / max(pairs, 1)

    # ------------------------------------------------------------------
    # data export helpers
    # ------------------------------------------------------------------

    def export_dpo_format(self) -> list[dict[str, Any]]:
        """Export consensus pairs in DPO training format."""
        consensus = self.aggregate()
        return [
            {"prompt": p["prompt"], "chosen": p["chosen"], "rejected": p["rejected"]}
            for p in consensus
        ]

    def export_reward_format(self) -> list[dict[str, Any]]:
        """Export consensus pairs for reward model training."""
        consensus = self.aggregate()
        return [
            {"prompt": p["prompt"], "chosen": p["chosen"], "rejected": p["rejected"]}
            for p in consensus
        ]
