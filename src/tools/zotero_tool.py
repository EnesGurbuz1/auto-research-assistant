"""
Zotero Web API client.

Kullanıcı `ZOTERO_API_KEY` + `ZOTERO_USER_ID` ile kütüphanesine erişir,
belirli bir collection'daki makaleleri ve PDF eklentilerini indirir.

Standart paper dict formatı (`src/agents/literature.py` ile uyumlu):
{
    "id": "ZOTERO:<itemKey>" veya DOI varsa DOI,
    "title", "authors", "year", "published",
    "abstract", "categories", "venue", "doi",
    "doi_url", "arxiv_url" (boş), "scopus_url" (boş), "pdf_url" (boş — local'a kaydedilir),
    "source": "zotero",
    "zotero_key": <itemKey>,
    "pdf_local_path": str | None,  # PDF indirildiyse
    "full_text": str | None,
}
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterable

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

API_BASE = "https://api.zotero.org"
DEFAULT_TIMEOUT = 30.0
PAGE_LIMIT = 100  # Zotero API başına maks 100


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Zotero-API-Version": "3",
        "Authorization": f"Bearer {api_key}",
    }


def _get_credentials(
    api_key: Optional[str] = None, user_id: Optional[str] = None
) -> tuple[str, str]:
    api_key = api_key or os.getenv("ZOTERO_API_KEY", "")
    user_id = user_id or os.getenv("ZOTERO_USER_ID", "")
    if not api_key or not user_id:
        raise RuntimeError(
            "Zotero erişimi için .env içinde ZOTERO_API_KEY ve ZOTERO_USER_ID gereklidir. "
            "https://www.zotero.org/settings/keys adresinden alabilirsin."
        )
    return api_key, user_id


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
def _api_get(url: str, headers: Dict[str, str], params: Optional[Dict] = None) -> httpx.Response:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            logger.warning(f"[Zotero] 429 rate-limit, {retry_after:.0f}s bekleniyor")
            time.sleep(retry_after)
            raise httpx.HTTPError("Rate limited")
        resp.raise_for_status()
        return resp


def list_collections(
    api_key: Optional[str] = None, user_id: Optional[str] = None
) -> List[Dict[str, str]]:
    """Kullanıcının tüm collection'larını listele. [{key, name, parent}]."""
    api_key, user_id = _get_credentials(api_key, user_id)
    headers = _headers(api_key)
    url = f"{API_BASE}/users/{user_id}/collections"

    all_cols: List[Dict[str, str]] = []
    start = 0
    while True:
        resp = _api_get(url, headers, params={"limit": PAGE_LIMIT, "start": start})
        batch = resp.json()
        if not batch:
            break
        for c in batch:
            data = c.get("data", {})
            all_cols.append(
                {
                    "key": data.get("key", ""),
                    "name": data.get("name", "(isimsiz)"),
                    "parent": data.get("parentCollection", "") or "",
                    "num_items": c.get("meta", {}).get("numItems", 0),
                }
            )
        if len(batch) < PAGE_LIMIT:
            break
        start += PAGE_LIMIT

    logger.info(f"[Zotero] {len(all_cols)} collection bulundu")
    return sorted(all_cols, key=lambda c: c["name"].lower())


def _parse_creators(creators: List[Dict[str, str]]) -> List[str]:
    names = []
    for c in creators or []:
        if c.get("creatorType") not in {"author", "editor", "contributor"}:
            continue
        if "name" in c and c["name"]:
            names.append(c["name"])
        else:
            first = c.get("firstName", "").strip()
            last = c.get("lastName", "").strip()
            full = f"{first} {last}".strip()
            if full:
                names.append(full)
    return names


def _parse_year(date_str: str) -> int:
    if not date_str:
        return 0
    m = re.search(r"(19|20)\d{2}", date_str)
    return int(m.group(0)) if m else 0


