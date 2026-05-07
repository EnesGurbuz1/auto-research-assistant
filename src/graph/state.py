"""
LangGraph state tanımı — tüm ajanlar bu shared state üzerinden iletişir.
"""

import operator
from typing import TypedDict, List, Dict, Any, Optional, Annotated


class ResearchState(TypedDict):
    # Kullanıcı girdisi
    query: str

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

    # Hata varsa
    error: Optional[str]
