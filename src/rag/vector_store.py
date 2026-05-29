"""
Qdrant vector store wrapper — local disk modunda çalışır, server gerekmez.

İki ayrı koleksiyon:
  - 'papers'        : Paper-level vektörler (title+abstract). Genel filtreleme/seçim için.
  - 'paper_chunks'  : Chunk-level vektörler (paragraflar). Fine-grained synthesis context.

Her ikisi de 384 boyutlu cosine.
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
)

COLLECTION_PAPERS = "papers"
COLLECTION_CHUNKS = "paper_chunks"
VECTOR_DIM = 384
QDRANT_PATH = str(Path(__file__).parent.parent.parent / "data" / "qdrant")

_client_singleton: Optional[QdrantClient] = None


def _get_client() -> QdrantClient:
    global _client_singleton
    if _client_singleton is None:
        Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
        _client_singleton = QdrantClient(path=QDRANT_PATH)
    return _client_singleton


def _ensure_collection(client: QdrantClient, name: str):
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Qdrant koleksiyonu oluşturuldu: {name}")


# ============================================================================
# Paper-level
# ============================================================================


def upsert_papers(papers: List[Dict[str, Any]], vectors: List[List[float]]) -> int:
    """Makaleleri ve paper-level vektörlerini 'papers' koleksiyonuna ekle/güncelle."""
    client = _get_client()
    _ensure_collection(client, COLLECTION_PAPERS)

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
            "scopus_url": paper.get("scopus_url", ""),
            "doi_url": paper.get("doi_url", ""),
            "venue": paper.get("venue", ""),
            "zotero_key": paper.get("zotero_key", ""),
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    if points:
        client.upsert(collection_name=COLLECTION_PAPERS, points=points)
        logger.info(f"Qdrant/papers'a {len(points)} makale eklendi")

    return len(points)


def search_similar(query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
    """Sorgu vektörüne en yakın makaleleri 'papers' koleksiyonundan getir."""
    client = _get_client()
    _ensure_collection(client, COLLECTION_PAPERS)

    hits = client.query_points(
        collection_name=COLLECTION_PAPERS,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": h.score, **h.payload} for h in hits]


def count_papers() -> int:
    try:
        client = _get_client()
        _ensure_collection(client, COLLECTION_PAPERS)
        return client.count(collection_name=COLLECTION_PAPERS).count
    except Exception:
        return 0


# ============================================================================
# Chunk-level
# ============================================================================


def upsert_chunks(
    paper: Dict[str, Any], chunks: List[str], vectors: List[List[float]]
) -> int:
    """Bir makalenin chunk'larını 'paper_chunks' koleksiyonuna yaz."""
    if not chunks:
        return 0
    client = _get_client()
    _ensure_collection(client, COLLECTION_CHUNKS)

    paper_id = paper.get("id") or paper.get("title", "")
    points = []
    for idx, (chunk_text, vec) in enumerate(zip(chunks, vectors)):
        # Deterministik id: paper_id + chunk index
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{paper_id}::chunk::{idx}"))
        payload = {
            "paper_id": paper_id,
            "chunk_index": idx,
            "chunk_text": chunk_text[:2500],
            "title": paper.get("title", ""),
            "year": paper.get("year", 0),
            "authors": paper.get("authors", []),
            "source": paper.get("source", ""),
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    client.upsert(collection_name=COLLECTION_CHUNKS, points=points)
    return len(points)


def search_chunks(
    query_vector: List[float], top_k: int = 30, paper_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Sorgu vektörüne en yakın chunk'ları getir.
    paper_ids verilirse yalnızca o makalelerin chunk'larını döndürür (current run filtresi).
    """
    client = _get_client()
    _ensure_collection(client, COLLECTION_CHUNKS)

    # Eski kayıtları elemek için daha geniş çek + manuel filtre
    fetch_k = top_k * 3 if paper_ids else top_k
    hits = client.query_points(
        collection_name=COLLECTION_CHUNKS,
        query=query_vector,
        limit=fetch_k,
        with_payload=True,
    ).points

    results: List[Dict[str, Any]] = []
    paper_id_set = set(paper_ids) if paper_ids else None
    for h in hits:
        payload = dict(h.payload or {})
        if paper_id_set is not None and payload.get("paper_id", "") not in paper_id_set:
            continue
        payload["score"] = h.score
        results.append(payload)
        if len(results) >= top_k:
            break
    return results


def count_chunks() -> int:
    try:
        client = _get_client()
        _ensure_collection(client, COLLECTION_CHUNKS)
        return client.count(collection_name=COLLECTION_CHUNKS).count
    except Exception:
        return 0
