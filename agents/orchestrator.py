"""
Orchestrator - Temel orkestrasyon sınıfı.
Ajanlar arası koordinasyonu sağlar.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
from rich.console import Console

from agents.llm_interface import LLMInterface

console = Console()


class Orchestrator:
    """Temel orkestrasyon sınıfı - ajanlar arası iş akışını yönetir."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.llm = LLMInterface(config)
        self.run_log: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime] = None

    def log_step(self, agent: str, action: str, status: str, details: str = ""):
        """Her adımı logla."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "action": action,
            "status": status,
            "details": details,
        }
        self.run_log.append(entry)
        logger.info(f"[{agent}] {action}: {status} — {details}")

    def save_run_log(self):
        """Çalışma logunu kaydet."""
        log_dir = self.project_root / "logs" / "agent_runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"run_{timestamp}.json"
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self.run_log, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Çalışma logu kaydedildi: {log_file}")

    def get_keywords(self) -> List[str]:
        """Konfigürasyondaki anahtar kelimeleri getir."""
        research = self.config.get("research", {})
        keywords = []
        keywords.extend(research.get("primary_keywords", []))
        keywords.extend(research.get("survey_keywords", []))
        return keywords

    def get_survey_keywords(self) -> List[str]:
        """Survey/review odaklı anahtar kelimeleri getir."""
        return self.config.get("research", {}).get("survey_keywords", [])

    def save_results(self, subdir: str, filename: str, data: Any):
        """Sonuçları JSON olarak kaydet."""
        output_dir = self.project_root / "data" / subdir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Sonuçlar kaydedildi: {output_file}")
        return output_file
