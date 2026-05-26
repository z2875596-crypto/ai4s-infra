"""RLHF Pipeline — end-to-end orchestrator tying feedback, reward, and policy together.

Full RLHF cycle:
  1. Collect human preferences (FeedbackCollector)
  2. Aggregate multi-annotator consensus (FeedbackAggregator)
  3. Train reward model on preference pairs (RewardModelTrainer)
  4. Train policy via PPO against reward model or via DPO
  5. Evaluate and iterate

Usage::

    pipeline = RLHFPipeline(
        policy_model=my_sft_model,
        reference_model=my_sft_model,  # frozen reference
        config=Config(),
    )

    # Setup feedback loop
    pipeline.setup_feedback_loop()

    # Run iterations
    for iteration in range(10):
        result = await pipeline.run_iteration(prompts)
"""

from __future__ import annotations

from typing import Any

from transformers import AutoModelForCausalLM, AutoTokenizer

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.rlhf.feedback.aggregator import FeedbackAggregator
from ai4s.rlhf.feedback.collector import AnnotationChoice, FeedbackCollector, FeedbackItem
from ai4s.rlhf.policy.dpo import DPOPair, DPOTrainer
from ai4s.rlhf.policy.ppo import PPOConfig, PPOTrainer
from ai4s.rlhf.policy.trainer import PolicyTrainer
from ai4s.rlhf.reward.base import HuggingFaceRewardModel, RewardInput, RewardModel
from ai4s.rlhf.reward.ensemble import RewardEnsemble
from ai4s.rlhf.reward.trainer import PreferencePair, RewardModelTrainer

logger = get_logger(__name__)


