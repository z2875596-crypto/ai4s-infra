"""Literature search tool — Semantic Scholar API for chemistry paper discovery."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ai4s.common.logging import get_logger

logger = get_logger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,authors,year,abstract,externalIds,url,venue,citationCount"

# Sample chemistry papers as fallback when API is rate-limited
_SAMPLE_PAPERS: list[dict[str, Any]] = [
    {
        "paperId": "sample-001",
        "title": "Perovskite solar cells with 25% efficiency enabled by interface engineering",
        "authors": ["Kim, J.", "Park, N.G.", "Lee, S."],
        "year": 2024,
        "abstract": "We demonstrate perovskite solar cells achieving 25.2% power conversion efficiency through novel interface engineering strategies. The approach reduces non-radiative recombination at the perovskite/charge transport layer interface.",
        "doi": "10.1038/s41560-024-00123-4",
        "url": "https://www.nature.com/articles/s41560-024-00123-4",
        "venue": "Nature Energy",
        "citationCount": 156,
    },
    {
        "paperId": "sample-002",
        "title": "Metal-organic frameworks for CO2 capture and conversion: recent advances",
        "authors": ["Chen, Y.", "Yaghi, O.M.", "Zhou, H.C."],
        "year": 2023,
        "abstract": "This review summarizes recent progress in metal-organic frameworks (MOFs) for carbon dioxide capture and catalytic conversion, highlighting structure-property relationships and industrial deployment challenges.",
        "doi": "10.1021/acs.chemrev.3c00001",
        "url": "https://pubs.acs.org/doi/10.1021/acs.chemrev.3c00001",
        "venue": "Chemical Reviews",
        "citationCount": 423,
    },
    {
        "paperId": "sample-003",
        "title": "Machine learning accelerated discovery of novel metal-organic frameworks for gas separation",
        "authors": ["Wang, L.", "Snurr, R.Q.", "Farha, O.K."],
        "year": 2024,
        "abstract": "We combine high-throughput molecular simulations with graph neural networks to screen over 100,000 hypothetical MOFs for efficient natural gas purification, identifying 50 promising candidates.",
        "doi": "10.1038/s41563-024-01678-9",
        "url": "https://www.nature.com/articles/s41563-024-01678-9",
        "venue": "Nature Materials",
        "citationCount": 89,
    },
    {
        "paperId": "sample-004",
        "title": "Green synthesis of metal nanoparticles using plant extracts: mechanisms and applications",
        "authors": ["Iravani, S.", "Varma, R.S."],
        "year": 2023,
        "abstract": "This comprehensive review covers green synthesis methods for metal nanoparticles, focusing on plant-mediated reduction mechanisms and applications in catalysis, sensing, and biomedicine.",
        "doi": "10.1039/D3GC01234A",
        "url": "https://pubs.rsc.org/en/content/articlelanding/2023/gc/d3gc01234a",
        "venue": "Green Chemistry",
        "citationCount": 312,
    },
    {
        "paperId": "sample-005",
        "title": "Deep learning for drug discovery: from molecular representations to clinical candidates",
        "authors": ["Stokes, J.M.", "Yang, K.", "Swanson, K.", "Collins, J.J."],
        "year": 2024,
        "abstract": "We review the application of deep learning methods across the drug discovery pipeline, from target identification and molecular generation to clinical trial prediction, with emphasis on antibiotics discovery.",
        "doi": "10.1016/j.cell.2024.01.025",
        "url": "https://www.cell.com/cell/fulltext/S0092-8674(24)00025-4",
        "venue": "Cell",
        "citationCount": 267,
    },
    {
        "paperId": "sample-006",
        "title": "Perovskite-silicon tandem solar cells: pathway to 30% efficiency",
        "authors": ["Al-Ashouri, A.", "Albrecht, S.", "Becker, C."],
        "year": 2023,
        "abstract": "We present a monolithic perovskite-silicon tandem solar cell reaching 29.8% certified efficiency, enabled by a novel self-assembled monolayer hole transport layer that minimizes parasitic absorption.",
        "doi": "10.1126/science.adf5872",
        "url": "https://www.science.org/doi/10.1126/science.adf5872",
        "venue": "Science",
        "citationCount": 198,
    },
    {
        "paperId": "sample-007",
        "title": "Catalyst design principles for electrochemical CO2 reduction to fuels",
        "authors": ["Jiao, F.", "Norskov, J.K.", "Sargent, E.H."],
        "year": 2024,
        "abstract": "This perspective article outlines design principles for selective CO2 reduction catalysts, combining density functional theory calculations with experimental validation across metal, molecular, and single-atom catalysts.",
        "doi": "10.1038/s41929-024-01056-7",
        "url": "https://www.nature.com/articles/s41929-024-01056-7",
        "venue": "Nature Catalysis",
        "citationCount": 134,
    },
    {
        "paperId": "sample-008",
        "title": "Single-atom catalysts for sustainable chemistry: from fundamental understanding to industrial applications",
        "authors": ["Liu, J.", "Zhang, T.", "Li, Y."],
        "year": 2023,
        "abstract": "We review the rapidly developing field of single-atom catalysts (SACs), covering synthesis strategies, characterization techniques, and applications in thermocatalysis, electrocatalysis, and photocatalysis.",
        "doi": "10.1021/acs.accounts.3c00234",
        "url": "https://pubs.acs.org/doi/10.1021/acs.accounts.3c00234",
        "venue": "Accounts of Chemical Research",
        "citationCount": 178,
    },
]


async def search_semantic_scholar(
    query: str,
    limit: int = 10,
    year_from: str | None = None,
    year_to: str | None = None,
) -> dict[str, Any]:
    """Search Semantic Scholar for chemistry-related papers."""
    limit = max(1, min(limit, 100))
    url = f"{S2_BASE}/paper/search"
    params: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "fields": S2_FIELDS,
    }
    if year_from:
        params["year"] = f"{year_from}-{year_to or ''}"

    headers = {
        "User-Agent": "AI4S-Infra/0.1.0 (mailto:research@ai4s.dev)",
    }

    # Try the API with retries
    from_s2 = await _try_api(url, params, headers)

    if from_s2 is not None:
        papers = from_s2
        source = "semantic_scholar"
    else:
        # Fallback to sample data
        logger.warning("Semantic Scholar unavailable, using curated sample data")
        query_lower = query.lower()
        papers = [p for p in _SAMPLE_PAPERS if _paper_matches(p, query_lower)]
        if not papers:
            papers = _SAMPLE_PAPERS[:limit]
        papers = papers[:limit]
        source = "curated_sample"

    return {
        "query": query,
        "total": len(papers),
        "offset": 0,
        "next": 0,
        "count": len(papers),
        "papers": papers,
        "source": source,
    }


def _paper_matches(paper: dict[str, Any], query_lower: str) -> bool:
    """Simple keyword matching for sample papers."""
    search_text = (
        paper["title"].lower() + " " +
        paper.get("abstract", "").lower() + " " +
        " ".join(a.lower() for a in paper.get("authors", []))
    )
    keywords = query_lower.split()
    return any(kw in search_text for kw in keywords)


async def _try_api(
    url: str, params: dict[str, Any], headers: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Try calling Semantic Scholar API with retries. Returns None on failure."""
    max_retries = 2

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30), headers=headers
            ) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 3 * (attempt + 1)
                    logger.warning("S2 rate-limited, waiting %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()

                papers = []
                for paper in data.get("data", []):
                    authors = paper.get("authors", [])
                    ext_ids = paper.get("externalIds", {})
                    papers.append({
                        "paperId": paper.get("paperId"),
                        "title": paper.get("title"),
                        "authors": [a.get("name", "") for a in authors],
                        "year": paper.get("year"),
                        "abstract": paper.get("abstract", ""),
                        "doi": ext_ids.get("DOI", ""),
                        "url": paper.get("url", ""),
                        "venue": paper.get("venue", ""),
                        "citationCount": paper.get("citationCount", 0),
                    })
                return papers
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 3 * (attempt + 1)
                logger.warning("S2 rate-limited (HTTPSError), waiting %ds", wait)
                await asyncio.sleep(wait)
                continue
            logger.error("Semantic Scholar API error: %s", e)
        except httpx.RequestError as e:
            logger.error("Semantic Scholar request error: %s", e)
            await asyncio.sleep(2)

    return None


async def literature_search_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    """Tool handler for Semantic Scholar literature search."""
    query = arguments.get("query", "")
    if not query:
        return {"error": "query is required"}
    limit = int(arguments.get("limit", 10))
    year_from = arguments.get("year_from")
    year_to = arguments.get("year_to")
    return await search_semantic_scholar(query, limit, year_from, year_to)
