"""PDF literature extraction — find SMILES, InChI, and tabular data in PDFs.

Uses ``pypdf`` when available; raises a clear error if it's missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# optional pypdf import
# ---------------------------------------------------------------------------

try:
    from pypdf import PdfReader

    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False
    PdfReader = None  # type: ignore

# ---------------------------------------------------------------------------
# regex patterns
# ---------------------------------------------------------------------------

_SMILES_RE = re.compile(
    r"(?:^|\s|[\(\[])([A-Za-z0-9@+\-\[\]\(\)\\\/=#$:.%]{5,})(?=\s|$|[\)\].,;])"
)

_INCHI_RE = re.compile(
    r"\b(InChI=1S?/[A-Za-z0-9]+(?:/[a-zA-Z0-9+\-;\(\)\[\],\.]+)+)\b"
)

_SMILES_FILTER = re.compile(r"[0-9]")  # must contain at least one digit (ring/bond)


def _likely_smiles(candidate: str) -> bool:
    """Quick heuristic: a SMILES-like string has letters, digits/brackets, and
    balanced parentheses. Rejects pure numbers and InChI strings."""
    c = candidate.strip().strip("()[].,;:-")
    if len(c) < 4:
        return False
    # Must contain at least one letter (organic atom symbol)
    if not re.search(r"[A-Za-z]", c):
        return False
    # Reject InChI strings mis-detected as SMILES
    if c.startswith("InChI="):
        return False
    if not _SMILES_FILTER.search(c) and "[" not in c:
        return False
    if c.count("(") != c.count(")"):
        return False
    return True


# ---------------------------------------------------------------------------
# data types
# ---------------------------------------------------------------------------


@dataclass
class ExtractedStructure:
    """A molecular structure found in a PDF page."""

    smiles: str | None = None
    inchi: str | None = None
    page: int = 0
    context: str = ""  # surrounding text snippet


@dataclass
class ExtractedTable:
    """Tabular data extracted from a PDF page."""

    page: int = 0
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str = ""


@dataclass
class PdfExtractionResult:
    """Full result of PDF extraction."""

    filename: str = ""
    structures: list[ExtractedStructure] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    full_text: str = ""


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def extract_from_pdf(file_path: str | Path) -> PdfExtractionResult:
    """Extract molecular structures and tables from a PDF file.

    Returns a :class:`PdfExtractionResult` with SMILES, InChI, and tabular data.
    Requires ``pypdf`` to be installed.
    """
    if not _HAS_PYPDF:
        raise ImportError(
            "pypdf is required for PDF extraction. Install with: pip install pypdf"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    reader = PdfReader(str(path))
    result = PdfExtractionResult(filename=path.name)
    all_text_parts: list[str] = []

    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        all_text_parts.append(text)

        # Extract structures (SMILES / InChI)
        structures = _extract_structures(text, page_num)
        result.structures.extend(structures)

        # Extract tables
        tables = _extract_tables(text, page_num)
        result.tables.extend(tables)

    result.full_text = "\n\n".join(all_text_parts)
    logger.info(
        "Extracted %d structures and %d tables from %s",
        len(result.structures),
        len(result.tables),
        path.name,
    )
    return result


def pdf_to_source_record(
    file_path: str | Path, source_name: str = "pdf"
) -> "SourceRecord":
    """Extract PDF content and wrap it as a :class:`SourceRecord` ready for the
    ingestion pipeline."""
    # Deferred import to avoid circular dependency
    from datetime import datetime, timezone

    from ai4s.data_infra.ingestion.connector import SourceRecord

    ex = extract_from_pdf(file_path)

    rows: list[dict[str, Any]] = []
    for s in ex.structures:
        rows.append(
            {
                "type": "structure",
                "smiles": s.smiles,
                "inchi": s.inchi,
                "page": s.page,
                "context": s.context,
            }
        )
    for t in ex.tables:
        for row in t.rows:
            if t.headers and len(t.headers) == len(row):
                rows.append(
                    {"type": "table_row", "page": t.page, **dict(zip(t.headers, row))}
                )

    return SourceRecord(
        source=source_name,
        table=Path(file_path).stem,
        batch_id=f"pdf-{Path(file_path).stem}-{datetime.now(timezone.utc).timestamp():.0f}",
        rows=rows,
        metadata={
            "filename": ex.filename,
            "structure_count": len(ex.structures),
            "table_count": len(ex.tables),
            "char_count": len(ex.full_text),
        },
    )


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _extract_structures(text: str, page: int) -> list[ExtractedStructure]:
    """Find SMILES and InChI patterns in page text."""
    structures: list[ExtractedStructure] = []

    # InChI first (high precision)
    inchi_seen: set[str] = set()
    for m in _INCHI_RE.finditer(text):
        inchi = m.group(1)
        if inchi not in inchi_seen:
            inchi_seen.add(inchi)
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            structures.append(
                ExtractedStructure(
                    inchi=inchi,
                    page=page,
                    context=text[start:end].replace("\n", " "),
                )
            )

    # SMILES
    smiles_seen: set[str] = set()
    for m in _SMILES_RE.finditer(text):
        candidate = m.group(1).strip("()[].,;:- \t\n")
        if candidate and _likely_smiles(candidate) and candidate not in smiles_seen:
            smiles_seen.add(candidate)
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            structures.append(
                ExtractedStructure(
                    smiles=candidate,
                    page=page,
                    context=text[start:end].replace("\n", " "),
                )
            )

    return structures


def _extract_tables(text: str, page: int) -> list[ExtractedTable]:
    """Detect tabular data using line-based heuristics."""
    tables: list[ExtractedTable] = []
    lines = text.split("\n")

    # Look for runs of lines with consistent whitespace column separation
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Candidate: line with multiple whitespace-separated fields
        fields = _split_table_line(line)
        if len(fields) < 3:
            i += 1
            continue

        # Collect consecutive lines with same column count
        table_lines = [fields]
        j = i + 1
        while j < len(lines):
            next_fields = _split_table_line(lines[j])
            if len(next_fields) == len(fields):
                table_lines.append(next_fields)
                j += 1
            elif len(next_fields) == 0:
                j += 1  # skip blank lines
            else:
                break

        if len(table_lines) >= 2:
            caption = _find_caption(lines, i)
            headers = table_lines[0]
            rows = table_lines[1:]
            tables.append(
                ExtractedTable(page=page, headers=headers, rows=rows, caption=caption)
            )
        i = j

    return tables


def _split_table_line(line: str) -> list[str]:
    """Split a line by whitespace into table columns. Returns empty list if
    the line doesn't look tabular (fewer than 3 columns or all-single-word)."""
    line = line.strip()
    if not line:
        return []
    parts = re.split(r"\s{2,}|\t+", line)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 3:
        return parts
    return []


def _find_caption(lines: list[str], table_start: int) -> str:
    """Look for a caption (Table X / Fig X) just above the table."""
    for k in range(max(0, table_start - 3), table_start):
        line = lines[k].strip().lower()
        if line.startswith(("table ", "fig ", "figure ")):
            return lines[k].strip()
    return ""
