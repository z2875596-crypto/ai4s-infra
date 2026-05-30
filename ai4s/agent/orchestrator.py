"""ReAct orchestrator — LLM-driven research agent with tool use.

Implements the ReAct pattern (Thought → Action → Observation loop) using
DeepSeek API's Function Calling. Each step is yielded as a streaming event
for SSE delivery to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from urllib.parse import quote
from datetime import datetime
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx

from ai4s.agent.memory import AgentMemory, Session
from ai4s.common.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# DeepSeek client configuration
# ---------------------------------------------------------------------------

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# ---------------------------------------------------------------------------
# Embedded periodic table data (subset for agent tools)
# ---------------------------------------------------------------------------

_ELEMENT_DATA: dict[str, dict[str, Any]] = {
    "H":  {"z":1,  "name":"氢",   "mass":1.008,   "config":"1s¹",           "eneg":2.20, "mp":-259.16, "bp":-252.88},
    "He": {"z":2,  "name":"氦",   "mass":4.0026,  "config":"1s²",           "eneg":None, "mp":None,    "bp":-268.93},
    "Li": {"z":3,  "name":"锂",   "mass":6.94,    "config":"[He]2s¹",       "eneg":0.98, "mp":180.5,   "bp":1330},
    "Be": {"z":4,  "name":"铍",   "mass":9.0122,  "config":"[He]2s²",       "eneg":1.57, "mp":1287,    "bp":2469},
    "B":  {"z":5,  "name":"硼",   "mass":10.81,   "config":"[He]2s²2p¹",    "eneg":2.04, "mp":2076,    "bp":3927},
    "C":  {"z":6,  "name":"碳",   "mass":12.011,  "config":"[He]2s²2p²",    "eneg":2.55, "mp":3550,    "bp":4027},
    "N":  {"z":7,  "name":"氮",   "mass":14.007,  "config":"[He]2s²2p³",    "eneg":3.04, "mp":-210.0,  "bp":-195.8},
    "O":  {"z":8,  "name":"氧",   "mass":15.999,  "config":"[He]2s²2p⁴",    "eneg":3.44, "mp":-218.8,  "bp":-183.0},
    "F":  {"z":9,  "name":"氟",   "mass":18.998,  "config":"[He]2s²2p⁵",    "eneg":3.98, "mp":-219.67, "bp":-188.11},
    "Ne": {"z":10, "name":"氖",   "mass":20.180,  "config":"[He]2s²2p⁶",    "eneg":None, "mp":-248.59, "bp":-246.05},
    "Na": {"z":11, "name":"钠",   "mass":22.990,  "config":"[Ne]3s¹",       "eneg":0.93, "mp":97.79,   "bp":882.94},
    "Mg": {"z":12, "name":"镁",   "mass":24.305,  "config":"[Ne]3s²",       "eneg":1.31, "mp":650,     "bp":1090},
    "Al": {"z":13, "name":"铝",   "mass":26.982,  "config":"[Ne]3s²3p¹",    "eneg":1.61, "mp":660.32,  "bp":2519},
    "Si": {"z":14, "name":"硅",   "mass":28.085,  "config":"[Ne]3s²3p²",    "eneg":1.90, "mp":1414,    "bp":3265},
    "P":  {"z":15, "name":"磷",   "mass":30.974,  "config":"[Ne]3s²3p³",    "eneg":2.19, "mp":44.15,   "bp":280.5},
    "S":  {"z":16, "name":"硫",   "mass":32.06,   "config":"[Ne]3s²3p⁴",    "eneg":2.58, "mp":115.21,  "bp":444.61},
    "Cl": {"z":17, "name":"氯",   "mass":35.45,   "config":"[Ne]3s²3p⁵",    "eneg":3.16, "mp":-101.5,  "bp":-34.04},
    "Ar": {"z":18, "name":"氩",   "mass":39.95,   "config":"[Ne]3s²3p⁶",    "eneg":None, "mp":-189.34, "bp":-185.85},
    "K":  {"z":19, "name":"钾",   "mass":39.098,  "config":"[Ar]4s¹",       "eneg":0.82, "mp":63.5,    "bp":759},
    "Ca": {"z":20, "name":"钙",   "mass":40.08,   "config":"[Ar]4s²",       "eneg":1.00, "mp":842,     "bp":1484},
    "Sc": {"z":21, "name":"钪",   "mass":44.956,  "config":"[Ar]3d¹4s²",    "eneg":1.36, "mp":1541,    "bp":2836},
    "Ti": {"z":22, "name":"钛",   "mass":47.867,  "config":"[Ar]3d²4s²",    "eneg":1.54, "mp":1668,    "bp":3287},
    "V":  {"z":23, "name":"钒",   "mass":50.942,  "config":"[Ar]3d³4s²",    "eneg":1.63, "mp":1910,    "bp":3407},
    "Cr": {"z":24, "name":"铬",   "mass":51.996,  "config":"[Ar]3d⁵4s¹",    "eneg":1.66, "mp":1907,    "bp":2671},
    "Mn": {"z":25, "name":"锰",   "mass":54.938,  "config":"[Ar]3d⁵4s²",    "eneg":1.55, "mp":1246,    "bp":2061},
    "Fe": {"z":26, "name":"铁",   "mass":55.845,  "config":"[Ar]3d⁶4s²",    "eneg":1.83, "mp":1538,    "bp":2861},
    "Co": {"z":27, "name":"钴",   "mass":58.933,  "config":"[Ar]3d⁷4s²",    "eneg":1.88, "mp":1495,    "bp":2927},
    "Ni": {"z":28, "name":"镍",   "mass":58.693,  "config":"[Ar]3d⁸4s²",    "eneg":1.91, "mp":1455,    "bp":2913},
    "Cu": {"z":29, "name":"铜",   "mass":63.546,  "config":"[Ar]3d¹⁰4s¹",   "eneg":1.90, "mp":1084.62, "bp":2562},
    "Zn": {"z":30, "name":"锌",   "mass":65.38,   "config":"[Ar]3d¹⁰4s²",   "eneg":1.65, "mp":419.53,  "bp":907},
    "Br": {"z":35, "name":"溴",   "mass":79.904,  "config":"[Ar]3d¹⁰4s²4p⁵", "eneg":2.96, "mp":-7.2,   "bp":58.8},
    "Ag": {"z":47, "name":"银",   "mass":107.87,  "config":"[Kr]4d¹⁰5s¹",   "eneg":1.93, "mp":961.78,  "bp":2162},
    "I":  {"z":53, "name":"碘",   "mass":126.90,  "config":"[Kr]4d¹⁰5s²5p⁵", "eneg":2.66, "mp":113.7,  "bp":184.3},
    "Pt": {"z":78, "name":"铂",   "mass":195.08,  "config":"[Xe]4f¹⁴5d⁹6s¹", "eneg":2.28, "mp":1768.3, "bp":3825},
    "Au": {"z":79, "name":"金",   "mass":196.97,  "config":"[Xe]4f¹⁴5d¹⁰6s¹","eneg":2.54, "mp":1064.18,"bp":2856},
    "Hg": {"z":80, "name":"汞",   "mass":200.59,  "config":"[Xe]4f¹⁴5d¹⁰6s²","eneg":2.00, "mp":-38.83, "bp":356.73},
    "Pb": {"z":82, "name":"铅",   "mass":207.2,   "config":"[Xe]4f¹⁴5d¹⁰6s²6p²","eneg":2.33,"mp":327.46,"bp":1749},
}

# ---------------------------------------------------------------------------
# Event types for SSE streaming
# ---------------------------------------------------------------------------

@dataclass
class AgentEvent:
    type: str          # thought | action | observation | answer | error | done
    content: str
    tool_name: str | None = None
    step_index: int = 0


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_literature",
            "description": "搜索化学/材料科学文献数据库。输入研究关键词，返回相关论文的标题、作者、年份、摘要和引用次数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如 'perovskite solar cells' 或 'CO2 reduction catalyst'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回论文数量上限，默认10，最大20",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_pubchem",
            "description": "在PubChem数据库中搜索化合物信息。输入化合物名称或CID，返回该化合物的基本性质（分子式、分子量、SMILES、LogP等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "化合物名称（如 'aspirin'、'caffeine'）或PubChem CID",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_properties",
            "description": "基于SMILES结构式，使用RDKit预测分子的理化性质和ADMET参数，包括：分子量、LogP、氢键供体/受体数、可旋转键数、TPSA、重原子数、环数、芳环数等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "smiles": {
                        "type": "string",
                        "description": "化合物的SMILES表示，如 'CC(=O)OC1=CC=CC=C1C(=O)O' (aspirin)",
                    },
                },
                "required": ["smiles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_molar_mass",
            "description": "计算给定化学式的摩尔质量（分子量）。支持括号嵌套和水合物（如 Ca(OH)2、CuSO4·5H2O）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "formula": {
                        "type": "string",
                        "description": "化学式，如 'H2SO4'、'C6H12O6'、'Ca(OH)2'",
                    },
                },
                "required": ["formula"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_element",
            "description": "查询元素周期表中某一元素的基本信息：原子序数、原子量、电子构型、电负性、熔点、沸点等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "元素符号，如 'Fe'、'Pd'、'Au'",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
]

def _build_system_prompt() -> str:
    current_year = datetime.now().year
    return f"""你是一个化学研究 AI 助手，拥有以下能力：
