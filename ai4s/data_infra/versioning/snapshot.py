"""Snapshot manager — immutable, versioned dataset snapshots with LakeFS/Delta integration."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai4s.common.exceptions import VersioningError
from ai4s.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Snapshot:
    """Immutable snapshot of a dataset at a point in time."""

    snapshot_id: str
    dataset: str
    created_at: str
    location: str                     # Storage path (s3://, /data/, lakefs://)
    row_count: int
    size_bytes: int = 0
    schema_version: str = "v1"
    checksum: str = ""                # Content hash for integrity verification
    parent_snapshot_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def short_id(self) -> str:
        return self.snapshot_id[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "dataset": self.dataset,
            "created_at": self.created_at,
            "location": self.location,
            "row_count": self.row_count,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "checksum": self.checksum,
            "parent_snapshot_id": self.parent_snapshot_id,
            "tags": self.tags,
            "metadata": self.metadata,
        }


class SnapshotManager:
    """Creates, restores, diffs, and manages dataset snapshots.

    Backends
    --------
    - filesystem : local or NFS mount
    - lakefs     : LakeFS API for Git-like branching
    - delta      : Delta Lake time-travel
    """

    def __init__(
        self,
        backend: str = "filesystem",
        root_path: str = "/data/snapshots",
        lakefs_endpoint: str | None = None,
        lakefs_repo: str | None = None,
    ) -> None:
        self.backend = backend
        self.root_path = Path(root_path)
        self._lakefs_endpoint = lakefs_endpoint
        self._lakefs_repo = lakefs_repo
        self._snapshots: dict[str, Snapshot] = {}
        self._load_index()

    # -- create -------------------------------------------------------------

    async def create_snapshot(
        self,
        dataset: str,
        source_path: str,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> Snapshot:
        """Create a new snapshot from source_path."""
        snap_id = f"{dataset}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        ts = datetime.now(timezone.utc).isoformat()

        if self.backend == "lakefs" and self._lakefs_endpoint:
            return await self._create_lakefs(snap_id, dataset, source_path, ts, tags, metadata)
        elif self.backend == "delta":
            return await self._create_delta(snap_id, dataset, source_path, ts, tags, metadata)
        else:
            return await self._create_filesystem(snap_id, dataset, source_path, ts, tags, metadata, parent_id)

    async def _create_filesystem(
        self,
        snap_id: str,
        dataset: str,
        source_path: str,
        ts: str,
        tags: dict[str, str] | None,
        metadata: dict[str, Any] | None,
        parent_id: str | None,
    ) -> Snapshot:
        snap_dir = self.root_path / snap_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        # Copy files (in prod: use hardlinks or copy-on-write)
        source = Path(source_path)
        if not source.exists():
            raise VersioningError(f"Source path does not exist: {source_path}")

        import shutil

        total_size = 0
        row_count = 0
        for f in source.rglob("*"):
            if f.is_file():
                dest = snap_dir / f.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                total_size += f.stat().st_size
                if f.suffix == ".parquet":
                    import pyarrow.parquet as pq

                    row_count += pq.read_metadata(str(f)).num_rows

        # Compute checksum
        checksum = self._dir_checksum(snap_dir)

        snap = Snapshot(
            snapshot_id=snap_id,
            dataset=dataset,
            created_at=ts,
            location=str(snap_dir),
            row_count=row_count,
            size_bytes=total_size,
            checksum=checksum,
            parent_snapshot_id=parent_id,
            tags=tags or {},
            metadata=metadata or {},
        )

        self._snapshots[snap_id] = snap
        self._save_index()
        logger.info("Snapshot created: %s (rows=%d, size=%dMB)", snap_id, row_count, total_size // 1_000_000)
        return snap

    async def _create_lakefs(
        self,
        snap_id: str,
        dataset: str,
        source_path: str,
        ts: str,
        tags: dict[str, str] | None,
        metadata: dict[str, Any] | None,
    ) -> Snapshot:
        # Stub: LakeFS API — POST /repositories/{repo}/branches → commit
        import httpx

        async with httpx.AsyncClient(base_url=self._lakefs_endpoint) as client:
            branch = snap_id
            resp = await client.post(
                f"/repositories/{self._lakefs_repo}/branches",
                json={"name": branch, "source": "main"},
            )
            if resp.status_code not in (201, 409):
                raise VersioningError(f"LakeFS branch creation failed: {resp.text}")

            # Upload files to branch (in production: use lakefs-sdk or s3 gateway)
            # Then commit
            commit_resp = await client.post(
                f"/repositories/{self._lakefs_repo}/branches/{branch}/commits",
                json={"message": f"Snapshot {snap_id} for {dataset}"},
            )
            commit_data = commit_resp.json() if commit_resp.status_code == 201 else {}

        snap = Snapshot(
            snapshot_id=snap_id,
            dataset=dataset,
            created_at=ts,
            location=f"lakefs://{self._lakefs_repo}/{branch}",
            row_count=0,
            tags=tags or {},
            metadata=metadata or {},
        )
        self._snapshots[snap_id] = snap
        return snap

    async def _create_delta(
        self, snap_id: str, dataset: str, source_path: str, ts: str, tags: dict[str, str] | None, metadata: dict[str, Any] | None
    ) -> Snapshot:
        try:
            from deltalake import DeltaTable

            dt = DeltaTable(source_path)
            version = dt.version()
            snap = Snapshot(
                snapshot_id=snap_id,
                dataset=dataset,
                created_at=ts,
                location=source_path,
                row_count=0,
                tags=tags or {},
                metadata={** (metadata or {}), "delta_version": version},
            )
            self._snapshots[snap_id] = snap
            return snap
        except ImportError:
            return await self._create_filesystem(snap_id, dataset, source_path, ts, tags, metadata, None)

    # -- restore ------------------------------------------------------------

    async def restore_snapshot(self, snapshot_id: str, target_path: str) -> Snapshot:
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            raise VersioningError(f"Snapshot not found: {snapshot_id}")

        if snap.location.startswith("lakefs://"):
            return await self._restore_lakefs(snap, target_path)

        import shutil

        target = Path(target_path)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(snap.location, str(target), dirs_exist_ok=True)
        logger.info("Snapshot %s restored to %s", snapshot_id, target_path)
        return snap

    async def _restore_lakefs(self, snap: Snapshot, target_path: str) -> Snapshot:
        # Stub: Read from LakeFS branch via S3 gateway
        logger.info("LakeFS restore: %s → %s", snap.location, target_path)
        return snap

    # -- diff ---------------------------------------------------------------

    async def diff_snapshots(self, snap_id_a: str, snap_id_b: str) -> dict[str, Any]:
        """Compare two snapshots: added/removed/changed files, row deltas."""
        snap_a = self._snapshots.get(snap_id_a)
        snap_b = self._snapshots.get(snap_id_b)
        if not snap_a or not snap_b:
            raise VersioningError("One or both snapshots not found")

        path_a = Path(snap_a.location)
        path_b = Path(snap_b.location)

        files_a = {f.relative_to(path_a).as_posix() for f in path_a.rglob("*.parquet") if f.is_file()}
        files_b = {f.relative_to(path_b).as_posix() for f in path_b.rglob("*.parquet") if f.is_file()}

        return {
            "snapshot_a": snap_id_a,
            "snapshot_b": snap_id_b,
            "rows_a": snap_a.row_count,
            "rows_b": snap_b.row_count,
            "row_delta": snap_b.row_count - snap_a.row_count,
            "size_delta_bytes": snap_b.size_bytes - snap_a.size_bytes,
            "files_added": sorted(files_b - files_a),
            "files_removed": sorted(files_a - files_b),
            "files_common": len(files_a & files_b),
        }

    # -- listing ------------------------------------------------------------

    async def list_snapshots(
        self, dataset: str | None = None, tag: str | None = None
    ) -> list[Snapshot]:
        results = list(self._snapshots.values())
        if dataset:
            results = [s for s in results if s.dataset == dataset]
        if tag:
            results = [s for s in results if tag in s.tags.values()]
        return sorted(results, key=lambda s: s.created_at, reverse=True)

    async def delete_snapshot(self, snapshot_id: str) -> None:
        snap = self._snapshots.pop(snapshot_id, None)
        if snap and snap.location.startswith("/"):
            import shutil

            path = Path(snap.location)
            if path.exists():
                shutil.rmtree(path)
        self._save_index()
        logger.info("Snapshot deleted: %s", snapshot_id)

    # -- persistence --------------------------------------------------------

    def _load_index(self) -> None:
        index_file = self.root_path / "_snapshot_index.json"
        if index_file.exists():
            try:
                with open(index_file, encoding="utf-8") as f:
                    data = json.load(f)
                self._snapshots = {k: Snapshot(**v) for k, v in data.items()}
            except Exception as exc:
                logger.warning("Failed to load snapshot index: %s", exc)

    def _save_index(self) -> None:
        self.root_path.mkdir(parents=True, exist_ok=True)
        index_file = self.root_path / "_snapshot_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)

    # -- utility ------------------------------------------------------------

    @staticmethod
    def _dir_checksum(path: Path) -> str:
        import hashlib

        hasher = hashlib.sha256()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                hasher.update(f.name.encode())
                with open(f, "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        hasher.update(chunk)
        return hasher.hexdigest()
