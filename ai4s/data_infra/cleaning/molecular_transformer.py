"""Molecular data cleaning — SMILES / InChI validation, canonicalisation, and transforms.

Uses RDKit when available for authoritative validation; falls back to regex-based
checks when RDKit is not installed.
"""

from __future__ import annotations

import re
from typing import Callable

from ai4s.common.logging import get_logger
from ai4s.data_infra.cleaning.transformer import DataTransformer, TransformFunc
from ai4s.data_infra.ingestion.connector import SourceRecord

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# optional RDKit import
# ---------------------------------------------------------------------------

try:
    from rdkit import Chem
    from rdkit.Chem import MolFromSmiles, MolToSmiles  # noqa: F401

    _HAS_RDKIT = True
except ImportError:
    _HAS_RDKIT = False

# ---------------------------------------------------------------------------
# SMILES validation
# ---------------------------------------------------------------------------

_SMILES_RE = re.compile(
    r"^(?:\[[A-Za-z0-9@+\-]+\]|[A-Za-z]{1,2}[a-z]?|"
    r"[0-9]+|"
    r"[=\#/\\@\.:\-%\(\)\[\]]|"
    r"%(?:[0-9]{2}))+$"
)


def is_valid_smiles(s: str) -> bool:
    """Return True if *s* appears to be a syntactically valid SMILES string.

    Uses RDKit ``MolFromSmiles`` when available; otherwise falls back to a
    permissive regex that checks for valid atom / bond / ring-closure tokens.
    """
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) < 2:
        return False

    if _HAS_RDKIT:
        mol = Chem.MolFromSmiles(s)
        return mol is not None

    return _SMILES_RE.match(s) is not None


def canonicalize_smiles(s: str) -> str:
    """Return the canonical (unique) SMILES for *s*.

    With RDKit this produces the canonical tautomer-independent SMILES.
    Without RDKit the original string is returned after whitespace cleanup.
    """
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()

    if _HAS_RDKIT:
        mol = Chem.MolFromSmiles(s)
        if mol is not None:
            return Chem.MolToSmiles(mol, canonical=True)
        logger.debug("RDKit could not parse SMILES %r, returning as-is", s[:40])
        return s

    logger.debug("RDKit unavailable — returning raw SMILES for %r", s[:40])
    return s


# ---------------------------------------------------------------------------
# InChI validation
# ---------------------------------------------------------------------------

_INCHI_RE = re.compile(r"^InChI=1S?/[A-Za-z0-9]+(/[a-zA-Z0-9+\-;\(\)\[\],\.]+)+$")


def is_valid_inchi(s: str) -> bool:
    """Return True if *s* matches the InChI format (``InChI=1S/...``)."""
    if not s or not isinstance(s, str):
        return False
    return _INCHI_RE.match(s.strip()) is not None


# ---------------------------------------------------------------------------
# MolecularTransformer
# ---------------------------------------------------------------------------


class MolecularTransformer(DataTransformer):
    """Extends :class:`DataTransformer` with chainable molecular transforms.

    Each method appends a transform function and returns *self* so calls can be
    chained::

        transformer = (
            MolecularTransformer()
            .validate_smiles("SMILES")
            .canonicalize_smiles_col("SMILES", "CanonicalSMILES")
        )
    """

    def validate_smiles(
        self, col: str, drop_invalid: bool = False
    ) -> MolecularTransformer:
        """Validate SMILES strings in *col*.  If *drop_invalid* is True, rows with
        invalid SMILES are removed; otherwise an ``_mol_smiles_valid`` field is
        added to each row."""

        def _validate(batch: SourceRecord) -> SourceRecord:
            kept: list[dict] = []
            for row in batch.rows:
                val = is_valid_smiles(row.get(col, ""))
                row["_mol_smiles_valid"] = val
                if not drop_invalid or val:
                    kept.append(row)
            batch.rows = kept
            return batch

        self._transforms.append(_validate)
        return self

    def validate_inchi(
        self, col: str, drop_invalid: bool = False
    ) -> MolecularTransformer:
        """Validate InChI strings in *col*."""

        def _validate(batch: SourceRecord) -> SourceRecord:
            kept: list[dict] = []
            for row in batch.rows:
                val = is_valid_inchi(row.get(col, ""))
                row["_mol_inchi_valid"] = val
                if not drop_invalid or val:
                    kept.append(row)
            batch.rows = kept
            return batch

        self._transforms.append(_validate)
        return self

    def validate_molecule(
        self, smiles_col: str = "CanonicalSMILES", inchi_col: str = "InChI",
        drop_invalid: bool = False,
    ) -> MolecularTransformer:
        """Combined check: mark ``_mol_valid`` True when BOTH SMILES and InChI
        pass validation."""

        def _validate(batch: SourceRecord) -> SourceRecord:
            kept: list[dict] = []
            for row in batch.rows:
                ok = is_valid_smiles(row.get(smiles_col, "")) and is_valid_inchi(
                    row.get(inchi_col, "")
                )
                row["_mol_valid"] = ok
                if not drop_invalid or ok:
                    kept.append(row)
            batch.rows = kept
            return batch

        self._transforms.append(_validate)
        return self

    def canonicalize_smiles_col(
        self, src_col: str, dst_col: str = "CanonicalSMILES"
    ) -> MolecularTransformer:
        """Produce a canonical SMILES column *dst_col* from *src_col*."""

        def _canon(batch: SourceRecord) -> SourceRecord:
            for row in batch.rows:
                row[dst_col] = canonicalize_smiles(row.get(src_col, ""))
            return batch

        self._transforms.append(_canon)
        return self

    # -- property extraction --------------------------------------------------

    _FORMULA_RE = re.compile(r"^[A-Z][a-z]?[A-Za-z0-9]*$")

    def extract_molecular_formula(
        self, smiles_col: str = "CanonicalSMILES", dst_col: str = "_formula"
    ) -> MolecularTransformer:
        """Extract molecular formula from a SMILES column via RDKit.
        Without RDKit this is a no-op (writes empty string)."""

        def _extract(batch: SourceRecord) -> SourceRecord:
            for row in batch.rows:
                smi = row.get(smiles_col, "")
                if _HAS_RDKIT and smi:
                    mol = Chem.MolFromSmiles(smi)
                    if mol is not None:
                        row[dst_col] = Chem.rdMolDescriptors.CalcMolFormula(mol)
                    else:
                        row[dst_col] = ""
                else:
                    row[dst_col] = ""
            return batch

        self._transforms.append(_extract)
        return self
