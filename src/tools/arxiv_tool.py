"""
arXiv arama aracı — resmi arxiv API kullanır, rate-limit uyumlu.
"""

import time
from typing import List, Dict, Any, Optional
from loguru import logger

import arxiv


def search_arxiv(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    arXiv'de arama yap ve standart format döndür.

    Döndürülen her makale şu alanları içerir:
      id, title, authors, year, abstract, categories, pdf_url, arxiv_url
    """
    results = []
    try:
        client = arxiv.Client(page_size=max_results, delay_seconds=3, num_retries=3)
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        for paper in client.results(search):
            arxiv_id = paper.entry_id.split("/abs/")[-1] if paper.entry_id else ""
            results.append({
                "id": arxiv_id,
                "title": paper.title,
                "authors": [a.name for a in paper.authors[:8]],
                "year": paper.published.year if paper.published else 0,
                "published": paper.published.isoformat() if paper.published else "",
                "abstract": paper.summary or "",
                "categories": list(paper.categories),
                "pdf_url": paper.pdf_url or "",
                "arxiv_url": paper.entry_id or "",
                "source": "arxiv",
                "query": query,
            })
        logger.info(f"arXiv '{query}' → {len(results)} makale")
    except Exception as exc:
        logger.error(f"arXiv arama hatası ({query}): {exc}")

    return results


def deduplicate(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """arxiv_id bazında tekrar eden makaleleri çıkar."""
    seen: set = set()
    unique = []
    for p in papers:
        pid = p.get("id", "")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
        elif not pid:
            unique.append(p)
    return unique
