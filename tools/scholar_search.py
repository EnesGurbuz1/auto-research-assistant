"""
Google Scholar Search - scholarly kütüphanesi ile Google Scholar araması.
Rate limiting ve cache mekanizması içerir.
"""

import json
import time
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None

try:
    from scholarly import scholarly, ProxyGenerator
except ImportError:
    scholarly = None
    ProxyGenerator = None


class ScholarSearch:
    """Google Scholar arama aracı."""

    def __init__(self, config: dict):
        self.config = config.get("sources", {}).get("scholar", {})
        self.max_results = self.config.get("max_results_per_query", 20)
        self.year_range = self.config.get("year_range", [2020, 2026])
        self.use_serpapi = self.config.get("use_serpapi", True)
        self.serpapi_max_requests_monthly = int(self.config.get("serpapi_max_requests_monthly", 50))
        self.serpapi_key = os.getenv("SERPAPI_KEY", "") or os.getenv("SERPAPI_API_KEY", "")
        self.cache_dir = Path(config.get("project_root", ".")) / "data" / "cache" / "scholar"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Proxy sadece açıkça istendiğinde denenir.
        self.use_proxy = os.getenv("SCHOLAR_USE_PROXY", "0") == "1"
        if self.use_proxy and ProxyGenerator is not None:
            try:
                pg = ProxyGenerator()
                pg.FreeProxies()
                scholarly.use_proxy(pg)
                logger.info("Scholarly için free proxy ayarlandı.")
            except Exception as e:
                logger.warning(f"Scholar proxy ayarlanamadı, proxysiz devam ediliyor: {e}")

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Google Scholar'da arama yap."""
        # Cache kontrol
        cached = self._check_cache(query)
        if cached is not None:
            logger.info(f"Cache'den yüklendi: {query}")
            return cached

        logger.info(f"Google Scholar aranıyor: '{query}'")

        # 1) SerpAPI tercih edilir (daha stabil)
        if self.use_serpapi and self.serpapi_key:
            results = self._search_with_serpapi(query)
            if results:
                self._save_cache(query, results)
                return results
            logger.warning("SerpAPI'den sonuç alınamadı, scholarly fallback deneniyor")

        # 2) scholarly fallback
        results = self._search_with_scholarly(query)
        if results:
            self._save_cache(query, results)
        return results

    def _search_with_serpapi(self, query: str) -> List[Dict[str, Any]]:
        """SerpAPI üzerinden Google Scholar araması."""
        if httpx is None:
            logger.error("httpx kütüphanesi yüklü değil, SerpAPI kullanılamıyor")
            return []

        if not self._can_use_serpapi():
            logger.warning(
                f"SerpAPI aylık istek limiti doldu ({self.serpapi_max_requests_monthly}). "
                "Bu sorgu için scholarly fallback kullanılacak."
            )
            return []

        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google_scholar",
            "q": query,
            "api_key": self.serpapi_key,
            "num": min(self.max_results, 20),
            "hl": "en",
            "as_ylo": self.year_range[0],
            "as_yhi": self.year_range[1],
        }

        results: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            self._increment_serpapi_usage()

            for item in data.get("organic_results", [])[: self.max_results]:
                publication = item.get("publication_info", {})
                summary = publication.get("summary", "")
                year = ""
                if summary:
                    import re
                    m = re.search(r"\b(19|20)\d{2}\b", summary)
                    if m:
                        year = m.group(0)

                results.append({
                    "title": item.get("title", ""),
                    "authors": summary,
                    "year": year,
                    "venue": summary,
                    "abstract": item.get("snippet", ""),
                    "citation_count": item.get("inline_links", {}).get("cited_by", {}).get("total", 0),
                    "url": item.get("link", ""),
                    "eprint_url": item.get("resources", [{}])[0].get("link", "") if item.get("resources") else "",
                    "source": "google_scholar_serpapi",
                    "query": query,
                })

            logger.info(f"Google Scholar (SerpAPI): '{query}' → {len(results)} sonuç")
        except Exception as e:
            logger.error(f"SerpAPI Scholar arama hatası: {e}")

        return results

    def _search_with_scholarly(self, query: str) -> List[Dict[str, Any]]:
        """scholarly kütüphanesi ile fallback arama."""
        if scholarly is None:
            logger.error("scholarly kütüphanesi yüklü değil: pip install scholarly")
            return []

        results = []
        try:
            search_query = scholarly.search_pubs(
                query,
                year_low=self.year_range[0],
                year_high=self.year_range[1],
            )

            for i, pub in enumerate(search_query):
                if i >= self.max_results:
                    break

                bib = pub.get("bib", {})
                result = {
                    "title": bib.get("title", ""),
                    "authors": bib.get("author", ""),
                    "year": bib.get("pub_year", ""),
                    "venue": bib.get("venue", ""),
                    "abstract": bib.get("abstract", ""),
                    "citation_count": pub.get("num_citations", 0),
                    "url": pub.get("pub_url", ""),
                    "eprint_url": pub.get("eprint_url", ""),
                    "source": "google_scholar",
                    "query": query,
                }
                results.append(result)

            logger.info(f"Google Scholar (scholarly): '{query}' → {len(results)} sonuç")
        except Exception as e:
            logger.error(f"Google Scholar arama hatası: {e}")

        return results

    def _check_cache(self, query: str) -> Optional[List[Dict]]:
        """Cache'de sonuç var mı kontrol et."""
        cache_file = self.cache_dir / f"{self._query_hash(query)}.json"
        if cache_file.exists():
            # 24 saatten eski cache'leri kullanma
            import os
            age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
            if age_hours < 24:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None

    def _save_cache(self, query: str, results: List[Dict]):
        """Sonuçları cache'e kaydet."""
        cache_file = self.cache_dir / f"{self._query_hash(query)}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    def _query_hash(self, query: str) -> str:
        """Query'yi hash'e çevir (dosya adı için)."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]

    def _serpapi_usage_file(self) -> Path:
        """Aylık SerpAPI kullanım dosya yolu."""
        ym = datetime.now().strftime("%Y%m")
        return self.cache_dir / f"serpapi_usage_{ym}.json"

    def _load_serpapi_usage(self) -> int:
        """Bu ay yapılan SerpAPI istek sayısını yükle."""
        usage_file = self._serpapi_usage_file()
        if not usage_file.exists():
            return 0
        try:
            with open(usage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(data.get("count", 0)) if isinstance(data, dict) else 0
        except Exception:
            return 0

    def _save_serpapi_usage(self, count: int):
        """Bu ayın SerpAPI kullanımını kaydet."""
        usage_file = self._serpapi_usage_file()
        payload = {
            "month": datetime.now().strftime("%Y-%m"),
            "count": int(count),
        }
        with open(usage_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _can_use_serpapi(self) -> bool:
        """Aylık limit dahilinde SerpAPI çağrısı yapılıp yapılamayacağını kontrol et."""
        used = self._load_serpapi_usage()
        return used < self.serpapi_max_requests_monthly

    def _increment_serpapi_usage(self):
        """SerpAPI aylık kullanım sayacını bir arttır."""
        used = self._load_serpapi_usage() + 1
        self._save_serpapi_usage(used)
