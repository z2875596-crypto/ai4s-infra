"""Reward model — HF Transformers-based with proper batching, device management, caching."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from transformers import AutoModelForSequenceClassification, AutoTokenizer, PreTrainedModel, PreTrainedTokenizer

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RewardInput:
    prompt: str
    response: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_text(self, template: str = "{prompt}\n\n{response}") -> str:
        return template.format(prompt=self.prompt, response=self.response)


@dataclass
class RewardOutput:
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# abstract interface
# ---------------------------------------------------------------------------


class RewardModel(ABC):
    def __init__(self, model_name: str, device: str = "cuda") -> None:
        self.model_name = model_name
        self.device = device

    @abstractmethod
    def score(self, inputs: list[RewardInput]) -> list[RewardOutput]: ...

    @abstractmethod
    def score_batch(self, inputs: list[RewardInput], batch_size: int = 32) -> list[RewardOutput]: ...

    @abstractmethod
    def save(self, path: str) -> None: ...

    @abstractmethod
    def load(self, path: str) -> None: ...


# ---------------------------------------------------------------------------
# HuggingFace-based reward model
# ---------------------------------------------------------------------------


class HuggingFaceRewardModel(RewardModel):
    """Reward model backed by a HuggingFace sequence-classification model.

    Supports:
      - float16 / bfloat16 inference
      - Flash Attention 2 for speed
      - 8-bit quantization for memory-constrained setups
      - Tokenizer chat templates
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cuda",
        max_length: int = 2048,
        dtype: str = "float16",         # float16 | bfloat16 | float32
        load_in_8bit: bool = False,
        use_flash_attention_2: bool = False,
        prompt_template: str = "{prompt}\n\n{response}",
    ) -> None:
        super().__init__(model_name, device)
        self.max_length = max_length
        self.dtype = dtype
        self.load_in_8bit = load_in_8bit
        self.use_flash_attention_2 = use_flash_attention_2
        self.prompt_template = prompt_template
        self._tokenizer: PreTrainedTokenizer | None = None
        self._model: PreTrainedModel | None = None
        self._torch_dtype = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }[dtype]

    # -- initialization (lazy) ----------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        logger.info("Loading reward model: %s (device=%s, dtype=%s)", self.model_name, self.device, self.dtype)

        model_kwargs: dict[str, Any] = {
            "num_labels": 1,
            "torch_dtype": self._torch_dtype,
        }
        if self.load_in_8bit:
            model_kwargs["load_in_8bit"] = True
            model_kwargs["device_map"] = "auto"
        if self.use_flash_attention_2:
            model_kwargs["use_flash_attention_2"] = True

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name, **model_kwargs
        )

        if not self.load_in_8bit:
            self._model = self._model.to(self.device)
        self._model.eval()

        logger.info("Reward model loaded: %s (%d params)", self.model_name,
                     sum(p.numel() for p in self._model.parameters()))

    # -- scoring ------------------------------------------------------------

    @torch.no_grad()
    def score(self, inputs: list[RewardInput]) -> list[RewardOutput]:
        return self.score_batch(inputs, batch_size=len(inputs))

    @torch.no_grad()
    def score_batch(self, inputs: list[RewardInput], batch_size: int = 32) -> list[RewardOutput]:
        self._ensure_loaded()

        all_scores: list[float] = []
        texts = [inp.to_text(self.prompt_template) for inp in inputs]

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            encoded = self._tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)

            logits = self._model(**encoded).logits.squeeze(-1)
            scores = logits.cpu().tolist()
            if isinstance(scores, float):
                scores = [scores]
            all_scores.extend(scores)

        return [RewardOutput(score=s) for s in all_scores]

    def pairwise_score(
        self, inputs: list[RewardInput]
    ) -> tuple[list[RewardOutput], list[RewardOutput]]:
        """Score chosen and rejected separately (for Bradley-Terry training)."""
        self._ensure_loaded()

        chosen_texts = [inp.to_text(self.prompt_template) for inp in inputs]
        rejected_texts = [
            (inp.metadata.get("rejected") or "").replace("{prompt}", inp.prompt)
            for inp in inputs
        ]

        encoded_chosen = self._tokenizer(
            chosen_texts, padding=True, truncation=True,
            max_length=self.max_length, return_tensors="pt",
        ).to(self.device)
        encoded_rejected = self._tokenizer(
            rejected_texts, padding=True, truncation=True,
            max_length=self.max_length, return_tensors="pt",
        ).to(self.device)

        logits_c = self._model(**encoded_chosen).logits.squeeze(-1).cpu().tolist()
        logits_r = self._model(**encoded_rejected).logits.squeeze(-1).cpu().tolist()

        return (
            [RewardOutput(score=s) for s in (logits_c if isinstance(logits_c, list) else [logits_c])],
            [RewardOutput(score=s) for s in (logits_r if isinstance(logits_r, list) else [logits_r])],
        )

    # -- save / load --------------------------------------------------------

    def save(self, path: str) -> None:
        self._ensure_loaded()
        Path(path).mkdir(parents=True, exist_ok=True)
        self._model.save_pretrained(path)
        self._tokenizer.save_pretrained(path)
        # Save config
        config = {
            "model_name": self.model_name,
            "max_length": self.max_length,
            "dtype": self.dtype,
            "prompt_template": self.prompt_template,
        }
        with open(Path(path) / "reward_config.json", "w") as f:
            json.dump(config, f)

    def load(self, path: str) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(path)
        self._model = AutoModelForSequenceClassification.from_pretrained(path)
        self._model = self._model.to(self.device).eval()
        config_path = Path(path) / "reward_config.json"
        if config_path.exists():
            with open(config_path) as f:
                cfg = json.load(f)
                self.max_length = cfg.get("max_length", self.max_length)
                self.prompt_template = cfg.get("prompt_template", self.prompt_template)


# ---------------------------------------------------------------------------
# Ensemble-capable random reward (for testing / debugging)
# ---------------------------------------------------------------------------


class ConstantRewardModel(RewardModel):
    """Always returns a fixed score — useful for pipeline testing."""

    def __init__(self, score: float = 0.5, model_name: str = "constant", device: str = "cpu"):
        super().__init__(model_name, device)
        self._score = score

    def score(self, inputs: list[RewardInput]) -> list[RewardOutput]:
        return [RewardOutput(score=self._score) for _ in inputs]

    def score_batch(self, inputs: list[RewardInput], batch_size: int = 32) -> list[RewardOutput]:
        return self.score(inputs)

    def save(self, path: str) -> None:
        pass

    def load(self, path: str) -> None:
        pass
