"""Integration tests for agent_runtime API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai4s.agent_runtime.api import router


@pytest.fixture(autouse=True)
def reset_globals():
    import ai4s.agent_runtime.api as api_mod

    api_mod._orchestrator = None
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestTaskRoutes:
    def test_submit_task(self, client):
        resp = client.post("/api/v1/agent/tasks", json={
            "agent_type": "worker",
            "action": "compute",
            "payload": {"input": 42},
            "priority": "normal",
        })
        assert resp.status_code == 200
        assert "task_id" in resp.json()
        assert resp.json()["status"] == "queued"

    def test_submit_with_all_priorities(self, client):
        for prio in ["low", "normal", "high", "critical"]:
            resp = client.post("/api/v1/agent/tasks", json={
                "agent_type": "worker", "action": "ping", "priority": prio,
            })
            assert resp.status_code == 200

    def test_get_queue_stats(self, client):
        # Submit a task to have something in queue
        client.post("/api/v1/agent/tasks", json={
            "agent_type": "worker", "action": "ping",
        })
        resp = client.get("/api/v1/agent/queue/stats")
        assert resp.status_code == 200
        assert "pending" in resp.json()
        assert "active" in resp.json()


class TestAgentRoutes:
    def test_register_and_list(self, client):
        resp = client.post("/api/v1/agent/agents", json={
            "agent_id": "agent-1",
            "capabilities": ["compute", "search"],
            "max_capacity": 5,
        })
        assert resp.status_code == 200

        resp = client.get("/api/v1/agent/agents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_unregister_agent(self, client):
        client.post("/api/v1/agent/agents", json={
            "agent_id": "temp-agent", "capabilities": ["test"],
        })
        resp = client.delete("/api/v1/agent/agents/temp-agent")
        assert resp.status_code == 200

        resp = client.get("/api/v1/agent/agents")
        assert resp.json()["total"] == 0


class TestToolRoutes:
    def test_register_and_list(self, client):
        resp = client.post("/api/v1/agent/tools", json={
            "name": "web_search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "category": "search",
        })
        assert resp.status_code == 200

        resp = client.get("/api/v1/agent/tools")
        assert resp.status_code == 200
        assert len(resp.json()["tools"]) == 1

    def test_execute_tool_not_found(self, client):
        resp = client.post("/api/v1/agent/tools/execute", json={
            "tool_name": "nonexistent",
            "arguments": {},
        })
        assert resp.status_code == 500

    def test_execute_chain(self, client):
        resp = client.post("/api/v1/agent/tools/chain", json={
            "steps": [],
        })
        assert resp.status_code == 200
        assert resp.json()["results"] == []


class TestMemoryRoutes:
    def test_remember_and_recall(self, client):
        resp = client.post("/api/v1/agent/memory", json={
            "content": "The user prefers dark mode UI.",
            "tags": ["user_preference", "ui"],
            "importance": 0.8,
            "source": "user",
        })
        assert resp.status_code == 200
        mem_id = resp.json()["memory_id"]

        resp = client.post("/api/v1/agent/memory/recall", json={
            "query": "dark mode preference",
            "top_k": 3,
        })
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_recall_as_context(self, client):
        client.post("/api/v1/agent/memory", json={
            "content": "GPU cluster has 128 nodes.",
            "tags": ["infra"],
        })
        resp = client.post("/api/v1/agent/memory/recall", json={
            "query": "GPU nodes",
            "as_context": True,
        })
        assert resp.status_code == 200
        assert isinstance(resp.json()["context"], str)

    def test_memory_stats(self, client):
        resp = client.get("/api/v1/agent/memory/stats")
        assert resp.status_code == 200

    def test_summarize_conversation(self, client):
        resp = client.post("/api/v1/agent/memory/summarize", json={
            "messages": [
                {"role": "user", "content": "I need to train a model."},
                {"role": "assistant", "content": "What kind of model?"},
                {"role": "user", "content": "A BERT for sentiment analysis."},
            ],
            "tags": ["conversation"],
        })
        assert resp.status_code == 200
        assert "memory_id" in resp.json()
        assert "compression_ratio" in resp.json()

    def test_compress_memories(self, client):
        resp = client.post("/api/v1/agent/memory/compress?days=30")
        assert resp.status_code == 200
        assert "compressed" in resp.json()


class TestStatusRoute:
    def test_status(self, client):
        resp = client.get("/api/v1/agent/status")
        assert resp.status_code == 200
        assert "queue" in resp.json()
        assert "agents" in resp.json()
        assert "tools" in resp.json()
        assert "memories" in resp.json()
        assert "dispatcher" in resp.json()
