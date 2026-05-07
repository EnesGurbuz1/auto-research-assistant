"""
Literature Scout - Akademik literatür tarama ajanı.
Google Scholar, Semantic Scholar, arXiv ve Scopus'tan makale arar.
Survey/review makalelerine öncelik verir.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
from rich.console import Console

from agents.orchestrator import Orchestrator

console = Console()


class LiteratureScout(Orchestrator):
    """Akademik literatür tarama ajanı."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)
        self.sources_config = config.get("sources", {})
        self.rate_limits = config.get("rate_limits", {})
        self.results: List[Dict[str, Any]] = []

    def run(self) -> List[Dict[str, Any]]:
        """Tüm kaynaklardan literatür taraması yap."""
        self.start_time = datetime.now()
        all_results = []

        # 1. Semantic Scholar (en güvenilir API)
        if self.sources_config.get("semantic_scholar", {}).get("enabled", True):
            console.print("  [dim]→ Semantic Scholar taranıyor...[/dim]")
            try:
                from tools.semantic_scholar_api import SemanticScholarSearch
                ss = SemanticScholarSearch(self.config)
                
                # API key yoksa sorgu sayısını sınırla (10 req/5 min limit)
                if ss.has_api_key:
                    survey_kws = self.get_survey_keywords()
                    primary_kws = self.get_keywords()[:5]
                    delay = 1
                else:
                    survey_kws = self.get_survey_keywords()[:2]
                    primary_kws = self.get_keywords()[:2]
                    delay = 35  # ~10 req/5 min → 30s arası güvenli
                    console.print("  [dim yellow]⚠ S2 API key yok, sorgu sayısı azaltıldı[/dim yellow]")
                
                for keyword in survey_kws:
                    results = ss.search(keyword)
                    all_results.extend(results)
                    time.sleep(delay)
                
                for keyword in primary_kws:
                    results = ss.search(keyword)
                    all_results.extend(results)
                    time.sleep(delay)
                    
                self.log_step("LiteratureScout", "semantic_scholar", "success",
                              f"{len(all_results)} sonuç")
            except Exception as e:
                self.log_step("LiteratureScout", "semantic_scholar", "error", str(e))
                logger.error(f"Semantic Scholar hatası: {e}")

        # 2. arXiv
        if self.sources_config.get("arxiv", {}).get("enabled", True):
            console.print("  [dim]→ arXiv taranıyor...[/dim]")
            try:
                from tools.arxiv_search import ArxivSearch
                arxiv = ArxivSearch(self.config)
                
                for keyword in self.get_keywords()[:5]:
                    results = arxiv.search(keyword)
                    all_results.extend(results)
                    delay = self.rate_limits.get("arxiv_delay_sec", 3)
                    time.sleep(delay)
                    
                self.log_step("LiteratureScout", "arxiv", "success",
                              f"arXiv sonuçları eklendi")
            except Exception as e:
                self.log_step("LiteratureScout", "arxiv", "error", str(e))
                logger.error(f"arXiv hatası: {e}")

        # 3. Google Scholar (rate limit dikkatli)
        if self.sources_config.get("scholar", {}).get("enabled", True):
            console.print("  [dim]→ Google Scholar taranıyor...[/dim]")
            try:
                from tools.scholar_search import ScholarSearch
                scholar = ScholarSearch(self.config)
                
                for keyword in self.get_survey_keywords()[:3]:
                    results = scholar.search(keyword)
                    all_results.extend(results)
                    delay = self.rate_limits.get("scholar_delay_sec", 15)
                    time.sleep(delay)
                    
                self.log_step("LiteratureScout", "scholar", "success",
                              f"Scholar sonuçları eklendi")
            except Exception as e:
                self.log_step("LiteratureScout", "scholar", "error", str(e))
                logger.error(f"Google Scholar hatası: {e}")

        # 4. Scopus
        if self.sources_config.get("scopus", {}).get("enabled", True):
            console.print("  [dim]→ Scopus taranıyor...[/dim]")
            try:
                from tools.scopus_search import ScopusSearch
                scopus = ScopusSearch(self.config)
                
                for keyword in self.get_keywords()[:3]:
                    results = scopus.search(keyword)
                    all_results.extend(results)
                    time.sleep(2)
                    
                self.log_step("LiteratureScout", "scopus", "success",
                              f"Scopus sonuçları eklendi")
            except Exception as e:
                self.log_step("LiteratureScout", "scopus", "error", str(e))
                logger.error(f"Scopus hatası: {e}")

        # Deduplikasyon
        all_results = self._deduplicate(all_results)
        
        # Sonuçları kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_results(
            "papers/scholar_results",
            f"literature_scan_{timestamp}.json",
            all_results
        )
        
        # LLM ile survey/review sınıflandırması
        if all_results:
            self._classify_surveys(all_results)
        
        self.results = all_results
        return all_results

    def run_incremental(self) -> List[Dict[str, Any]]:
        """Sadece yeni sonuçları topla (öncekilerle karşılaştır)."""
        existing = self._load_existing_results()
        existing_titles = {r.get("title", "").lower() for r in existing}
        
        new_results = self.run()
        truly_new = [r for r in new_results if r.get("title", "").lower() not in existing_titles]
        
        if truly_new:
            logger.info(f"{len(truly_new)} yeni sonuç bulundu (toplam {len(new_results)} içinden)")
        
        return truly_new

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        """Başlığa göre deduplikasyon yap."""
        seen = set()
        unique = []
        for r in results:
            title_key = r.get("title", "").lower().strip()
            if title_key and title_key not in seen:
                seen.add(title_key)
                unique.append(r)
        logger.info(f"Deduplikasyon: {len(results)} → {len(unique)}")
        return unique

    def _classify_surveys(self, results: List[Dict]):
        """LLM ile sonuçları survey/review vs orijinal araştırma olarak sınıflandır."""
        try:
            system_prompt = self.llm.load_system_prompt(
                "literature_scout_system", self.project_root
            )
            
            titles = [r.get("title", "") for r in results[:30]]
            prompt = (
                "Aşağıdaki makale başlıklarını 'survey', 'review', veya 'original' "
                "olarak sınıflandır. JSON array döndür:\n\n"
                + json.dumps(titles, ensure_ascii=False)
            )
            
            classifications = self.llm.generate_json(prompt, system_prompt)
            logger.info(f"Sınıflandırma tamamlandı: {len(classifications)} makale")
        except Exception as e:
            logger.warning(f"Sınıflandırma atlandı: {e}")

    def _load_existing_results(self) -> List[Dict]:
        """Mevcut sonuçları yükle."""
        results_dir = self.project_root / "data" / "papers" / "scholar_results"
        all_results = []
        
        if results_dir.exists():
            for f in sorted(results_dir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                        if isinstance(data, list):
                            all_results.extend(data)
                except Exception:
                    continue
        
        return all_results
