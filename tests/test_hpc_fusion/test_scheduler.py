"""Tests for HPC scheduling engine."""

from ai4s.hpc_fusion.scheduler.priority import JobPrioritizer, PrioritizedJob
from ai4s.hpc_fusion.connector.base import HPCJob, JobState, NodeInfo


class TestJobPrioritizer:
    def test_basic_priority(self):
        p = JobPrioritizer()
        result = p.prioritize({"name": "job1", "gpus": 4, "priority": 5})
        assert isinstance(result, PrioritizedJob)
        assert result.priority > 0
        assert "queue" in result.factors

    def test_higher_queue_priority_wins(self):
        p = JobPrioritizer()
        low = p.prioritize({"name": "low", "gpus": 4, "priority": 9})
        high = p.prioritize({"name": "high", "gpus": 4, "priority": 1})
        assert high.priority > low.priority

    def test_fair_share_boosts_light_users(self):
        p = JobPrioritizer(fairshare_weight=1.0, queue_weight=0)
        p.record_usage("heavy_user", 1000)
        heavy = p.prioritize({"name": "h", "priority": 5, "user": "heavy_user"})
        light = p.prioritize({"name": "l", "priority": 5, "user": "light_user"})
        assert light.priority > heavy.priority


class TestHPCJob:
    def test_job_creation(self):
        job = HPCJob(
            job_id="123", name="train-gpt", state=JobState.PENDING,
            partition="gpu", nodes=4, gpus_per_node=8, cpu_cores=256,
            memory_mb=512000, wall_time_min=1440, submit_time="2024-01-01T00:00:00Z",
        )
        assert job.job_id == "123"
        assert job.gpus_per_node == 8


class TestNodeInfo:
    def test_node_available_gpus(self):
        node = NodeInfo(
            node_id="gpu01", state="idle",
            cpu_total=128, cpu_alloc=32,
            mem_total_mb=512000, mem_alloc_mb=128000,
            gpu_total=8, gpu_alloc=2,
        )
        assert (node.gpu_total - node.gpu_alloc) == 6
