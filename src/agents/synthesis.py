"""
Synthesis Agent — hiyerarşik, çok geçişli (multi-pass) RAG sentezi.

Akış:
  1. Paper-level RAG ile top-K makale seçilir (current-run filtreli).
  2. Chunk-level RAG ile sorguya en alakalı chunk'lar getirilir, paper bazında
     gruplanır (her makale için top-3 chunk). PDF zenginleşmemiş makaleler için
     abstract fallback.
  3. **Pass 1 — Per-paper extraction**: Makaleler 4'lü batch'ler halinde LLM'e
     verilir, her makaleden yapılandırılmış JSON çıkarılır
     (key_findings, methods, datasets, limitations, contribution, relevance).
  4. **Pass 2 — Cross-paper synthesis**: Tüm extraction'lar + chunk özetleri
     birleştirilir, son sentez JSON'ı üretilir (gap_analysis, trend_analysis,
     active_researchers, key_papers, summary).

Hallüsinasyon önleme:
  - Yalnızca Qdrant'tan gelen makaleler context'tir.
  - Tüm bulgular [N] formatında atıflıdır; N, papers listesindeki 1-tabanlı pozisyon.
  - generate_json temperature=0.1 (deterministik).
"""

from __future__ import annotations

import math
from typing import List, Dict, Any
from loguru import logger

from src.graph.state import ResearchState
from src.agents.llm import generate_json
from src.rag.embedder import embed_text
from src.rag.vector_store import search_similar, search_chunks

DEFAULT_TOP_K = 20
CHUNKS_PER_PAPER = 3
GLOBAL_CHUNK_POOL = 120  # paper-level filtreden önce çekilecek toplam chunk
EXTRACTION_BATCH = 4     # her LLM çağrısında kaç makale işlenecek

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """\
Sen bir akademik makale analiz uzmanısın.
Verilen makale parçalarını (başlık, özet, ilgili pasajlar) dikkatle okur ve
yapılandırılmış JSON çıkarımı yaparsın. ASLA verilmeyen bilgileri uydurmazsın.
Bilgi makalede açıkça yer almıyorsa ilgili alanı boş bırakırsın.
"""

EXTRACTION_PROMPT_TEMPLATE = """\
Aşağıda {n} akademik makalenin bilgileri var. Kullanıcının araştırma sorusu:
"{query}"

Her makale için, SADECE verilen metinlere dayanarak aşağıdaki JSON yapısını üret.
Hiçbir alanı uydurma; bilgi yoksa boş liste/string bırak.

Makaleler:
---
{papers_block}
---

ÇIKTI FORMATI (kesinlikle bu yapıda bir JSON):
{{
  "extractions": [
    {{
      "doc_index": <kaynak makale numarası, [N] içinde verilen N>,
      "relevance_to_query": "<1 cümle: bu makale soruyla ne kadar ve nasıl ilgili>",
      "core_contribution": "<1-2 cümle: makalenin ana katkısı>",
      "key_findings": ["<bulgu 1>", "<bulgu 2>"],
      "methods": ["<yöntem/teknik>"],
      "datasets": ["<veri seti/test ortamı>"],
      "limitations": ["<sınırlama, açıkça belirtilen veya çıkarılabilen>"],
      "open_questions": ["<makalenin bıraktığı açık soru, varsa>"]
    }}
  ]
}}
"""

SYNTHESIS_SYSTEM = """\
Sen bir tez danışmanı seviyesinde akademik sentez yazarısın.
Sana verilen yapılandırılmış makale özetlerinden (extractions) ve sorguya en alakalı
metin pasajlarından (chunks) yararlanarak DERİN, KESKİN ve KANITA DAYALI bir
araştırma sentezi üretirsin.

Kurallar:
- ASLA makaleler dışında kaynak uydurma, hallüsinasyon yapma.
- Her bulgu, eğilim, sonuç için mutlaka [N] (gerekirse [N, M]) formatında atıf ver.
- Sayılar (N) makale listesindeki 1-tabanlı sıra numaralarıdır.
- Aynı yorumu tekrar etme; içgörü odaklı yaz.
- Gap analizi: gerçekten çözülmemiş, makalelerin LIMITASYON/açık soru olarak
  işaret ettiği veya hiçbir makalede ele alınmayan konuları ayırt et.
- Trend analizi: yıl bazlı yöntem değişimi, popülerleşen veya azalan yaklaşımlar.
- Akademik dil kullan, abartı yapma.
"""

