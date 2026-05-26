"""Policy trainer orchestrator — selects and runs PPO or DPO based on config."""

from __future__ import annotations

from typing import Any

from transformers import AutoModelForCausalLM, AutoTokenizer

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.rlhf.reward.base import RewardModel

logger = get_logger(__name__)


class PolicyTrainer:
    """Orchestrates policy training: routes to PPO or DPO based on config.

    Config keys (from ai4s.rlhf.policy):
      algorithm : "ppo" | "dpo"
      ppo_epochs, batch_size, ... → forwarded to PPOConfig
      dpo_beta, dpo_epochs, ...   → forwarded to DPOTrainer
    """

    def __init__(
        self,
        policy_model: AutoModelForCausalLM,
        policy_tokenizer: AutoTokenizer,
        reference_model: AutoModelForCausalLM,
        reward_model: RewardModel | None = None,
        config: Config | None = None,
    ) -> None:
        self.policy = policy_model
        self.tokenizer = policy_tokenizer
        self.ref = reference_model
        self.reward = reward_model
        self.config = config or Config()

    # ------------------------------------------------------------------

    def train(self, training_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Train policy. training_data is a list of dicts.

        For PPO: [{"prompt": ..., "response": ..., "reward": ...}, ...]
        For DPO: [{"prompt": ..., "chosen": ..., "rejected": ...}, ...]
        """
        algo = self.config.rlhf.get("policy", {}).get("algorithm", "dpo")
        logger.info("Starting policy training: algorithm=%s samples=%d", algo, len(training_data))

        if algo == "ppo":
            return self._train_ppo(training_data)
        elif algo == "dpo":
            return self._train_dpo(training_data)
        else:
            raise ValueError(f"Unknown RL algorithm: {algo}. Supported: ppo, dpo")

    # ------------------------------------------------------------------

    def _train_ppo(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        if self.reward is None:
            raise ValueError("PPO requires a reward model — pass reward_model= to PolicyTrainer")

        from ai4s.rlhf.policy.ppo import PPOTrainer, PPOConfig, PPOTrajectory

        cfg = PPOConfig(
            ppo_epochs=self.config.rlhf.get("policy", {}).get("ppo_epochs", 4),
            batch_size=self.config.rlhf.get("policy", {}).get("batch_size", 64),
            kl_penalty_coef=self.config.rlhf.get("policy", {}).get("kl_penalty_coef", 0.1),
        )

        trainer = PPOTrainer(
            policy_model=self.policy,
            policy_tokenizer=self.tokenizer,
            reference_model=self.ref,
            reward_model=self.reward,
            config=cfg,
        )

        trajectories = [
            PPOTrajectory(
                prompts=[d.get("prompt", "") for d in data],
                responses=[d.get("response", "") for d in data],
                rewards=[d.get("reward", 0.0) for d in data],
                values=[0.0] * len(data),
                log_probs=[0.0] * len(data),
            )
        ]
        return trainer.train_step(trajectories)

    # ------------------------------------------------------------------

    def _train_dpo(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        from ai4s.rlhf.policy.dpo import DPOTrainer, DPOPair

        pairs = [
            DPOPair(
                prompt=d.get("prompt", ""),
                chosen=d.get("chosen", ""),
                rejected=d.get("rejected", ""),
            )
            for d in data
            if d.get("chosen") and d.get("rejected")
        ]

        if not pairs:
            raise ValueError("No valid DPO pairs found in training data")

        trainer = DPOTrainer(
            policy_model=self.policy,
            policy_tokenizer=self.tokenizer,
            reference_model=self.ref,
            beta=self.config.rlhf.get("policy", {}).get("dpo_beta", 0.1),
            epochs=self.config.rlhf.get("policy", {}).get("dpo_epochs", 1),
            batch_size=self.config.rlhf.get("policy", {}).get("batch_size", 32),
        )

        return trainer.train(pairs)

    # ------------------------------------------------------------------

    def generate(self, prompts: list[str], **gen_kwargs) -> list[str]:
        """Generate responses from the current policy."""
        self.policy.eval()
        device = self.policy.device

        encoded = self.tokenizer(
            prompts, padding=True, truncation=True, return_tensors="pt"
        ).to(device)

        defaults = dict(
            max_new_tokens=512, temperature=0.7, top_p=0.9, do_sample=True,
            pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
        )
        defaults.update(gen_kwargs)

        outputs = self.policy.generate(**encoded, **defaults)
        responses = self.tokenizer.batch_decode(
            outputs[:, encoded["input_ids"].shape[1]:], skip_special_tokens=True
        )
        return responses
