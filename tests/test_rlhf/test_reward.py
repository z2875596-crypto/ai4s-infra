"""Tests for reward model infrastructure."""

import pytest

from ai4s.rlhf.reward.base import RewardInput, RewardOutput
from ai4s.rlhf.reward.ensemble import RewardEnsemble


class MockRewardModel:
    """Mock reward model that returns fixed scores."""
    def __init__(self, scores: list[float]):
        self._scores = scores
        self.model_name = "mock"
        self.device = "cpu"

    def score(self, inputs: list[RewardInput]) -> list[RewardOutput]:
        return [RewardOutput(score=self._scores[i % len(self._scores)]) for i in range(len(inputs))]

    def save(self, path: str) -> None:
        pass

    def load(self, path: str) -> None:
        pass


class TestRewardEnsemble:
    def test_single_model(self):
        model = MockRewardModel([0.8])
        ensemble = RewardEnsemble([model])
        inputs = [RewardInput(prompt="hello", response="hi")]
        outputs = ensemble.score(inputs)
        assert len(outputs) == 1
        assert outputs[0].score == 0.8

    def test_weighted_ensemble(self):
        m1 = MockRewardModel([1.0])
        m2 = MockRewardModel([0.0])
        ensemble = RewardEnsemble([m1, m2], weights=[0.7, 0.3])
        inputs = [RewardInput(prompt="p", response="r")]
        outputs = ensemble.score(inputs)
        assert outputs[0].score == pytest.approx(0.7)

    def test_no_models_raises(self):
        with pytest.raises(ValueError, match="At least one"):
            RewardEnsemble([])

    def test_weight_mismatch_raises(self):
        with pytest.raises(ValueError, match="Weights must match"):
            RewardEnsemble([MockRewardModel([0.5])], weights=[1.0, 1.0])
