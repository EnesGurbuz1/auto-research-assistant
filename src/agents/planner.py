"""
Planner Agent — kullanıcı sorgusundan araştırma stratejisi ve arXiv sorgu listesi üretir.
"""

from loguru import logger
from src.graph.state import ResearchState
from src.agents.llm import generate_json

SYSTEM = """\
Sen bir akademik araştırma planlama uzmanısın.
Kullanıcının araştırma sorusunu analiz edip arXiv'de aranacak spesifik sorgular üretirsin.
Her sorgu arXiv full-text search için optimize edilmiş, İngilizce olmalı.
"""

PROMPT_TEMPLATE = """\
Araştırma sorusu: "{query}"

Bu araştırma sorusu için arXiv'de aranacak 4 farklı, birbirini tamamlayan sorgu üret.
Sorgular birbirinden farklı açılardan konuyu kapsamalı (örn: genel survey, yöntem odaklı, uygulama odaklı, karşılaştırmalı).

JSON formatında döndür:
{{
  "research_plan": "Araştırma stratejisinin kısa açıklaması (2-3 cümle)",
  "search_queries": [
    "query 1",
    "query 2",
    "query 3",
    "query 4"
  ]
}}
"""


def planner_node(state: ResearchState) -> dict:
    query = state["query"]
    logger.info(f"[Planner] Sorgu analiz ediliyor: {query}")

    result = generate_json(PROMPT_TEMPLATE.format(query=query), system=SYSTEM)

    plan = result.get("research_plan", f"'{query}' konusunda akademik araştırma")
    queries = result.get("search_queries", [query])

    # Fallback: LLM başarısız olursa basit sorgu üret
    if not queries:
        queries = [query, f"{query} survey", f"{query} review 2024"]

    logger.info(f"[Planner] {len(queries)} sorgu üretildi")

    return {
        "research_plan": plan,
        "search_queries": queries,
        "current_step": "planner",
        "messages": [f"Planlama tamamlandı: {len(queries)} arama sorgusu üretildi"],
    }
