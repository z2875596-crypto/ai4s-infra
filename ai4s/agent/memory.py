"""SQLite-backed session memory for agent reasoning chains.

Stores each research session and every ReAct step (Thought / Action / Observation / Answer)
so the full reasoning trace can be replayed later.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_PATH = _DB_DIR / "agent_sessions.db"

StepType = Literal["thought", "action", "observation", "answer"]


@dataclass
class Step:
    step_type: StepType
    content: str
    tool_name: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    title: str
    query: str
    steps: list[Step] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class AgentMemory:
    """SQLite-backed persistent store for agent sessions and reasoning steps."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                query TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_type TEXT NOT NULL CHECK(step_type IN ('thought','action','observation','answer')),
                content TEXT NOT NULL,
                tool_name TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session_id, created_at);
        """)
        self.conn.commit()

    # ── session CRUD ──────────────────────────────────────────────

    def create_session(self, session_id: str, title: str, query: str) -> Session:
        self._ensure_tables()
        now = time.time()
        self.conn.execute(
            "INSERT INTO sessions (session_id, title, query, created_at, updated_at) VALUES (?,?,?,?,?)",
            (session_id, title, query, now, now),
        )
        self.conn.commit()
        return Session(session_id=session_id, title=title, query=query, created_at=now, updated_at=now)

    def get_session(self, session_id: str) -> Session | None:
        self._ensure_tables()
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        steps = self._load_steps(session_id)
        return Session(
            session_id=row["session_id"],
            title=row["title"],
            query=row["query"],
            steps=steps,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_sessions(self, limit: int = 20) -> list[Session]:
        self._ensure_tables()
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result: list[Session] = []
        for row in rows:
            steps = self._load_steps(row["session_id"])
            result.append(Session(
                session_id=row["session_id"],
                title=row["title"],
                query=row["query"],
                steps=steps,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))
        return result

    # ── steps ─────────────────────────────────────────────────────

    def append_step(self, session_id: str, step_type: StepType, content: str,
                    tool_name: str | None = None) -> None:
        self._ensure_tables()
        self.conn.execute(
            "INSERT INTO steps (session_id, step_type, content, tool_name, created_at) VALUES (?,?,?,?,?)",
            (session_id, step_type, content, tool_name, time.time()),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (time.time(), session_id),
        )
        self.conn.commit()

    def _load_steps(self, session_id: str) -> list[Step]:
        rows = self.conn.execute(
            "SELECT * FROM steps WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [
            Step(
                step_type=row["step_type"],
                content=row["content"],
                tool_name=row["tool_name"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ── delete ────────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> bool:
        """Delete a single session and its steps. Returns True if deleted."""
        self._ensure_tables()
        self.conn.execute("DELETE FROM steps WHERE session_id = ?", (session_id,))
        cursor = self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_all_sessions(self) -> int:
        """Delete all sessions and steps. Returns number of deleted sessions."""
        self._ensure_tables()
        self.conn.execute("DELETE FROM steps")
        cursor = self.conn.execute("DELETE FROM sessions")
        self.conn.commit()
        return cursor.rowcount

    # ── serialisation for API ─────────────────────────────────────

    def session_to_dict(self, session: Session) -> dict:
        return {
            "session_id": session.session_id,
            "title": session.title,
            "query": session.query,
            "steps": [
                {
                    "step_type": s.step_type,
                    "content": s.content,
                    "tool_name": s.tool_name,
                    "created_at": s.created_at,
                }
                for s in session.steps
            ],
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
