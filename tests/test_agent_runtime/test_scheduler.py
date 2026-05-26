"""Tests for agent scheduler."""

from ai4s.agent_runtime.scheduler.queue import Task, TaskQueue, TaskStatus, TaskPriority
from ai4s.agent_runtime.scheduler.router import TaskRouter, RoutingStrategy


class TestTask:
    def test_task_defaults(self):
        task = Task(agent_type="test", action="run")
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.max_retries == 3

    def test_task_json_roundtrip(self):
        task = Task(
            agent_type="type_a", action="do_stuff",
            payload={"key": "value"}, priority=TaskPriority.HIGH,
        )
        json_str = task.to_json()
        restored = Task.from_json(json_str)
        assert restored.agent_type == "type_a"
        assert restored.action == "do_stuff"
        assert restored.priority == TaskPriority.HIGH
        assert restored.payload == {"key": "value"}


class TestTaskRouter:
    def test_route_to_eligible_agent(self):
        router = TaskRouter(strategy=RoutingStrategy.ROUND_ROBIN)
        router.register_agent("agent1", ["run", "train"])
        router.register_agent("agent2", ["infer"])

        result = router.route("run", ["agent1", "agent2"])
        assert result == "agent1"

    def test_route_no_eligible(self):
        router = TaskRouter(strategy=RoutingStrategy.ROUND_ROBIN)
        router.register_agent("agent1", ["train"])
        result = router.route("run", ["agent1"])
        assert result is None

    def test_unregister_agent(self):
        router = TaskRouter()
        router.register_agent("agent1", ["run"])
        router.unregister_agent("agent1")
        result = router.route("run", ["agent1"])
        assert result is None
