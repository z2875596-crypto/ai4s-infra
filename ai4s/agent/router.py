"""FastAPI router for AI4S Agent — SSE streaming research endpoint."""

from __future__ import annotations

import json
import re
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from docx import Document
from docx.shared import Pt, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

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
    follow_up: bool = Field(False, description="是否为追问模式（携带历史结论作为上下文）")


class ExportDocxRequest(BaseModel):
    content: str = Field(..., description="研究报告 Markdown 文本")
    topic: str | None = Field(None, description="研究课题")


# ---------------------------------------------------------------------------
# docx helpers
# ---------------------------------------------------------------------------


def _set_run_font(run, size_pt, bold=False):
    """Set both Latin and East-Asian fonts on a run."""
    run.font.size = Pt(size_pt)
    run.font.name = "Times New Roman"
    run.bold = bold
    r = run._r
    rPr = r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), "宋体")


def _clean_inline(text: str) -> str:
    """Strip inline Markdown formatting for plain-text docx output."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text.strip()


def _apply_cell_border(cell, edges: dict):
    """Apply border dict to a single cell.  edges = {"top": {...}, "bottom": {...}}"""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    existing = tcPr.find(qn("w:tcBorders"))
    if existing is not None:
        tcPr.remove(existing)
    for edge, attrs in edges.items():
        el = OxmlElement(f"w:{edge}")
        for k, v in attrs.items():
            el.set(qn(f"w:{k}"), str(v))
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _add_three_line_table(doc, headers: list[str], rows: list[list[str]]):
    """Add a three-line table (top, header-bottom, table-bottom borders only)."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(h.strip())
        _set_run_font(run, 10.5, bold=True)

    # Data rows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            run = cell.paragraphs[0].add_run(val.strip())
            _set_run_font(run, 10.5)

    # ---- Three-line borders ----
    sz = 8  # half-points
    for cell in table.rows[0].cells:
        _apply_cell_border(cell, {"top": {"val": "single", "sz": str(sz), "space": "0", "color": "000000"}})
    for cell in table.rows[0].cells:
        _apply_cell_border(cell, {"bottom": {"val": "single", "sz": "6", "space": "0", "color": "000000"}})
    for cell in table.rows[-1].cells:
        _apply_cell_border(cell, {"bottom": {"val": "single", "sz": str(sz), "space": "0", "color": "000000"}})

    return table


def _build_docx(content: str, topic: str) -> Document:
    """Parse Markdown and build a python-docx Document."""
    doc = Document()

    # Set default paragraph font for the whole document
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.18)

    # Topic title
    if topic:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(topic)
        _set_run_font(run, 16, bold=True)

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Separator
        if line.strip() == "---":
            i += 1
            continue

        # Headings
        hm = re.match(r"^(#{1,3})\s+(.+)$", line)
        if hm:
            level = len(hm.group(1))
            text = _clean_inline(hm.group(2))
            size_map = {1: 14, 2: 13, 3: 12}
            _add_paragraph(doc, text, size_map[level], bold=True)
            i += 1
            continue

        # Table: line starts with | and next line is a separator
        if (
            line.strip().startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1])
        ):
            headers = [c.strip() for c in line.strip().split("|")[1:-1]]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [_clean_inline(c) for c in lines[i].strip().split("|")[1:-1]]
                if row:
                    rows.append(row)
                i += 1
            if headers:
                _add_three_line_table(doc, headers, rows)
            continue

        # Regular paragraph
        clean = _clean_inline(line.strip())
        if clean:
            _add_paragraph(doc, clean, 11)
        i += 1

    return doc


def _add_paragraph(doc, text, size_pt, bold=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    _set_run_font(run, size_pt, bold)
    return p


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.post("/export-docx")
async def export_docx(req: ExportDocxRequest):
    """Generate a .docx file from the research report Markdown."""
    try:
        doc = _build_docx(req.content, req.topic or "")
        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        topic_clean = re.sub(r'[/\\?%*:|"<>]', "", (req.topic or "report")[:10])
        filename = f"鸢见研究报告_{topic_clean}.docx"
        encoded = quote(filename)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
                follow_up=req.follow_up,
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
