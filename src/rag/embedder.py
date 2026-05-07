"""
Embedding katmanı — sentence-transformers kullanır, API key gerekmez.
Model: all-MiniLM-L6-v2 (384 boyut, hızlı ve yeterince iyi)
"""

from typing import List
from loguru import logger

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Embedding modeli yükleniyor: all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding modeli hazır")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Metinleri embedding vektörlerine dönüştür."""
    model = _get_model()
    vectors = model.encode(texts, show_progress_bar=False, batch_size=32)
    return vectors.tolist()


def embed_text(text: str) -> List[float]:
    """Tek metni embedding vektörüne dönüştür."""
    return embed_texts([text])[0]
