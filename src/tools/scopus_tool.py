"""
Scopus arama aracı — Elsevier Scopus API, pipeline formatına normalize edilmiş çıktı.
SCOPUS_API_KEY ortam değişkeni gerektirir.

Abstract eksikliği: Scopus Search API abstract döndürmez.
enrich_with_semantic_scholar() ile DOI → Semantic Scholar batch lookup yaparak
abstract ve open access PDF URL eklenir.
"""

import os
import time
from typing import List, Dict, Any
from loguru import logger

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


BASE_URL = "https://api.elsevier.com/content/search/scopus"
MIN_REQUEST_INTERVAL = 1.0
_last_request_time = 0.0
_debug_logged = False  # İlk entry sadece bir kez loglanır


def _log_first_entry_debug(entry: dict) -> None:
    """
    İlk Scopus entry'sinin ham içeriğini loglar.
    Hangi alanların gelip gelmediğini görmek için kullanılır.
    """
    global _debug_logged
    if _debug_logged:
        return
    _debug_logged = True

    # İzlenecek alanlar ve durumları
    fields_to_check = [
        ("dc:title",              "Başlık"),
        ("dc:creator",            "İlk yazar"),
        ("dc:description",        "Abstract"),
        ("prism:doi",             "DOI"),
        ("dc:identifier",         "Scopus ID"),
        ("prism:coverDate",       "Yayın tarihi"),
        ("prism:publicationName", "Dergi adı"),
        ("citedby-count",         "Atıf sayısı"),
        ("authkeywords",          "Anahtar kelimeler"),
        ("subtype",               "Kaynak tipi"),
        ("link",                  "Linkler"),
        ("openaccess",            "Open Access bayrağı"),
        ("openaccessFlag",        "Open Access flag"),
        ("prism:url",             "Kaynak URL"),
    ]

    lines = ["[Scopus DEBUG] ── İlk Entry Alan Raporu ──"]
    for key, label in fields_to_check:
        val = entry.get(key)
        if val is None:
            status = "✗ YOK"
            preview = ""
        elif val == "" or val == [] or val == {}:
            status = "✗ BOŞ"
            preview = ""
        else:
            status = "✓ VAR"
            raw = str(val)
            preview = f" → {raw[:120]}{'…' if len(raw) > 120 else ''}"
        lines.append(f"  {status}  {label:25s} ({key}){preview}")

    # Ham entry'de var ama listede olmayan diğer anahtarlar
    known_keys = {k for k, _ in fields_to_check}
    extra = {k: v for k, v in entry.items() if k not in known_keys and v not in ("", [], {}, None)}
    if extra:
        lines.append(f"  [Diğer dolu alanlar: {', '.join(extra.keys())}]")

    lines.append("[Scopus DEBUG] ── Abstract durumu: " + (
        f"VAR ({len(entry.get('dc:description', ''))} karakter)"
        if entry.get("dc:description")
        else "YOK — embedding başlık bazlı olacak"
    ) + " ──")

    logger.info("\n".join(lines))


