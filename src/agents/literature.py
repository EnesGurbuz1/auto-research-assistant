"""
Literature Agent — arXiv'den makale toplar ve tekilleştirir.
"""

from loguru import logger
from src.graph.state import ResearchState
from src.tools.arxiv_tool import search_arxiv, deduplicate

MAX_PER_QUERY = 15


def literature_node(state: ResearchState) -> dict:
    queries = state.get("search_queries", [state["query"]])
    logger.info(f"[Literature] {len(queries)} sorgu ile arXiv taranıyor")

    all_papers = []
    for q in queries:
        papers = search_arxiv(q, max_results=MAX_PER_QUERY)
        all_papers.extend(papers)

    unique = deduplicate(all_papers)
    logger.info(f"[Literature] Toplam {len(unique)} benzersiz makale bulundu")

    return {
        "papers": unique,
        "current_step": "literature",
        "messages": [f"arXiv taraması tamamlandı: {len(unique)} makale bulundu"],
    }
