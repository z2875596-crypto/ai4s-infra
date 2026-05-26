"""Lineage tracker — DAG-based data provenance from ingestion to consumption.

Tracks the full lifecycle of each dataset:
  source → ingest → clean → transform → snapshot → consume → model

Supports both in-memory tracking (for pipeline runs) and persistent
storage (SQLite / Postgres for production).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


class LineageStepType(str, Enum):
    INGEST = "ingest"
    CLEAN = "clean"
    TRANSFORM = "transform"
    VALIDATE = "validate"
    SNAPSHOT = "snapshot"
    CONSUME = "consume"
    TRAIN = "train"
    EVALUATE = "evaluate"
    EXPORT = "export"


@dataclass
class LineageEdge:
    edge_id: str
    source_id: str
    target_id: str
    step_type: LineageStepType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None


class LineageTracker:
    """Directed acyclic graph tracker for data provenance.

    Usage::

        tracker = LineageTracker(persist_path="/data/lineage.db")
        tracker.record("s3://raw/logs", "s3://clean/logs", LineageStepType.CLEAN,
                        metadata={"rows": 1_000_000})

        # Query
        upstream = tracker.upstream_of("s3://clean/logs")
        full_graph = tracker.export_graph()
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._edges: list[LineageEdge] = []
        self._persist_path = persist_path
        if persist_path and Path(persist_path).suffix == ".db":
            self._init_db()

    # -- record -------------------------------------------------------------

    def record(
        self,
        source_id: str,
        target_id: str,
        step_type: LineageStepType,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LineageEdge:
        import uuid

        edge = LineageEdge(
            edge_id=uuid.uuid4().hex[:12],
            source_id=source_id,
            target_id=target_id,
            step_type=step_type,
            metadata=metadata or {},
            run_id=run_id,
        )
        self._edges.append(edge)
        self._persist_edge(edge)
        return edge

    # -- query --------------------------------------------------------------

    def upstream_of(self, dataset_id: str, depth: int | None = None) -> list[LineageEdge]:
        """Return all edges that directly or transitively produced this dataset."""
        results: list[LineageEdge] = []
        visited: set[str] = set()
        queue = [dataset_id]

        for current_depth in range(depth or 1000):
            if not queue:
                break
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            parents = [e for e in self._edges if e.target_id == current]
            results.extend(parents)
            queue.extend(e.source_id for e in parents)

        return results

    def downstream_of(self, dataset_id: str, depth: int | None = None) -> list[LineageEdge]:
        """Return all edges consuming this dataset (directly and transitively)."""
        results: list[LineageEdge] = []
        visited: set[str] = set()
        queue = [dataset_id]

        for current_depth in range(depth or 1000):
            if not queue:
                break
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            children = [e for e in self._edges if e.source_id == current]
            results.extend(children)
            queue.extend(e.target_id for e in children)

        return results

    def full_lineage(self, dataset_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "dataset_id": dataset_id,
            "upstream": [self._edge_to_dict(e) for e in self.upstream_of(dataset_id)],
            "downstream": [self._edge_to_dict(e) for e in self.downstream_of(dataset_id)],
        }

    def by_run(self, run_id: str) -> list[LineageEdge]:
        return [e for e in self._edges if e.run_id == run_id]

    def by_type(self, step_type: LineageStepType) -> list[LineageEdge]:
        return [e for e in self._edges if e.step_type == step_type]

    # -- export -------------------------------------------------------------

    def export_graph(self) -> dict[str, Any]:
        nodes: dict[str, set[str]] = {}  # node_id → {labels}
        all_edges: list[dict[str, Any]] = []

        for e in self._edges:
            nodes.setdefault(e.source_id, set()).add("source")
            nodes.setdefault(e.target_id, set()).add("target")
            all_edges.append({
                "from": e.source_id,
                "to": e.target_id,
                "type": e.step_type.value,
                "timestamp": e.timestamp,
                "metadata": e.metadata,
            })

        return {
            "nodes": [{"id": nid, "labels": list(labels)} for nid, labels in nodes.items()],
            "edges": all_edges,
        }

    def to_mermaid(self) -> str:
        """Export as Mermaid flowchart for visualization."""
        lines = ["graph LR"]
        id_map: dict[str, str] = {}
        for i, e in enumerate(self._edges):
            if e.source_id not in id_map:
                id_map[e.source_id] = f"N{i}"
            if e.target_id not in id_map:
                id_map[e.target_id] = f"N{i + len(self._edges)}"

        for e in self._edges:
            src = id_map[e.source_id]
            tgt = id_map[e.target_id]
            label = e.step_type.value
            lines.append(f'    {src}["{e.source_id.split("/")[-1][:20]}"] -->|{label}| {tgt}["{e.target_id.split("/")[-1][:20]}"]')

        return "\n".join(lines)

    # -- persistence --------------------------------------------------------

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._persist_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lineage_edges (
                edge_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                step_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                run_id TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON lineage_edges(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON lineage_edges(target_id)")
        conn.commit()
        conn.close()

    def _persist_edge(self, edge: LineageEdge) -> None:
        if not self._persist_path:
            return
        try:
            conn = sqlite3.connect(self._persist_path)
            conn.execute(
                "INSERT INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    edge.edge_id, edge.source_id, edge.target_id,
                    edge.step_type.value, edge.timestamp,
                    json.dumps(edge.metadata), edge.run_id,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to persist lineage edge: %s", exc)

    @staticmethod
    def _edge_to_dict(e: LineageEdge) -> dict[str, Any]:
        return {
            "edge_id": e.edge_id,
            "source": e.source_id,
            "target": e.target_id,
            "type": e.step_type.value,
            "timestamp": e.timestamp,
            "metadata": e.metadata,
        }
