"""
Dataset Search - Çoklu veri seti platformu arama aracı.
HuggingFace, Kaggle, Zenodo, UCI, IEEE DataPort ve OpenML destekler.
"""

import json
import time
from json import JSONDecodeError
from urllib.parse import quote_plus
from typing import Dict, List, Any
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None


class DatasetSearch:
    """Çoklu platform veri seti arama aracı."""

    def __init__(self, config: dict):
        self.config = config
        self.figshare_token = self.config.get("api_keys", {}).get("figshare")
        self.figshare_token = self.figshare_token or __import__("os").getenv("FIGSHARE_TOKEN", "")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

    def _query_variants(self, query: str) -> List[str]:
        """Uzun sorgular için kısa/fallback varyantlar üret."""
        cleaned = query.lower().strip()
        variants = [query]

        replacements = {
            "electric vehicle": "ev",
            "dataset": "",
            "data": "",
            "multi-agent": "multi agent",
        }
        compact = cleaned
        for old, new in replacements.items():
            compact = compact.replace(old, new)
        compact = " ".join(compact.split())
        if compact and compact not in variants:
            variants.append(compact)

        tokens = [t for t in compact.replace("-", " ").split() if len(t) > 2]
        token_fallbacks = [
            "ev charging",
            "smart grid",
            "energy",
            "battery",
        ]
        if len(tokens) >= 2:
            token_fallbacks.insert(0, " ".join(tokens[:2]))
        if tokens:
            token_fallbacks.insert(1, tokens[0])

        for v in token_fallbacks:
            v = v.strip()
            if v and v not in variants:
                variants.append(v)

        return variants[:5]

    def _matches_query(self, text: str, query: str, min_hits: int = 1) -> bool:
        """Metnin sorgu ile temel eşleşmesini kontrol et."""
        if not text:
            return False
        hay = text.lower()
        q_tokens = [t for t in query.lower().replace("-", " ").split() if len(t) > 2]
        if not q_tokens:
            return False
        hits = sum(1 for t in q_tokens if t in hay)
        return hits >= min_hits

    def search_huggingface(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """HuggingFace Datasets Hub'da arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://huggingface.co/api/datasets"
        params = {
            "search": query,
            "limit": max_results,
            "sort": "downloads",
            "direction": "-1",
        }

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                for variant in self._query_variants(query):
                    params["search"] = variant
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                    for ds in data:
                        results.append({
                            "name": ds.get("id", ""),
                            "title": ds.get("id", "").split("/")[-1],
                            "description": ds.get("description", "")[:500],
                            "downloads": ds.get("downloads", 0),
                            "likes": ds.get("likes", 0),
                            "tags": ds.get("tags", []),
                            "url": f"https://huggingface.co/datasets/{ds.get('id', '')}",
                            "source": "huggingface",
                            "query": query,
                        })
                    if results:
                        break

            logger.info(f"HuggingFace: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"HuggingFace hatası: {e}")

        return results

    def search_kaggle(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Kaggle Datasets'te arama yap (API key opsiyonel)."""
        if httpx is None:
            return []

        results = []
        # Kaggle public API
        url = "https://www.kaggle.com/api/v1/datasets/list"
        params = {
            "search": query,
            "maxSize": max_results,
            "sortBy": "relevance",
        }

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                for variant in self._query_variants(query):
                    params["search"] = variant
                    resp = client.get(url, params=params)
                    if resp.status_code != 200:
                        logger.warning(f"Kaggle API: HTTP {resp.status_code} ({variant})")
                        continue

                    try:
                        data = resp.json()
                    except JSONDecodeError:
                        logger.warning(f"Kaggle JSON parse hatası, olası anti-bot yanıtı ({variant})")
                        continue

                    for ds in data:
                        results.append({
                            "name": ds.get("ref", ""),
                            "title": ds.get("title", ""),
                            "description": ds.get("subtitle", ""),
                            "size": ds.get("totalBytes", 0),
                            "download_count": ds.get("downloadCount", 0),
                            "vote_count": ds.get("voteCount", 0),
                            "url": f"https://www.kaggle.com/datasets/{ds.get('ref', '')}",
                            "source": "kaggle",
                            "query": query,
                        })
                    if results:
                        break

                if not results:
                    logger.warning("Kaggle sonucu boş. HuggingFace fallback uygulanıyor.")
                    fallback = self.search_huggingface(query, max_results=max_results)
                    for item in fallback:
                        cloned = dict(item)
                        cloned["source"] = "kaggle_fallback"
                        results.append(cloned)
                        if len(results) >= max_results:
                            break

            logger.info(f"Kaggle: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"Kaggle hatası: {e}")

        return results

    def search_zenodo(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Zenodo'da veri seti arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://zenodo.org/api/records"
        params = {
            "q": query,
            "type": "dataset",
            "size": max_results,
            "sort": "mostrecent",
        }

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 403:
                    logger.warning("Zenodo API erişimi engellendi (HTTP 403). Mendeley fallback uygulanıyor.")
                    fallback = self.search_mendeley(query, max_results=max_results)
                    for item in fallback:
                        cloned = dict(item)
                        cloned["source"] = "zenodo_fallback"
                        results.append(cloned)
                    logger.info(f"Zenodo: '{query}' → {len(results)} veri seti (fallback)")
                    return results
                resp.raise_for_status()
                data = resp.json()

            for hit in data.get("hits", {}).get("hits", []):
                meta = hit.get("metadata", {})
                results.append({
                    "name": meta.get("title", ""),
                    "title": meta.get("title", ""),
                    "description": meta.get("description", "")[:500],
                    "doi": meta.get("doi", ""),
                    "created": meta.get("publication_date", ""),
                    "authors": ", ".join(
                        c.get("name", "") for c in meta.get("creators", [])[:5]
                    ),
                    "url": hit.get("links", {}).get("html", ""),
                    "source": "zenodo",
                    "query": query,
                })

            logger.info(f"Zenodo: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"Zenodo hatası: {e}")

        return results

    def search_uci(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """UCI ML Repository'de arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://archive.ics.uci.edu/datasets"

        try:
            from bs4 import BeautifulSoup

            with httpx.Client(timeout=30, headers=self.headers, follow_redirects=True) as client:
                seen = set()
                for variant in self._query_variants(query):
                    resp = client.get(url, params={"search": variant})
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select("a[href^='/dataset/']"):
                        href = a.get("href", "")
                        title = a.get_text(strip=True)
                        if not href or not title:
                            continue
                        key = f"{href}|{title}".lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append({
                            "name": title,
                            "title": title,
                            "description": "",
                            "url": f"https://archive.ics.uci.edu{href}",
                            "source": "uci",
                            "query": query,
                        })
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break

            logger.info(f"UCI: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"UCI hatası: {e}")

        return results

    def search_openml(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """OpenML'de veri seti arama yap."""
        if httpx is None:
            return []

        results = []
        url = "https://www.openml.org/api/v1/json/data/list"

        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                query_variants = self._query_variants(query)
                domain_terms = ["energy", "electric", "electrical", "electricity", "ev", "grid", "charging", "power", "load"]

                # OpenML arama endpointi kısıtlı olduğu için sayfalı tarama + metin eşleşmesi.
                for offset in (0, 500, 1000, 2000, 5000):
                    resp = client.get(url, params={"limit": 500, "offset": offset})
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    datasets = data.get("data", {}).get("dataset", [])

                    for ds in datasets:
                        title = ds.get("name", "")
                        matches_query = any(self._matches_query(title, q, min_hits=1) for q in query_variants)
                        matches_domain = any(term in title.lower() for term in domain_terms)
                        if not (matches_query or matches_domain):
                            continue
                        results.append({
                            "name": title,
                            "title": title,
                            "description": "",
                            "instances": ds.get("NumberOfInstances", 0),
                            "features": ds.get("NumberOfFeatures", 0),
                            "url": f"https://www.openml.org/d/{ds.get('did', '')}",
                            "source": "openml",
                            "query": query,
                        })
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break

            logger.info(f"OpenML: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"OpenML hatası: {e}")

        return results

    def search_papers_with_code(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Papers With Code API ile veri seti arama."""
        if httpx is None:
            return []

        results = []
        url = f"https://paperswithcode.com/datasets?q={quote_plus(query)}"

        try:
            from bs4 import BeautifulSoup

            with httpx.Client(timeout=30, headers=self.headers, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select("a[href*='/dataset/']"):
                        href = a.get("href", "")
                        title = a.get_text(strip=True)
                        if not href or not title:
                            continue
                        results.append({
                            "name": title,
                            "title": title,
                            "description": "",
                            "url": f"https://paperswithcode.com{href}" if href.startswith("/") else href,
                            "source": "papers_with_code",
                            "query": query,
                        })
                        if len(results) >= max_results:
                            break
                if not results:
                    # PWC endpointi bazı ortamlarda HuggingFace sayfasına yönleniyor.
                    logger.warning("PWC doğrudan parse edilemedi, HuggingFace fallback uygulanıyor.")
                    fallback = self.search_huggingface(query, max_results=max_results)
                    for item in fallback:
                        cloned = dict(item)
                        cloned["source"] = "papers_with_code_fallback"
                        results.append(cloned)
                        if len(results) >= max_results:
                            break
            logger.info(f"Papers With Code: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"Papers With Code hatası: {e}")

        return results

    def search_ieee_dataport(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """IEEE DataPort'ta veri seti arama."""
        if httpx is None:
            return []

        results = []
        url = "https://ieee-dataport.org/search"

        try:
            search_url = f"{url}?query={quote_plus(query)}"
            with httpx.Client(timeout=30, headers=self.headers, follow_redirects=True) as client:
                resp = client.get(search_url)
                if resp.status_code == 200:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for item in soup.select(".search-result, .views-row, article, .node"):
                            title_el = item.select_one("h2 a, h3 a, .node-title a, a")
                            title = title_el.get_text(strip=True) if title_el else ""
                            link = ""
                            if title_el and title_el.get("href"):
                                href = title_el["href"]
                                link = f"https://ieee-dataport.org{href}" if href.startswith("/") else href
                            if title and len(title) > 5 and "dataset" in link:
                                results.append({
                                    "name": title,
                                    "title": title,
                                    "url": link,
                                    "source": "ieee_dataport",
                                    "query": query,
                                })
                                if len(results) >= max_results:
                                    break
                    except ImportError:
                        logger.warning("BeautifulSoup yüklü değil, IEEE DataPort parse edilemiyor")
            logger.info(f"IEEE DataPort: '{query}' → {len(results)} veri seti")
        except Exception as e:
            logger.error(f"IEEE DataPort hatası: {e}")

        return results

    def search_figshare(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Figshare API aracılığıyla veri seti arama."""
        if httpx is None:
            return []
        
        results = []
        url = "https://api.figshare.com/v2/articles/search"
        data = {
            "search_for": query,
            "item_type": 3,
            "limit": max_results
        }
        
        try:
            figshare_headers = dict(self.headers)
            if self.figshare_token:
                figshare_headers["Authorization"] = f"token {self.figshare_token}"

            with httpx.Client(timeout=30, headers=figshare_headers) as client:
                resp = client.post(url, json=data)
                if resp.status_code == 403:
                    logger.warning("Figshare erişimi engellendi (HTTP 403). Bu kaynak için API token/proxy gerekebilir.")
                    fallback = self.search_mendeley(query, max_results=max_results)
                    for item in fallback:
                        cloned = dict(item)
                        cloned["source"] = "figshare_fallback"
                        results.append(cloned)
                    return results
                if resp.status_code == 200:
                    for item in resp.json()[:max_results]:
                        results.append({
                            "name": item.get("title", ""),
                            "title": item.get("title", ""),
                            "description": "",
                            "url": item.get("url_public_html", ""),
                            "doi": item.get("doi", ""),
                            "source": "figshare",
                            "query": query
                        })
            logger.info(f"Figshare: '{query}' -> {len(results)} sonuç")
        except Exception as e:
            logger.error(f"Figshare arama hatası: {e}")
            
        return results

    def search_mendeley(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Mendeley Data arama."""
        if httpx is None:
            return []
            
        results = []
        url = "https://data.mendeley.com/api/datasets"
        
        try:
            with httpx.Client(timeout=30, headers=self.headers) as client:
                resp = client.get(url, params={"query": query, "limit": max_results})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", {}).get("results", []) if isinstance(data, dict) else data
                    if isinstance(items, dict):
                        items = list(items.values())
                    for ds in items[:max_results]:
                        version = ds.get("versions", [{}])[0] if isinstance(ds, dict) else {}
                        results.append({
                            "name": version.get("name", ds.get("name", "")) if isinstance(ds, dict) else "",
                            "title": version.get("name", ds.get("name", "")) if isinstance(ds, dict) else "",
                            "description": version.get("description", "")[:500] if isinstance(ds, dict) else "",
                            "url": f"https://data.mendeley.com/datasets/{ds.get('id', '')}" if isinstance(ds, dict) else "",
                            "source": "mendeley",
                            "query": query
                        })
            logger.info(f"Mendeley: '{query}' -> {len(results)} sonuç")
        except Exception as e:
            logger.error(f"Mendeley Data arama hatası: {e}")
            
        return results
