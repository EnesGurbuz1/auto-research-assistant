"""
Semantic Scholar API - Ücretsiz akademik arama API'si.
Rate limit: 100 req/5 min (authenticated), 10 req/5 min (unauthenticated).
"""

import json
import time
from typing import Dict, List, Any, Optional
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None


class SemanticScholarSearch:
    """Semantic Scholar API arama aracı."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, config: dict):
        self.config = config.get("sources", {}).get("semantic_scholar", {})
        self.max_results = self.config.get("max_results_per_query", 50)
        self.fields = self.config.get("fields", [
            "title", "abstract", "year", "citationCount",
            "authors", "venue", "openAccessPdf", "externalIds"
        ])
        import os
        self.api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

    @property
    def has_api_key(self) -> bool:
        """API key ayarlanmış mı?"""
        return bool(self.api_key)

    def search(self, query: str, limit: Optional[int] = None, _retry: int = 0) -> List[Dict[str, Any]]:
        """Semantic Scholar'da arama yap. Rate limit'te max 1 retry yapar."""
        if httpx is None:
            logger.error("httpx kütüphanesi yüklü değil")
            return []

        max_results = limit or self.max_results
        results = []
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": ",".join(self.fields),
            "year": "2020-2026",
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{self.BASE_URL}/paper/search",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            for paper in data.get("data", []):
                authors_list = paper.get("authors", [])
                authors_str = ", ".join(a.get("name", "") for a in authors_list[:5])
                if len(authors_list) > 5:
                    authors_str += " et al."

                pdf_info = paper.get("openAccessPdf") or {}
                
                result = {
                    "title": paper.get("title", ""),
                    "authors": authors_str,
                    "year": paper.get("year", ""),
                    "venue": paper.get("venue", ""),
                    "abstract": paper.get("abstract", ""),
                    "citation_count": paper.get("citationCount", 0),
                    "paper_id": paper.get("paperId", ""),
                    "doi": (paper.get("externalIds") or {}).get("DOI", ""),
                    "arxiv_id": (paper.get("externalIds") or {}).get("ArXiv", ""),
                    "pdf_url": pdf_info.get("url", ""),
                    "source": "semantic_scholar",
                    "query": query,
                }
                results.append(result)

            logger.info(f"Semantic Scholar: '{query}' → {len(results)} sonuç")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                if _retry < 1:
                    wait = 65 if not self.api_key else 30
                    logger.warning(f"Semantic Scholar rate limit, {wait}s sonra tekrar denenecek (retry {_retry+1}/1)")
                    time.sleep(wait)
                    return self.search(query, limit, _retry=_retry + 1)
                else:
                    logger.warning(f"Semantic Scholar rate limit aşıldı, '{query}' atlanıyor")
            else:
                logger.error(f"Semantic Scholar HTTP hatası: {e}")
        except Exception as e:
            logger.error(f"Semantic Scholar arama hatası: {e}")

        return results

    def get_paper_details(self, paper_id: str) -> Optional[Dict]:
        """Belirli bir makalenin detaylarını getir."""
        if httpx is None:
            return None

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        fields = "title,abstract,year,citationCount,authors,venue,references,citations,openAccessPdf"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{self.BASE_URL}/paper/{paper_id}",
                    headers=headers,
                    params={"fields": fields},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Paper detay hatası ({paper_id}): {e}")
            return None

    def get_citations(self, paper_id: str, limit: int = 50) -> List[Dict]:
        """Bir makalenin atıflarını getir (citation network için)."""
        if httpx is None:
            return []

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{self.BASE_URL}/paper/{paper_id}/citations",
                    headers=headers,
                    params={
                        "fields": "title,year,citationCount,authors",
                        "limit": limit,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return [c.get("citingPaper", {}) for c in data.get("data", [])]
        except Exception as e:
            logger.error(f"Citation hatası ({paper_id}): {e}")
            return []
