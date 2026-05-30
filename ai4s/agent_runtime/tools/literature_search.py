"""Literature search tool — Semantic Scholar API for chemistry paper discovery."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from ai4s.common.logging import get_logger

logger = get_logger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,authors,year,abstract,externalIds,url,venue,citationCount"


async def search_semantic_scholar(
    query: str,
    limit: int = 10,
    year_from: str | None = None,
    year_to: str | None = None,
) -> dict[str, Any]:
    """Search Semantic Scholar for chemistry-related papers.
    Falls back to CrossRef API if Semantic Scholar is unavailable."""
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

    # Try Semantic Scholar with retries
    from_s2 = await _try_s2(url, params, headers)

    if from_s2 is not None:
        papers = from_s2
        source = "semantic_scholar"
    else:
        logger.warning("Semantic Scholar unavailable, falling back to CrossRef")
        papers = await _search_crossref(query, limit)
        source = "crossref"

    return {
        "query": query,
        "total": len(papers),
        "offset": 0,
        "next": 0,
        "count": len(papers),
        "papers": papers,
        "source": source,
    }


async def _search_crossref(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search CrossRef API as fallback — free, no API key required."""
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": min(limit, 20)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            papers = []
            for item in data.get("message", {}).get("items", []):
                authors = item.get("author", [])
                author_names = [
                    f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
                    for a in authors
                ]
                # Get year from date-parts (try multiple fields)
                date_parts = (
                    item.get("published-print", {}).get("date-parts", [[]])[0]
                    or item.get("published-online", {}).get("date-parts", [[]])[0]
                    or item.get("issued", {}).get("date-parts", [[]])[0]
                )
                year = date_parts[0] if date_parts else None
                doi = item.get("DOI", "")
                abstract = item.get("abstract", "") or ""
                abstract = re.sub(r"<[^>]+>", "", abstract)[:300]

                papers.append({
                    "paperId": doi,
                    "title": (item.get("title") or [""])[0],
                    "authors": author_names[:5],
                    "year": year,
                    "abstract": abstract,
                    "doi": doi,
                    "url": f"https://doi.org/{doi}",
                    "venue": (item.get("container-title") or [""])[0],
                    "citationCount": item.get("is-referenced-by-count", 0),
                })
            return papers
    except Exception as e:
        logger.error("CrossRef API error: %s", e)
        return []


async def _try_s2(
    url: str, params: dict[str, Any], headers: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Try calling Semantic Scholar API with retries (3 attempts, 1s wait)."""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30), headers=headers
            ) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    logger.warning("S2 rate-limited (attempt %d/%d)", attempt + 1, max_retries)
                    await asyncio.sleep(1)
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
                await asyncio.sleep(1)
                continue
            logger.error("Semantic Scholar API error: %s", e)
        except httpx.RequestError as e:
            logger.error("Semantic Scholar request error: %s", e)
            await asyncio.sleep(1)

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
