"""
Embedding katmanı — sentence-transformers kullanır, API key gerekmez.
Model: all-MiniLM-L6-v2 (384 boyut, hızlı ve yeterince iyi)
Ağırlıklar: models/all-MiniLM-L6-v2/ (proje içi, HF Hub'a istek gitmez)
"""

from pathlib import Path
from typing import List
from loguru import logger

_model = None

# Proje kökündeki local model klasörü; yoksa HF Hub'dan indirilir (fallback)
_LOCAL_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "all-MiniLM-L6-v2"


def _get_model():
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer

    if _LOCAL_MODEL_PATH.exists():
        logger.info(f"Embedding modeli local'den yükleniyor: {_LOCAL_MODEL_PATH}")
        _model = SentenceTransformer(str(_LOCAL_MODEL_PATH))
    else:
        logger.warning(
            "models/all-MiniLM-L6-v2 bulunamadı, HF Hub'dan indiriliyor "
            "(ilk çalıştırmada normal, sonraki çalışmalarda local kullanılır)"
        )
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
