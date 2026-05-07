"""
Patent Scanner - Patent veritabanı tarama ajanı.
Espacenet, Google Patents, TÜRKPATENT ve WIPO'dan patent arar.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from loguru import logger
from rich.console import Console

from agents.orchestrator import Orchestrator

console = Console()


class PatentScanner(Orchestrator):
    """Patent tarama ve analiz ajanı."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)
        self.patent_config = config.get("sources", {}).get("patents", {})
        self.rate_limits = config.get("rate_limits", {})
        self.results: List[Dict[str, Any]] = []

    def run(self) -> List[Dict[str, Any]]:
        """Tüm patent veritabanlarından tarama yap."""
        self.start_time = datetime.now()
        all_patents = []
        keywords = self._get_patent_keywords()

        # 1. Google Patents
        if self.patent_config.get("google_patents", True):
            console.print("  [dim]→ Google Patents taranıyor...[/dim]")
            try:
                from tools.patent_search import PatentSearch
                ps = PatentSearch(self.config)
                
                for kw in keywords:
                    results = ps.search_google_patents(kw)
                    all_patents.extend(results)
                    time.sleep(self.rate_limits.get("patent_delay_sec", 5))
                    
                self.log_step("PatentScanner", "google_patents", "success",
                              f"{len(all_patents)} patent")
            except Exception as e:
                self.log_step("PatentScanner", "google_patents", "error", str(e))
                logger.error(f"Google Patents hatası: {e}")

        # 2. Espacenet
        if self.patent_config.get("espacenet", True):
            console.print("  [dim]→ Espacenet taranıyor...[/dim]")
            try:
                from tools.patent_search import PatentSearch
                ps = PatentSearch(self.config)
                
                for kw in keywords[:3]:
                    results = ps.search_espacenet(kw)
                    all_patents.extend(results)
                    time.sleep(self.rate_limits.get("patent_delay_sec", 5))
                    
                self.log_step("PatentScanner", "espacenet", "success", "Espacenet tarandı")
            except Exception as e:
                self.log_step("PatentScanner", "espacenet", "error", str(e))
                logger.error(f"Espacenet hatası: {e}")

        # 3. WIPO
        if self.patent_config.get("wipo", True):
            console.print("  [dim]→ WIPO taranıyor...[/dim]")
            try:
                from tools.patent_search import PatentSearch
                ps = PatentSearch(self.config)
                
                for kw in keywords[:2]:
                    results = ps.search_wipo(kw)
                    all_patents.extend(results)
                    time.sleep(self.rate_limits.get("patent_delay_sec", 5))
                    
                self.log_step("PatentScanner", "wipo", "success", "WIPO tarandı")
            except Exception as e:
                self.log_step("PatentScanner", "wipo", "error", str(e))
                logger.error(f"WIPO hatası: {e}")

        # 4. TÜRKPATENT
        if self.patent_config.get("turkpatent", True):
            console.print("  [dim]→ TÜRKPATENT taranıyor...[/dim]")
            try:
                from tools.patent_search import PatentSearch
                ps = PatentSearch(self.config)
                
                tr_keywords = self.config.get("research", {}).get("turkish_keywords", [])
                for kw in tr_keywords[:2]:
                    results = ps.search_turkpatent(kw)
                    all_patents.extend(results)
                    time.sleep(self.rate_limits.get("patent_delay_sec", 5))
                    
                self.log_step("PatentScanner", "turkpatent", "success", "TÜRKPATENT tarandı")
            except Exception as e:
                self.log_step("PatentScanner", "turkpatent", "error", str(e))
                logger.error(f"TÜRKPATENT hatası: {e}")

        # Deduplikasyon
        all_patents = self._deduplicate_patents(all_patents)
        
        # Sonuçları kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_results("patents", f"patents_{timestamp}.json", all_patents)
        
        self.results = all_patents
        return all_patents

    def run_incremental(self) -> List[Dict[str, Any]]:
        """Artımlı patent taraması."""
        return self.run()

    def _get_patent_keywords(self) -> List[str]:
        """config.yaml'daki patent sorgularını getir."""
        # Yeni format: search_queries.patents
        queries = self.config.get("search_queries", {}).get("patents", [])
        if queries:
            return queries
        # Fallback: hardcoded
        return [
            "multi-agent electric vehicle charging system",
            "smart charging load negotiation",
            "EV fleet charging optimization",
            "distributed EV charging coordination",
            "AI-based electric vehicle charging management",
            "battery health aware charging system",
            "electric vehicle grid load balancing",
            "autonomous charging scheduling system",
            "vehicle-to-grid energy trading platform",
            "intelligent power distribution electric vehicles",
        ]

    def _deduplicate_patents(self, patents: List[Dict]) -> List[Dict]:
        """Patent numarasına veya başlığa göre deduplikasyon."""
        seen = set()
        unique = []
        for p in patents:
            key = p.get("patent_number", "") or p.get("title", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
