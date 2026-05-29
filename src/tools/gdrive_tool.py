"""
Google Drive Folder Tool.

Kullanım: Paylaşıma açık ("anyone with the link" / "Bağlantıya sahip olan herkes")
bir Google Drive **klasör** linki verilir. Klasördeki tüm PDF'ler indirilir,
metadata + ilk sayfa metni çıkarılır ve pipeline'ın standart paper dict formatına
çevrilir. Auth gerektirmez; `gdown` paketinin public folder desteğini kullanır.

Standart paper formatı (Zotero/arXiv ile uyumlu):
{
    "id": <DOI varsa> | "GDRIVE:<file_id>",
    "title", "authors", "year", "published",
    "abstract", "categories", "venue", "doi",
    "doi_url", "arxiv_url"="", "scopus_url"="", "pdf_url"="",
    "source": "drive",
    "drive_file_id": <Drive file id>,
    "pdf_local_path": <Path>,
    "full_text": <ilk ~6000 char> (PDF Fetcher node tarafından zenginleştirilir),
}
"""

from __future__ import annotations

import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from loguru import logger

try:
    import gdown
    _GDOWN_AVAILABLE = True
except ImportError:
    _GDOWN_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_OPEN_ID_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def extract_folder_id(url: str) -> Optional[str]:
    """Drive folder URL'sinden klasör id'sini çıkar.

    Desteklenen biçimler:
      https://drive.google.com/drive/folders/<ID>
      https://drive.google.com/drive/folders/<ID>?usp=sharing
      https://drive.google.com/open?id=<ID>
      Düz <ID> (33+ karakter, Drive id formatı)
    """
    if not url:
        return None
    url = url.strip()
    m = _FOLDER_RE.search(url)
    if m:
        return m.group(1)
    m = _OPEN_ID_RE.search(url)
    if m:
        return m.group(1)
    # Düz id verildiyse
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", url):
        return url
    return None


# ---------------------------------------------------------------------------
# Folder download
# ---------------------------------------------------------------------------


def download_folder(folder_url: str, dest_dir: Path) -> List[Path]:
    """Public Drive klasörünü indirir. PDF dosyalarının yerel yollarını döndürür."""
    if not _GDOWN_AVAILABLE:
        raise RuntimeError(
            "gdown paketi yüklü değil. 'pip install gdown' ile kur."
        )

    folder_id = extract_folder_id(folder_url)
    if not folder_id:
        raise ValueError(f"Geçerli bir Google Drive klasör linki bulunamadı: {folder_url}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    drive_url = f"https://drive.google.com/drive/folders/{folder_id}"
    logger.info(f"[Drive] Klasör indiriliyor: {folder_id} → {dest_dir}")

    # gdown API sürümleri arasında kwarg'lar değişti (örn. 6.x'te `remaining_ok`
    # kaldırıldı). Bu yüzden desteklenen kwarg setini runtime'da tespit ediyoruz.
    import inspect as _inspect
    supported = set(_inspect.signature(gdown.download_folder).parameters)
    kwargs = {"url": drive_url, "output": str(dest_dir), "quiet": True}
    if "use_cookies" in supported:
        kwargs["use_cookies"] = False
    if "remaining_ok" in supported:
        kwargs["remaining_ok"] = True

    try:
        downloaded = gdown.download_folder(**kwargs)
    except Exception as e:
        raise RuntimeError(
            f"Drive klasörü indirilemedi (klasör paylaşımı 'Bağlantıya sahip herkes' "
            f"olarak ayarlı mı? Hata: {e})"
        ) from e

    if not downloaded:
        # gdown bazen None döndürebilir; klasörü manuel tara
        downloaded = [str(p) for p in dest_dir.rglob("*") if p.is_file()]

    pdfs = [Path(p) for p in downloaded if str(p).lower().endswith(".pdf") and Path(p).exists()]
    logger.info(f"[Drive] İndirme tamamlandı: {len(pdfs)} PDF bulundu")
    return pdfs


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20\d{2})\b")
_EMAIL_RE = re.compile(r"\S+@\S+")


def _extract_first_page_text(pdf_path: Path, pages: int = 2) -> str:
    if not _FITZ_AVAILABLE:
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        parts = []
        for i, page in enumerate(doc):
            if i >= pages:
                break
            parts.append(page.get_text())
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"[Drive] PDF okunamadı ({pdf_path.name}): {e}")
        return ""


def _pdf_metadata(pdf_path: Path) -> Dict[str, str]:
    if not _FITZ_AVAILABLE:
        return {}
    try:
        doc = fitz.open(str(pdf_path))
        meta = dict(doc.metadata or {})
        doc.close()
        return meta
    except Exception:
        return {}


def _guess_title(meta: Dict[str, str], first_page: str, filename: str) -> str:
    # 1) PDF metadata
    t = (meta.get("title") or "").strip()
    if t and len(t) > 8 and not t.lower().startswith("untitled"):
        return t
    # 2) İlk sayfanın boş olmayan ilk anlamlı satırı
    if first_page:
        for line in first_page.splitlines():
            line = line.strip()
            if 15 <= len(line) <= 250 and not _EMAIL_RE.search(line) and not line.lower().startswith(("doi", "arxiv", "abstract")):
                return line
    # 3) Dosya adı
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip()


