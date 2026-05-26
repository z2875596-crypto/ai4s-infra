"""Connector registry — dynamic registration and lifecycle management."""

from __future__ import annotations

from typing import Any

from ai4s.common.logging import get_logger
from ai4s.data_infra.ingestion.connector import (
    DataConnector,
    LocalConnector,
    PostgresConnector,
    RESTConnector,
    S3Connector,
)
from ai4s.data_infra.ingestion.pubchem_connector import PubChemConnector

logger = get_logger(__name__)

# Built-in connector class registry
_CONNECTOR_CLASSES: dict[str, type[DataConnector]] = {
    "s3": S3Connector,
    "postgresql": PostgresConnector,
    "postgres": PostgresConnector,
    "rest": RESTConnector,
    "http": RESTConnector,
    "local": LocalConnector,
    "filesystem": LocalConnector,
    "pubchem": PubChemConnector,
}


class ConnectorRegistry:
    """Holds active connector instances, supports late registration."""

    def __init__(self) -> None:
        self._connectors: dict[str, DataConnector] = {}

    # -- register -----------------------------------------------------------

    def register(self, name: str, source_type: str, config: dict[str, Any]) -> DataConnector:
        if name in self._connectors:
            raise ValueError(f"Connector '{name}' already registered; unregister first")

        cls = _CONNECTOR_CLASSES.get(source_type)
        if cls is None:
            raise ValueError(
                f"Unsupported source type '{source_type}'. Available: {list(_CONNECTOR_CLASSES)}"
            )

        instance = cls(name=name, config=config)
        self._connectors[name] = instance
        logger.info("Connector registered: %s (type=%s)", name, source_type)
        return instance

    def unregister(self, name: str) -> DataConnector | None:
        return self._connectors.pop(name, None)

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> DataConnector | None:
        return self._connectors.get(name)

    def list_sources(self) -> list[str]:
        return list(self._connectors.keys())

    def list_by_type(self, source_type: str) -> list[DataConnector]:
        return [c for c in self._connectors.values() if type(c).__name__.lower().startswith(source_type)]

    # -- lifecycle ----------------------------------------------------------

    async def connect_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, conn in self._connectors.items():
            try:
                await conn.connect()
                results[name] = True
            except Exception as exc:
                logger.error("Failed to connect %s: %s", name, exc)
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        for name, conn in self._connectors.items():
            try:
                await conn.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting %s: %s", name, exc)

    # -- dynamic class registration -----------------------------------------

    @classmethod
    def register_connector_class(cls, source_type: str, connector_cls: type[DataConnector]) -> None:
        _CONNECTOR_CLASSES[source_type] = connector_cls
        logger.info("Connector class registered: %s → %s", source_type, connector_cls.__name__)
