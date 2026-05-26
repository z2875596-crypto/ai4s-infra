"""FastAPI routes for rlhf — feedback, reward training, policy training, pipeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.rlhf.feedback.aggregator import FeedbackAggregator
from ai4s.rlhf.feedback.collector import (
    AnnotationChoice,
    FeedbackCollector,
    FeedbackItem,
    FeedbackStatus,
)
from ai4s.rlhf.pipeline import RLHFPipeline
from ai4s.rlhf.reward.base import ConstantRewardModel, RewardInput
from ai4s.rlhf.reward.trainer import PreferencePair, RewardModelTrainer

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# globals (singletons — replaced with DI in production)
# ---------------------------------------------------------------------------

_collector: FeedbackCollector | None = None
_aggregator: FeedbackAggregator | None = None
_pipeline: RLHFPipeline | None = None


def get_collector() -> FeedbackCollector:
    global _collector
    if _collector is None:
        _collector = FeedbackCollector()
    return _collector


def get_aggregator() -> FeedbackAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = FeedbackAggregator(get_collector())
    return _aggregator


def get_pipeline() -> RLHFPipeline:
    global _pipeline
    if _pipeline is None:
        from ai4s.rlhf.reward.base import ConstantRewardModel
        _pipeline = RLHFPipeline(
            policy_model=None,   # Must be set before training
            reference_model=None,
            reward_model=ConstantRewardModel(score=0.5),
            config=Config(),
        )
    return _pipeline


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/rlhf", tags=["rlhf"])

# ---------------------------------------------------------------------------
# request / response models
# ---------------------------------------------------------------------------


class AddFeedbackRequest(BaseModel):
    prompts: list[str]
    responses_a: list[str]
    responses_b: list[str]
    metadata: dict[str, Any] | None = None


class AnnotateRequest(BaseModel):
    item_id: str
    annotator_id: str
    choice: str = Field(..., description="A | B | tie | both_bad | both_good")
    confidence: float = 1.0
    notes: str = ""


class AssignRequest(BaseModel):
    annotator_id: str
    n: int = 5
    strategy: str = "random"


class PreferencePairRequest(BaseModel):
    pairs: list[dict[str, str]] = Field(..., description="[{'prompt':..., 'chosen':..., 'rejected':...}, ...]")


class TrainRewardRequest(BaseModel):
    train_pairs: list[dict[str, str]]
    eval_pairs: list[dict[str, str]] | None = None
    epochs: int = 3
    learning_rate: float = 1e-5


class ScoreRequest(BaseModel):
    prompts: list[str]
    responses: list[str]


class PolicyTrainRequest(BaseModel):
    training_data: list[dict[str, Any]]
    algorithm: str = "dpo"


class PipelineIterateRequest(BaseModel):
    prompts: list[str]
    rollout_batch_size: int = 32


# ---------------------------------------------------------------------------
# feedback routes
# ---------------------------------------------------------------------------


@router.get("/feedback/stats")
async def feedback_stats():
    return get_collector().stats()


@router.post("/feedback/items")
async def add_feedback_items(req: AddFeedbackRequest):
    collector = get_collector()
    ids = collector.add_generated_pairs(req.prompts, req.responses_a, req.responses_b)
    return {"status": "added", "count": len(ids), "item_ids": ids}


@router.post("/feedback/assign")
async def assign_feedback(req: AssignRequest):
    collector = get_collector()
    items = collector.assign_to_annotator(req.annotator_id, n=req.n, strategy=req.strategy)
    return {
        "assigned": len(items),
        "items": [{"item_id": i.item_id, "prompt": i.prompt[:100]} for i in items],
    }


@router.post("/feedback/annotate")
async def annotate_feedback(req: AnnotateRequest):
    collector = get_collector()
    try:
        choice = AnnotationChoice(req.choice)
    except ValueError:
        raise HTTPException(400, f"Invalid choice '{req.choice}'. Use: A, B, tie, both_bad, both_good")

    item = collector.record_annotation(req.item_id, req.annotator_id, choice, req.confidence, req.notes)
    return {"status": "annotated", "item_id": item.item_id, "choice": item.annotation.value if item.annotation else None}


@router.get("/feedback/consensus")
async def get_consensus_pairs():
    aggregator = get_aggregator()
    pairs = aggregator.aggregate()
    return {"count": len(pairs), "pairs": pairs}


@router.get("/feedback/annotator-quality")
async def annotator_quality():
    aggregator = get_aggregator()
    return aggregator.annotator_quality_report()


# ---------------------------------------------------------------------------
# reward model routes
# ---------------------------------------------------------------------------


@router.post("/reward/train")
async def train_reward_model(req: TrainRewardRequest):
    pipeline = get_pipeline()
    result = pipeline.train_reward_model(
        req.train_pairs, req.eval_pairs,
        base_model=None,
    )
    return result


@router.post("/reward/score")
async def score_with_reward(req: ScoreRequest):
    pipeline = get_pipeline()
    inputs = [RewardInput(prompt=p, response=r) for p, r in zip(req.prompts, req.responses)]
    outputs = pipeline.reward.score(inputs)
    return {"scores": [{"prompt": inp.prompt[:80], "score": out.score} for inp, out in zip(inputs, outputs)]}


# ---------------------------------------------------------------------------
# policy routes
# ---------------------------------------------------------------------------


@router.post("/policy/train")
async def train_policy(req: PolicyTrainRequest):
    if req.algorithm not in ("ppo", "dpo"):
        raise HTTPException(400, "algorithm must be 'ppo' or 'dpo'")
    pipeline = get_pipeline()
    pipeline.config._data.setdefault("rlhf", {}).setdefault("policy", {})["algorithm"] = req.algorithm
    result = await pipeline._run_dpo_iteration([d.get("prompt", "") for d in req.training_data], 32)
    return result


# ---------------------------------------------------------------------------
# pipeline routes
# ---------------------------------------------------------------------------


@router.post("/pipeline/iterate")
async def run_pipeline_iteration(req: PipelineIterateRequest):
    pipeline = get_pipeline()
    result = await pipeline.run_iteration(req.prompts, req.rollout_batch_size)
    return result


@router.post("/pipeline/evaluate")
async def evaluate_policy(req: ScoreRequest):
    pipeline = get_pipeline()
    result = await pipeline.evaluate(req.prompts, req.responses)
    return result


@router.get("/pipeline/feedback-stats")
async def pipeline_feedback_stats():
    pipeline = get_pipeline()
    return pipeline.get_feedback_stats()
