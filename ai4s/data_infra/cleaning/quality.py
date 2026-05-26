"""Data quality checker — statistical validation and drift detection."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from ai4s.common.logging import get_logger
from ai4s.common.metrics import MetricsRegistry
from ai4s.data_infra.ingestion.connector import SourceRecord

logger = get_logger(__name__)


@dataclass
class QualityReport:
    batch_id: str
    row_count: int
    null_ratios: dict[str, float] = field(default_factory=dict)
    duplicate_count: int = 0
    duplicate_ratio: float = 0.0
    column_cardinality: dict[str, int] = field(default_factory=dict)
    outlier_count: dict[str, int] = field(default_factory=dict)
    schema_drift: list[str] = field(default_factory=list)
    distribution_drift: dict[str, float] = field(default_factory=dict)
    custom_checks: dict[str, bool] = field(default_factory=dict)
    passed: bool = True
    score: float = 1.0                     # 0.0 - 1.0


# ---------------------------------------------------------------------------
# QualityChecker
# ---------------------------------------------------------------------------


class QualityChecker:
    """Batch-level and cross-batch data quality assessment.

    Checks performed:
      - null ratio per column
      - duplicate row detection
      - schema drift vs baseline
      - numeric outlier detection (Z-score)
      - custom user-defined checks
    """

    def __init__(
        self,
        max_null_ratio: float = 0.10,
        max_duplicate_ratio: float = 0.05,
        outlier_std_threshold: float = 3.0,
        quality_threshold: float = 0.95,
        baseline_schema: dict[str, str] | None = None,
    ) -> None:
        self.max_null_ratio = max_null_ratio
        self.max_duplicate_ratio = max_duplicate_ratio
        self.outlier_std_threshold = outlier_std_threshold
        self.quality_threshold = quality_threshold
        self._baseline_schema = baseline_schema or {}
        self._custom_checks: list[tuple[str, callable]] = []

    def add_check(self, name: str, check_fn: callable) -> None:
        """Register a custom check: check_fn(batch: SourceRecord) -> bool."""
        self._custom_checks.append((name, check_fn))

    # ------------------------------------------------------------------

    async def check_batch(self, batch: SourceRecord) -> QualityReport:
        n = batch.row_count
        if n == 0:
            return QualityReport(batch_id=batch.batch_id, row_count=0, passed=False)

        table = batch.to_arrow()
        report = QualityReport(batch_id=batch.batch_id, row_count=n)

        # 1. null ratios
        report.null_ratios = self._compute_null_ratios(table, n)

        # 2. duplicates
        report.duplicate_count = self._count_duplicates(table)
        report.duplicate_ratio = report.duplicate_count / n

        # 3. schema drift
        report.schema_drift = self._detect_schema_drift(table)

        # 4. outliers
        report.outlier_count = self._detect_outliers(table)

        # 5. column cardinality
        report.column_cardinality = self._compute_cardinality(table)

        # 6. custom checks
        for name, check_fn in self._custom_checks:
            try:
                report.custom_checks[name] = check_fn(batch)
            except Exception as exc:
                logger.warning("Custom check '%s' failed: %s", name, exc)
                report.custom_checks[name] = False

        # 7. compute score & pass/fail
        report.score = self._compute_score(report)
        report.passed = report.score >= self.quality_threshold

        if not report.passed:
            logger.warning(
                "Quality FAIL batch=%s score=%.2f nulls=%s dups=%d drift=%s",
                batch.batch_id, report.score, report.null_ratios,
                report.duplicate_count, report.schema_drift,
            )
            MetricsRegistry.data_cleaning_issues.labels(severity="warn").inc()

        return report

    # -- individual checks --------------------------------------------------

    @staticmethod
    def _compute_null_ratios(table: pa.Table, n: int) -> dict[str, float]:
        ratios: dict[str, float] = {}
        for col_name in table.schema.names:
            col = table.column(col_name)
            ratios[col_name] = col.null_count / n
        return ratios

    @staticmethod
    def _count_duplicates(table: pa.Table) -> int:
        """Count rows that appear more than once."""
        if table.num_rows <= 1:
            return 0
        seen: set[str] = set()
        dupes = 0
        col_names = table.schema.names
        for i in range(table.num_rows):
            row_key = hashlib.md5(
                "|".join(str(table.column(c)[i].as_py()) for c in col_names).encode()
            ).hexdigest()
            if row_key in seen:
                dupes += 1
            else:
                seen.add(row_key)
        return dupes

    def _detect_schema_drift(self, table: pa.Table) -> list[str]:
        drift: list[str] = []
        current = {f.name: str(f.type) for f in table.schema}
        for col, exp_type in self._baseline_schema.items():
            if col not in current:
                drift.append(f"missing_column:{col}")
            elif current[col] != exp_type:
                drift.append(f"type_changed:{col}({exp_type}→{current[col]})")
        for col in current:
            if col not in self._baseline_schema:
                drift.append(f"new_column:{col}")
        return drift

    def _detect_outliers(self, table: pa.Table) -> dict[str, int]:
        outliers: dict[str, int] = {}
        for col_name in table.schema.names:
            col = table.column(col_name)
            if not pa.types.is_floating(col.type) and not pa.types.is_integer(col.type):
                continue
            arr = col.drop_null()
            if len(arr) < 10:
                continue
            mean = pc.mean(arr).as_py()
            std = pc.stddev(arr).as_py()
            if std == 0:
                continue
            threshold = self.outlier_std_threshold * std
            count = pc.sum(pc.greater(pc.abs(pc.subtract(arr, mean)), pa.scalar(threshold))).as_py()
            if count:
                outliers[col_name] = count
        return outliers

    @staticmethod
    def _compute_cardinality(table: pa.Table) -> dict[str, int]:
        card: dict[str, int] = {}
        for col_name in table.schema.names:
            unique = pc.unique(table.column(col_name))
            card[col_name] = len(unique)
        return card

    def _compute_score(self, report: QualityReport) -> float:
        """Weighted quality score 0.0 – 1.0."""
        scores: list[float] = []

        # null penalty
        if report.null_ratios:
            max_null = max(report.null_ratios.values())
            scores.append(1.0 - min(max_null / self.max_null_ratio, 1.0) * 0.4)

        # duplicate penalty
        scores.append(1.0 - min(report.duplicate_ratio / self.max_duplicate_ratio, 1.0) * 0.3)

        # schema drift penalty
        drift_penalty = min(len(report.schema_drift) * 0.05, 0.3)
        scores.append(1.0 - drift_penalty)

        return max(sum(scores) / len(scores), 0.0)


# ---------------------------------------------------------------------------
# cross-batch checks
# ---------------------------------------------------------------------------


class DistributionMonitor:
    """Tracks column distributions across batches to detect drift."""

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._history: dict[str, list[dict[str, float]]] = {}

    def update(self, report: QualityReport) -> dict[str, float]:
        drifts: dict[str, float] = {}
        prev = self._history.setdefault(report.batch_id, [])
        prev.append(report.null_ratios)
        if len(prev) > self.window_size:
            prev.pop(0)
        if len(prev) >= 10:
            for col in report.null_ratios:
                recent = [h.get(col, 0) for h in prev[-10:]]
                avg = sum(recent) / len(recent)
                current = report.null_ratios.get(col, 0)
                drift_pct = abs(current - avg) / max(avg, 0.001)
                if drift_pct > 0.5:
                    drifts[col] = drift_pct
        return drifts