def _normalize_item(item_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Zotero item → pipeline paper dict. Sadece akademik tipler."""
    item_type = item_data.get("itemType", "")
    if item_type in {"attachment", "note", "annotation"}:
        return None
    if item_type not in {
        "journalArticle",
        "conferencePaper",
        "preprint",
        "book",
        "bookSection",
        "thesis",
        "report",
        "manuscript",
    }:
        # Diğer tipleri de geçirebiliriz ama tipik akademik kapsam bunlar
        pass

    key = item_data.get("key", "")
    title = item_data.get("title", "").strip()
    if not title:
        return None

    doi = (item_data.get("DOI", "") or "").strip()
    pid = doi if doi else f"ZOTERO:{key}"

    return {
        "id": pid,
        "title": title,
        "authors": _parse_creators(item_data.get("creators", [])),
        "year": _parse_year(item_data.get("date", "")),
        "published": item_data.get("date", ""),
        "abstract": item_data.get("abstractNote", "") or "",
        "categories": [t.get("tag", "") for t in item_data.get("tags", []) if t.get("tag")],
        "venue": item_data.get("publicationTitle", "")
        or item_data.get("proceedingsTitle", "")
        or item_data.get("bookTitle", "")
        or "",
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "arxiv_url": "",
        "scopus_url": "",
        "pdf_url": "",
        "source": "zotero",
        "zotero_key": key,
        "pdf_local_path": None,
        "full_text": None,
        "item_type": item_type,
    }


def fetch_collection_items(
    collection_key: str,
    api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    year_from: int = 1990,
    year_to: int = 2099,
    max_results: int = 200,
) -> List[Dict[str, Any]]:
    """Bir collection'daki tüm top-level item'ları çek + yıl filtresi uygula."""
    api_key, user_id = _get_credentials(api_key, user_id)
    headers = _headers(api_key)
    url = f"{API_BASE}/users/{user_id}/collections/{collection_key}/items/top"

    papers: List[Dict[str, Any]] = []
    start = 0
    while len(papers) < max_results:
        resp = _api_get(
            url,
            headers,
            params={"limit": PAGE_LIMIT, "start": start, "include": "data"},
        )
        batch = resp.json()
        if not batch:
            break
        for raw in batch:
            data = raw.get("data") or {}
            normalized = _normalize_item(data)
            if not normalized:
                continue
            yr = normalized["year"]
            if yr and not (year_from <= yr <= year_to):
                continue
            papers.append(normalized)
            if len(papers) >= max_results:
                break
        if len(batch) < PAGE_LIMIT:
            break
        start += PAGE_LIMIT

    logger.info(
        f"[Zotero] Collection {collection_key}: {len(papers)} makale alındı "
        f"(yıl filtresi {year_from}-{year_to})"
    )
    return papers


def _list_children(
    user_id: str, headers: Dict[str, str], parent_key: str
) -> List[Dict[str, Any]]:
    url = f"{API_BASE}/users/{user_id}/items/{parent_key}/children"
    resp = _api_get(url, headers, params={"limit": PAGE_LIMIT, "include": "data"})
    return resp.json() or []


def _pick_pdf_attachment(children: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Children listesinden en uygun PDF attachment'ını seç."""
    pdfs = []
    for ch in children:
        data = ch.get("data") or {}
        if data.get("itemType") != "attachment":
            continue
        ctype = (data.get("contentType") or "").lower()
        link_mode = data.get("linkMode", "")
        if ctype == "application/pdf" or data.get("filename", "").lower().endswith(".pdf"):
            pdfs.append({"key": data.get("key", ""), "link_mode": link_mode, "data": data})
    if not pdfs:
        return None
    # Imported_file/url önce, linked dosyalar (yerel path) son tercih
    pdfs.sort(key=lambda p: 0 if p["link_mode"] in ("imported_file", "imported_url") else 1)
    return pdfs[0]


def download_attachment_pdf(
    item_key: str,
    dest_dir: Path,
    api_key: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[Path]:
    """Bir Zotero item'ının PDF attachment'ını indir. Yok ise None."""
    api_key, user_id = _get_credentials(api_key, user_id)
    headers = _headers(api_key)

    try:
        children = _list_children(user_id, headers, item_key)
    except Exception as e:
        logger.warning(f"[Zotero] Children listesi alınamadı ({item_key}): {e}")
        return None

    attachment = _pick_pdf_attachment(children)
    if not attachment:
        logger.debug(f"[Zotero] PDF attachment yok: {item_key}")
        return None

    att_key = attachment["key"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{item_key}_{att_key}.pdf"
    if dest_path.exists() and dest_path.stat().st_size > 1024:
        return dest_path

    file_url = f"{API_BASE}/users/{user_id}/items/{att_key}/file"
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(file_url, headers=headers)
            if resp.status_code == 404:
                logger.debug(f"[Zotero] PDF dosyası API'de yok (linked file olabilir): {item_key}")
                return None
            resp.raise_for_status()
            content = resp.content
            if not content or len(content) < 1024:
                logger.warning(f"[Zotero] PDF içeriği çok küçük: {item_key}")
                return None
            # PDF magic number kontrolü
            if not content[:4] == b"%PDF":
                logger.warning(f"[Zotero] Yanıt PDF değil ({item_key}): {content[:32]!r}")
                return None
            dest_path.write_bytes(content)
            logger.info(f"[Zotero] PDF indirildi: {dest_path.name} ({len(content)//1024} KB)")
            return dest_path
    except Exception as e:
        logger.warning(f"[Zotero] PDF indirme hatası ({item_key}): {e}")
        return None


def deduplicate_zotero(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ID üzerinden tekilleştir."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for p in papers:
        pid = p.get("id") or p.get("zotero_key")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(p)
    return out