def _guess_authors(meta: Dict[str, str], first_page: str) -> List[str]:
    raw = (meta.get("author") or "").strip()
    if raw:
        # "A. Smith; B. Jones" / "A. Smith, B. Jones" formatlarını destekle
        parts = re.split(r"[;,]\s+|\s+and\s+", raw)
        names = [p.strip() for p in parts if p.strip()]
        if names:
            return names[:20]
    # Heuristic: ilk sayfanın ilk 20 satırından e-mail içeren satırın bir önceki satırını dene
    if first_page:
        lines = [l.strip() for l in first_page.splitlines() if l.strip()][:30]
        for i, line in enumerate(lines):
            if _EMAIL_RE.search(line) and i > 0:
                cand = lines[i - 1]
                if len(cand) < 200 and re.search(r"[A-Z]", cand):
                    parts = re.split(r"[,;]|\sand\s", cand)
                    names = [p.strip() for p in parts if 2 < len(p.strip()) < 80]
                    if names:
                        return names
    return []


def _guess_year(meta: Dict[str, str], first_page: str) -> int:
    # PDF creationDate: "D:20230615..."
    for key in ("creationDate", "modDate"):
        v = meta.get(key, "")
        m = re.search(r"(19[8-9]\d|20\d{2})", v or "")
        if m:
            return int(m.group(1))
    if first_page:
        # İlk sayfada en yaygın olan yılı al (yayın yılı genelde başta görünür)
        years = _YEAR_RE.findall(first_page[:2000])
        if years:
            from collections import Counter
            return int(Counter(years).most_common(1)[0][0])
    return 0


def _guess_doi(first_page: str) -> str:
    if not first_page:
        return ""
    m = _DOI_RE.search(first_page)
    return m.group(0).rstrip(".,;)") if m else ""


def _guess_abstract(first_page: str) -> str:
    if not first_page:
        return ""
    lower = first_page.lower()
    for marker in ("abstract", "özet", "summary"):
        idx = lower.find(marker)
        if idx == -1:
            continue
        start = idx + len(marker)
        chunk = first_page[start : start + 2200].strip(" :.\n")
        # Bitişi "introduction" / "keywords" / "1 introduction" ile kırp
        end_lower = chunk.lower()
        for end in ("introduction", "keywords", "1 introduction", "i. introduction", "anahtar kelimeler", "giriş"):
            ei = end_lower.find(end)
            if ei > 80:
                chunk = chunk[:ei]
                break
        return chunk.strip()
    # Bulunamadıysa ilk uzun paragrafı al
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", first_page) if len(p.strip()) > 200]
    return paragraphs[0][:1500] if paragraphs else ""


def _drive_file_id_from_path(pdf_path: Path) -> str:
    """gdown indirme sırasında dosya id'sini direkt vermiyor; içerik hash'i fallback."""
    h = hashlib.md5(pdf_path.read_bytes()[:1024 * 64]).hexdigest()[:16]
    return h


def pdf_to_paper(pdf_path: Path) -> Optional[Dict[str, Any]]:
    """Bir PDF dosyasından paper dict üret."""
    if not pdf_path.exists() or pdf_path.stat().st_size < 1024:
        return None

    meta = _pdf_metadata(pdf_path)
    first_page = _extract_first_page_text(pdf_path, pages=2)

    title = _guess_title(meta, first_page, pdf_path.name)
    authors = _guess_authors(meta, first_page)
    year = _guess_year(meta, first_page)
    doi = _guess_doi(first_page)
    abstract = _guess_abstract(first_page)
    file_id = _drive_file_id_from_path(pdf_path)

    pid = doi if doi else f"GDRIVE:{file_id}"

    return {
        "id": pid,
        "title": title,
        "authors": authors,
        "year": year,
        "published": str(year) if year else "",
        "abstract": abstract,
        "categories": [],
        "venue": (meta.get("subject") or "").strip(),
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "arxiv_url": "",
        "scopus_url": "",
        "pdf_url": "",
        "source": "drive",
        "drive_file_id": file_id,
        "drive_filename": pdf_path.name,
        "pdf_local_path": str(pdf_path),
        "full_text": None,
        "item_type": "drivePdf",
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def fetch_drive_folder(
    folder_url: str,
    project_root: Path,
    year_from: int = 1990,
    year_to: int = 2099,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Folder linkini alır, PDF'leri indirir ve paper dict'leri döndürür."""
    dest_dir = project_root / "data" / "papers" / "pdfs" / "drive"
    pdfs = download_folder(folder_url, dest_dir)

    papers: List[Dict[str, Any]] = []
    for pdf_path in pdfs[: max_results * 3]:  # parse cap (filtreler sonra)
        paper = pdf_to_paper(pdf_path)
        if not paper:
            continue
        yr = paper.get("year") or 0
        # Yıl bilinmiyorsa (0) eleme (PDF'ten yıl çıkmayabilir)
        if yr and not (year_from <= yr <= year_to):
            continue
        papers.append(paper)
        if len(papers) >= max_results:
            break

    logger.info(
        f"[Drive] {len(papers)} makale hazırlandı "
        f"(yıl filtresi {year_from}-{year_to}, {len(pdfs)} PDF'den)"
    )
    return papers


def deduplicate_drive(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for p in papers:
        key = p.get("id") or p.get("drive_file_id") or p.get("drive_filename") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
