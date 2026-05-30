"""FastAPI router for AI4S Agent — SSE streaming research endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai4s.agent.orchestrator import AgentEvent, get_orchestrator
from ai4s.agent.memory import AgentMemory
from ai4s.common.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/agent", tags=["ai4s-agent"])

# ---------------------------------------------------------------------------
# globals (singleton pattern matching existing project style)
# ---------------------------------------------------------------------------

_memory: AgentMemory | None = None


def get_memory() -> AgentMemory:
    global _memory
    if _memory is None:
        _memory = AgentMemory()
    return _memory

# ---------------------------------------------------------------------------
# request / response models
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    query: str = Field(..., description="研究问题或任务描述", min_length=1, max_length=5000)
    session_id: str | None = Field(None, description="继续已有会话（可选）")
    max_steps: int = Field(10, ge=1, le=30, description="最大推理步数")


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.post("/run")
async def agent_run(req: AgentRunRequest):
    """Run the ReAct research agent with SSE streaming response.

    Returns a stream of Server-Sent Events, one per reasoning step.
    Each event is JSON with type, content, tool_name, and step_index fields.

    Event types:
      - thought:   LLM's reasoning before calling a tool
      - action:    Tool invocation with parameters
      - observation: Tool execution result
      - answer:    Final synthesized research report
      - error:     Error occurred during execution
      - done:      Stream complete
    """
    orchestrator = get_orchestrator()
    memory = get_memory()

    async def event_stream():
        try:
            async for event in orchestrator.run(
                query=req.query,
                session_id=req.session_id,
                max_steps=req.max_steps,
            ):
                data = json.dumps({
                    "type": event.type,
                    "content": event.content,
                    "tool_name": event.tool_name,
                    "step_index": event.step_index,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as e:
            logger.exception("Agent run failed")
            error_data = json.dumps({
                "type": "error",
                "content": f"Agent 执行异常: {e}",
                "tool_name": None,
                "step_index": 0,
            }, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
        finally:
            yield "data: {\"type\":\"done\",\"content\":\"\",\"tool_name\":null,\"step_index\":0}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def list_sessions(limit: int = Query(20, ge=1, le=100)):
    """List recent research sessions."""
    memory = get_memory()
    sessions = memory.list_sessions(limit=limit)
    return {
        "count": len(sessions),
        "sessions": [memory.session_to_dict(s) for s in sessions],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session with all reasoning steps."""
    memory = get_memory()
    session = memory.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return memory.session_to_dict(session)


@router.delete("/sessions")
async def delete_all_sessions():
    """Delete all research sessions."""
    memory = get_memory()
    count = memory.delete_all_sessions()
    return {"status": "ok", "deleted_count": count}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a single research session."""
    memory = get_memory()
    deleted = memory.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return {"status": "ok", "deleted": True}