SYNTHESIS_PROMPT_TEMPLATE = """\
Araştırma sorusu: "{query}"

Aşağıda {n_papers} makaleden çıkarılmış yapılandırılmış özetler ve en alakalı
metin pasajları (chunks) var. Her bilgi [N] kaynak numarasıyla etiketli; N, makale
listesindeki orijinal pozisyondur.

=== MAKALE ÖZETLERİ ({n_papers}) ===
{extractions_block}

=== EN ALAKALI METİN PASAJLARI ({n_chunks}) ===
{chunks_block}

SADECE yukarıdaki verilere dayanarak, KAPSAMLI ve DERİN bir araştırma sentezi
yap. Sonucu yalnızca aşağıdaki JSON şemasında döndür:

{{
  "summary": "<5-7 cümle, akademik bir abstract gibi; tüm önemli noktaları [N] atıflarıyla bağlayan derinlikli özet>",
  "gap_analysis": {{
    "solved_problems": ["<çözülmüş problem, [N]>"],
    "open_problems": ["<açık problem, [N]>"],
    "research_gaps": ["<makaleler arası karşılaştırmadan çıkan boşluk, [N, M]>"]
  }},
  "trend_analysis": {{
    "emerging_methods": ["<yükselen yöntem [N]>"],
    "temporal_shift": "<2-3 cümle: yıllar arası kayma [N, M]>",
    "hot_topics": ["<güncel konu [N]>"],
    "declining_approaches": ["<azalan/eleştirilen yaklaşım [N], varsa>"]
  }},
  "methodological_landscape": {{
    "dominant_methods": ["<en yaygın yöntem [N, M]>"],
    "method_clusters": [
      {{"name": "<küme adı>", "papers": [<N>, <M>], "description": "<1 cümle>"}}
    ]
  }},
  "active_researchers": [
    {{"name": "<Yazar Adı>", "affiliation": "", "focus": "<1 cümle>"}}
  ],
  "key_papers": [
    {{"title": "<başlık>", "year": <yıl>, "doc_index": <N>, "why_important": "<1-2 cümle>"}}
  ],
  "thesis_recommendations": [
    "<bu sentezden çıkan, doğrudan tez çalışmasına yön verecek somut öneri [N, M]>"
  ]
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_position_map(papers: List[Dict[str, Any]]) -> Dict[str, int]:
    pos: Dict[str, int] = {}
    for i, p in enumerate(papers, 1):
        pid = p.get("id") or p.get("arxiv_id") or ""
        if pid:
            pos[pid] = i
    return pos


def _select_top_papers(
    query_vec: List[float],
    papers: List[Dict[str, Any]],
    position_map: Dict[str, int],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Paper-level RAG; current-run filtreli."""
    fetch_k = max(top_k * 3, len(papers))
    hits = search_similar(query_vec, top_k=fetch_k)
    selected: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for hit in hits:
        pid = hit.get("arxiv_id", "")
        if pid not in position_map or pid in seen_ids:
            continue
        seen_ids.add(pid)
        hit["global_index"] = position_map[pid]
        selected.append(hit)
        if len(selected) >= top_k:
            break
    # RAG hiçbir şey döndürmediyse fallback: ilk top_k makale
    if not selected:
        for p in papers[:top_k]:
            pid = p.get("id", "")
            selected.append({**p, "arxiv_id": pid, "global_index": position_map.get(pid, 0)})
    return selected


