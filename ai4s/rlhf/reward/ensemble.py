"""Reward ensemble — combines multiple reward models to reduce reward hacking."""

from __future__ import annotations

from typing import Any

import numpy as np

from ai4s.common.logging import get_logger
from ai4s.rlhf.reward.base import RewardInput, RewardOutput, RewardModel

logger = get_logger(__name__)


class RewardEnsemble:
    """Weighted ensemble of reward models.

    Why ensemble? Single reward models can be gamed (reward hacking).
    Ensembling multiple independently-trained models with different
    architectures / training data improves robustness.

    Aggregation strategies:
      - weighted_mean  : weighted average of scores
      - median          : median score (robust to outliers)
      - trimmed_mean    : drop top/bottom k%, average the rest
      - min             : conservative: take minimum (pessimistic)
    """

    def __init__(
        self,
        models: list[RewardModel],
        weights: list[float] | None = None,
        strategy: str = "weighted_mean",
        trim_ratio: float = 0.1,
    ) -> None:
        if not models:
            raise ValueError("At least one reward model required")
        if weights and len(weights) != len(models):
            raise ValueError(f"Weights length ({len(weights)}) must match model count ({len(models)})")

        self.models = models
        self.weights = weights or [1.0 / len(models)] * len(models)
        self.strategy = strategy
        self.trim_ratio = trim_ratio

        # Normalize weights
        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]

    # -- scoring ------------------------------------------------------------

    def score(self, inputs: list[RewardInput]) -> list[RewardOutput]:
        # Collect scores from all models
        all_scores: list[list[float]] = []
        for model in self.models:
            outputs = model.score(inputs)
            all_scores.append([o.score for o in outputs])

        # Transpose: per-input list of model scores
        scores_per_input = list(zip(*all_scores))  # (n_inputs, n_models)

        results: list[RewardOutput] = []
        for model_scores in scores_per_input:
            aggregated = self._aggregate(list(model_scores))
            results.append(RewardOutput(
                score=aggregated["score"],
                breakdown={
                    **{f"model_{i}": s for i, s in enumerate(model_scores)},
                    "mean": aggregated.get("mean", aggregated["score"]),
                    "std": aggregated.get("std", 0.0),
                },
            ))

        return results

    def score_batch(self, inputs: list[RewardInput], batch_size: int = 32) -> list[RewardOutput]:
        return self.score(inputs)  # Delegates batching to individual models

    # -- aggregation --------------------------------------------------------

    def _aggregate(self, scores: list[float]) -> dict[str, float]:
        arr = np.array(scores)
        mean = float(np.mean(arr))
        std = float(np.std(arr))

        if self.strategy == "weighted_mean":
            score = float(np.average(arr, weights=self.weights))
        elif self.strategy == "median":
            score = float(np.median(arr))
        elif self.strategy == "trimmed_mean":
            k = max(1, int(len(arr) * self.trim_ratio))
            if len(arr) > 2 * k:
                trimmed = np.sort(arr)[k:-k]
                score = float(np.mean(trimmed))
            else:
                score = float(np.median(arr))
        elif self.strategy == "min":
            score = float(np.min(arr))
        else:
            score = mean

        return {"score": score, "mean": mean, "std": std}

    # -- diagnostics --------------------------------------------------------

    def disagreement(self, inputs: list[RewardInput]) -> dict[str, float]:
        """Measure inter-model disagreement (std dev and range)."""
        all_scores = [model.score(inputs) for model in self.models]
        scores_per_input = list(zip(*[[s.score for s in batch] for batch in all_scores]))

        stds = [float(np.std(s)) for s in scores_per_input]
        ranges = [float(np.max(s) - np.min(s)) for s in scores_per_input]

        return {
            "mean_std": float(np.mean(stds)),
            "max_std": float(np.max(stds)),
            "mean_range": float(np.mean(ranges)),
            "max_range": float(np.max(ranges)),
            "high_disagreement_ratio": sum(1 for s in stds if s > 1.0) / max(len(stds), 1),
        }

    def per_model_stats(self, inputs: list[RewardInput]) -> dict[str, dict[str, float]]:
        """Return per-model mean and std for a batch."""
        stats: dict[str, dict[str, float]] = {}
        for i, model in enumerate(self.models):
            outputs = model.score(inputs)
            scores = [o.score for o in outputs]
            stats[f"model_{i}"] = {
                "mean": float(np.mean(scores)),
                "std": float(np.std(scores)),
                "min": float(np.min(scores)),
                "max": float(np.max(scores)),
            }
        return stats

    # -- save / load --------------------------------------------------------

    def save_all(self, base_dir: str) -> None:
        from pathlib import Path

        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        for i, model in enumerate(self.models):
            model.save(str(base / f"model_{i}"))

    def load_all(self, base_dir: str) -> None:
        from pathlib import Path

        base = Path(base_dir)
        for i, model in enumerate(self.models):
            model.load(str(base / f"model_{i}"))
