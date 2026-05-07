"""
Dataset Hunter - Veri seti keşif ajanı.
Kaggle, UCI, HuggingFace, Zenodo, IEEE DataPort ve OpenML'den veri seti arar.
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


class DatasetHunter(Orchestrator):
    """Veri seti keşif ve kataloglama ajanı."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)
        self.dataset_config = config.get("sources", {}).get("datasets", {})
        self.results: List[Dict[str, Any]] = []

    def run(self) -> List[Dict[str, Any]]:
        """Tüm veri seti platformlarından tarama yap."""
        self.start_time = datetime.now()
        all_datasets = []
        keywords = self._get_dataset_keywords()

        # 1. HuggingFace Datasets
        if self.dataset_config.get("huggingface", True):
            self._scan_source(all_datasets, "huggingface", "HuggingFace Datasets taranıyor...", "search_huggingface", keywords)

        # 2. Kaggle
        if self.dataset_config.get("kaggle", True):
            self._scan_source(all_datasets, "kaggle", "Kaggle taranıyor...", "search_kaggle", keywords)

        # 3. Zenodo
        if self.dataset_config.get("zenodo", True):
            self._scan_source(all_datasets, "zenodo", "Zenodo taranıyor...", "search_zenodo", keywords[:3])

        # 4. UCI ML Repository
        if self.dataset_config.get("uci", True):
            self._scan_source(all_datasets, "uci", "UCI ML Repository taranıyor...", "search_uci", keywords[:2])

        # 5. OpenML
        if self.dataset_config.get("openml", True):
            self._scan_source(all_datasets, "openml", "OpenML taranıyor...", "search_openml", keywords[:2])

        # 6. Papers With Code
        if self.dataset_config.get("papers_with_code", True):
            self._scan_source(all_datasets, "papers_with_code", "Papers With Code taranıyor...", "search_papers_with_code", keywords[:3])

        # 7. IEEE DataPort
        if self.dataset_config.get("ieee_dataport", True):
            self._scan_source(all_datasets, "ieee_dataport", "IEEE DataPort taranıyor...", "search_ieee_dataport", keywords[:2])

        # 8. Figshare
        if self.dataset_config.get("figshare", True):
            self._scan_source(all_datasets, "figshare", "Figshare taranıyor...", "search_figshare", keywords[:3])

        # 9. Mendeley Data
        if self.dataset_config.get("mendeley", True):
            self._scan_source(all_datasets, "mendeley", "Mendeley Data taranıyor...", "search_mendeley", keywords[:2])

        # Deduplikasyon
        all_datasets = self._deduplicate_datasets(all_datasets)
        
        # Sonuçları kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_results("datasets_catalog", f"datasets_{timestamp}.json", all_datasets)
        
        # LLM ile veri seti uygunluk analizi
        if all_datasets:
            self._analyze_relevance(all_datasets)
        
        self.results = all_datasets
        return all_datasets

    def _scan_source(self, all_datasets: List[Dict[str, Any]], source_key: str, label: str, method_name: str, keywords: List[str]):
        """Tek kaynak taramasını yürüt ve 0 sonucu warning olarak logla."""
        console.print(f"  [dim]→ {label}[/dim]")
        try:
            from tools.dataset_search import DatasetSearch
            ds = DatasetSearch(self.config)
            source_count = 0

            for kw in keywords:
                method = getattr(ds, method_name)
                results = method(kw)
                source_count += len(results)
                all_datasets.extend(results)
                time.sleep(2)

            status = "success" if source_count > 0 else "warning"
            details = f"{source_count} sonuç" if source_count > 0 else "0 sonuç"
            self.log_step("DatasetHunter", source_key, status, details)
        except Exception as e:
            self.log_step("DatasetHunter", source_key, "error", str(e))
            logger.error(f"{source_key} hatası: {e}")

    def run_incremental(self) -> List[Dict[str, Any]]:
        """Artımlı veri seti taraması."""
        return self.run()

    def _get_dataset_keywords(self) -> List[str]:
        """config.yaml'daki veri seti sorgularını getir."""
        # Yeni format: search_queries.datasets
        queries = self.config.get("search_queries", {}).get("datasets", [])
        if queries:
            return queries
        # Fallback: hardcoded
        return [
            "electric vehicle charging dataset",
            "EV charging station dataset",
            "smart grid load dataset",
            "battery degradation dataset",
            "EV charging demand dataset",
            "building energy consumption EV",
            "electric vehicle battery dataset",
            "power grid demand response dataset",
            "EV fleet charging data",
            "renewable energy grid dataset",
        ]

    def _deduplicate_datasets(self, datasets: List[Dict]) -> List[Dict]:
        """Veri seti adına göre deduplikasyon."""
        seen = set()
        unique = []
        for d in datasets:
            key = d.get("name", "").lower().strip() or d.get("title", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(d)
        return unique

    def _analyze_relevance(self, datasets: List[Dict]):
        """LLM ile veri setlerinin tez konusuna uygunluğunu analiz et."""
        try:
            system_prompt = self.llm.load_system_prompt(
                "dataset_hunter_system", self.project_root
            )
            
            summaries = []
            for d in datasets[:20]:
                summaries.append({
                    "name": d.get("name", d.get("title", "")),
                    "description": d.get("description", "")[:200],
                    "source": d.get("source", ""),
                })
            
            prompt = (
                "Aşağıdaki veri setlerini 'Multi-Agent Grid Load Negotiation for EV Charging' "
                "tez konusuna uygunluğuna göre 1-5 puan ver. JSON array döndür:\n\n"
                + json.dumps(summaries, ensure_ascii=False)
            )
            
            self.llm.generate_json(prompt, system_prompt)
            logger.info("Veri seti uygunluk analizi tamamlandı")
        except Exception as e:
            logger.warning(f"Uygunluk analizi atlandı: {e}")
