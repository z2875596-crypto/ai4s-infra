"""Data source connectors — S3, PostgreSQL, REST API, local filesystem.

Production connectors with connection pooling, retry with backoff,
streaming reads, and schema inference.
"""

from __future__ import annotations

import io
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import pyarrow as pa
import pyarrow.parquet as pq

from ai4s.common.config import Config
from ai4s.common.exceptions import IngestionError
from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------


@dataclass
class SourceRecord:
    source: str
    table: str
    batch_id: str
    rows: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    ingested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_arrow(self) -> pa.Table:
        return pa.Table.from_pylist(self.rows)

    @classmethod
    def from_arrow(cls, source: str, table: str, batch_id: str, table_arrow: pa.Table) -> SourceRecord:
        return cls(
            source=source,
            table=table,
            batch_id=batch_id,
            rows=table_arrow.to_pylist(),
        )


# ---------------------------------------------------------------------------
# abstract connector
# ---------------------------------------------------------------------------


class DataConnector(ABC):
    """Abstract connector with retry, metrics, and health-check."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self._connected = False
        self._metrics = MetricsRegistry

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def read_batches(self, table: str, batch_size: int = 10000) -> AsyncIterator[SourceRecord]: ...

    @abstractmethod
    async def schema(self, table: str) -> dict[str, str]: ...

    async def health_check(self) -> bool:
        try:
            await self.connect()
            return True
        except Exception:
            return False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()


# ---------------------------------------------------------------------------
# S3 connector
# ---------------------------------------------------------------------------


class S3Connector(DataConnector):
    """Reads Parquet / JSON / CSV from S3-compatible storage.

    Config keys
    -----------
    bucket : str
    region : str (default us-east-1)
    endpoint_url : str | None — for MinIO / Ceph
    prefix  : str | None — key prefix filter
    format  : str — "parquet" | "json" | "csv"
    access_key : str | None
    secret_key : str | None
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._client: Any = None
        self._bucket = config["bucket"]
        self._prefix = config.get("prefix", "")
        self._fmt = config.get("format", "parquet")

    async def connect(self) -> None:
        if self._connected:
            return
        import boto3
        from botocore.config import Config as BotoConfig

        kwargs: dict[str, Any] = dict(
            region_name=self.config.get("region", "us-east-1"),
            config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
        )
        if ep := self.config.get("endpoint_url"):
            kwargs["endpoint_url"] = ep
        if ak := self.config.get("access_key"):
            kwargs["aws_access_key_id"] = ak
        if sk := self.config.get("secret_key"):
            kwargs["aws_secret_access_key"] = sk

        self._client = boto3.client("s3", **kwargs)
        self._connected = True
        logger.info("S3 connector [%s] connected bucket=%s", self.name, self._bucket)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._connected = False

    async def read_batches(self, table: str, batch_size: int = 10000) -> AsyncIterator[SourceRecord]:
        if not self._connected:
            raise IngestionError("S3 connector not connected")

        key_prefix = f"{self._prefix}/{table}" if self._prefix else table
        key_prefix = key_prefix.lstrip("/")
        paginator = self._client.get_paginator("list_objects_v2")
        batch_idx = 0

        for page in paginator.paginate(Bucket=self._bucket, Prefix=key_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if self._fmt == "parquet" and not key.endswith(".parquet"):
                    continue
                if self._fmt == "json" and not key.endswith((".json", ".jsonl")):
                    continue
                if self._fmt == "csv" and not key.endswith(".csv"):
                    continue

                logger.debug("Reading s3://%s/%s", self._bucket, key)
                try:
                    resp = self._client.get_object(Bucket=self._bucket, Key=key)
                    body = resp["Body"].read()

                    if self._fmt == "parquet":
                        table_arrow = pq.read_table(io.BytesIO(body))
                    elif self._fmt == "json":
                        table_arrow = self._read_json(body)
                    elif self._fmt == "csv":
                        table_arrow = self._read_csv(body)
                    else:
                        raise IngestionError(f"Unsupported format: {self._fmt}")

                    for arrow_batch in table_arrow.to_batches(max_chunksize=batch_size):
                        batch_idx += 1
                        bid = f"{self.name}/{table}/{batch_idx:06d}"
                        yield SourceRecord.from_arrow(self.name, table, bid, arrow_batch)
                except Exception as exc:
                    self._metrics.data_ingested_rows.labels(source=self.name, status="failed").inc()
                    logger.error("Failed to read s3://%s/%s: %s", self._bucket, key, exc)
                    raise IngestionError(f"S3 read failed: {key}") from exc

    async def schema(self, table: str) -> dict[str, str]:
        # Read first matching parquet file and infer schema
        key_prefix = f"{self._prefix}/{table}" if self._prefix else table
        key_prefix = key_prefix.lstrip("/")
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=key_prefix, MaxKeys=1):
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith(".parquet"):
                    continue
                resp = self._client.get_object(Bucket=self._bucket, Key=obj["Key"])
                schema_pa = pq.read_schema(io.BytesIO(resp["Body"].read()))
                return {f.name: str(f.type) for f in schema_pa}
        return {}

    def _read_json(self, body: bytes) -> pa.Table:
        lines = body.decode("utf-8").strip().split("\n")
        rows = [json.loads(line) for line in lines if line]
        return pa.Table.from_pylist(rows)

    def _read_csv(self, body: bytes) -> pa.Table:
        import pyarrow.csv as pcsv
        return pcsv.read_csv(io.BytesIO(body))


