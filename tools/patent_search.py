"""
Patent Search - Çoklu patent veritabanı arama aracı.
Google Patents, Espacenet, WIPO ve TÜRKPATENT destekler.
"""

import json
import time
from typing import Dict, List, Any
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class PatentSearch:
    """Çoklu patent veritabanı arama aracı."""

    def __init__(self, config: dict):
        self.config = config
        self.rate_limits = config.get("rate_limits", {})
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ThesisResearchBot/1.0)"
        }

    def search_google_patents(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Google Patents'te arama yap."""
        if httpx is None:
            logger.error("httpx yüklü değil")
            return []

        results = []
        url = "https://patents.google.com/xhr/query"
        params = {
            "url": f"q={query}&oq={query}&num={max_results}&type=PATENT",
        }

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                resp = client.get(
                    f"https://patents.google.com/?q={query}&oq={query}&num={max_results}",
                )
                
                if BeautifulSoup and resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    for item in soup.select("search-result-item, article"):
                        title_el = item.select_one("h3, .result-title, span.style-scope")
                        patent_id_el = item.select_one("a[href*='patent']")
                        
                        title = title_el.get_text(strip=True) if title_el else ""
                        patent_url = ""
                        patent_number = ""
                        
                        if patent_id_el:
                            href = patent_id_el.get("href", "")
                            patent_url = f"https://patents.google.com{href}" if href.startswith("/") else href
                            patent_number = href.split("/")[-1] if "/" in href else ""
                        
                        if title:
                            results.append({
                                "title": title,
                                "patent_number": patent_number,
                                "url": patent_url,
                                "source": "google_patents",
                                "query": query,
                            })

            logger.info(f"Google Patents: '{query}' → {len(results)} sonuç")
        except Exception as e:
            logger.error(f"Google Patents hatası: {e}")

        return results

    def search_espacenet(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Espacenet OPS API ile arama yap."""
        if httpx is None:
            return []

        results = []
        # Espacenet Open Patent Services (OPS) API
        url = "https://ops.epo.org/3.2/rest-services/published-data/search"
        params = {
            "q": f'ta="{query}"',
            "Range": f"1-{max_results}",
        }

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                resp = client.get(url, params=params)
                
                if resp.status_code == 200:
                    # XML parse (basitleştirilmiş)
                    text = resp.text
                    # TODO: Tam XML parsing implementasyonu
                    logger.info(f"Espacenet yanıt alındı: {len(text)} bytes")
                elif resp.status_code == 403:
                    logger.warning("Espacenet: API erişimi reddedildi (auth gerekebilir)")
                else:
                    logger.warning(f"Espacenet: HTTP {resp.status_code}")

        except Exception as e:
            logger.error(f"Espacenet hatası: {e}")

        return results

    def search_wipo(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """WIPO PATENTSCOPE'ta arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://patentscope.wipo.int/search/en/search.jsf"

        try:
            with httpx.Client(timeout=30, headers=self.headers, follow_redirects=True) as client:
                resp = client.get(url, params={"query": query})
                
                if BeautifulSoup and resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    for item in soup.select(".ps-patent-result, .resultRow"):
                        title_el = item.select_one(".resultTitle, h3, a")
                        title = title_el.get_text(strip=True) if title_el else ""
                        
                        if title:
                            results.append({
                                "title": title,
                                "source": "wipo",
                                "query": query,
                            })

            logger.info(f"WIPO: '{query}' → {len(results)} sonuç")
        except Exception as e:
            logger.error(f"WIPO hatası: {e}")

        return results

    def search_turkpatent(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """TÜRKPATENT veritabanında arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://www.turkpatent.gov.tr/arama"

        try:
            with httpx.Client(timeout=30, headers=self.headers, follow_redirects=True) as client:
                resp = client.get(url, params={"q": query})
                
                if BeautifulSoup and resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    for item in soup.select(".search-result, .patent-item, tr"):
                        title_el = item.select_one("td:nth-child(2), .title, a")
                        title = title_el.get_text(strip=True) if title_el else ""
                        
                        if title and len(title) > 10:
                            results.append({
                                "title": title,
                                "source": "turkpatent",
                                "query": query,
                            })

            logger.info(f"TÜRKPATENT: '{query}' → {len(results)} sonuç")
        except Exception as e:
            logger.error(f"TÜRKPATENT hatası: {e}")

        return results
