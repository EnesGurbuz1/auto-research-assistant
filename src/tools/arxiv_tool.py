"""
arXiv arama aracı — resmi arxiv API kullanır, agresif rate-limit korumalı.
"""

import time
from typing import List, Dict, Any
from loguru import logger

import arxiv


_last_request_time = 0.0
MIN_REQUEST_INTERVAL = 5.0


def search_arxiv(query: str, max_results: int = 20, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    arXiv'de arama yap ve standart format döndür.
    HTTP 429 hatalarında exponential backoff ile yeniden dener.
    """
    global _last_request_time

    for attempt in range(1, max_retries + 1):
        elapsed = time.time() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            wait = MIN_REQUEST_INTERVAL - elapsed
            logger.debug(f"arXiv rate-limit koruması: {wait:.1f}s bekleniyor")
            time.sleep(wait)

        _last_request_time = time.time()
        results = []

        try:
            client = arxiv.Client(
                page_size=max_results,
                delay_seconds=5,
                num_retries=2,
            )
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
            logger.info(f"arXiv '{query[:60]}' → {len(results)} makale")
            return results

        except Exception as exc:
            error_str = str(exc)
            if "429" in error_str:
                backoff = MIN_REQUEST_INTERVAL * (2 ** attempt)
                logger.warning(
                    f"arXiv 429 rate-limit (deneme {attempt}/{max_retries}), "
                    f"{backoff:.0f}s bekleniyor..."
                )
                time.sleep(backoff)
                _last_request_time = time.time()
            else:
                logger.error(f"arXiv arama hatası ({query[:60]}): {exc}")
                return results

    logger.error(f"arXiv {max_retries} deneme sonrası başarısız: {query[:60]}")
    return []


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
