"""
Synthesis Agent — RAG tabanlı gap analizi, trend tespiti, aktif araştırmacı belirleme.
Hallüsinasyonu önlemek için yalnızca Qdrant'tan gelen makaleleri context olarak kullanır.
"""

import json
from loguru import logger
from src.graph.state import ResearchState
from src.agents.llm import generate_json
from src.rag.embedder import embed_text
from src.rag.vector_store import search_similar

MAX_CONTEXT = 15

SYSTEM = """\
Sen bir akademik araştırma sentez uzmanısın.
Sana verilen gerçek makale verileri (başlık, özet, yazar, yıl) üzerinden analiz yaparsın.
ASLA verilen makalelerin dışında kaynak uydurmaz, hayal etmezsin.
Tüm bulgularını yalnızca verilen makale listesine dayandırırsın.
"""

PROMPT_TEMPLATE = """\
Kullanıcı araştırma sorusu: "{query}"

Aşağıda bu konuda bulunan {n} akademik makale bulunmaktadır:
---
{papers_text}
---

Bu makaleleri analiz ederek aşağıdaki JSON yapısını döndür:

{{
  "gap_analysis": {{
    "solved_problems": ["çözülmüş problem 1", "çözülmüş problem 2"],
    "open_problems": ["açık problem 1", "açık problem 2"],
    "research_gaps": ["boşluk 1", "boşluk 2"]
  }},
  "trend_analysis": {{
    "emerging_methods": ["yöntem 1", "yöntem 2"],
    "temporal_shift": "2-3 yılda ne değişti",
    "hot_topics": ["konu 1", "konu 2"]
  }},
  "active_researchers": [
    {{"name": "Yazar Adı", "affiliation": "Kurum (bilinmiyorsa boş bırak)", "focus": "çalışma alanı"}},
  ],
  "key_papers": [
    {{"title": "Makale başlığı", "year": 2024, "why_important": "önemi"}}
  ],
  "summary": "Araştırma alanının genel değerlendirmesi (3-4 cümle)"
}}
"""


def _format_papers(papers: list) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.get("authors", [])[:3])
        if len(p.get("authors", [])) > 3:
            authors += " et al."
        abstract = p.get("abstract", "")[:300]
        lines.append(
            f"[{i}] {p.get('title', 'Başlık yok')} ({p.get('year', '?')})\n"
            f"    Yazarlar: {authors}\n"
            f"    Özet: {abstract}"
        )
    return "\n\n".join(lines)


def synthesis_node(state: ResearchState) -> dict:
    query = state["query"]
    papers = state.get("papers", [])

    logger.info(f"[Synthesis] RAG ile sentez yapılıyor, toplam makale: {len(papers)}")

    # RAG: sorgu vektörüne en yakın makaleleri al (hallüsinasyonu önler)
    if papers:
        query_vec = embed_text(query)
        rag_hits = search_similar(query_vec, top_k=MAX_CONTEXT)
        # Score'a göre sırala
        context_papers = sorted(rag_hits, key=lambda x: x.get("score", 0), reverse=True)
    else:
        context_papers = []

    if not context_papers:
        return {
            "synthesis": {"error": "Sentez için yeterli makale bulunamadı."},
            "current_step": "synthesis",
            "messages": ["Sentez: Yeterli makale yok, atlandı"],
        }

    papers_text = _format_papers(context_papers)
    prompt = PROMPT_TEMPLATE.format(
        query=query,
        n=len(context_papers),
        papers_text=papers_text,
    )

    result = generate_json(prompt, system=SYSTEM)

    if not result:
        result = {"error": "Sentez üretilemedi", "summary": "LLM yanıt vermedi."}

    logger.info("[Synthesis] Sentez tamamlandı")

    return {
        "synthesis": result,
        "current_step": "synthesis",
        "messages": ["Sentez ve gap analizi tamamlandı"],
    }