# ---------------------------------------------------------------------------
# PostgreSQL connector
# ---------------------------------------------------------------------------


class PostgresConnector(DataConnector):
    """PostgreSQL connector using asyncpg with connection pooling.

    Config keys
    -----------
    host : str
    port : int (default 5432)
    user : str
    password : str
    database : str
    pool_min : int (default 2)
    pool_max : int (default 10)
    ssl : bool (default False)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._pool: Any = None

    async def connect(self) -> None:
        if self._connected:
            return
        import asyncpg

        self._pool = await asyncpg.create_pool(
            host=self.config["host"],
            port=self.config.get("port", 5432),
            user=self.config["user"],
            password=self.config["password"],
            database=self.config["database"],
            min_size=self.config.get("pool_min", 2),
            max_size=self.config.get("pool_max", 10),
            ssl=self.config.get("ssl", False),
        )
        self._connected = True
        logger.info("Postgres connector [%s] connected host=%s db=%s",
                     self.name, self.config["host"], self.config["database"])

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._connected = False

    async def read_batches(self, table: str, batch_size: int = 10000) -> AsyncIterator[SourceRecord]:
        if not self._connected:
            raise IngestionError("Postgres connector not connected")

        columns_sql = await self.schema(table)
        columns = list(columns_sql.keys())
        col_str = ", ".join(f'"{c}"' for c in columns) if columns else "*"

        batch_idx = 0
        offset = 0

        async with self._pool.acquire() as conn:
            while True:
                rows = await conn.fetch(
                    f'SELECT {col_str} FROM "{table}" LIMIT $1 OFFSET $2',
                    batch_size, offset,
                )
                if not rows:
                    break

                batch_idx += 1
                bid = f"{self.name}/{table}/{batch_idx:06d}"
                yield SourceRecord(
                    source=self.name,
                    table=table,
                    batch_id=bid,
                    rows=[dict(r) for r in rows],
                )
                offset += len(rows)

    async def schema(self, table: str) -> dict[str, str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_name = $1
                   ORDER BY ordinal_position""",
                table,
            )
            return {r["column_name"]: r["data_type"] for r in rows}


# ---------------------------------------------------------------------------
# REST API connector
# ---------------------------------------------------------------------------


