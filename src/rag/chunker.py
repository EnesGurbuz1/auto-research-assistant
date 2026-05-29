"""
Metin chunk'lama — paragraf-aware, overlap'li.

Akademik makaleler için ~ 1000 karakter chunk + 200 karakter overlap ideal
(MiniLM context'ini doldurur ama section bağlamını kaybetmez).
"""

from __future__ import annotations
import re
from typing import List


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 200
MIN_CHUNK_SIZE = 200


def _split_paragraphs(text: str) -> List[str]:
    """Boş satır veya çift newline'la paragrafları ayır."""
    parts = re.split(r"\n\s*\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> List[str]:
    """Basit cümle bölücü (regex). Akademik metinlerde mükemmel değil ama yeterli."""
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])", text)
    return [s.strip() for s in pieces if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[str]:
    """
    Metni paragraf-aware overlap'li chunk'lara böl.

    Algoritma:
      1. Paragraflara böl.
      2. Mevcut chunk + paragraf chunk_size'ı aşmıyorsa ekle, aşıyorsa flush.
      3. Tek paragraf chunk_size'tan büyükse cümle bazlı yeniden böl.
      4. Her chunk arasında son `overlap` karakter tekrar edilir (context köprüsü).
    """
    if not text or not text.strip():
        return []
    text = re.sub(r"[ \t]+", " ", text)

    paragraphs = _split_paragraphs(text)
    chunks: List[str] = []
    buffer = ""

    def flush():
        nonlocal buffer
        if buffer.strip() and len(buffer.strip()) >= MIN_CHUNK_SIZE // 2:
            chunks.append(buffer.strip())
        buffer = ""

    for p in paragraphs:
        if len(p) > chunk_size:
            # Büyük paragrafı cümle bazlı parçala
            flush()
            sentence_buffer = ""
            for s in _split_sentences(p):
                if len(sentence_buffer) + len(s) + 1 <= chunk_size:
                    sentence_buffer = (sentence_buffer + " " + s).strip()
                else:
                    if sentence_buffer:
                        chunks.append(sentence_buffer.strip())
                    sentence_buffer = s
            if sentence_buffer:
                chunks.append(sentence_buffer.strip())
            continue

        if len(buffer) + len(p) + 2 <= chunk_size:
            buffer = (buffer + "\n\n" + p).strip() if buffer else p
        else:
            flush()
            buffer = p

    flush()

    # Overlap uygula (chunk[i]'in sonundan chunk[i+1]'in başına `overlap` karakter)
    if overlap > 0 and len(chunks) > 1:
        with_overlap: List[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            with_overlap.append((prev_tail + " " + chunks[i]).strip())
        chunks = with_overlap

    return chunks
