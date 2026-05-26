"""Prometheus-based metrics registry for all four AI4S modules."""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

_registry = CollectorRegistry(auto_describe=True)


class MetricsRegistry:
    """Central registry for application-level metrics."""

    # --- Data Infra ---
    data_ingested_rows = Counter(
        "ai4s_data_ingested_rows_total",
        "Total rows ingested",
        ["source", "status"],
        registry=_registry,
    )
    data_cleaning_issues = Counter(
        "ai4s_data_cleaning_issues_total",
        "Issues found during cleaning",
        ["severity"],
        registry=_registry,
    )

    # --- RLHF ---
    rlhf_reward_mean = Gauge(
        "ai4s_rlhf_reward_mean",
        "Mean reward score across training batch",
        registry=_registry,
    )
    rlhf_policy_kl = Gauge(
        "ai4s_rlhf_policy_kl_divergence",
        "KL divergence between current and reference policy",
        registry=_registry,
    )
    rlhf_training_step = Counter(
        "ai4s_rlhf_training_steps_total",
        "Total RLHF training steps",
        registry=_registry,
    )

    # --- Agent Runtime ---
    agent_active_tasks = Gauge(
        "ai4s_agent_active_tasks",
        "Currently active agent tasks",
        ["agent_type"],
        registry=_registry,
    )
    agent_task_latency = Histogram(
        "ai4s_agent_task_latency_seconds",
        "Agent task end-to-end latency",
        ["agent_type"],
        registry=_registry,
    )

    # --- HPC Fusion ---
    hpc_node_utilization = Gauge(
        "ai4s_hpc_node_utilization_ratio",
        "GPU/CPU node utilization",
        ["node_id", "resource_type"],
        registry=_registry,
    )
    hpc_queue_depth = Gauge(
        "ai4s_hpc_queue_depth",
        "Pending jobs in scheduling queue",
        ["queue_name"],
        registry=_registry,
    )
    hpc_job_duration = Histogram(
        "ai4s_hpc_job_duration_seconds",
        "Job wall-clock duration",
        ["partition"],
        registry=_registry,
    )

    @classmethod
    def export(cls) -> bytes:
        return generate_latest(_registry)

    @classmethod
    def get_registry(cls) -> CollectorRegistry:
        return _registry
