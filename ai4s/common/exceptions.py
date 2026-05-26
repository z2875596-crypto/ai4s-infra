"""Domain exceptions for AI4S modules."""

from __future__ import annotations


class AI4SError(Exception):
    """Base exception for all AI4S errors."""


# --- Data Infra ---
class IngestionError(AI4SError):
    """Data source connection or read failure."""


class ValidationError(AI4SError):
    """Schema or quality validation failure."""


class VersioningError(AI4SError):
    """Snapshot or lineage operation failure."""


# --- RLHF ---
class RewardModelError(AI4SError):
    """Reward model training or inference failure."""


class PolicyTrainingError(AI4SError):
    """Policy optimization failure (PPO/DPO)."""


class FeedbackCollectionError(AI4SError):
    """Human feedback pipeline failure."""


# --- Agent Runtime ---
class AgentTimeoutError(AI4SError):
    """Agent task exceeded timeout."""


class ToolExecutionError(AI4SError):
    """Sandboxed tool execution failure."""


class MemoryStoreError(AI4SError):
    """Memory retrieval or storage failure."""


# --- HPC Fusion ---
class SchedulingError(AI4SError):
    """Job scheduling or placement failure."""


class ConnectorError(AI4SError):
    """HPC connector communication failure."""


class ResourceExhaustedError(AI4SError):
    """No available resources for job placement."""
