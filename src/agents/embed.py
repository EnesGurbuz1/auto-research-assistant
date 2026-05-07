"""
Embed Agent — makaleleri embedding'e çevirir ve Qdrant'a kaydeder.
Her makale için: title + abstract birleştirilip embed edilir.
"""

from loguru import logger
from src.graph.state import ResearchState
from src.rag.embedder import embed_texts
from src.rag.vector_store import upsert_papers


def embed_node(state: ResearchState) -> dict:
    papers = state.get("papers", [])
    if not papers:
        return {
            "embedded_count": 0,
            "current_step": "embed",
            "messages": ["Embed: Makale bulunamadı, atlandı"],
        }

    logger.info(f"[Embed] {len(papers)} makale embed ediliyor")

    texts = [f"{p['title']}. {p.get('abstract', '')}" for p in papers]
    vectors = embed_texts(texts)

    count = upsert_papers(papers, vectors)
    logger.info(f"[Embed] {count} makale Qdrant'a kaydedildi")

    return {
        "embedded_count": count,
        "current_step": "embed",
        "messages": [f"Embedding tamamlandı: {count} makale vektör veritabanına kaydedildi"],
    }
