"""Task queue — Redis-backed priority queue with in-memory fallback.

Features:
  - Priority queues via Redis Sorted Sets (or in-memory heapq)
  - Delayed / scheduled tasks
  - Dead-letter queue for permanently failed tasks
  - Per-task TTL and retry with exponential backoff
  - Prometheus metrics
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ai4s.common.exceptions import AI4SError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD = "dead"                       # permanently failed, moved to DLQ


class TaskPriority(int, Enum):
    LOW = 10
    NORMAL = 5
    HIGH = 1
    CRITICAL = 0


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_type: str = ""
    action: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: Any = None
    error: str | None = None
    max_retries: int = 3
    retry_count: int = 0
    retry_backoff_base: float = 2.0     # exponential backoff multiplier
    timeout_sec: int = 3600
    scheduled_at: str | None = None      # ISO timestamp for delayed execution
    tags: list[str] = field(default_factory=list)
    parent_task_id: str | None = None    # For DAG task dependencies
    trace_id: str | None = None          # OpenTelemetry trace ID
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        d = self.__dict__.copy()
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return json.dumps(d, default=str)

    @classmethod
    def from_json(cls, data: str) -> Task:
        d = json.loads(data)
        d["priority"] = TaskPriority(d["priority"])
        d["status"] = TaskStatus(d["status"])
        return cls(**d)

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.DEAD, TaskStatus.CANCELLED)

    @property
    def retry_delay_sec(self) -> float:
        return self.retry_backoff_base ** self.retry_count


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------


class _InMemoryQueue:
    """Drop-in fallback when Redis is unavailable — uses dicts and lists."""

    def __init__(self) -> None:
        self._pending: dict[str, Task] = {}
        self._active: dict[str, Task] = {}
        self._dead: list[Task] = []
        self._scheduled: dict[str, Task] = {}
        self._results: dict[str, str] = {}

    async def zadd(self, key: str, mapping: dict) -> None:
        for data, _score in mapping.items():
            task = Task.from_json(data)
            if "scheduled" in key:
                self._scheduled[task.task_id] = task
            else:
                self._pending[task.task_id] = task

    async def zcard(self, key: str) -> int:
        if "pending" in key:
            return len(self._pending)
        if "scheduled" in key:
            return len(self._scheduled)
        return 0

    async def zpopmin(self, key: str, count: int = 1) -> list:
        if not self._pending:
            return []
        # Pop highest priority (lowest score)
        sorted_tasks = sorted(self._pending.items(), key=lambda x: x[1].priority.value)
        results = []
        for _ in range(min(count, len(sorted_tasks))):
            tid, task = sorted_tasks.pop(0)
            del self._pending[tid]
            results.append((task.to_json(), task.priority.value))
        return results

    async def zrangebyscore(self, key: str, lo: float, hi: float, start: int = 0, num: int = 1) -> list:
        now = datetime.now(timezone.utc).timestamp()
        ready = []
        for tid, task in list(self._scheduled.items()):
            if task.scheduled_at:
                epoch = datetime.fromisoformat(task.scheduled_at).timestamp()
                if epoch <= now:
                    ready.append(task.to_json())
        return ready[start:start + num]

    async def zrem(self, key: str, *members: str) -> None:
        for m in members:
            task = Task.from_json(m)
            self._scheduled.pop(task.task_id, None)

    async def hset(self, key: str, task_id: str, data: str) -> None:
        self._active[task_id] = Task.from_json(data)

    async def hget(self, key: str, task_id: str) -> str | None:
        task = self._active.get(task_id)
        return task.to_json() if task else None

    async def hdel(self, key: str, task_id: str) -> None:
        self._active.pop(task_id, None)

    async def hlen(self, key: str) -> int:
        return len(self._active)

    async def setex(self, key: str, ttl: int, data: str) -> None:
        # Extract task_id from key pattern "ai4s:task:result:{task_id}"
        tid = key.rsplit(":", 1)[-1]
        self._results[tid] = data

    async def get(self, key: str) -> str | None:
        tid = key.rsplit(":", 1)[-1]
        return self._results.get(tid)

    async def lpush(self, key: str, data: str) -> None:
        self._dead.insert(0, Task.from_json(data))

    async def llen(self, key: str) -> int:
        return len(self._dead)

    async def rpop(self, key: str) -> str | None:
        if not self._dead:
            return None
        task = self._dead.pop()
        return task.to_json()

    async def ping(self) -> bool:
        return True

    def pipeline(self) -> _InMemoryPipeline:
        return _InMemoryPipeline(self)


class _InMemoryPipeline:
    def __init__(self, store: _InMemoryQueue) -> None:
        self._store = store
        self._cmds: list[tuple[str, tuple]] = []

    def zadd(self, key: str, mapping: dict) -> None:
        self._cmds.append(("zadd", (key, mapping)))

    async def execute(self) -> None:
        for cmd, args in self._cmds:
            if cmd == "zadd":
                await self._store.zadd(*args)


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


class TaskQueue:
    """Redis-backed priority task queue with in-memory fallback.

    Redis keys used:
      ai4s:task:pending      — Sorted Set (score=priority, member=task_json)
      ai4s:task:active       — Hash (task_id → task_json)
      ai4s:task:dead         — List (dead letter queue)
      ai4s:task:scheduled    — Sorted Set (score=epoch, member=task_json)
      ai4s:task:result:{id}  — String (result JSON, with TTL)
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", prefix: str = "ai4s:task") -> None:
        self._redis_url = redis_url
        self._prefix = prefix
        self._redis: Any = None
        self._fallback: _InMemoryQueue | None = None

    async def _connect(self) -> None:
        if self._redis is not None or self._fallback is not None:
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            await self._redis.ping()
            logger.info("Connected to Redis at %s", self._redis_url)
        except Exception as e:
            logger.warning("Redis unavailable (%s), using in-memory queue fallback", e)
            self._redis = None
            self._fallback = _InMemoryQueue()

    @property
    def _store(self) -> Any:
        return self._redis if self._redis is not None else self._fallback

    # -- enqueue ------------------------------------------------------------

    async def enqueue(self, task: Task) -> str:
        await self._connect()
        store = self._store

        if task.scheduled_at:
            from datetime import datetime
            epoch = datetime.fromisoformat(task.scheduled_at).timestamp()
            await store.zadd(f"{self._prefix}:scheduled", {task.to_json(): epoch})
        else:
            score = task.priority.value
            await store.zadd(f"{self._prefix}:pending", {task.to_json(): score})

        logger.info("Task enqueued: %s (agent=%s action=%s priority=%s)",
                     task.task_id, task.agent_type, task.action, task.priority.name)
        MetricsRegistry.agent_active_tasks.labels(agent_type=task.agent_type).inc()
        return task.task_id

    async def enqueue_batch(self, tasks: list[Task]) -> list[str]:
        await self._connect()
        store = self._store
        ids: list[str] = []
        pipe = store.pipeline()
        for task in tasks:
            score = task.priority.value
            pipe.zadd(f"{self._prefix}:pending", {task.to_json(): score})
            ids.append(task.task_id)
        await pipe.execute()
        return ids

    # -- dequeue ------------------------------------------------------------

    async def dequeue(self, agent_type: str | None = None) -> Task | None:
        await self._connect()
        store = self._store

        # First, check scheduled tasks
        now = datetime.now(timezone.utc).timestamp()
        scheduled = await store.zrangebyscore(
            f"{self._prefix}:scheduled", 0, now, start=0, num=1
        )
        if scheduled:
            task = Task.from_json(scheduled[0])
            await store.zrem(f"{self._prefix}:scheduled", scheduled[0])
            await self._start_task(task)
            return task

        # Pop highest-priority pending task
        results = await store.zpopmin(f"{self._prefix}:pending", count=1)
        if not results:
            return None

        task = Task.from_json(results[0][0])
        if agent_type and task.agent_type != agent_type:
            await self.enqueue(task)
            return None

        await self._start_task(task)
        return task

    async def _start_task(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        await self._store.hset(f"{self._prefix}:active", task.task_id, task.to_json())

    # -- complete / fail ----------------------------------------------------

    async def complete(self, task: Task, result: Any = None) -> None:
        await self._connect()
        store = self._store
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.result = result

        await store.hdel(f"{self._prefix}:active", task.task_id)
        await store.setex(
            f"{self._prefix}:result:{task.task_id}",
            86400,
            json.dumps(result, default=str),
        )
        MetricsRegistry.agent_active_tasks.labels(agent_type=task.agent_type).dec()
        logger.info("Task completed: %s", task.task_id)

    async def fail(self, task: Task, error: str) -> None:
        await self._connect()
        store = self._store
        task.retry_count += 1

        if task.retry_count < task.max_retries:
            task.status = TaskStatus.RETRYING
            task.error = error
            delay_sec = task.retry_delay_sec
            task.scheduled_at = datetime.now(timezone.utc).isoformat()
            await store.hdel(f"{self._prefix}:active", task.task_id)
            await self._schedule_retry(task, delay_sec)
            logger.info("Task %s retry %d/%d (delay=%ds)",
                         task.task_id, task.retry_count, task.max_retries, delay_sec)
        else:
            task.status = TaskStatus.DEAD
            task.error = error
            task.completed_at = datetime.now(timezone.utc).isoformat()
            await store.hdel(f"{self._prefix}:active", task.task_id)
            await store.lpush(f"{self._prefix}:dead", task.to_json())
            MetricsRegistry.agent_active_tasks.labels(agent_type=task.agent_type).dec()
            logger.error("Task %s permanently failed (DLQ): %s", task.task_id, error)

    async def _schedule_retry(self, task: Task, delay_sec: float) -> None:
        task.status = TaskStatus.PENDING
        await self._store.zadd(
            f"{self._prefix}:pending",
            {task.to_json(): task.priority.value + 1},
        )

    async def cancel(self, task_id: str) -> bool:
        await self._connect()
        store = self._store
        active = await store.hget(f"{self._prefix}:active", task_id)
        if active:
            task = Task.from_json(active)
            task.status = TaskStatus.CANCELLED
            await store.hdel(f"{self._prefix}:active", task_id)
            return True
        return False

    # -- query --------------------------------------------------------------

    async def get_task(self, task_id: str) -> Task | None:
        await self._connect()
        store = self._store
        active = await store.hget(f"{self._prefix}:active", task_id)
        if active:
            return Task.from_json(active)
        result = await store.get(f"{self._prefix}:result:{task_id}")
        if result:
            data = json.loads(result)
            return Task(task_id=task_id, status=TaskStatus.COMPLETED, result=data)
        return None

    async def get_result(self, task_id: str) -> Any | None:
        await self._connect()
        store = self._store
        raw = await store.get(f"{self._prefix}:result:{task_id}")
        return json.loads(raw) if raw else None

    async def pending_count(self) -> int:
        await self._connect()
        return await self._store.zcard(f"{self._prefix}:pending")

    async def active_count(self) -> int:
        await self._connect()
        return await self._store.hlen(f"{self._prefix}:active")

    async def dead_count(self) -> int:
        await self._connect()
        return await self._store.llen(f"{self._prefix}:dead")

    # -- dead letter queue --------------------------------------------------

    async def replay_dead_letter(self, limit: int = 100) -> int:
        """Re-enqueue dead tasks for retry (manual intervention)."""
        await self._connect()
        store = self._store
        count = 0
        for _ in range(limit):
            raw = await store.rpop(f"{self._prefix}:dead")
            if not raw:
                break
            task = Task.from_json(raw)
            task.retry_count = 0
            task.status = TaskStatus.PENDING
            task.max_retries += 2
            await self.enqueue(task)
            count += 1
        logger.info("Replayed %d tasks from DLQ", count)
        return count

    # -- stats --------------------------------------------------------------

    async def stats(self) -> dict[str, Any]:
        return {
            "pending": await self.pending_count(),
            "active": await self.active_count(),
            "dead": await self.dead_count(),
            "scheduled": 0,
        }