def _group_chunks_by_paper(
    query_vec: List[float],
    paper_ids: List[str],
    position_map: Dict[str, int],
    per_paper: int,
) -> Dict[str, List[Dict[str, Any]]]:
    """Global chunk pool çek, paper_id bazında en alakalı `per_paper` chunk'ı tut."""
    pool = search_chunks(query_vec, top_k=GLOBAL_CHUNK_POOL, paper_ids=paper_ids)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for ch in pool:
        pid = ch.get("paper_id", "")
        if pid not in position_map:
            continue
        bucket = grouped.setdefault(pid, [])
        if len(bucket) < per_paper:
            ch["global_index"] = position_map[pid]
            bucket.append(ch)
    return grouped


def _format_paper_block(
    paper: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    global_index: int,
) -> str:
    authors = ", ".join((paper.get("authors") or [])[:3])
    if len(paper.get("authors") or []) > 3:
        authors += " et al."
    abstract = (paper.get("abstract") or "")[:600]
    chunk_text = "\n".join(
        f"  • {c.get('chunk_text','')[:500].strip()}" for c in chunks if c.get("chunk_text")
    ) or "  (tam metin yok, sadece özet)"
    return (
        f"[{global_index}] {paper.get('title', 'Başlık yok')} ({paper.get('year', '?')})\n"
        f"  Yazarlar: {authors or 'bilinmiyor'}\n"
        f"  Özet: {abstract}\n"
        f"  En alakalı pasajlar:\n{chunk_text}"
    )


