"""Agent orchestrator — unified high-level API for the entire agent runtime."""

from __future__ import annotations

from typing import Any

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.agent_runtime.scheduler.dispatcher import AgentDispatcher
from ai4s.agent_runtime.scheduler.queue import Task, TaskQueue, TaskPriority
from ai4s.agent_runtime.scheduler.router import TaskRouter, RoutingStrategy
from ai4s.agent_runtime.tools.executor import ToolExecutor
from ai4s.agent_runtime.tools.registry import ToolDefinition, ToolRegistry
from ai4s.agent_runtime.tools.sandbox import ExecutionSandbox
from ai4s.agent_runtime.memory.store import MemoryEntry, MemoryStore
from ai4s.agent_runtime.memory.retrieval import MemoryRetriever
from ai4s.agent_runtime.memory.summarizer import MemorySummarizer

logger = get_logger(__name__)


class AgentOrchestrator:
    """Unified orchestrator for agent scheduling, tools, and memory.

    This is the single entrypoint that applications use to interact with
    the agent runtime. It wires together all subsystems.

    Usage::

        orch = AgentOrchestrator(Config())

        # Setup
        orch.register_tool(ToolDefinition(name="search", ...))
        orch.register_agent("worker-1", ["search", "compute"])

        # Submit tasks
        task_id = await orch.submit_task("worker", "search", {"query": "..."})

        # Memory
        await orch.remember("User prefers metric units", tags=["user_pref"])
        context = await orch.recall("metric units")

        # Execute tools directly
        result = await orch.execute_tool("search", {"query": "..."})
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        ac = self.config.agent_runtime

        # -- scheduler --
        self.task_queue = TaskQueue(
            redis_url=ac.get("scheduler", {}).get("queue_backend", "redis://localhost:6379")
        )
        self.router = TaskRouter(
            strategy=RoutingStrategy(
                ac.get("scheduler", {}).get("routing_strategy", "least_busy")
            )
        )
        self.dispatcher = AgentDispatcher(
            self.task_queue,
            self.router,
            max_concurrent=ac.get("scheduler", {}).get("max_concurrent_agents", 100),
        )

        # -- tools --
        self.tool_registry = ToolRegistry()
        self.sandbox = ExecutionSandbox(
            sandbox_type=ac.get("tools", {}).get("sandbox_type", "gvisor"),
            network=ac.get("tools", {}).get("allowed_network", "isolated"),
        )
        self.tool_executor = ToolExecutor(self.tool_registry, self.sandbox)

        # -- memory --
        self.memory_store = MemoryStore(
            backend=ac.get("memory", {}).get("backend", "weaviate"),
            embedding_model=ac.get("memory", {}).get("embedding_model", "text-embedding-3-small"),
        )
        self.memory_retriever = MemoryRetriever(
            self.memory_store,
            top_k=ac.get("memory", {}).get("retrieval_top_k", 10),
        )
        self.memory_summarizer = MemorySummarizer(
            self.memory_store,
            max_context_tokens=ac.get("memory", {}).get("max_context_tokens", 128000),
        )

    # -- task management ----------------------------------------------------

    async def submit_task(
        self,
        agent_type: str,
        action: str,
        payload: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_sec: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        task = Task(
            agent_type=agent_type,
            action=action,
            payload=payload,
            priority=priority,
            timeout_sec=timeout_sec or self.config.agent_runtime.get("scheduler", {}).get("task_timeout_sec", 3600),
            tags=tags or [],
        )
        task_id = await self.task_queue.enqueue(task)
        logger.info("Task submitted: %s (agent=%s action=%s)", task_id, agent_type, action)
        return task_id

    async def get_task_result(self, task_id: str) -> Any | None:
        return await self.task_queue.get_result(task_id)

    async def get_queue_stats(self) -> dict[str, Any]:
        return await self.task_queue.stats()

    # -- agent registration -------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        capabilities: list[str],
        max_capacity: int = 10,
        weight: float = 1.0,
    ) -> None:
        self.router.register_agent(agent_id, capabilities, max_capacity, weight)

    def register_handler(self, agent_type: str, handler: callable) -> None:
        self.dispatcher.register_handler(agent_type, handler)

    # -- tool management ----------------------------------------------------

    def register_tool(self, tool: ToolDefinition) -> None:
        self.tool_registry.register(tool)

    def register_tools(self, tools: list[ToolDefinition]) -> None:
        for t in tools:
            self.tool_registry.register(t)

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.tool_executor.execute(tool_name, arguments)

    async def execute_tool_chain(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self.tool_executor.execute_chain(steps)

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.tool_registry.list_all()]

    # -- memory management --------------------------------------------------

    async def remember(
        self,
        content: str,
        tags: list[str] | None = None,
        importance: float = 0.5,
        source: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.memory_store.store_text(
            content=content,
            tags=tags or [],
            importance=importance,
            source=source,
            metadata=metadata,
        )

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        filter_tags: list[str] | None = None,
        as_context: bool = False,
    ) -> list[dict[str, Any]] | str:
        entries = await self.memory_retriever.semantic_search(
            query, top_k=top_k, filter_tags=filter_tags
        )
        if as_context:
            return self.memory_retriever.format_context(entries)
        return [
            {"id": e.memory_id, "content": e.content, "importance": e.importance, "tags": e.tags}
            for e in entries
        ]

    async def summarize_conversation(
        self,
        messages: list[dict[str, str]],
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        return await self.memory_summarizer.summarize_conversation(messages, tags)

    async def get_memory_stats(self) -> dict[str, Any]:
        return await self.memory_store.stats()

    async def compress_old_memories(self, days: int = 30) -> int:
        return await self.memory_summarizer.compress_old_memories(days)

    # -- lifecycle ----------------------------------------------------------

    async def start_dispatcher(self) -> None:
        import asyncio
        asyncio.create_task(self.dispatcher.start())

    async def stop_dispatcher(self) -> None:
        await self.dispatcher.stop()

    async def status(self) -> dict[str, Any]:
        return {
            "queue": await self.task_queue.stats(),
            "agents": self.router.agent_summary(),
            "tools": len(self.tool_registry.list_all()),
            "memories": await self.memory_store.count(),
            "dispatcher": self.dispatcher.status(),
        }
