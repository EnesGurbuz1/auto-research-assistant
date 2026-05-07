"""
Trend Detection - Araştırma trendlerini tespit etme becerisi.
Danışman sorusu: "2-3 yıl önce ile bugün arasında ne değişti?"
"""

import json
from typing import Dict, List, Any
from loguru import logger
from agents.llm_interface import LLMInterface


class TrendDetection:
    """Araştırma alanındaki trendleri ve değişimleri tespit eder."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)

    def detect(self, papers: List[Dict]) -> Dict[str, Any]:
        """Yıllara göre trend analizi yap."""
        
        # Yıla göre grupla
        by_year = {}
        for p in papers:
            year = str(p.get("year", "unknown"))
            if year not in by_year:
                by_year[year] = []
            by_year[year].append({
                "title": p.get("title", ""),
                "abstract": (p.get("abstract", "") or "")[:200],
            })

        prompt = f"""Aşağıdaki makaleleri yıllara göre analiz et.
"Multi-Agent EV Charging" alanında trendleri tespit et.

YILLARA GÖRE MAKALELER:
{json.dumps(by_year, ensure_ascii=False)}

Şu formatta JSON döndür:
{{
    "yearly_focus": {{
        "2020-2022": ["trend1", "trend2"],
        "2023-2024": ["trend1", "trend2"],
        "2025-2026": ["trend1", "trend2"]
    }},
    "rising_methods": [
        {{"method": "...", "adoption_rate": "increasing|stable|decreasing"}}
    ],
    "declining_approaches": ["..."],
    "breakthrough_technologies": [
        {{"technology": "...", "impact": "...", "first_seen": "..."}}
    ],
    "publication_volume_trend": "increasing|stable|decreasing",
    "key_insight": "..."
}}"""

        try:
            result = self.llm.generate_json(prompt)
            logger.info("Trend tespiti tamamlandı")
            return result
        except Exception as e:
            logger.error(f"Trend tespiti hatası: {e}")
            return {"error": str(e)}