1. 搜索化学文献数据库获取最新研究进展
2. 查询 PubChem 化合物数据库
3. 预测分子的理化性质和 ADMET 参数
4. 计算摩尔质量
5. 查询元素周期表信息

请使用 ReAct（推理-行动）模式工作：
- 首先分析用户的问题，规划研究步骤
- 然后逐个调用工具获取所需信息
- 综合所有结果，给出专业、结构化的最终报告

报告要求：
- 当前年份为 {current_year} 年，引用文献和生成报告时使用正确的年份
- 使用 Markdown 格式
- 包含数据表格（如有数值结果）
- 引用文献时给出标题、作者、年份，并标注 DOI 编号，格式为 [DOI: 10.xxxx/xxxx]
- 文献综述部分，每篇文献用 --- 分隔，使报告结构清晰
- 给出结论或建议
- 使用中文撰写"""

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def _execute_search_literature(args: dict[str, Any]) -> str:
    """Execute literature search via Semantic Scholar."""
    from ai4s.agent_runtime.tools.literature_search import search_semantic_scholar

    result = await search_semantic_scholar(
        query=args.get("query", ""),
        limit=min(int(args.get("limit", 10)), 20),
    )
    papers = result.get("papers", [])
    if not papers:
        return "未找到相关文献。"
    lines = [f"找到 {len(papers)} 篇相关论文：\n"]
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.get("authors", [])[:3])
        if len(p.get("authors", [])) > 3:
            authors += " et al."

        # Build paper link: DOI → URL → Google Scholar fallback
        doi = p.get("doi", "") or ""
        url = p.get("url", "") or ""
        title = p.get("title", "")
        link_url = ""
        if doi:
            link_url = f"https://doi.org/{doi}"
        elif url:
            link_url = url
        elif title:
            link_url = f"https://scholar.google.com/scholar?q={quote(title)}"

        link_line = f"   [查看原文 →]({link_url})\n" if link_url else ""

        lines.append(
            f"{i}. **{p.get('title', 'N/A')}**\n"
            f"   作者: {authors} | 年份: {p.get('year', 'N/A')} | "
            f"期刊: {p.get('venue', 'N/A')} | 引用: {p.get('citationCount', 0)}\n"
            f"   摘要: {(p.get('abstract') or 'N/A')[:300]}...\n"
            f"{link_line}"
        )
    return "\n".join(lines)


async def _execute_search_pubchem(args: dict[str, Any]) -> str:
    """Execute PubChem search."""
    query = args.get("query", "").strip()
    if not query:
        return "错误：未提供搜索关键词。"

    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        try:
            # Try to fetch by CID first if query is numeric
            if query.isdigit():
                url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{query}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,IUPACName/JSON"
            else:
                url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,IUPACName/JSON"

            resp = await client.get(url)
            if resp.status_code == 404:
                return f"未在 PubChem 中找到 '{query}' 的信息。"
            resp.raise_for_status()
            data = resp.json()

            props = data["PropertyTable"]["Properties"][0]
            return (
                f"**{query}** (PubChem)\n"
                f"- IUPAC名称: {props.get('IUPACName', 'N/A')}\n"
                f"- 分子式: {props.get('MolecularFormula', 'N/A')}\n"
                f"- 分子量: {props.get('MolecularWeight', 'N/A')} g/mol\n"
                f"- SMILES: {props.get('CanonicalSMILES', 'N/A')}\n"
                f"- LogP: {props.get('XLogP', 'N/A')}\n"
                f"- TPSA: {props.get('TPSA', 'N/A')} Å²\n"
                f"- 氢键供体: {props.get('HBondDonorCount', 'N/A')}\n"
                f"- 氢键受体: {props.get('HBondAcceptorCount', 'N/A')}\n"
                f"- 可旋转键: {props.get('RotatableBondCount', 'N/A')}"
            )
        except httpx.HTTPStatusError as e:
            return f"PubChem API 请求失败: {e.response.status_code}"
        except Exception as e:
            return f"PubChem 查询出错: {e}"


async def _execute_predict_properties(args: dict[str, Any]) -> str:
    """Execute molecular property prediction via RDKit."""
    smiles = args.get("smiles", "").strip()
    if not smiles:
        return "错误：未提供 SMILES。"

    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, AllChem, Crippen

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return f"无效的 SMILES: {smiles}"

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)
        rot_bonds = Descriptors.NumRotatableBonds(mol)
        tpsa = Descriptors.TPSA(mol)
        heavy = mol.GetNumHeavyAtoms()
        rings = Chem.rdMolDescriptors.CalcNumRings(mol)
        aromatic = Chem.rdMolDescriptors.CalcNumAromaticRings(mol)
        formula = Chem.rdMolDescriptors.CalcMolFormula(mol)

        # Lipinski Rule of Five
        violations = sum([
            1 if mw > 500 else 0,
            1 if logp > 5 else 0,
            1 if hbd > 5 else 0,
            1 if hba > 10 else 0,
        ])
        lipinski = "通过 ✓" if violations <= 1 else f"不通过 ✗ ({violations} 项违规)"

        return (
            f"**分子性质预测结果** (SMILES: `{smiles}`)\n"
            f"- 分子式: {formula}\n"
            f"- 分子量: {mw:.2f} g/mol\n"
            f"- LogP: {logp:.2f}\n"
            f"- 氢键供体: {hbd}\n"
            f"- 氢键受体: {hba}\n"
            f"- 可旋转键: {rot_bonds}\n"
            f"- TPSA: {tpsa:.2f} Å²\n"
            f"- 重原子数: {heavy}\n"
            f"- 环数: {rings} (芳环: {aromatic})\n"
            f"- Lipinski 五规则: {lipinski}"
        )
    except ImportError:
        return "RDKit 未安装，无法进行分子性质预测。请安装: pip install rdkit"
    except Exception as e:
        return f"性质预测出错: {e}"


def _execute_calculate_molar_mass(args: dict[str, Any]) -> str:
    """Calculate molar mass from chemical formula."""
    formula = args.get("formula", "").strip()
    if not formula:
        return "错误：未提供化学式。"

    # Remove whitespace
    s = formula.replace(" ", "")

    def parse_element(i: int) -> tuple[str, int]:
        """Parse one element symbol starting at position i."""
        if i >= len(s) or not s[i].isupper():
            return "", i
        sym = s[i]
        i += 1
        while i < len(s) and s[i].islower():
            sym += s[i]
            i += 1
        return sym, i

    def parse_number(i: int) -> tuple[int, int]:
        """Parse an integer starting at position i."""
        num = 0
        while i < len(s) and s[i].isdigit():
            num = num * 10 + int(s[i])
            i += 1
        return num if num else 1, i

    def parse_group(depth: int = 0) -> tuple[dict[str, int], int]:
        """Parse a group (possibly parenthesized), returns element->count map and next index."""
        counts: dict[str, int] = {}
        i = 0
        while i < len(s):
            if s[i] == "(":
                inner, ni = parse_group(depth + 1)
                ni = ni  # ni is the position after the inner group
                # Actually, we need to re-parse from the inner group position
                # Let's use a different approach
                pass
            break
        return counts, i

    # Iterative parser with explicit index
    i = 0
    stack: list[dict[str, int]] = [{}]

    while i < len(s):
        c = s[i]
        if c == "(":
            stack.append({})
            i += 1
        elif c == ")":
            i += 1
            mult, i = parse_number(i)
            inner = stack.pop()
            for elem, cnt in inner.items():
                stack[-1][elem] = stack[-1].get(elem, 0) + cnt * mult
        elif c == "·" or c == ".":
            # Hydrate separator — just continue parsing into the same top group
            i += 1
        elif c.isupper():
            sym, i = parse_element(i)
            cnt, i = parse_number(i)
            if sym in _ELEMENT_DATA:
                stack[-1][sym] = stack[-1].get(sym, 0) + cnt
            else:
                return f"未知元素: {sym}"
        else:
            i += 1  # skip unexpected chars

    if len(stack) != 1:
        return "化学式括号不匹配。"

    total = 0.0
    detail_lines = []
    for sym, cnt in sorted(stack[0].items()):
        el = _ELEMENT_DATA[sym]
        mass = el["mass"] * cnt
        total += mass
        detail_lines.append(f"  {sym}: {cnt} × {el['mass']:.3f} = {mass:.4f} g/mol")

    lines = [f"**{formula}** 的摩尔质量计算："]
    lines.extend(detail_lines)
    lines.append(f"\n**总摩尔质量: {total:.4f} g/mol**")
    return "\n".join(lines)


def _execute_lookup_element(args: dict[str, Any]) -> str:
    """Lookup element from periodic table data."""
    symbol = args.get("symbol", "").strip()
    # Capitalize first letter, lowercase rest
    symbol = symbol.capitalize() if symbol else ""
    el = _ELEMENT_DATA.get(symbol)
    if not el:
        return f"未找到元素 '{symbol}'。请使用标准元素符号（如 Fe、Au、C）。"

    mp_str = f"{el['mp']} °C" if el["mp"] is not None else "N/A"
    bp_str = f"{el['bp']} °C" if el["bp"] is not None else "N/A"
    eneg_str = f"{el['eneg']:.2f}" if el["eneg"] is not None else "N/A"

    return (
        f"**{el['name']} ({symbol})** — Z={el['z']}\n"
        f"- 原子量: {el['mass']:.3f} g/mol\n"
        f"- 电子构型: {el['config']}\n"
        f"- 电负性: {eneg_str}\n"
        f"- 熔点: {mp_str}\n"
        f"- 沸点: {bp_str}"
    )


TOOL_EXECUTORS: dict[str, Any] = {
    "search_literature": _execute_search_literature,
    "search_pubchem": _execute_search_pubchem,
    "predict_properties": _execute_predict_properties,
    "calculate_molar_mass": _execute_calculate_molar_mass,
    "lookup_element": _execute_lookup_element,
}

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """ReAct agent orchestrator using DeepSeek API with Function Calling."""

    def __init__(self, memory: AgentMemory | None = None) -> None:
        self.memory = memory or AgentMemory()
        self._client: httpx.AsyncClient | None = None

    @property
    def api_key(self) -> str:
        return DEEPSEEK_API_KEY

    @property
    def base_url(self) -> str:
        return DEEPSEEK_BASE_URL.rstrip("/")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120),
            )
        return self._client

    async def run(
        self,
        query: str,
        session_id: str | None = None,
        max_steps: int = 10,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the ReAct loop, yielding AgentEvent for each step.

        The caller should consume this async generator and forward events
        as SSE messages to the frontend.
        """
        if not self.api_key:
            yield AgentEvent(type="error", content="DeepSeek API key 未配置。请设置环境变量 DEEPSEEK_API_KEY。")
            return

        # Create or load session
        if session_id is None:
            session_id = uuid.uuid4().hex[:12]
        session = self.memory.create_session(
            session_id=session_id,
            title=query[:60],
            query=query,
        )

        yield AgentEvent(type="thought", content=f"开始研究: {query}", step_index=0)

        # Build message history
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": query},
        ]

        step_index = 0

        for _ in range(max_steps):
            step_index += 1

            # ── Call LLM ─────────────────────────────────────
            client = await self._get_client()
            request_body = {
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "tools": TOOL_DEFINITIONS,
                "temperature": 0.3,
                "max_tokens": 4096,
            }
            print("\n=== DeepSeek API 请求体 ===")
            print(json.dumps(request_body, ensure_ascii=False, indent=2))
            print("=== 请求体结束 ===\n")
            try:
                resp = await client.post(
                    "/chat/completions",
                    json=request_body,
                )
                resp.raise_for_status()
                result = resp.json()
            except httpx.HTTPStatusError as e:
                logger.error("DeepSeek API error: %s", e)
                print(f"\n=== DeepSeek 400 响应详情 ===\n{e.response.text}\n=== 响应结束 ===\n")
                yield AgentEvent(type="error", content=f"API 调用失败: {e.response.status_code}", step_index=step_index)
                return
            except Exception as e:
                logger.error("DeepSeek request error: %s", e)
                yield AgentEvent(type="error", content=f"请求失败: {e}", step_index=step_index)
                return

            choice = result["choices"][0]
            msg = choice["message"]
            print(f"\n=== DeepSeek 返回的 message ===\n{json.dumps(msg, ensure_ascii=False, indent=2)}\n=== message 结束 ===")

            # ── Check if LLM wants to call a tool ────────────
            if msg.get("tool_calls"):
                tool_calls = msg["tool_calls"]
                print(f"\n=== LLM 返回了 {len(tool_calls)} 个 tool_calls ===")
                for i, tc in enumerate(tool_calls):
                    print(f"  tool_call[{i}]: id={tc.get('id')}, name={tc['function']['name']}")

                # Yield thought (extract from content if present)
                thought = msg.get("content") or ""
                if thought.strip():
                    yield AgentEvent(type="thought", content=thought, step_index=step_index)
                    self.memory.append_step(session_id, "thought", thought)

                # Execute each tool, collect (tool_call, observation) pairs
                tool_results: list[tuple[dict[str, Any], str]] = []
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    # Yield action
                    action_desc = f"调用工具: **{tool_name}**\n参数: ```json\n{json.dumps(tool_args, ensure_ascii=False, indent=2)}\n```"
                    yield AgentEvent(type="action", content=action_desc, tool_name=tool_name, step_index=step_index)
                    self.memory.append_step(session_id, "action", action_desc, tool_name=tool_name)

                    # Execute tool
                    executor = TOOL_EXECUTORS.get(tool_name)
                    if executor:
                        observation = await executor(tool_args) if asyncio.iscoroutinefunction(executor) else executor(tool_args)
                    else:
                        observation = f"未知工具: {tool_name}"

                    yield AgentEvent(type="observation", content=observation, tool_name=tool_name, step_index=step_index)
                    self.memory.append_step(session_id, "observation", observation, tool_name=tool_name)

                    tool_results.append((tool_call, observation))

                # Append assistant msg, then all tool responses
                assistant_msg: dict[str, Any] = {"role": "assistant"}
                if msg.get("content"):
                    assistant_msg["content"] = msg["content"]
                assistant_msg["tool_calls"] = [tc for tc, _ in tool_results]
                messages.append(assistant_msg)
                for tc, obs in tool_results:
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": obs})
                print(f"=== 已处理 {len(tool_results)} 个 tool_calls，消息历史已更新 ===\n")

            else:
                # ── Final answer ──────────────────────────────
                answer = msg.get("content", "")
                if answer:
                    yield AgentEvent(type="answer", content=answer, step_index=step_index)
                    self.memory.append_step(session_id, "answer", answer)
                yield AgentEvent(type="done", content="", step_index=step_index)
                return

        # Max steps reached — force summary
        yield AgentEvent(type="error", content=f"超过最大推理步数 ({max_steps})，请简化问题后重试。", step_index=step_index)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Module-level singleton (follows existing project pattern)
# ---------------------------------------------------------------------------

_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
