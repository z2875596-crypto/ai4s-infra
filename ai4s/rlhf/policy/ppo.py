"""PPO trainer — Proximal Policy Optimization for RLHF with full GAE and KL penalty."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.rlhf.reward.base import RewardInput, RewardModel

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@dataclass
class PPOConfig:
    ppo_epochs: int = 4
    batch_size: int = 64
    mini_batch_size: int = 16
    clip_epsilon: float = 0.2
    value_loss_coef: float = 0.5
    entropy_coef: float = 0.01
    kl_penalty_coef: float = 0.1
    kl_target: float = 0.01
    gamma: float = 1.0
    lam: float = 0.95
    max_grad_norm: float = 1.0
    response_max_length: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    use_adaptive_kl: bool = True


# ---------------------------------------------------------------------------
# trajectory
# ---------------------------------------------------------------------------


@dataclass
class PPOTrajectory:
    prompts: list[str]
    responses: list[str]
    rewards: list[float]
    values: list[float]
    log_probs: list[float]
    advantages: list[float] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)

    def __post_init__(self):
        n = len(self.rewards)
        if not self.advantages:
            self.advantages = [0.0] * n
        if not self.returns:
            self.returns = [0.0] * n


# ---------------------------------------------------------------------------
# PPO Trainer
# ---------------------------------------------------------------------------


class PPOTrainer:
    """PPO with GAE advantage estimation and adaptive KL penalty to a frozen reference.

    Data Flow
    ---------
      1. Rollout: policy.generate() → responses
      2. Reward:  reward_model.score(prompt, response) → scalar reward
      3. Value:   value head (or separate model) → value estimate
      4. GAE:     compute advantages from rewards + values
      5. PPO step:  clip loss on policy + value loss + entropy bonus - KL penalty
    """

    def __init__(
        self,
        policy_model: AutoModelForCausalLM,
        policy_tokenizer: AutoTokenizer,
        reference_model: AutoModelForCausalLM,
        reward_model: RewardModel,
        config: PPOConfig | None = None,
        value_model: AutoModelForCausalLM | None = None,
    ) -> None:
        self.policy = policy_model
        self.tokenizer = policy_tokenizer
        self.ref = reference_model
        self.reward = reward_model
        self.cfg = config or PPOConfig()

        # Value model: can share trunk with policy (just a linear head on top)
        self.value_model = value_model or policy_model
        self._value_head = torch.nn.Linear(
            policy_model.config.hidden_size, 1, bias=False
        ).to(policy_model.device)

        # Freeze reference
        self.ref.eval()
        for p in self.ref.parameters():
            p.requires_grad = False

        self._kl_coef = self.cfg.kl_penalty_coef

    # ------------------------------------------------------------------
    # train step
    # ------------------------------------------------------------------

    def train_step(self, trajectories: list[PPOTrajectory]) -> dict[str, float]:
        device = self.policy.device
        optimizer = torch.optim.AdamW(
            list(self.policy.parameters()) + list(self._value_head.parameters()),
            lr=1e-6,
        )

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        total_kl = 0.0
        n_updates = 0

        self.policy.train()

        for epoch in range(self.cfg.ppo_epochs):
            for traj in trajectories:
                self._compute_gae(traj)

                # Prepare tokenized data
                encoded = self.tokenizer(
                    [f"{p}{r}" for p, r in zip(traj.prompts, traj.responses)],
                    padding=True, truncation=True,
                    max_length=self.cfg.response_max_length + 512,
                    return_tensors="pt",
                ).to(device)

                advantages_t = torch.tensor(traj.advantages, device=device)
                returns_t = torch.tensor(traj.returns, device=device)
                old_log_probs_t = torch.tensor(traj.log_probs, device=device)

                n = len(traj.responses)
                indices = torch.randperm(n)

                for start in range(0, n, self.cfg.mini_batch_size):
                    idx = indices[start : start + self.cfg.mini_batch_size]

                    # Forward policy
                    outputs = self.policy(**{k: v[idx] for k, v in encoded.items()})
                    new_log_probs = self._compute_log_probs(outputs.logits, encoded["input_ids"][idx])

                    # Forward reference for KL
                    with torch.no_grad():
                        ref_outputs = self.ref(**{k: v[idx] for k, v in encoded.items()})
                        ref_log_probs = self._compute_log_probs(ref_outputs.logits, encoded["input_ids"][idx])

                    # KL divergence
                    kl = (new_log_probs - ref_log_probs).mean()

                    # Value
                    hidden = outputs.hidden_states[-1] if outputs.hidden_states else outputs.logits
                    values = self._value_head(hidden.mean(dim=1)).squeeze(-1)

                    # PPO clipped objective
                    ratio = torch.exp(new_log_probs - old_log_probs_t[idx])
                    adv = advantages_t[idx]
                    adv = (adv - adv.mean()) / (adv.std() + 1e-8)  # Normalize

                    surr1 = ratio * adv
                    surr2 = torch.clamp(ratio, 1 - self.cfg.clip_epsilon, 1 + self.cfg.clip_epsilon) * adv
                    policy_loss = -torch.min(surr1, surr2).mean()

                    # Value loss
                    value_loss = F.mse_loss(values, returns_t[idx])

                    # Entropy bonus
                    entropy = self._compute_entropy(outputs.logits[idx])

                    # Total loss
                    loss = (
                        policy_loss
                        + self.cfg.value_loss_coef * value_loss
                        - self.cfg.entropy_coef * entropy
                        + self._kl_coef * kl
                    )

                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.cfg.max_grad_norm)
                    optimizer.step()

                    total_policy_loss += policy_loss.item()
                    total_value_loss += value_loss.item()
                    total_entropy += entropy.item()
                    total_kl += kl.item()
                    n_updates += 1

        # Adaptive KL coefficient
        if self.cfg.use_adaptive_kl:
            avg_kl = total_kl / max(n_updates, 1)
            if avg_kl > 2 * self.cfg.kl_target:
                self._kl_coef *= 2.0
            elif avg_kl < self.cfg.kl_target / 2:
                self._kl_coef /= 2.0

        self.policy.eval()

        # Metrics
        MetricsRegistry.rlhf_training_step.inc()
        MetricsRegistry.rlhf_policy_kl.set(total_kl / max(n_updates, 1))

        logger.info(
            "PPO step | policy_loss=%.4f value_loss=%.4f kl=%.4f entropy=%.4f kl_coef=%.4f",
            total_policy_loss / max(n_updates, 1),
            total_value_loss / max(n_updates, 1),
            total_kl / max(n_updates, 1),
            total_entropy / max(n_updates, 1),
            self._kl_coef,
        )

        return {
            "policy_loss": total_policy_loss / max(n_updates, 1),
            "value_loss": total_value_loss / max(n_updates, 1),
            "kl": total_kl / max(n_updates, 1),
            "entropy": total_entropy / max(n_updates, 1),
            "kl_coef": self._kl_coef,
            "n_updates": n_updates,
        }

    # ------------------------------------------------------------------
    # rollout
    # ------------------------------------------------------------------

    @torch.no_grad()
    def rollout(self, prompts: list[str]) -> PPOTrajectory:
        """Generate responses with the current policy."""
        device = self.policy.device
        self.policy.eval()

        encoded = self.tokenizer(
            prompts, padding=True, truncation=True, return_tensors="pt"
        ).to(device)

        gen_outputs = self.policy.generate(
            **encoded,
            max_new_tokens=self.cfg.response_max_length,
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            do_sample=True,
            pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
        )

        responses = self.tokenizer.batch_decode(
            gen_outputs[:, encoded["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )

        # Get rewards
        reward_inputs = [
            RewardInput(prompt=p, response=r)
            for p, r in zip(prompts, responses)
        ]
        reward_outputs = self.reward.score(reward_inputs)
        rewards = [r.score for r in reward_outputs]

        # Get values
        values = self._estimate_values(encoded).cpu().tolist()

        # Get log_probs for old policy
        outputs = self.policy(**encoded)
        log_probs = self._compute_log_probs(outputs.logits, encoded["input_ids"]).cpu().tolist()

        MetricsRegistry.rlhf_reward_mean.set(sum(rewards) / max(len(rewards), 1))

        logger.info("Rollout: %d prompts, avg_reward=%.3f", len(prompts),
                     sum(rewards) / max(len(rewards), 1))

        return PPOTrajectory(
            prompts=prompts,
            responses=responses,
            rewards=rewards,
            values=values,
            log_probs=log_probs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _compute_gae(self, traj: PPOTrajectory) -> None:
        n = len(traj.rewards)
        advantages = [0.0] * n
        gae = 0.0
        for t in reversed(range(n)):
            next_val = traj.values[t + 1] if t + 1 < n else 0.0
            delta = traj.rewards[t] + self.cfg.gamma * next_val - traj.values[t]
            gae = delta + self.cfg.gamma * self.cfg.lam * gae
            advantages[t] = gae
        traj.advantages = advantages
        traj.returns = [adv + val for adv, val in zip(advantages, traj.values)]

    def _compute_log_probs(self, logits: torch.Tensor, input_ids: torch.Tensor) -> torch.Tensor:
        log_probs = F.log_softmax(logits, dim=-1)
        return log_probs.gather(-1, input_ids.unsqueeze(-1)).squeeze(-1).sum(dim=-1)

    def _compute_entropy(self, logits: torch.Tensor) -> torch.Tensor:
        probs = F.softmax(logits, dim=-1)
        log_probs = F.log_softmax(logits, dim=-1)
        return -(probs * log_probs).sum(dim=-1).mean()

    def _estimate_values(self, encoded) -> torch.Tensor:
        with torch.no_grad():
            outputs = self.policy(**encoded)
            hidden = outputs.hidden_states[-1] if outputs.hidden_states else outputs.logits
            return self._value_head(hidden.mean(dim=1)).squeeze(-1)
