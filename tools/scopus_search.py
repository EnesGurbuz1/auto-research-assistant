"""
Scopus Search - Elsevier Scopus API ile akademik arama.
API key gerektirir (Elsevier Developer Portal).
"""

import json
import time
from typing import Dict, List, Any
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None


class ScopusSearch:
    """Scopus API arama aracı."""

    BASE_URL = "https://api.elsevier.com/content/search/scopus"

    def __init__(self, config: dict):
        self.config = config.get("sources", {}).get("scopus", {})
        self.max_results = self.config.get("max_results_per_query", 25)
        import os
        self.api_key = os.getenv("SCOPUS_API_KEY", "")
        self.inst_token = os.getenv("SCOPUS_INST_TOKEN", "")

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Scopus'ta arama yap."""
        if httpx is None:
            logger.error("httpx kütüphanesi yüklü değil")
            return []

        if not self.api_key:
            logger.warning("SCOPUS_API_KEY ayarlanmamış, Scopus atlanıyor")
            return []

        results = []
        headers = {
            "X-ELS-APIKey": self.api_key,
            "Accept": "application/json",
        }
        if self.inst_token:
            headers["X-ELS-Insttoken"] = self.inst_token

        params = {
            "query": query,
            "count": self.max_results,
            "sort": "citedby-count",
            "date": "2020-2026",
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(self.BASE_URL, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

            entries = data.get("search-results", {}).get("entry", [])
            for entry in entries:
                result = {
                    "title": entry.get("dc:title", ""),
                    "authors": entry.get("dc:creator", ""),
                    "year": entry.get("prism:coverDate", "")[:4],
                    "venue": entry.get("prism:publicationName", ""),
                    "doi": entry.get("prism:doi", ""),
                    "citation_count": int(entry.get("citedby-count", 0)),
                    "scopus_id": entry.get("dc:identifier", ""),
                    "url": next(
                        (l["@href"] for l in entry.get("link", []) if l.get("@ref") == "scopus"),
                        ""
                    ),
                    "source": "scopus",
                    "query": query,
                }
                results.append(result)

            logger.info(f"Scopus: '{query}' → {len(results)} sonuç")

        except Exception as e:
            logger.error(f"Scopus arama hatası: {e}")

        return results
