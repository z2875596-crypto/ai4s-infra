"""Reward model trainer — Bradley-Terry preference loss with evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.rlhf.reward.base import HuggingFaceRewardModel

logger = get_logger(__name__)


@dataclass
class PreferencePair:
    prompt: str
    chosen: str
    rejected: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PreferenceDataset(Dataset[PreferencePair]):
    def __init__(self, pairs: list[PreferencePair]):
        self.pairs = pairs

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> PreferencePair:
        return self.pairs[idx]


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


class RewardModelTrainer:
    """Trains a reward model on preference pairs using Bradley-Terry loss.

    Loss: -E[ log(sigma(r_chosen - r_rejected)) ]

    Architecture: HF sequence-classification model (num_labels=1)
    Input:       prompt + response concatenated → single scalar reward
    """

    def __init__(
        self,
        model: HuggingFaceRewardModel,
        learning_rate: float = 1e-5,
        batch_size: int = 32,
        eval_batch_size: int = 64,
        epochs: int = 3,
        warmup_steps: int = 100,
        weight_decay: float = 0.01,
        max_grad_norm: float = 1.0,
        save_best: bool = True,
        output_dir: str = "./checkpoints/reward",
        label_smoothing: float = 0.0,
    ):
        self.model = model
        self.lr = learning_rate
        self.batch_size = batch_size
        self.eval_batch_size = eval_batch_size
        self.epochs = epochs
        self.warmup_steps = warmup_steps
        self.weight_decay = weight_decay
        self.max_grad_norm = max_grad_norm
        self.save_best = save_best
        self.output_dir = Path(output_dir)
        self.label_smoothing = label_smoothing

    # ------------------------------------------------------------------

    def train(
        self,
        train_pairs: list[PreferencePair],
        eval_pairs: list[PreferencePair] | None = None,
    ) -> dict[str, Any]:
        self.model._ensure_loaded()
        model = self.model._model
        tokenizer = self.model._tokenizer

        self.output_dir.mkdir(parents=True, exist_ok=True)

        train_dataset = PreferenceDataset(train_pairs)
        train_loader = DataLoader(
            train_dataset, batch_size=self.batch_size, shuffle=True, drop_last=False
        )

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay,
        )

        total_steps = len(train_loader) * self.epochs
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=self.lr, total_steps=total_steps,
            pct_start=self.warmup_steps / max(total_steps, 1),
        )

        best_eval_acc = 0.0
        history: dict[str, list[float]] = {"train_loss": [], "eval_accuracy": []}

        model.train()
        global_step = 0

        for epoch in range(self.epochs):
            epoch_loss = 0.0
            n_batches = 0

            for batch in train_loader:
                # Tokenize chosen and rejected
                chosen_texts = [f"{p.prompt}\n\n{p.chosen}" for p in batch.pairs]
                rejected_texts = [f"{p.prompt}\n\n{p.rejected}" for p in batch.pairs]

                enc_chosen = tokenizer(
                    chosen_texts, padding=True, truncation=True,
                    max_length=self.model.max_length, return_tensors="pt",
                ).to(self.model.device)

                enc_rejected = tokenizer(
                    rejected_texts, padding=True, truncation=True,
                    max_length=self.model.max_length, return_tensors="pt",
                ).to(self.model.device)

                r_chosen = model(**enc_chosen).logits.squeeze(-1)   # (B,)
                r_rejected = model(**enc_rejected).logits.squeeze(-1)

                # Bradley-Terry loss: -log(sigmoid(r_c - r_r))
                logits_diff = r_chosen - r_rejected
                loss = -F.logsigmoid(logits_diff).mean()

                # Label smoothing (optional regularization)
                if self.label_smoothing > 0:
                    smooth_loss = -F.logsigmoid(-logits_diff).mean()
                    loss = (1 - self.label_smoothing) * loss + self.label_smoothing * smooth_loss

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), self.max_grad_norm)
                optimizer.step()
                scheduler.step()

                epoch_loss += loss.item()
                n_batches += 1
                global_step += 1

            avg_loss = epoch_loss / max(n_batches, 1)
            history["train_loss"].append(avg_loss)
            MetricsRegistry.rlhf_reward_mean.set(avg_loss)

            # Evaluation
            eval_acc = 0.0
            if eval_pairs:
                eval_acc = self.evaluate(eval_pairs)
                history["eval_accuracy"].append(eval_acc)

                # Save best model
                if self.save_best and eval_acc > best_eval_acc:
                    best_eval_acc = eval_acc
                    self.model.save(str(self.output_dir / "best_model"))
                    logger.info("Best model saved (eval_acc=%.4f)", best_eval_acc)

            logger.info(
                "Epoch %d/%d | loss=%.4f | eval_acc=%.4f | lr=%.2e",
                epoch + 1, self.epochs, avg_loss, eval_acc,
                scheduler.get_last_lr()[0],
            )

            MetricsRegistry.rlhf_training_step.inc()

        # Save final model
        self.model.save(str(self.output_dir / "final_model"))
        model.eval()

        return {
            "epochs": self.epochs,
            "final_loss": history["train_loss"][-1],
            "best_eval_accuracy": best_eval_acc,
            "history": history,
        }

    # ------------------------------------------------------------------

    @torch.no_grad()
    def evaluate(self, eval_pairs: list[PreferencePair]) -> float:
        """Compute preference accuracy: % of pairs where r_chosen > r_rejected."""
        self.model._ensure_loaded()
        model = self.model._model
        tokenizer = self.model._tokenizer
        model.eval()

        correct = 0
        total = 0

        for i in range(0, len(eval_pairs), self.eval_batch_size):
            batch = eval_pairs[i : i + self.eval_batch_size]
            chosen_texts = [f"{p.prompt}\n\n{p.chosen}" for p in batch]
            rejected_texts = [f"{p.prompt}\n\n{p.rejected}" for p in batch]

            enc_c = tokenizer(chosen_texts, padding=True, truncation=True,
                              max_length=self.model.max_length, return_tensors="pt").to(self.model.device)
            enc_r = tokenizer(rejected_texts, padding=True, truncation=True,
                              max_length=self.model.max_length, return_tensors="pt").to(self.model.device)

            r_c = model(**enc_c).logits.squeeze(-1)
            r_r = model(**enc_r).logits.squeeze(-1)
            correct += (r_c > r_r).sum().item()
            total += len(batch)

        model.train()
        return correct / max(total, 1)

    # ------------------------------------------------------------------

    @classmethod
    def from_checkpoint(cls, checkpoint_path: str, **kwargs) -> RewardModelTrainer:
        model = HuggingFaceRewardModel(checkpoint_path)
        model.load(checkpoint_path)
        return cls(model, **kwargs)

    def save_pairs(self, pairs: list[PreferencePair], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"prompt": p.prompt, "chosen": p.chosen, "rejected": p.rejected}
                       for p in pairs], f, ensure_ascii=False)

    @classmethod
    def load_pairs(cls, path: str) -> list[PreferencePair]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [PreferencePair(**d) for d in data]
