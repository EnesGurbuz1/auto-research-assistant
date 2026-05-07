"""
Qdrant vector store wrapper — local disk modunda çalışır, server gerekmez.
Koleksiyon: 'papers', 384 boyutlu vektörler (MiniLM uyumlu).
"""

import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    NamedVector,
    Query,
)

COLLECTION = "papers"
VECTOR_DIM = 384
QDRANT_PATH = str(Path(__file__).parent.parent.parent / "data" / "qdrant")


def _get_client() -> QdrantClient:
    Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=QDRANT_PATH)


def _ensure_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Qdrant koleksiyonu oluşturuldu: {COLLECTION}")


def upsert_papers(papers: List[Dict[str, Any]], vectors: List[List[float]]) -> int:
    """Makaleleri ve vektörlerini Qdrant'a ekle/güncelle."""
    client = _get_client()
    _ensure_collection(client)

    points = []
    for paper, vec in zip(papers, vectors):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, paper.get("id", paper["title"])))
        payload = {
            "arxiv_id": paper.get("id", ""),
            "title": paper.get("title", ""),
            "authors": paper.get("authors", []),
            "year": paper.get("year", 0),
            "abstract": paper.get("abstract", "")[:1000],
            "categories": paper.get("categories", []),
            "pdf_url": paper.get("pdf_url", ""),
            "arxiv_url": paper.get("arxiv_url", ""),
            "source": paper.get("source", "arxiv"),
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    if points:
        client.upsert(collection_name=COLLECTION, points=points)
        logger.info(f"Qdrant'a {len(points)} makale eklendi")

    return len(points)


def search_similar(query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
    """Sorgu vektörüne en yakın makaleleri getir."""
    client = _get_client()
    _ensure_collection(client)

    hits = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": h.score, **h.payload} for h in hits]


def count_papers() -> int:
    """Koleksiyondaki toplam makale sayısı."""
    try:
        client = _get_client()
        _ensure_collection(client)
        return client.count(collection_name=COLLECTION).count
    except Exception:
        return 0
