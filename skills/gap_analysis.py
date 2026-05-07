"""
Gap Analysis - Literatürdeki boşlukları tespit etme becerisi.
Danışman sorusu: "Bu alanda çözülmüş ne var, çözülmemiş ne var?"
"""

import json
from typing import Dict, List, Any
from loguru import logger
from agents.llm_interface import LLMInterface


class GapAnalysis:
    """Araştırma alanındaki boşlukları (gap) tespit eder."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)

    def analyze(self, papers: List[Dict], patents: List[Dict] = None) -> Dict[str, Any]:
        """Literatür ve patentlerden gap analizi yap."""
        
        # Makaleleri özetle
        paper_summaries = []
        for p in papers[:30]:
            paper_summaries.append({
                "title": p.get("title", ""),
                "year": p.get("year", ""),
                "abstract": (p.get("abstract", "") or "")[:300],
            })

        patent_summaries = []
        if patents:
            for pt in patents[:15]:
                patent_summaries.append({
                    "title": pt.get("title", ""),
                    "patent_number": pt.get("patent_number", ""),
                })

        prompt = f"""Aşağıdaki akademik çalışmaları ve patentleri analiz et.
"Multi-Agent Grid Load Negotiation for EV Charging" alanında gap analizi yap.

MAKALELER:
{json.dumps(paper_summaries, ensure_ascii=False)}

PATENTLER:
{json.dumps(patent_summaries, ensure_ascii=False)}

Şu formatta JSON döndür:
{{
    "solved_problems": [
        {{"problem": "...", "evidence": "...", "maturity": "high|medium|low"}}
    ],
    "unsolved_problems": [
        {{"problem": "...", "why_unsolved": "...", "difficulty": "high|medium|low"}}
    ],
    "emerging_areas": [
        {{"area": "...", "potential": "...", "timeline": "..."}}
    ],
    "recommended_focus": "..."
}}"""

        try:
            result = self.llm.generate_json(prompt)
            logger.info("Gap analizi tamamlandı")
            return result
        except Exception as e:
            logger.error(f"Gap analizi hatası: {e}")
            return {"error": str(e)}