def search_scopus(
    query: str,
    max_results: int = 25,
    year_from: int = 1990,
    year_to: int = 2099,
) -> List[Dict[str, Any]]:
    """
    Scopus'ta arama yap ve pipeline standart formatında makale listesi döndür.
    API key yoksa boş liste döner.
    """
    global _last_request_time

    if not _HTTPX_AVAILABLE:
        logger.error("[Scopus] httpx kütüphanesi yüklü değil")
        return []

    api_key = os.getenv("SCOPUS_API_KEY", "")
    if not api_key:
        logger.warning("[Scopus] SCOPUS_API_KEY ayarlanmamış, Scopus atlanıyor")
        return []

    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    inst_token = os.getenv("SCOPUS_INST_TOKEN", "")
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token

    date_range = f"{year_from}-{year_to}"
    params = {
        "query": query,
        "count": min(max_results, 200),
        "sort": "citedby-count",
        "date": date_range,
        "field": "dc:title,dc:creator,prism:coverDate,prism:publicationName,prism:doi,"
                 "citedby-count,dc:identifier,dc:description,link,authkeywords,subtype",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(BASE_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[Scopus] HTTP hata {e.response.status_code}: {query[:60]}")
        return []
    except Exception as e:
        logger.error(f"[Scopus] Arama hatası: {e}")
        return []

    entries = data.get("search-results", {}).get("entry", [])
    if not entries:
        logger.info(f"[Scopus] '{query[:60]}' → 0 sonuç")
        return []

    # İlk entry'yi detaylı logla: hangi alanların dolu geldiğini göster
    _log_first_entry_debug(entries[0])

    results = []
    for entry in entries:
        # Hata girişi (quota, auth) kontrolü
        if "error" in entry:
            logger.warning(f"[Scopus] API hata girişi: {entry.get('error')}")
            continue

        doi = entry.get("prism:doi", "")
        scopus_id = entry.get("dc:identifier", "")
        # Benzersiz ID: DOI varsa kullan, yoksa Scopus ID
        uid = doi if doi else scopus_id

        # Yazar: dc:creator yalnızca ilk yazarı verir
        creator = entry.get("dc:creator", "")
        authors = [creator] if creator else []

        # Yıl
        cover_date = entry.get("prism:coverDate", "")
        try:
            year = int(cover_date[:4]) if cover_date else 0
        except ValueError:
            year = 0

        # URL'ler
        scopus_url = next(
            (lnk["@href"] for lnk in entry.get("link", []) if lnk.get("@ref") == "scopus"),
            "",
        )
        doi_url = f"https://doi.org/{doi}" if doi else ""

        paper: Dict[str, Any] = {
            "id": uid,
            "title": entry.get("dc:title", ""),
            "authors": authors,
            "year": year,
            "published": cover_date + "T00:00:00Z" if cover_date else "",
            "abstract": entry.get("dc:description", ""),
            "categories": [],
            "pdf_url": "",        # Scopus tam metin erişimi kurumsal lisans gerektirir
            "arxiv_url": "",
            "scopus_url": scopus_url,
            "doi_url": doi_url,
            "doi": doi,
            "venue": entry.get("prism:publicationName", ""),
            "citation_count": int(entry.get("citedby-count", 0) or 0),
            "source": "scopus",
            "query": query,
        }
        results.append(paper)

    # Alan doluluğu istatistiği
    with_abstract = sum(1 for p in results if p.get("abstract"))
    with_doi      = sum(1 for p in results if p.get("doi"))
    with_scopus_url = sum(1 for p in results if p.get("scopus_url"))
    logger.info(
        f"[Scopus] '{query[:60]}' → {len(results)} makale (tarih: {date_range}) | "
        f"abstract: {with_abstract}/{len(results)}, "
        f"DOI: {with_doi}/{len(results)}, "
        f"Scopus URL: {with_scopus_url}/{len(results)}"
    )
    return results


def enrich_with_semantic_scholar(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scopus'tan dönen makaleleri Semantic Scholar Batch API ile zenginleştirir.
    DOI üzerinden abstract, tüm yazar listesi ve open-access PDF URL çeker.
    API key olmadan 1 req/s, S2_API_KEY ile 10 req/s.
    """
    if not _HTTPX_AVAILABLE:
        logger.warning("[S2] httpx yüklü değil, zenginleştirme atlandı")
        return papers

    doi_papers = [(i, p) for i, p in enumerate(papers) if p.get("doi")]
    if not doi_papers:
        logger.warning("[S2] DOI bulunan makale yok, zenginleştirme atlandı")
        return papers

    ids = [f"DOI:{p['doi']}" for _, p in doi_papers]
    fields = "abstract,openAccessPdf,authors,year,title,externalIds"

    headers: dict = {"Content-Type": "application/json"}
    s2_key = os.getenv("S2_API_KEY", "")
    if s2_key:
        headers["x-api-key"] = s2_key

    BATCH_SIZE = 100
    s2_results: Dict[str, Any] = {}

    for batch_start in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[batch_start: batch_start + BATCH_SIZE]
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"https://api.semanticscholar.org/graph/v1/paper/batch?fields={fields}",
                    headers=headers,
                    json={"ids": batch_ids},
                )
                if resp.status_code == 429:
                    logger.warning("[S2] Rate limit, 15s bekleniyor...")
                    time.sleep(15)
                    resp = client.post(
                        f"https://api.semanticscholar.org/graph/v1/paper/batch?fields={fields}",
                        headers=headers,
                        json={"ids": batch_ids},
                    )
                resp.raise_for_status()
                batch_data = resp.json()
        except Exception as e:
            logger.error(f"[S2] Batch API hatası: {e}")
            continue

        if not s2_key:
            time.sleep(1.1)  # rate-limit koruması (key yoksa 1 req/s)

        for item in batch_data:
            if not item:
                continue
            ext_ids = item.get("externalIds") or {}
            doi_key = ext_ids.get("DOI", "")
            if doi_key:
                s2_results[doi_key.lower()] = item

    enriched_count = 0
    pdf_count = 0
    for orig_idx, paper in doi_papers:
        doi_lower = paper["doi"].lower()
        s2 = s2_results.get(doi_lower)
        if not s2:
            continue

        abstract = s2.get("abstract") or ""
        if abstract:
            paper["abstract"] = abstract
            enriched_count += 1

        oa_pdf = s2.get("openAccessPdf") or {}
        pdf_url = oa_pdf.get("url", "")
        if pdf_url:
            paper["pdf_url"] = pdf_url
            pdf_count += 1

        s2_authors = s2.get("authors") or []
        if s2_authors:
            paper["authors"] = [a.get("name", "") for a in s2_authors[:8] if a.get("name")]

        papers[orig_idx] = paper

    logger.info(
        f"[S2] {len(doi_papers)} DOI sorgulandı → "
        f"abstract: {enriched_count}/{len(doi_papers)}, "
        f"open-access PDF: {pdf_count}/{len(doi_papers)}"
    )
    return papers


def deduplicate_scopus(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """DOI veya id bazında tekrar eden Scopus makalelerini çıkar."""
    seen: set = set()
    unique = []
    for p in papers:
        pid = p.get("id", "") or p.get("doi", "")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
        elif not pid:
            unique.append(p)
    return unique


def enrich_with_semantic_scholar(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scopus'tan gelen makaleleri Semantic Scholar batch API ile zenginleştirir.
    DOI olan makalelere abstract ve open access PDF URL eklenir.

    Semantic Scholar Paper Batch API:
      POST /graph/v1/paper/batch
      body: {"ids": ["DOI:10.xxx/yyy", ...]}
      params: fields=abstract,openAccessPdf,authors

    Rate limit: unauthenticated 100 req/5min, batch max 500 paper.
    """
    if not _HTTPX_AVAILABLE:
        logger.warning("[Scopus Enrich] httpx yok, Semantic Scholar zenginleştirme atlandı")
        return papers

    # DOI olan makaleleri topla
    doi_to_idx: Dict[str, int] = {}
    for i, p in enumerate(papers):
        doi = p.get("doi", "")
        if doi:
            doi_to_idx[doi] = i

    if not doi_to_idx:
        logger.warning("[Scopus Enrich] Hiçbir makalede DOI yok, zenginleştirme atlandı")
        return papers

    s2_api_key = os.getenv("S2_API_KEY", "")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    ids = [f"DOI:{doi}" for doi in doi_to_idx]
    fields = "abstract,openAccessPdf,authors,year,title"
    logger.info(f"[Scopus Enrich] {len(ids)} DOI → Semantic Scholar batch sorgusu")

    try:
        with _httpx_client() as client:
            resp = client.post(
                "https://api.semanticscholar.org/graph/v1/paper/batch",
                headers=headers,
                params={"fields": fields},
                json={"ids": ids},
                timeout=30,
            )
            if resp.status_code == 429:
                logger.warning("[Scopus Enrich] Semantic Scholar rate limit, 60s bekleniyor")
                time.sleep(60)
                resp = client.post(
                    "https://api.semanticscholar.org/graph/v1/paper/batch",
                    headers=headers,
                    params={"fields": fields},
                    json={"ids": ids},
                    timeout=30,
                )
            resp.raise_for_status()
            batch_results = resp.json()
    except Exception as e:
        logger.error(f"[Scopus Enrich] Semantic Scholar batch hatası: {e}")
        return papers

    enriched_count = 0
    pdf_count = 0

    # batch_results: [paper_obj | null, ...] — giriş sırasıyla eşleşir
    for s2_paper, doi in zip(batch_results, doi_to_idx.keys()):
        if not s2_paper:
            continue

        idx = doi_to_idx[doi]
        paper = papers[idx]

        abstract = s2_paper.get("abstract") or ""
        if abstract and not paper.get("abstract"):
            paper["abstract"] = abstract
            enriched_count += 1

        pdf_info = s2_paper.get("openAccessPdf") or {}
        pdf_url = pdf_info.get("url", "")
        if pdf_url and not paper.get("pdf_url"):
            paper["pdf_url"] = pdf_url
            pdf_count += 1

        # Semantic Scholar bazen daha fazla yazar verir
        s2_authors = s2_paper.get("authors") or []
        if s2_authors and len(paper.get("authors", [])) <= 1:
            paper["authors"] = [a.get("name", "") for a in s2_authors[:8] if a.get("name")]

    logger.info(
        f"[Scopus Enrich] Tamamlandı: {enriched_count}/{len(ids)} abstract eklendi, "
        f"{pdf_count}/{len(ids)} open access PDF bulundu"
    )

    # Abstract hâlâ eksik olanları logla
    still_missing = [p.get("title", "")[:60] for p in papers if not p.get("abstract")]
    if still_missing:
        logger.warning(
            f"[Scopus Enrich] {len(still_missing)} makalede abstract hâlâ yok "
            f"(DOI yok veya S2'de kayıt yok): {'; '.join(still_missing[:3])}"
        )

    return papers


def _httpx_client():
    """httpx.Client factory — import guard ile."""
    import httpx as _httpx
    return _httpx.Client()


def deduplicate_combined(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Karışık kaynaklı (arxiv + scopus + zotero + drive) listesini tekilleştir.
    Eşleme: (1) id/DOI, (2) DOI alanı, (3) punctuation-stripped normalleştirilmiş başlık.
    """
    import re as _re

    def _norm_title(t: str) -> str:
        if not t:
            return ""
        t = t.lower()
        t = _re.sub(r"[^a-z0-9\s]+", " ", t)
        return " ".join(t.split())

    seen_ids: set = set()
    seen_dois: set = set()
    seen_titles: set = set()
    unique = []

    for p in papers:
        uid = (p.get("id") or "").strip()
        doi = (p.get("doi") or "").strip().lower()
        title_key = _norm_title(p.get("title", ""))

        if uid and uid in seen_ids:
            continue
        if doi and doi in seen_dois:
            continue
        if title_key and title_key in seen_titles:
            continue

        if uid:
            seen_ids.add(uid)
        if doi:
            seen_dois.add(doi)
        if title_key:
            seen_titles.add(title_key)
        unique.append(p)

    return unique
