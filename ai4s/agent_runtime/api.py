"""FastAPI routes for agent_runtime — tasks, tools, memory, orchestration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ai4s.common.config import Config
from ai4s.common.logging import get_logger
from ai4s.agent_runtime.orchestration import AgentOrchestrator
from ai4s.agent_runtime.scheduler.queue import TaskPriority
from ai4s.agent_runtime.tools.registry import ToolDefinition

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# globals
# ---------------------------------------------------------------------------

_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator(Config())
    return _orchestrator


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/agent", tags=["agent-runtime"])

# ---------------------------------------------------------------------------
# request / response models
# ---------------------------------------------------------------------------


class SubmitTaskRequest(BaseModel):
    agent_type: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"           # low | normal | high | critical
    timeout_sec: int | None = None
    tags: list[str] | None = None


class RegisterAgentRequest(BaseModel):
    agent_id: str
    capabilities: list[str]
    max_capacity: int = 10
    weight: float = 1.0


class RegisterToolRequest(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    category: str = "general"
    timeout_sec: int = 300
    requires_sandbox: bool = True


class ExecuteToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecuteChainRequest(BaseModel):
    steps: list[dict[str, Any]]


class RememberRequest(BaseModel):
    content: str
    tags: list[str] | None = None
    importance: float = 0.5
    source: str = "user"
    metadata: dict[str, Any] | None = None


class RecallRequest(BaseModel):
    query: str
    top_k: int = 5
    filter_tags: list[str] | None = None
    as_context: bool = False


class SummarizeRequest(BaseModel):
    messages: list[dict[str, str]]
    tags: list[str] | None = None


# ---------------------------------------------------------------------------
# task routes
# ---------------------------------------------------------------------------


@router.post("/tasks")
async def submit_task(req: SubmitTaskRequest):
    orch = get_orchestrator()
    prio_map = {
        "low": TaskPriority.LOW,
        "normal": TaskPriority.NORMAL,
        "high": TaskPriority.HIGH,
        "critical": TaskPriority.CRITICAL,
    }
    task_id = await orch.submit_task(
        agent_type=req.agent_type,
        action=req.action,
        payload=req.payload,
        priority=prio_map.get(req.priority, TaskPriority.NORMAL),
        timeout_sec=req.timeout_sec,
        tags=req.tags,
    )
    return {"task_id": task_id, "status": "queued"}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    orch = get_orchestrator()
    result = await orch.get_task_result(task_id)
    task = await orch.task_queue.get_task(task_id)
    if task:
        return {"task_id": task_id, "status": task.status.value, "result": result}
    raise HTTPException(404, f"Task '{task_id}' not found")


@router.get("/queue/stats")
async def get_queue_stats():
    orch = get_orchestrator()
    return await orch.get_queue_stats()


# ---------------------------------------------------------------------------
# agent registration
# ---------------------------------------------------------------------------


@router.post("/agents")
async def register_agent(req: RegisterAgentRequest):
    orch = get_orchestrator()
    orch.register_agent(req.agent_id, req.capabilities, req.max_capacity, req.weight)
    return {"status": "registered", "agent_id": req.agent_id}


@router.get("/agents")
async def list_agents():
    orch = get_orchestrator()
    return orch.router.agent_summary()


@router.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    orch = get_orchestrator()
    orch.router.unregister_agent(agent_id)
    return {"status": "unregistered", "agent_id": agent_id}


# ---------------------------------------------------------------------------
# tool routes
# ---------------------------------------------------------------------------


@router.post("/tools")
async def register_tool(req: RegisterToolRequest):
    orch = get_orchestrator()
    tool = ToolDefinition(
        name=req.name,
        description=req.description,
        parameters=req.parameters,
        handler=None,
        category=req.category,
        timeout_sec=req.timeout_sec,
        requires_sandbox=req.requires_sandbox,
    )
    orch.register_tool(tool)
    return {"status": "registered", "tool": req.name}


@router.get("/tools")
async def list_tools():
    orch = get_orchestrator()
    return {"tools": orch.list_tools()}


@router.post("/tools/execute")
async def execute_tool(req: ExecuteToolRequest):
    orch = get_orchestrator()
    try:
        result = await orch.execute_tool(req.tool_name, req.arguments)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/tools/chain")
async def execute_tool_chain(req: ExecuteChainRequest):
    orch = get_orchestrator()
    try:
        results = await orch.execute_tool_chain(req.steps)
        return {"results": results}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# memory routes
# ---------------------------------------------------------------------------


@router.post("/memory")
async def remember(req: RememberRequest):
    orch = get_orchestrator()
    mem_id = await orch.remember(
        content=req.content,
        tags=req.tags,
        importance=req.importance,
        source=req.source,
        metadata=req.metadata,
    )
    return {"memory_id": mem_id, "status": "stored"}


@router.post("/memory/recall")
async def recall(req: RecallRequest):
    orch = get_orchestrator()
    result = await orch.recall(
        query=req.query,
        top_k=req.top_k,
        filter_tags=req.filter_tags,
        as_context=req.as_context,
    )
    if isinstance(result, str):
        return {"context": result}
    return {"count": len(result), "memories": result}


@router.get("/memory/stats")
async def memory_stats():
    orch = get_orchestrator()
    return await orch.get_memory_stats()


@router.post("/memory/summarize")
async def summarize_conversation(req: SummarizeRequest):
    orch = get_orchestrator()
    entry = await orch.summarize_conversation(req.messages, req.tags)
    return {"memory_id": entry.memory_id, "content": entry.content, "compression_ratio": entry.metadata.get("compression_ratio")}


@router.post("/memory/compress")
async def compress_old_memories(days: int = 30):
    orch = get_orchestrator()
    count = await orch.compress_old_memories(days)
    return {"compressed": count}


# ---------------------------------------------------------------------------
# orchestrator status
# ---------------------------------------------------------------------------


@router.get("/status")
async def orchestrator_status():
    orch = get_orchestrator()
    return await orch.status()
