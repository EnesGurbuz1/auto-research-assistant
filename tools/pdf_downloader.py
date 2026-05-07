"""
PDF Downloader - Akademik makale PDF indirme aracı.
Open Access PDF'leri indirir, rate limiting uygular.
"""

import os
import time
import hashlib
from pathlib import Path
from typing import Optional
from loguru import logger

try:
    import httpx
except ImportError:
    httpx = None


class PDFDownloader:
    """Akademik PDF indirme aracı."""

    def __init__(self, config: dict, project_root: Path):
        self.download_dir = project_root / "data" / "papers" / "pdfs"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ThesisResearchBot/1.0; academic use)"
        }
        self.max_size_mb = 50  # 50 MB limit

    def download(self, url: str, filename: Optional[str] = None) -> Optional[Path]:
        """PDF indir."""
        if httpx is None:
            logger.error("httpx yüklü değil")
            return None

        if not url:
            return None

        # Dosya adı belirle
        if filename is None:
            filename = hashlib.md5(url.encode()).hexdigest()[:12] + ".pdf"
        
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        
        output_path = self.download_dir / filename

        # Zaten indirilmiş mi?
        if output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"PDF zaten mevcut: {filename}")
            return output_path

        try:
            with httpx.Client(
                timeout=60,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                # HEAD ile boyut kontrol
                try:
                    head = client.head(url)
                    content_length = int(head.headers.get("content-length", 0))
                    if content_length > self.max_size_mb * 1024 * 1024:
                        logger.warning(f"PDF çok büyük ({content_length / 1024 / 1024:.1f}MB): {url}")
                        return None
                except Exception:
                    pass

                # İndir
                resp = client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                    logger.warning(f"PDF değil (content-type: {content_type}): {url}")
                    return None

                output_path.write_bytes(resp.content)
                size_mb = len(resp.content) / 1024 / 1024
                logger.info(f"PDF indirildi: {filename} ({size_mb:.1f}MB)")
                return output_path

        except Exception as e:
            logger.error(f"PDF indirme hatası ({url}): {e}")
            return None

    def download_batch(self, urls: list, delay: float = 2.0) -> list:
        """Birden fazla PDF'i sırayla indir."""
        downloaded = []
        for url in urls:
            path = self.download(url)
            if path:
                downloaded.append(path)
            time.sleep(delay)
        return downloaded
