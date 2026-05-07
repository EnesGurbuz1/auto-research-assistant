"""
Comparison Matrix - Çalışmaları karşılaştırma matrisi oluşturma.
Survey/review tarzında sistematik karşılaştırma tablosu üretir.
"""

import json
from typing import Dict, List, Any
from loguru import logger
from agents.llm_interface import LLMInterface


class ComparisonMatrix:
    """Akademik çalışmaları karşılaştırma matrisi oluşturur."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)

    def create(self, papers: List[Dict]) -> Dict[str, Any]:
        """Karşılaştırma matrisi oluştur."""
        
        paper_summaries = []
        for p in papers[:20]:
            paper_summaries.append({
                "title": p.get("title", ""),
                "year": p.get("year", ""),
                "authors": p.get("authors", "")[:60] if isinstance(p.get("authors"), str) else "",
                "abstract": (p.get("abstract", "") or "")[:300],
            })

        prompt = f"""Aşağıdaki makaleler için karşılaştırma matrisi oluştur.
"Multi-Agent Grid Load Negotiation for EV Charging" bağlamında analiz et.

MAKALELER:
{json.dumps(paper_summaries, ensure_ascii=False)}

Şu formatta JSON döndür:
{{
    "comparison_criteria": [
        "Agent Type (RL/LLM/Rule-based/Hybrid)",
        "Communication Protocol (MQTT/HTTP/Custom)",
        "Optimization Objective",
        "Scalability",
        "Real-world Testing",
        "Dataset Used",
        "Grid Model Complexity"
    ],
    "matrix": [
        {{
            "paper": "...",
            "year": "...",
            "agent_type": "...",
            "communication": "...",
            "optimization": "...",
            "scalability": "low|medium|high",
            "real_world": "yes|no|simulation",
            "dataset": "...",
            "grid_complexity": "low|medium|high"
        }}
    ],
    "key_observations": [
        "...",
        "..."
    ],
    "most_cited_approach": "...",
    "gap_in_matrix": "..."
}}"""

        try:
            result = self.llm.generate_json(prompt)
            logger.info(f"Karşılaştırma matrisi oluşturuldu: {len(result.get('matrix', []))} satır")
            return result
        except Exception as e:
            logger.error(f"Karşılaştırma matrisi hatası: {e}")
            return {"error": str(e)}
