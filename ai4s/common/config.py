"""Configuration loader with layered resolution (defaults < file < env)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"


class Config:
    """Layered config: YAML file + environment overrides."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        for key in os.environ:
            if not key.startswith("AI4S_"):
                continue
            parts = key[5:].lower().split("__")
            if len(parts) < 2:
                continue
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = os.environ[key]

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    @property
    def data_infra(self) -> dict[str, Any]:
        return self._data.get("data_infra", {})

    @property
    def rlhf(self) -> dict[str, Any]:
        return self._data.get("rlhf", {})

    @property
    def agent_runtime(self) -> dict[str, Any]:
        return self._data.get("agent_runtime", {})

    @property
    def hpc_fusion(self) -> dict[str, Any]:
        return self._data.get("hpc_fusion", {})
