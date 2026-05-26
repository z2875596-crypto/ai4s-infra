"""Molecular property prediction using RDKit.

Predicts molecular descriptors from SMILES strings:
  - Molecular Weight
  - LogP (octanol-water partition coefficient)
  - Hydrogen Bond Donors / Acceptors
  - Rotatable Bond Count
  - Topological Polar Surface Area (TPSA)
"""

from __future__ import annotations

from typing import Any

from ai4s.common.logging import get_logger

logger = get_logger(__name__)


def predict_properties(smiles: str) -> dict[str, Any]:
    """Predict molecular properties from a SMILES string.

    Returns a dict with computed properties or an error message.
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen, Lipinski

    smiles = smiles.strip()
    if not smiles:
        return {"error": "SMILES string is required", "valid": False}

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"error": f"Invalid SMILES string: {smiles}", "valid": False}

    try:
        mol = Chem.AddHs(mol)
        formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
        mol = Chem.RemoveHs(mol)
    except Exception:
        formula = ""

    return {
        "valid": True,
        "smiles": smiles,
        "canonical_smiles": Chem.MolToSmiles(mol, canonical=True),
        "molecular_formula": formula,
        "molecular_weight": round(Descriptors.MolWt(mol), 2),
        "logp": round(Crippen.MolLogP(mol), 2),
        "h_bond_donors": Lipinski.NumHDonors(mol),
        "h_bond_acceptors": Lipinski.NumHAcceptors(mol),
        "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
        "tpsa": round(Descriptors.TPSA(mol), 2),
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "ring_count": Descriptors.RingCount(mol),
        "aromatic_rings": Descriptors.NumAromaticRings(mol),
    }
