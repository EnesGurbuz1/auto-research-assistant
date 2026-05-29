"""
Literature Agent — seçilen kaynaklardan (arXiv, Scopus, Zotero) makale toplar ve tekilleştirir.
Yıl filtresi ve max_results cap uygulanır.

Zotero kaynağında:
  - Kullanıcının belirttiği collection key (state["zotero_collection_key"]) zorunlu.
  - Web API üzerinden makaleler çekilir (planner sorguları kullanılmaz; tüm collection alınır).
  - Year filter uygulanır.
  - PDF'ler pdf_fetcher_node tarafından Zotero attachment'ından çekilir.
"""

import time
from pathlib import Path
from loguru import logger
from src.graph.state import ResearchState
from src.tools.arxiv_tool import search_arxiv, deduplicate
from src.tools.scopus_tool import search_scopus, enrich_with_semantic_scholar, deduplicate_combined
from src.tools.zotero_tool import fetch_collection_items, deduplicate_zotero
from src.tools.gdrive_tool import fetch_drive_folder, deduplicate_drive

DEFAULT_MAX_PER_QUERY = 15
QUERY_DELAY = 6.0
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _gather_drive(state: ResearchState, max_total: int, year_from: int, year_to: int):
    folder_url = (state.get("drive_folder_url") or "").strip()
    if not folder_url:
        logger.warning("[Literature] Drive seçili ama klasör linki boş, atlanıyor")
        return [], "Drive klasör linki verilmedi"
    try:
        papers = fetch_drive_folder(
            folder_url=folder_url,
            project_root=_PROJECT_ROOT,
            year_from=year_from,
            year_to=year_to,
            max_results=max_total,
        )
        papers = deduplicate_drive(papers)
        logger.info(f"[Literature] Drive: {len(papers)} makale hazırlandı")
        return papers, None
    except Exception as e:
        logger.exception(f"[Literature] Drive hatası: {e}")
        return [], f"Drive hatası: {e}"


def _gather_zotero(state: ResearchState, max_total: int, year_from: int, year_to: int):
    collection_key = state.get("zotero_collection_key") or ""
    if not collection_key:
        logger.warning("[Literature] Zotero seçili ama collection_key boş, atlanıyor")
        return [], "Zotero collection seçilmedi"

    try:
        papers = fetch_collection_items(
            collection_key=collection_key,
            year_from=year_from,
            year_to=year_to,
            max_results=max_total,
        )
        papers = deduplicate_zotero(papers)
        logger.info(f"[Literature] Zotero: {len(papers)} makale çekildi")
        return papers, None
    except Exception as e:
        logger.exception(f"[Literature] Zotero hatası: {e}")
        return [], f"Zotero hatası: {e}"


def literature_node(state: ResearchState) -> dict:
    sources = state.get("sources", ["arxiv"])
    max_total = state.get("max_results", DEFAULT_MAX_PER_QUERY)
    year_from = state.get("year_from", 1990)
    year_to = state.get("year_to", 2099)

    use_arxiv = "arxiv" in sources
    use_scopus = "scopus" in sources
    use_zotero = "zotero" in sources
    use_drive = "drive" in sources

    logger.info(
        f"[Literature] kaynaklar: {sources} | max {max_total} | yıl: {year_from}-{year_to}"
    )

    all_papers: list = []
    messages: list = []

    # --- Zotero (sorgu kullanmaz, collection bazlı) ---
    if use_zotero:
        zotero_papers, zerr = _gather_zotero(state, max_total, year_from, year_to)
        all_papers.extend(zotero_papers)
        if zerr:
            messages.append(f"⚠️ {zerr}")

    # --- Google Drive (sorgu kullanmaz, klasördeki PDF'ler) ---
    if use_drive:
        drive_papers, derr = _gather_drive(state, max_total, year_from, year_to)
        all_papers.extend(drive_papers)
        if derr:
            messages.append(f"⚠️ {derr}")

    # --- arXiv / Scopus (planner sorgularını gerektirir) ---
    if use_arxiv or use_scopus:
        queries = state.get("search_queries", [state["query"]])
        total = len(queries)
        failed_queries: list = []

        for i, q in enumerate(queries, 1):
            logger.info(f"[Literature] Sorgu {i}/{total}: {q[:80]}")

            if use_arxiv:
                arxiv_papers = search_arxiv(q, max_results=max_total)
                if arxiv_papers:
                    all_papers.extend(arxiv_papers)
                    logger.info(f"[Literature] arXiv {i}/{total}: {len(arxiv_papers)} makale")
                else:
                    logger.warning(f"[Literature] arXiv {i}/{total}: sonuç bulunamadı")

            if use_scopus:
                scopus_papers = search_scopus(
                    q, max_results=max_total, year_from=year_from, year_to=year_to
                )
                if scopus_papers:
                    scopus_papers = enrich_with_semantic_scholar(scopus_papers)
                    all_papers.extend(scopus_papers)
                    logger.info(f"[Literature] Scopus {i}/{total}: {len(scopus_papers)} makale")
                else:
                    logger.warning(f"[Literature] Scopus {i}/{total}: sonuç bulunamadı")

            if not use_arxiv and not use_scopus:
                failed_queries.append(q)

            if i < total:
                time.sleep(QUERY_DELAY)

        if failed_queries:
            messages.append(f"⚠️ {len(failed_queries)} sorgu sonuçsuz kaldı")

    # --- Deduplication ---
    unique = deduplicate_combined(all_papers)
    before_cap = len(unique)

    # Çoklu kaynak cap dengesi (zotero, drive, arxiv, scopus arası eşit slot)
    active_sources = [s for s in sources if s in ("arxiv", "scopus", "zotero", "drive")]
    if len(active_sources) > 1:
        per_source = max(1, max_total // len(active_sources))
        by_source: dict = {}
        for p in unique:
            src = p.get("source", "?")
            by_source.setdefault(src, []).append(p)

        capped: list = []
        for src in active_sources:
            capped.extend(by_source.get(src, [])[:per_source])

        # Kalan slotları doldurmak için diğer kaynaklardan al
        remaining = max_total - len(capped)
        if remaining > 0:
            used_ids = {id(p) for p in capped}
            for p in unique:
                if id(p) not in used_ids and remaining > 0:
                    capped.append(p)
                    remaining -= 1

        unique = capped
    else:
        unique = unique[:max_total]

    # Yıl filtresi
    before_year = len(unique)
    unique = [p for p in unique if year_from <= (p.get("year") or 0) <= year_to]

    source_counts: dict = {}
    for p in unique:
        src = p.get("source", "?")
        source_counts[src] = source_counts.get(src, 0) + 1

    source_summary = ", ".join(f"{src}: {cnt}" for src, cnt in source_counts.items())
    logger.info(
        f"[Literature] Dedup: {before_cap} → cap: {min(before_cap, max_total)} "
        f"→ yıl filtresi: {len(unique)} makale kaldı ({source_summary})"
    )

    messages.insert(
        0,
        f"Literatür taraması tamamlandı: {len(unique)} makale bulundu "
        f"({year_from}-{year_to}) [{source_summary or 'sonuç yok'}]",
    )
    if before_year > len(unique):
        messages.append(f"Yıl filtresi: {before_year - len(unique)} makale çıkarıldı")

    return {
        "papers": unique,
        "current_step": "literature",
        "messages": messages,
    }
