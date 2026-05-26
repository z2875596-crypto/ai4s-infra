"""Agent dispatcher — main loop pulling tasks from queue and dispatching via gRPC/HTTP."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ai4s.common.exceptions import AgentTimeoutError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.agent_runtime.scheduler.queue import Task, TaskQueue, TaskStatus
from ai4s.agent_runtime.scheduler.router import TaskRouter, RoutingStrategy

logger = get_logger(__name__)


class AgentDispatcher:
    """Continuously pulls tasks and dispatches to the selected agent.

    Features:
      - Concurrent task execution with configurable parallelism
      - Agent health checking
      - Graceful shutdown
      - Per-agent type dispatch handlers
    """

    def __init__(
        self,
        queue: TaskQueue,
        router: TaskRouter,
        max_concurrent: int = 100,
        poll_interval_sec: float = 0.2,
        agent_timeout_sec: float = 3600.0,
        graceful_shutdown_timeout: float = 30.0,
    ) -> None:
        self.queue = queue
        self.router = router
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval_sec
        self.agent_timeout = agent_timeout_sec
        self.graceful_shutdown_timeout = graceful_shutdown_timeout

        self._running = False
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._dispatch_handlers: dict[str, callable] = {}
        self._metrics = MetricsRegistry

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        logger.info("Agent dispatcher started (max_concurrent=%d)", self.max_concurrent)

        while self._running:
            try:
                active_count = len(self._active_tasks)

                # Clean completed futures
                self._reap_completed()

                if active_count < self.max_concurrent:
                    task = await self.queue.dequeue()
                    if task:
                        coro = self._execute_with_timeout(task)
                        atask = asyncio.create_task(coro)
                        self._active_tasks[task.task_id] = atask
                        self._metrics.agent_active_tasks.labels(agent_type=task.agent_type).inc()
                    else:
                        await asyncio.sleep(self.poll_interval)
                else:
                    await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Dispatcher loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def stop(self) -> None:
        logger.info("Stopping dispatcher... (%d active tasks)", len(self._active_tasks))
        self._running = False

        # Wait for active tasks to finish
        if self._active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks.values(), return_exceptions=True),
                    timeout=self.graceful_shutdown_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Graceful shutdown timed out, cancelling %d tasks", len(self._active_tasks))
                for t in self._active_tasks.values():
                    t.cancel()

        logger.info("Dispatcher stopped")

    # -- task execution -----------------------------------------------------

    async def _execute_with_timeout(self, task: Task) -> None:
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._execute(task),
                timeout=task.timeout_sec,
            )
            await self.queue.complete(task, result)
            elapsed = time.monotonic() - start
            self._metrics.agent_task_latency.labels(agent_type=task.agent_type).observe(elapsed)
        except asyncio.TimeoutError:
            await self.queue.fail(task, f"Task timed out after {task.timeout_sec}s")
        except asyncio.CancelledError:
            await self.queue.fail(task, "Task cancelled (dispatcher shutdown)")
        except Exception as exc:
            await self.queue.fail(task, str(exc))
        finally:
            self._metrics.agent_active_tasks.labels(agent_type=task.agent_type).dec()

    async def _execute(self, task: Task) -> Any:
        """Dispatch to the actual agent and wait for the result.

        Override or register handlers for different agent types.
        """
        # Select the best agent
        agent_id = self.router.route(task.action)
        if not agent_id:
            raise RuntimeError(f"No agent available for action: {task.action}")

        # Use registered handler if available
        handler = self._dispatch_handlers.get(task.agent_type)
        if handler:
            return await handler(task, agent_id)

        # Default: call agent via gRPC or HTTP
        return await self._dispatch_grpc(task, agent_id)

    async def _dispatch_grpc(self, task: Task, agent_id: str) -> Any:
        """Send task to agent via gRPC and await response.

        In production, this would use:
          - gRPC unary call: agent_stub.ExecuteTask(TaskRequest)
          - Or enqueue to agent-specific Redis queue and poll for result
        """
        # Stub: simulate agent execution
        await asyncio.sleep(0.05)  # Network + processing time
        logger.debug("Task %s dispatched to agent %s", task.task_id, agent_id)
        return {"status": "completed", "agent_id": agent_id, "task_id": task.task_id}

    # -- handler registration -----------------------------------------------

    def register_handler(self, agent_type: str, handler: callable) -> None:
        """Register a custom dispatch handler for an agent type.

        handler(task: Task, agent_id: str) -> Any
        """
        self._dispatch_handlers[agent_type] = handler
        logger.info("Handler registered for agent_type=%s", agent_type)

    # -- helpers ------------------------------------------------------------

    def _reap_completed(self) -> None:
        done = [
            tid for tid, t in self._active_tasks.items()
            if t.done()
        ]
        for tid in done:
            del self._active_tasks[tid]

    @property
    def active_count(self) -> int:
        return len(self._active_tasks)

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "active_tasks": len(self._active_tasks),
            "max_concurrent": self.max_concurrent,
            "handlers": list(self._dispatch_handlers.keys()),
        }
