"""
arXiv Search - arXiv API ile preprint araması.
Resmi arXiv API kullanır, rate limit: 3 req/sec (bekleme ile).
"""

import time
from typing import Dict, List, Any, Optional
from loguru import logger

try:
    import arxiv
except ImportError:
    arxiv = None


class ArxivSearch:
    """arXiv arama aracı."""

    def __init__(self, config: dict):
        self.config = config.get("sources", {}).get("arxiv", {})
        self.max_results = self.config.get("max_results_per_query", 30)
        self.categories = self.config.get("categories", ["cs.MA", "cs.AI", "eess.SY", "cs.LG"])

    def search(self, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """arXiv'de arama yap."""
        if arxiv is None:
            logger.error("arxiv kütüphanesi yüklü değil: pip install arxiv")
            return []

        max_results = limit or self.max_results
        results = []

        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            for paper in client.results(search):
                # Kategori filtresi (opsiyonel)
                paper_cats = [c for c in paper.categories]
                
                result = {
                    "title": paper.title,
                    "authors": ", ".join(a.name for a in paper.authors[:5]),
                    "year": paper.published.year if paper.published else "",
                    "published": paper.published.isoformat() if paper.published else "",
                    "abstract": paper.summary[:500] if paper.summary else "",
                    "categories": paper_cats,
                    "arxiv_id": paper.entry_id.split("/")[-1] if paper.entry_id else "",
                    "pdf_url": paper.pdf_url or "",
                    "doi": paper.doi or "",
                    "citation_count": 0,  # arXiv API citation vermez
                    "source": "arxiv",
                    "query": query,
                }
                results.append(result)

            logger.info(f"arXiv: '{query}' → {len(results)} sonuç")

        except Exception as e:
            logger.error(f"arXiv arama hatası: {e}")

        return results

    def search_by_category(self, category: str = "cs.MA", max_results: int = 20) -> List[Dict]:
        """Belirli bir kategoride son makaleleri getir."""
        query = f"cat:{category} AND (electric vehicle OR EV charging OR multi-agent)"
        return self.search(query, limit=max_results)

    def get_paper_by_id(self, arxiv_id: str) -> Optional[Dict]:
        """arXiv ID ile makale detayını getir."""
        if arxiv is None:
            return None

        try:
            client = arxiv.Client()
            search = arxiv.Search(id_list=[arxiv_id])
            paper = next(client.results(search), None)
            
            if paper:
                return {
                    "title": paper.title,
                    "authors": ", ".join(a.name for a in paper.authors),
                    "abstract": paper.summary,
                    "pdf_url": paper.pdf_url,
                    "published": paper.published.isoformat() if paper.published else "",
                    "categories": list(paper.categories),
                }
        except Exception as e:
            logger.error(f"arXiv paper detay hatası ({arxiv_id}): {e}")
        
        return None