class RLHFPipeline:
    """End-to-end RLHF orchestrator.

    Modes:
      - ppo  : train reward model → PPO with KL penalty
      - dpo  : directly optimize from preference pairs (no separate reward model)
    """

    def __init__(
        self,
        policy_model: AutoModelForCausalLM,
        reference_model: AutoModelForCausalLM,
        policy_tokenizer: AutoTokenizer | None = None,
        reward_model: RewardModel | None = None,
        config: Config | None = None,
    ) -> None:
        self.policy = policy_model
        self.ref = reference_model
        self.tokenizer = policy_tokenizer or AutoTokenizer.from_pretrained("gpt2")
        self.reward = reward_model
        self.config = config or Config()

        self._feedback_collector: FeedbackCollector | None = None
        self._feedback_aggregator: FeedbackAggregator | None = None
        self._reward_trainer: RewardModelTrainer | None = None
        self._iteration: int = 0

    # ------------------------------------------------------------------
    # Full RLHF iteration
    # ------------------------------------------------------------------

    async def run_iteration(
        self,
        prompts: list[str],
        rollout_batch_size: int = 32,
    ) -> dict[str, Any]:
        """Run one full RLHF iteration: rollout → score → train."""
        algo = self.config.rlhf.get("policy", {}).get("algorithm", "dpo")
        logger.info("RLHF iteration %d starting (algo=%s, prompts=%d)",
                     self._iteration, algo, len(prompts))

        if algo == "ppo":
            result = await self._run_ppo_iteration(prompts, rollout_batch_size)
        elif algo == "dpo":
            result = await self._run_dpo_iteration(prompts, rollout_batch_size)
        else:
            raise ValueError(f"Unknown algorithm: {algo}")

        self._iteration += 1
        MetricsRegistry.rlhf_training_step.inc()
        return result

    async def _run_ppo_iteration(
        self, prompts: list[str], batch_size: int
    ) -> dict[str, Any]:
        """PPO iteration: generate → reward → train."""
        if self.reward is None:
            raise ValueError("PPO requires a reward model")

        # 1. Rollout: generate responses
        from ai4s.rlhf.policy.ppo import PPOTrainer, PPOConfig

        ppo_cfg = PPOConfig(
            ppo_epochs=self.config.rlhf.get("policy", {}).get("ppo_epochs", 4),
            batch_size=self.config.rlhf.get("policy", {}).get("batch_size", 64),
            kl_penalty_coef=self.config.rlhf.get("policy", {}).get("kl_penalty_coef", 0.1),
        )

        ppo_trainer = PPOTrainer(
            policy_model=self.policy,
            policy_tokenizer=self.tokenizer,
            reference_model=self.ref,
            reward_model=self.reward,
            config=ppo_cfg,
        )

        trajectories = []
        for i in range(0, len(prompts), batch_size):
            batch = prompts[i : i + batch_size]
            traj = ppo_trainer.rollout(batch)
            trajectories.append(traj)

        rewards = []
        for t in trajectories:
            rewards.extend(t.rewards)
        avg_reward = sum(rewards) / max(len(rewards), 1)
        MetricsRegistry.rlhf_reward_mean.set(avg_reward)

        # 2. PPO step
        train_result = ppo_trainer.train_step(trajectories)

        logger.info("PPO iteration %d complete: avg_reward=%.3f", self._iteration, avg_reward)
        return {"avg_reward": avg_reward, "n_prompts": len(prompts), "training": train_result}

    async def _run_dpo_iteration(
        self, prompts: list[str], batch_size: int
    ) -> dict[str, Any]:
        """DPO iteration: generate pairs → train."""
        # To run DPO iteration, we need preference pairs.
        # In a live pipeline these come from the feedback system.
        # For automated iteration, we can self-generate via the policy.
        if self._feedback_collector:
            pairs = self._feedback_collector.get_preference_pairs()
        else:
            # Self-play: generate two responses per prompt, use reward model to choose
            pairs = await self._generate_self_play_pairs(prompts, batch_size)

        if not pairs:
            logger.warning("No preference pairs for DPO iteration")
            return {"n_prompts": len(prompts), "n_pairs": 0}

        dpo_pairs = [DPOPair(**p) for p in pairs]

        dpo_trainer = DPOTrainer(
            policy_model=self.policy,
            policy_tokenizer=self.tokenizer,
            reference_model=self.ref,
            beta=self.config.rlhf.get("policy", {}).get("dpo_beta", 0.1),
            batch_size=self.config.rlhf.get("policy", {}).get("batch_size", 32),
        )

        result = dpo_trainer.train(dpo_pairs)
        logger.info("DPO iteration %d complete: loss=%.4f", self._iteration,
                     result.get("final_loss", 0))
        return {"n_prompts": len(prompts), "n_pairs": len(dpo_pairs), "training": result}

    # ------------------------------------------------------------------
    # Self-play generation (for DPO without human feedback)
    # ------------------------------------------------------------------

    async def _generate_self_play_pairs(
        self, prompts: list[str], batch_size: int
    ) -> list[dict[str, Any]]:
        """Generate two responses per prompt and score with reward model."""
        pairs: list[dict[str, Any]] = []

        for i in range(0, len(prompts), batch_size):
            batch = prompts[i : i + batch_size]

            # Generate two candidate responses
            responses_a = self._generate(batch, temperature=0.7)
            responses_b = self._generate(batch, temperature=1.0)

            if self.reward:
                # Score via reward model to pick chosen/rejected
                inputs_a = [RewardInput(prompt=p, response=r) for p, r in zip(batch, responses_a)]
                inputs_b = [RewardInput(prompt=p, response=r) for p, r in zip(batch, responses_b)]
                scores_a = self.reward.score(inputs_a)
                scores_b = self.reward.score(inputs_b)

                for p, ra, rb, sa, sb in zip(batch, responses_a, responses_b, scores_a, scores_b):
                    if sa.score >= sb.score:
                        pairs.append({"prompt": p, "chosen": ra, "rejected": rb})
                    else:
                        pairs.append({"prompt": p, "chosen": rb, "rejected": ra})
            else:
                # Without reward model, use length heuristic (shorter = worse, longer = better)
                for p, ra, rb in zip(batch, responses_a, responses_b):
                    if len(ra) >= len(rb):
                        pairs.append({"prompt": p, "chosen": ra, "rejected": rb})
                    else:
                        pairs.append({"prompt": p, "chosen": rb, "rejected": ra})

        return pairs

    # ------------------------------------------------------------------
    # Reward model training
    # ------------------------------------------------------------------

    def train_reward_model(
        self,
        train_pairs: list[dict[str, Any]],
        eval_pairs: list[dict[str, Any]] | None = None,
        base_model: str | None = None,
    ) -> dict[str, Any]:
        """Train a reward model from preference pairs."""
        if self.reward is None:
            model_name = base_model or self.config.rlhf.get("reward_model", {}).get(
                "base_model", "meta-llama/Llama-2-7b-hf"
            )
            self.reward = HuggingFaceRewardModel(model_name)

        if not isinstance(self.reward, HuggingFaceRewardModel):
            raise ValueError("Reward model training requires HuggingFaceRewardModel")

        trainer = RewardModelTrainer(
            self.reward,
            batch_size=self.config.rlhf.get("reward_model", {}).get("train_batch_size", 32),
            epochs=3,
            learning_rate=self.config.rlhf.get("reward_model", {}).get("learning_rate", 1e-5),
        )

        train_prefs = [PreferencePair(**p) for p in train_pairs]
        eval_prefs = [PreferencePair(**p) for p in eval_pairs] if eval_pairs else None

        return trainer.train(train_prefs, eval_prefs)

    # ------------------------------------------------------------------
    # Feedback loop
    # ------------------------------------------------------------------

    def setup_feedback_loop(
        self,
        pool_size: int = 1000,
        agreement_threshold: float = 0.6,
        persist_path: str | None = None,
    ) -> None:
        self._feedback_collector = FeedbackCollector(
            pool_size=pool_size, persist_path=persist_path
        )
        self._feedback_aggregator = FeedbackAggregator(
            self._feedback_collector,
            agreement_threshold=agreement_threshold,
        )
        logger.info("Feedback loop initialized (pool=%d)", pool_size)

    def add_feedback_items(self, prompts: list[str], responses_a: list[str], responses_b: list[str]) -> list[str]:
        if not self._feedback_collector:
            self.setup_feedback_loop()
        return self._feedback_collector.add_generated_pairs(prompts, responses_a, responses_b)

    def get_consensus_pairs(self) -> list[dict[str, Any]]:
        if not self._feedback_aggregator:
            raise RuntimeError("Call setup_feedback_loop() first")
        return self._feedback_aggregator.aggregate()

    def get_feedback_stats(self) -> dict[str, Any]:
        if not self._feedback_collector:
            return {}
        stats = self._feedback_collector.stats()
        if self._feedback_aggregator:
            stats["inter_annotator_agreement"] = self._feedback_aggregator.inter_annotator_agreement()
        return stats

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @torch.no_grad()
    def _generate(self, prompts: list[str], **gen_kwargs) -> list[str]:
        self.policy.eval()
        device = self.policy.device
        encoded = self.tokenizer(prompts, padding=True, truncation=True, return_tensors="pt").to(device)

        defaults = dict(
            max_new_tokens=512, temperature=0.7, top_p=0.9, do_sample=True,
            pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
        )
        defaults.update(gen_kwargs)

        outputs = self.policy.generate(**encoded, **defaults)
        return self.tokenizer.batch_decode(
            outputs[:, encoded["input_ids"].shape[1]:], skip_special_tokens=True
        )

    async def evaluate(self, prompts: list[str], reference_responses: list[str]) -> dict[str, Any]:
        """Evaluate policy: generate responses and compute reward distribution."""
        import torch

        generated = self._generate(prompts)

        scores = []
        if self.reward:
            inputs = [RewardInput(prompt=p, response=r) for p, r in zip(prompts, generated)]
            outputs = self.reward.score(inputs)
            scores = [o.score for o in outputs]

        return {
            "avg_reward": sum(scores) / max(len(scores), 1),
            "min_reward": min(scores) if scores else 0,
            "max_reward": max(scores) if scores else 0,
            "n_samples": len(prompts),
        }
