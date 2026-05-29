"""
LangGraph state tanımı — tüm ajanlar bu shared state üzerinden iletişir.
"""

import operator
from typing import TypedDict, List, Dict, Any, Optional, Annotated


class ResearchState(TypedDict):
    # Kullanıcı girdisi
    query: str

    # Kullanıcı filtreler
    filters: Dict[str, Any]
    max_results: int

    # Aktif kaynaklar: ["arxiv"], ["scopus"], ["arxiv", "scopus"]
    sources: List[str]

    # Planner çıktısı: araştırma stratejisi
    research_plan: str
    search_queries: List[str]

    # Literature agent çıktısı: bulunan makaleler
    papers: List[Dict[str, Any]]

    # Embed agent çıktısı: Qdrant'a yüklenen paper id'leri
    embedded_count: int

    # Synthesis agent çıktısı
    synthesis: Dict[str, Any]

    # UI için ilerleme mesajları — Annotated[..., operator.add] ile birikir
    messages: Annotated[List[str], operator.add]

    # Aktif adım adı
    current_step: str

    # Yıl filtreleri
    year_from: int
    year_to: int

    # PDF zenginleştirme sayacı
    pdf_enriched_count: int

    # Chunk-level RAG sayacı (paper_chunks koleksiyonuna yazılan chunk sayısı)
    chunk_count: int

    # Zotero
    zotero_collection_key: Optional[str]
    zotero_collection_name: Optional[str]

    # Google Drive
    drive_folder_url: Optional[str]

    # Hata varsa
    error: Optional[str]