def _extract_papers_batch(
    query: str,
    papers_batch: List[Dict[str, Any]],
    chunks_by_paper: Dict[str, List[Dict[str, Any]]],
    full_papers_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Bir grup makale için yapılandırılmış extraction üret."""
    blocks: List[str] = []
    for p in papers_batch:
        pid = p.get("arxiv_id") or p.get("id") or ""
        gidx = p.get("global_index", 0)
        chunks = chunks_by_paper.get(pid, [])
        # Tam paper objesi varsa kullan (abstract / authors zengin)
        rich = full_papers_map.get(pid, p)
        blocks.append(_format_paper_block(rich, chunks, gidx))

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        n=len(papers_batch),
        query=query,
        papers_block="\n\n".join(blocks),
    )

    result = generate_json(prompt, system=EXTRACTION_SYSTEM)
    extractions = result.get("extractions") if isinstance(result, dict) else None
    if not isinstance(extractions, list):
        logger.warning(
            f"[Synthesis] Extraction batch beklenen formatta değil: {type(extractions).__name__}"
        )
        return []
    return extractions


def _format_extraction(ext: Dict[str, Any]) -> str:
    idx = ext.get("doc_index", "?")
    lines = [f"[{idx}] {ext.get('core_contribution', '').strip()}"]
    rel = ext.get("relevance_to_query", "")
    if rel:
        lines.append(f"  Soruyla ilişki: {rel}")
    for key, label in [
        ("key_findings", "Bulgular"),
        ("methods", "Yöntemler"),
        ("datasets", "Veri/test"),
        ("limitations", "Sınırlamalar"),
        ("open_questions", "Açık sorular"),
    ]:
        items = ext.get(key) or []
        if items:
            items_text = "; ".join(str(x) for x in items if x)
            if items_text:
                lines.append(f"  {label}: {items_text}")
    return "\n".join(lines)


def _format_global_chunks(
    chunks_by_paper: Dict[str, List[Dict[str, Any]]], limit: int = 25
) -> str:
    flat: List[Dict[str, Any]] = []
    for pid, chs in chunks_by_paper.items():
        for c in chs:
            flat.append(c)
    flat.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    flat = flat[:limit]
    lines = []
    for c in flat:
        gidx = c.get("global_index", "?")
        snippet = (c.get("chunk_text") or "")[:450].strip()
        if snippet:
            lines.append(f"[{gidx}] {snippet}")
    return "\n\n".join(lines) if lines else "(chunk yok)"


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


def synthesis_node(state: ResearchState) -> dict:
    query = state["query"]
    papers = state.get("papers", [])
    if not papers:
        return {
            "synthesis": {"error": "Sentez için makale yok."},
            "current_step": "synthesis",
            "messages": ["Sentez: makale yok, atlandı"],
        }

    top_k = max(8, min(state.get("max_results", DEFAULT_TOP_K), DEFAULT_TOP_K))
    position_map = _build_position_map(papers)
    full_papers_map = {p.get("id", ""): p for p in papers}

    logger.info(
        f"[Synthesis] Hiyerarşik sentez başlıyor | papers={len(papers)} top_k={top_k}"
    )

    query_vec = embed_text(query)

    # 1) Paper-level top-K
    top_papers = _select_top_papers(query_vec, papers, position_map, top_k)
    logger.info(f"[Synthesis] Paper-level RAG: {len(top_papers)} makale seçildi")

    selected_ids = [p.get("arxiv_id") or p.get("id") or "" for p in top_papers]

    # 2) Chunk-level grup
    chunks_by_paper = _group_chunks_by_paper(
        query_vec, selected_ids, position_map, CHUNKS_PER_PAPER
    )
    total_chunks_used = sum(len(v) for v in chunks_by_paper.values())
    logger.info(
        f"[Synthesis] Chunk-level RAG: {total_chunks_used} chunk, "
        f"{len(chunks_by_paper)} makale tam metin destekli"
    )

    # 3) Pass 1: per-paper extraction (batched)
    batches = [
        top_papers[i : i + EXTRACTION_BATCH]
        for i in range(0, len(top_papers), EXTRACTION_BATCH)
    ]
    all_extractions: List[Dict[str, Any]] = []
    for bi, batch in enumerate(batches, 1):
        logger.info(
            f"[Synthesis] Extraction batch {bi}/{len(batches)} ({len(batch)} makale)"
        )
        exts = _extract_papers_batch(query, batch, chunks_by_paper, full_papers_map)
        all_extractions.extend(exts)

    if not all_extractions:
        logger.warning("[Synthesis] Extraction boş döndü, son sentez yine de denenecek")

    # 4) Pass 2: final cross-paper synthesis
    extractions_block = "\n\n".join(_format_extraction(e) for e in all_extractions) or "(extraction yok)"
    chunks_block = _format_global_chunks(chunks_by_paper, limit=25)

    final_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        query=query,
        n_papers=len(top_papers),
        n_chunks=total_chunks_used,
        extractions_block=extractions_block,
        chunks_block=chunks_block,
    )
    final_result = generate_json(final_prompt, system=SYNTHESIS_SYSTEM)

    if not final_result:
        final_result = {"error": "Final sentez üretilemedi"}

    # Meta bilgiler
    used_indices = sorted({p.get("global_index") for p in top_papers if isinstance(p.get("global_index"), int)})
    final_result["rag_paper_indices"] = used_indices
    final_result["extractions"] = all_extractions  # UI'da görüntülemek için sakla

    # UI için kaynak listesi
    final_result["rag_papers"] = []
    for p in top_papers:
        pid = p.get("arxiv_id") or p.get("id") or ""
        rich = full_papers_map.get(pid, p)
        final_result["rag_papers"].append(
            {
                "global_index": p.get("global_index", "?"),
                "title": rich.get("title", ""),
                "authors": rich.get("authors", []),
                "year": rich.get("year", "?"),
                "source": rich.get("source", ""),
                "arxiv_url": rich.get("arxiv_url", ""),
                "arxiv_id": pid,
                "scopus_url": rich.get("scopus_url", ""),
                "doi_url": rich.get("doi_url", ""),
                "zotero_key": rich.get("zotero_key", ""),
                "chunks_used": len(chunks_by_paper.get(pid, [])),
            }
        )

    logger.info(
        f"[Synthesis] Tamamlandı: {len(top_papers)} makale, "
        f"{len(all_extractions)} extraction, {total_chunks_used} chunk kullanıldı"
    )

    return {
        "synthesis": final_result,
        "current_step": "synthesis",
        "messages": [
            f"Hiyerarşik sentez tamamlandı: {len(top_papers)} makale, "
            f"{len(all_extractions)} per-paper extraction, {total_chunks_used} chunk"
        ],
    }