class RESTConnector(DataConnector):
    """Generic REST API connector with pagination.

    Config keys
    -----------
    base_url : str
    endpoint : str
    method : str (default GET)
    headers : dict
    auth_type : str — "bearer" | "basic" | "apikey"
    auth_token : str | None
    pagination_type : str — "offset" | "cursor" | "page"
    page_size_param : str (default "limit")
    page_size : int (default 1000)
    max_pages : int (default 100)
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._client: Any = None
        self._base_url = config["base_url"].rstrip("/")
        self._endpoint = config.get("endpoint", "")
        self._method = config.get("method", "GET")

    async def connect(self) -> None:
        if self._connected:
            return
        import httpx

        headers = self.config.get("headers", {})
        auth = self.config.get("auth_type", "")
        token = self.config.get("auth_token", "")
        if auth == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth == "basic" and token:
            import base64
            headers["Authorization"] = f"Basic {base64.b64encode(token.encode()).decode()}"
        elif auth == "apikey" and token:
            header_name = self.config.get("apikey_header", "X-API-Key")
            headers[header_name] = token

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self.config.get("timeout", 60),
        )
        self._connected = True
        logger.info("REST connector [%s] connected to %s", self.name, self._base_url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._connected = False

    async def read_batches(self, table: str, batch_size: int = 10000) -> AsyncIterator[SourceRecord]:
        if not self._connected:
            raise IngestionError("REST connector not connected")

        pagination = self.config.get("pagination_type", "offset")
        page_size_param = self.config.get("page_size_param", "limit")
        page_size = self.config.get("page_size", 1000)
        max_pages = self.config.get("max_pages", 100)

        endpoint = f"{self._endpoint}/{table}" if self._endpoint else table
        batch_idx = 0
        cursor: str | None = None
        page_num = 0

        while page_num < max_pages:
            params: dict[str, Any] = {page_size_param: page_size}
            if pagination == "offset":
                params["offset"] = page_num * page_size
            elif pagination == "page":
                params["page"] = page_num + 1
            elif pagination == "cursor" and cursor:
                params["cursor"] = cursor

            resp = await self._client.request(self._method, endpoint, params=params)
            if resp.status_code != 200:
                raise IngestionError(
                    f"REST API error: {resp.status_code} from {endpoint}"
                )

            data = resp.json()
            items = data if isinstance(data, list) else data.get("data", data.get("results", []))
            if not items:
                break

            batch_idx += 1
            bid = f"{self.name}/{table}/{batch_idx:06d}"
            yield SourceRecord(
                source=self.name,
                table=table,
                batch_id=bid,
                rows=items if isinstance(items, list) else [items],
            )

            if pagination == "cursor":
                cursor = data.get("next_cursor") or data.get("pagination", {}).get("next")
                if not cursor:
                    break
            elif len(items) < page_size:
                break

            page_num += 1

    async def schema(self, table: str) -> dict[str, str]:
        return {}


# ---------------------------------------------------------------------------
# Local filesystem connector (for testing / small datasets)
# ---------------------------------------------------------------------------


class LocalConnector(DataConnector):
    """Local filesystem connector for Parquet/JSON/CSV files."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._root = Path(config["root_path"])

    async def connect(self) -> None:
        if not self._root.exists():
            raise IngestionError(f"Path does not exist: {self._root}")
        self._connected = True
        logger.info("Local connector [%s] connected root=%s", self.name, self._root)

    async def disconnect(self) -> None:
        self._connected = False

    async def read_batches(self, table: str, batch_size: int = 10000) -> AsyncIterator[SourceRecord]:
        table_dir = self._root / table
        if not table_dir.exists():
            raise IngestionError(f"Table directory not found: {table_dir}")

        parquet_files = sorted(table_dir.glob("*.parquet"))
        json_files = sorted(table_dir.glob("*.json")) + sorted(table_dir.glob("*.jsonl"))
        csv_files = sorted(table_dir.glob("*.csv"))

        batch_idx = 0
        for file_path in parquet_files + json_files + csv_files:
            try:
                if file_path.suffix == ".parquet":
                    table_arrow = pq.read_table(str(file_path))
                elif file_path.suffix in (".json", ".jsonl"):
                    with open(file_path, encoding="utf-8") as f:
                        rows = [json.loads(line) for line in f if line.strip()]
                    table_arrow = pa.Table.from_pylist(rows)
                else:
                    import pyarrow.csv as pcsv
                    table_arrow = pcsv.read_csv(str(file_path))

                for arrow_batch in table_arrow.to_batches(max_chunksize=batch_size):
                    batch_idx += 1
                    bid = f"{self.name}/{table}/{batch_idx:06d}"
                    yield SourceRecord.from_arrow(self.name, table, bid, arrow_batch)
            except Exception as exc:
                self._metrics.data_ingested_rows.labels(source=self.name, status="failed").inc()
                raise IngestionError(f"Failed to read {file_path}: {exc}") from exc

    async def schema(self, table: str) -> dict[str, str]:
        table_dir = self._root / table
        parquet_files = sorted(table_dir.glob("*.parquet"))
        if parquet_files:
            schema_pa = pq.read_schema(str(parquet_files[0]))
            return {f.name: str(f.type) for f in schema_pa}
        return {}
