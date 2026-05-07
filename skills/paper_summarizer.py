"""
Paper Summarizer - Makale özetleme becerisi.
PDF veya abstract'tan kısa ve yapılandırılmış özet üretir.
"""

import json
from typing import Dict, List, Optional
from loguru import logger
from agents.llm_interface import LLMInterface


class PaperSummarizer:
    """Akademik makale özetleme aracı."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)

    def summarize(self, paper: Dict, full_text: Optional[str] = None) -> Dict:
        """Bir makaleyi yapılandırılmış olarak özetle."""
        
        content = full_text if full_text else paper.get("abstract", "")
        if not content:
            return {"error": "Özetlenecek içerik yok"}

        prompt = f"""Aşağıdaki akademik makaleyi özetle.

BAŞLIK: {paper.get('title', 'Bilinmiyor')}
YAZARLAR: {paper.get('authors', 'Bilinmiyor')}
YIL: {paper.get('year', 'Bilinmiyor')}

İÇERİK:
{content[:5000]}

Şu formatta JSON döndür:
{{
    "title": "...",
    "one_line_summary": "...",
    "problem": "Çözdüğü problem nedir?",
    "method": "Kullanılan yöntem nedir?",
    "key_findings": ["bulgu1", "bulgu2"],
    "dataset_used": "Kullanılan veri seti",
    "limitations": ["kısıtlama1", "kısıtlama2"],
    "relevance_to_thesis": "Tez konusuyla ilişkisi (1-5 puan ve açıklama)",
    "key_references": ["Atıf yapılan önemli çalışmalar"]
}}"""

        try:
            result = self.llm.generate_json(prompt)
            return result
        except Exception as e:
            logger.error(f"Özetleme hatası: {e}")
            return {"error": str(e)}

    def batch_summarize(self, papers: List[Dict]) -> List[Dict]:
        """Birden fazla makaleyi özetle."""
        summaries = []
        for paper in papers:
            summary = self.summarize(paper)
            summaries.append(summary)
        return summaries
