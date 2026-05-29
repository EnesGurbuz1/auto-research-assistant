"""
PDF Parser - PDF dosyalarından metin çıkarma aracı.
PyMuPDF (fitz) kullanır.
"""

from pathlib import Path
from typing import Dict, Optional
from loguru import logger

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class PDFParser:
    """PDF dosyalarından metin çıkarma aracı."""

    def __init__(self):
        if fitz is None:
            logger.warning("PyMuPDF (fitz) yüklü değil: pip install pymupdf")

    def extract_text(self, pdf_path: Path, max_pages: int = 50) -> str:
        """PDF'den metin çıkar."""
        if fitz is None:
            return ""

        if not pdf_path.exists():
            logger.error(f"PDF bulunamadı: {pdf_path}")
            return ""

        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            text_parts = []

            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                text_parts.append(page.get_text())

            doc.close()
            full_text = "\n\n".join(text_parts)
            logger.info(
                f"PDF parse edildi: {pdf_path.name} "
                f"({len(full_text)} karakter, {min(page_count, max_pages)} sayfa)"
            )
            return full_text

        except Exception as e:
            logger.error(f"PDF parse hatası ({pdf_path}): {e}")
            return ""

    def extract_metadata(self, pdf_path: Path) -> Dict:
        """PDF metadata bilgilerini çıkar."""
        if fitz is None:
            return {}

        try:
            doc = fitz.open(str(pdf_path))
            meta = doc.metadata
            info = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "keywords": meta.get("keywords", ""),
                "creator": meta.get("creator", ""),
                "page_count": len(doc),
            }
            doc.close()
            return info
        except Exception as e:
            logger.error(f"Metadata çıkarma hatası ({pdf_path}): {e}")
            return {}

    def extract_abstract(self, pdf_path: Path) -> str:
        """PDF'den abstract bölümünü çıkarmaya çalış."""
        text = self.extract_text(pdf_path, max_pages=3)
        if not text:
            return ""

        # Abstract bölümünü bul
        text_lower = text.lower()
        
        # Olası abstract başlangıç noktaları
        start_markers = ["abstract", "özet"]
        end_markers = ["introduction", "1.", "keywords", "giriş", "anahtar kelimeler"]
        
        for start_marker in start_markers:
            start_idx = text_lower.find(start_marker)
            if start_idx == -1:
                continue
            
            # Abstract sonrasını al
            content_start = start_idx + len(start_marker)
            remaining = text[content_start:content_start + 3000]
            
            # Bitiş noktasını bul
            for end_marker in end_markers:
                end_idx = remaining.lower().find(end_marker)
                if end_idx > 50:  # En az 50 karakter abstract olmalı
                    return remaining[:end_idx].strip()
            
            # Bitiş bulunamazsa ilk 1000 karakteri al
            return remaining[:1000].strip()

        return ""
