"""
Literature Agent — arXiv'den makale toplar ve tekilleştirir.
Sorgular arası rate-limit koruması ve kısmi başarı desteği içerir.
"""

import time
from loguru import logger
from src.graph.state import ResearchState
from src.tools.arxiv_tool import search_arxiv, deduplicate

MAX_PER_QUERY = 15
QUERY_DELAY = 6.0


def literature_node(state: ResearchState) -> dict:
    queries = state.get("search_queries", [state["query"]])
    total = len(queries)
    logger.info(f"[Literature] {total} sorgu ile arXiv taranıyor")

    all_papers = []
    failed_queries = []

    for i, q in enumerate(queries, 1):
        logger.info(f"[Literature] Sorgu {i}/{total}: {q[:80]}")
        papers = search_arxiv(q, max_results=MAX_PER_QUERY)

        if papers:
            all_papers.extend(papers)
            logger.info(f"[Literature] Sorgu {i}/{total}: {len(papers)} makale bulundu")
        else:
            failed_queries.append(q)
            logger.warning(f"[Literature] Sorgu {i}/{total}: sonuç bulunamadı")

        if i < total:
            logger.debug(f"[Literature] Sonraki sorgu için {QUERY_DELAY}s bekleniyor")
            time.sleep(QUERY_DELAY)

    unique = deduplicate(all_papers)
    logger.info(f"[Literature] Toplam {len(unique)} benzersiz makale bulundu")

    messages = [f"arXiv taraması tamamlandı: {len(unique)} makale bulundu"]
    if failed_queries:
        messages.append(f"⚠️ {len(failed_queries)} sorgu sonuçsuz kaldı")

    return {
        "papers": unique,
        "current_step": "literature",
        "messages": messages,
    }
