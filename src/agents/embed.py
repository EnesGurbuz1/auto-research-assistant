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

    source_counts = {}
    no_abstract = []
    for p in papers:
        src = p.get("source", "?")
        source_counts[src] = source_counts.get(src, 0) + 1
        if not p.get("abstract") and not p.get("full_text"):
            no_abstract.append(p.get("title", "")[:60])

    logger.info(f"[Embed] {len(papers)} makale embed ediliyor: {source_counts}")
    if no_abstract:
        logger.warning(
            f"[Embed] {len(no_abstract)} makalede abstract yok (sadece başlık embed edilecek): "
            + "; ".join(no_abstract[:5])
        )

    # full_text varsa (PDF parse edilmişse) onu kullan, yoksa title + abstract
    texts = [
        f"{p['title']}. {p.get('full_text') or p.get('abstract', '')}"
        for p in papers
    ]
    vectors = embed_texts(texts)

    count = upsert_papers(papers, vectors)
    logger.info(f"[Embed] {count} makale Qdrant'a kaydedildi")

    return {
        "embedded_count": count,
        "current_step": "embed",
        "messages": [f"Embedding tamamlandı: {count} makale vektör veritabanına kaydedildi"],
    }
