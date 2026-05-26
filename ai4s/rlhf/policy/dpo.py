"""DPO trainer — Direct Preference Optimization (no explicit reward model needed).

Reference: Rafailov et al., "Direct Preference Optimization", NeurIPS 2023.

Key idea: The reward function is implicitly defined by the policy ratio,
so we can optimize directly from preference pairs without training a
separate reward model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry

logger = get_logger(__name__)


@dataclass
class DPOPair:
    prompt: str
    chosen: str
    rejected: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DPODataset(Dataset[DPOPair]):
    def __init__(self, pairs: list[DPOPair]):
        self.pairs = pairs

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> DPOPair:
        return self.pairs[idx]


# ---------------------------------------------------------------------------
# DPO Trainer
# ---------------------------------------------------------------------------


class DPOTrainer:
    """Direct Preference Optimization.

    Loss: -E[ log(sigma( beta * (log_pi(y_w|x) / log_ref(y_w|x) - log_pi(y_l|x) / log_ref(y_l|x)) )) ]

    Where:
      pi     = policy (being trained)
      ref    = reference (frozen, usually SFT model)
      y_w    = chosen response
      y_l    = rejected response
      beta   = temperature controlling deviation from reference
    """

    def __init__(
        self,
        policy_model: AutoModelForCausalLM,
        policy_tokenizer: AutoTokenizer,
        reference_model: AutoModelForCausalLM,
        beta: float = 0.1,
        learning_rate: float = 5e-7,
        batch_size: int = 32,
        epochs: int = 1,
        max_length: int = 2048,
        max_prompt_length: int = 512,
        weight_decay: float = 0.01,
        warmup_ratio: float = 0.1,
        max_grad_norm: float = 1.0,
        output_dir: str = "./checkpoints/dpo",
    ) -> None:
        self.policy = policy_model
        self.tokenizer = policy_tokenizer
        self.ref = reference_model
        self.beta = beta
        self.lr = learning_rate
        self.batch_size = batch_size
        self.epochs = epochs
        self.max_length = max_length
        self.max_prompt_length = max_prompt_length
        self.weight_decay = weight_decay
        self.warmup_ratio = warmup_ratio
        self.max_grad_norm = max_grad_norm
        self.output_dir = Path(output_dir)

        # Freeze reference
        self.ref.eval()
        for p in self.ref.parameters():
            p.requires_grad = False

    # ------------------------------------------------------------------

    def train(
        self,
        pairs: list[DPOPair],
        eval_pairs: list[DPOPair] | None = None,
    ) -> dict[str, Any]:
        device = self.policy.device
        self.output_dir.mkdir(parents=True, exist_ok=True)

        dataset = DPODataset(pairs)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True, drop_last=False)

        optimizer = torch.optim.AdamW(
            self.policy.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay,
        )

        total_steps = len(loader) * self.epochs
        warmup = int(total_steps * self.warmup_ratio)
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=self.lr, total_steps=total_steps,
            pct_start=warmup / max(total_steps, 1),
        )

        history: dict[str, list[float]] = {"train_loss": [], "eval_accuracy": []}
        global_step = 0

        self.policy.train()

        for epoch in range(self.epochs):
            epoch_loss = 0.0
            n_batches = 0

            for batch in loader:
                loss = self._compute_dpo_loss(batch, device)

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                optimizer.step()
                scheduler.step()

                epoch_loss += loss.item()
                n_batches += 1
                global_step += 1

            avg_loss = epoch_loss / max(n_batches, 1)
            history["train_loss"].append(avg_loss)

            # Eval
            eval_acc = 0.0
            if eval_pairs:
                eval_acc = self.evaluate(eval_pairs)
                history["eval_accuracy"].append(eval_acc)

            logger.info(
                "DPO epoch %d/%d | loss=%.4f | eval_acc=%.4f",
                epoch + 1, self.epochs, avg_loss, eval_acc,
            )

            MetricsRegistry.rlhf_training_step.inc()

        self.policy.eval()

        # Save final
        self.policy.save_pretrained(str(self.output_dir / "final"))
        self.tokenizer.save_pretrained(str(self.output_dir / "final"))

        return {
            "epochs": self.epochs,
            "final_loss": history["train_loss"][-1],
            "best_eval_accuracy": max(history["eval_accuracy"]) if history["eval_accuracy"] else 0.0,
            "history": history,
        }

    # ------------------------------------------------------------------

    def _compute_dpo_loss(self, batch: DPOPair, device: torch.device) -> torch.Tensor:
        # Tokenize (prompt + chosen) and (prompt + rejected)
        chosen_texts = [f"{p.prompt}\n{p.chosen}" for p in batch.pairs]
        rejected_texts = [f"{p.prompt}\n{p.rejected}" for p in batch.pairs]

        enc_chosen = self.tokenizer(
            chosen_texts, padding=True, truncation=True,
            max_length=self.max_length, return_tensors="pt",
        ).to(device)

        enc_rejected = self.tokenizer(
            rejected_texts, padding=True, truncation=True,
            max_length=self.max_length, return_tensors="pt",
        ).to(device)

        # Log-probs under policy
        policy_chosen_logp = self._sequence_log_prob(
            self.policy, enc_chosen.input_ids, enc_chosen.attention_mask
        )
        policy_rejected_logp = self._sequence_log_prob(
            self.policy, enc_rejected.input_ids, enc_rejected.attention_mask
        )

        # Log-probs under reference
        with torch.no_grad():
            ref_chosen_logp = self._sequence_log_prob(
                self.ref, enc_chosen.input_ids, enc_chosen.attention_mask
            )
            ref_rejected_logp = self._sequence_log_prob(
                self.ref, enc_rejected.input_ids, enc_rejected.attention_mask
            )

        # DPO loss
        chosen_ratio = policy_chosen_logp - ref_chosen_logp
        rejected_ratio = policy_rejected_logp - ref_rejected_logp
        logits = self.beta * (chosen_ratio - rejected_ratio)
        loss = -F.logsigmoid(logits).mean()

        return loss

    # ------------------------------------------------------------------

    def _sequence_log_prob(
        self,
        model: AutoModelForCausalLM,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Compute sum of log-probs for each sequence."""
        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        log_probs = F.log_softmax(outputs.logits, dim=-1)

        # Shift: predict token t+1 from position t
        shift_log_probs = log_probs[:, :-1, :]
        shift_labels = input_ids[:, 1:]

        # Gather log-prob of the correct token at each position
        token_log_probs = shift_log_probs.gather(-1, shift_labels.unsqueeze(-1)).squeeze(-1)

        # Sum over sequence (masking padding)
        mask = attention_mask[:, 1:].float()
        seq_log_prob = (token_log_probs * mask).sum(dim=-1)
        return seq_log_prob

    # ------------------------------------------------------------------

    @torch.no_grad()
    def evaluate(self, eval_pairs: list[DPOPair]) -> float:
        """Preference accuracy: % where policy assigns higher prob to chosen."""
        device = self.policy.device
        self.policy.eval()

        correct = 0
        total = 0

        for i in range(0, len(eval_pairs), self.batch_size):
            batch_pairs = eval_pairs[i : i + self.batch_size]
            batch = DPODataset(batch_pairs)
            batch_wrapper = next(iter(DataLoader(batch, batch_size=len(batch_pairs))))

            chosen_texts = [f"{p.prompt}\n{p.chosen}" for p in batch_pairs]
            rejected_texts = [f"{p.prompt}\n{p.rejected}" for p in batch_pairs]

            enc_c = self.tokenizer(
                chosen_texts, padding=True, truncation=True,
                max_length=self.max_length, return_tensors="pt",
            ).to(device)
            enc_r = self.tokenizer(
                rejected_texts, padding=True, truncation=True,
                max_length=self.max_length, return_tensors="pt",
            ).to(device)

            policy_c_logp = self._sequence_log_prob(self.policy, enc_c.input_ids, enc_c.attention_mask)
            policy_r_logp = self._sequence_log_prob(self.policy, enc_r.input_ids, enc_r.attention_mask)

            correct += (policy_c_logp > policy_r_logp).sum().item()
            total += len(batch_pairs)

        self.policy.train()
        return correct / max(total, 1)

    # ------------------------------------------------------------------
    # data I/O
    # ------------------------------------------------------------------

    @classmethod
    def load_pairs(cls, path: str) -> list[DPOPair]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [DPOPair(**d) for d in data]

    @staticmethod
    def save_pairs(pairs: list[DPOPair], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"prompt": p.prompt, "chosen": p.chosen, "rejected": p.rejected}
                       for p in pairs], f, ensure_ascii=False)
