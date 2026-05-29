"""
PDF Fetcher Agent — top-K makalenin tam metnini sağlar, chunk-level RAG için chunk'ları embed eder.

Akış:
  1. RAG ile (paper-level) top-K makale seçilir, current-run filtresi uygulanır.
  2. Her makale için full_text elde edilir:
       - source=zotero → Zotero attachment API üzerinden PDF indir
       - source=arxiv/scopus → mevcut PDFDownloader (open-access)
  3. full_text alınan makaleler chunk'lara bölünür ve paper_chunks koleksiyonuna yazılır.
  4. Paper-level vektör de full_text ile güncellenir (daha kaliteli retrieval).

PDF başarısız olursa makale abstract ile kalmaya devam eder (graceful fallback).
"""

import sys
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger

from src.graph.state import ResearchState
from src.rag.embedder import embed_text, embed_texts
from src.rag.vector_store import (
    search_similar,
    upsert_papers,
    upsert_chunks,
)
from src.rag.chunker import chunk_text

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from tools.pdf_downloader import PDFDownloader
    from tools.pdf_parser import PDFParser
    _PDF_TOOLS_AVAILABLE = True
except ImportError:
    _PDF_TOOLS_AVAILABLE = False

try:
    from src.tools.zotero_tool import download_attachment_pdf
    _ZOTERO_AVAILABLE = True
except ImportError:
    _ZOTERO_AVAILABLE = False


_BLOCKED_DOMAINS = {
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "link.springer.com",
    "www.sciencedirect.com",
    "onlinelibrary.wiley.com",
    "tandfonline.com",
    "doi.org",
}

# Chunk embedding için tam metnin ilk N karakteri (uzun PDF'lerde maliyeti sınırlamak için)
MAX_TEXT_FOR_CHUNKING = 25000


def _is_downloadable_url(url: str) -> bool:
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return not any(domain == b or domain.endswith("." + b) for b in _BLOCKED_DOMAINS)
    except Exception:
        return False


def _acquire_full_text(
    paper: dict,
    downloader: "PDFDownloader",
    parser: "PDFParser",
    zotero_dir: Path,
) -> str:
    """Bir makale için full_text üret. Boş string = başarısız."""
    title = paper.get("title", "")[:60]
    source = paper.get("source", "")

    # Drive: PDF zaten yerel diskte (literature_node tarafından indirildi)
    if source == "drive":
        local = paper.get("pdf_local_path")
        if not local:
            return ""
        pdf_path = Path(local)
        if not pdf_path.exists():
            logger.warning(f"[PDF] Drive PDF kayıp: {title}")
            return ""
        text = parser.extract_text(pdf_path, max_pages=40)
        return text or ""

    # Zotero: attachment API üzerinden indir
    if source == "zotero" and _ZOTERO_AVAILABLE:
        zkey = paper.get("zotero_key", "")
        if not zkey:
            return ""
        pdf_path = download_attachment_pdf(zkey, dest_dir=zotero_dir)
        if not pdf_path:
            logger.debug(f"[PDF] Zotero PDF yok: {title}")
            return ""
        text = parser.extract_text(pdf_path, max_pages=40)
        return text or ""

    # arxiv / scopus: open-access URL üzerinden
    pdf_url = paper.get("pdf_url", "")
    if not pdf_url:
        return ""

    if not _is_downloadable_url(pdf_url):
        logger.debug(f"[PDF] Engelli domain: {title}")
        return ""

    if "arxiv.org" in pdf_url and not pdf_url.endswith(".pdf"):
        pdf_url = pdf_url + ".pdf"

    arxiv_id = paper.get("id", "")
    safe_id = arxiv_id.replace("/", "_").replace(":", "_") if arxiv_id else None
    filename = f"{safe_id}.pdf" if safe_id else None
    pdf_path = downloader.download(pdf_url, filename=filename)
    if not pdf_path:
        return ""

    text = parser.extract_text(pdf_path, max_pages=40)
    return text or ""


def pdf_fetcher_node(state: ResearchState) -> dict:
    query = state["query"]
    max_k = state.get("max_results", 15)
    papers = state.get("papers", [])

    if not _PDF_TOOLS_AVAILABLE:
        logger.warning("[PDF] pdf araçları import edilemedi, adım atlandı")
        return {
            "pdf_enriched_count": 0,
            "chunk_count": 0,
            "current_step": "pdf_fetcher",
            "messages": ["PDF araçları yüklenemedi, adım atlandı"],
        }

    if not papers:
        return {
            "pdf_enriched_count": 0,
            "chunk_count": 0,
            "current_step": "pdf_fetcher",
            "messages": ["PDF: Makale yok, atlandı"],
        }

    current_ids = {p.get("id") or "" for p in papers if p.get("id")}
    paper_by_id = {p.get("id"): p for p in papers if p.get("id")}

    # Top-K seçimi: paper-level RAG (mevcut çalıştırma filtreli)
    logger.info(f"[PDF] RAG ile top-{max_k} makale seçiliyor")
    query_vec = embed_text(query)
    all_hits = search_similar(query_vec, top_k=max(max_k * 3, len(papers)))
    top_hits = [h for h in all_hits if h.get("arxiv_id", "") in current_ids][:max_k]

    if not top_hits:
        logger.warning("[PDF] Top-K seçimi boş, tüm papers üzerinden ilerleniyor")
        top_hits = [{"arxiv_id": p.get("id"), **p} for p in papers[:max_k]]

    downloader = PDFDownloader(config={}, project_root=_PROJECT_ROOT)
    parser = PDFParser()
    zotero_dir = _PROJECT_ROOT / "data" / "papers" / "pdfs" / "zotero"

    enriched = 0
    failed = 0
    total_chunks = 0

    for hit in top_hits:
        paper_id = hit.get("arxiv_id") or hit.get("id")
        paper = paper_by_id.get(paper_id) or hit
        title = paper.get("title", "")[:60]

        full_text = _acquire_full_text(paper, downloader, parser, zotero_dir)
        if not full_text or len(full_text) < 300:
            logger.debug(f"[PDF] Tam metin yok: {title}")
            failed += 1
            continue

        # Paper-level vektörü full_text ile güncelle (daha kaliteli retrieval için)
        paper["full_text"] = full_text[:5000]

        paper_text = f"{paper.get('title','')}. {full_text[:3000]}"
        paper_vec = embed_texts([paper_text])[0]
        upsert_papers([paper], [paper_vec])

        # Chunk-level: makalenin tamamını chunk'la ve ayrı koleksiyona yaz
        text_for_chunks = full_text[:MAX_TEXT_FOR_CHUNKING]
        chunks = chunk_text(text_for_chunks, chunk_size=1000, overlap=200)
        if chunks:
            chunk_vectors = embed_texts(chunks)
            n = upsert_chunks(paper, chunks, chunk_vectors)
            total_chunks += n
            logger.info(
                f"[PDF] Zenginleştirildi [{enriched+1}]: {title} ({len(chunks)} chunk)"
            )
        enriched += 1

    logger.info(
        f"[PDF] Tamamlandı: {enriched} makale tam metin, {total_chunks} chunk indekslendi, "
        f"{failed} başarısız"
    )

    return {
        "pdf_enriched_count": enriched,
        "chunk_count": total_chunks,
        "current_step": "pdf_fetcher",
        "messages": [
            f"PDF zenginleştirme: {enriched}/{len(top_hits)} makale tam metin, "
            f"{total_chunks} chunk vektörlendi"
            + (f" ({failed} başarısız)" if failed else "")
        ],
    }
