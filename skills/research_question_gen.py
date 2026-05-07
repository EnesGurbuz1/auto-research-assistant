"""
Research Question Generator - Araştırma sorusu üretme becerisi.
Gap analizine ve trendlere dayanarak potansiyel araştırma soruları önerir.
"""

import json
from typing import Dict, List, Any
from loguru import logger
from agents.llm_interface import LLMInterface


class ResearchQuestionGenerator:
    """Gap ve trend analizine dayalı araştırma sorusu üretici."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)

    def generate(self, gap_analysis: Dict, trend_analysis: Dict, dataset_info: Dict = None) -> Dict[str, Any]:
        """Araştırma soruları ve hipotezler üret."""
        
        prompt = f"""Aşağıdaki gap analizi, trend analizi ve veri seti bilgilerine dayanarak,
"Multi-Agent Grid Load Negotiation for EV Charging" konusunda araştırma soruları üret.

GAP ANALİZİ:
{json.dumps(gap_analysis, ensure_ascii=False)[:2000]}

TREND ANALİZİ:
{json.dumps(trend_analysis, ensure_ascii=False)[:2000]}

VERİ SETİ BİLGİLERİ:
{json.dumps(dataset_info or {}, ensure_ascii=False)[:1000]}

Şu formatta JSON döndür:
{{
    "primary_research_questions": [
        {{
            "question": "...",
            "rationale": "Neden bu soru önemli?",
            "feasibility": "high|medium|low",
            "novelty": "high|medium|low",
            "related_gap": "Hangi gap'e hitap ediyor?"
        }}
    ],
    "secondary_questions": ["..."],
    "hypotheses": [
        {{
            "hypothesis": "...",
            "testable": true,
            "method": "Nasıl test edilir?"
        }}
    ],
    "recommended_title_variations": [
        "Tez başlığı önerisi 1",
        "Tez başlığı önerisi 2"
    ],
    "scope_recommendation": "Tez kapsamı için öneri"
}}"""

        try:
            result = self.llm.generate_json(prompt)
            logger.info(f"Araştırma soruları üretildi: {len(result.get('primary_research_questions', []))} adet")
            return result
        except Exception as e:
            logger.error(f"Araştırma sorusu üretim hatası: {e}")
            return {"error": str(e)}
