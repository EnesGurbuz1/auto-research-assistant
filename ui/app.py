"""
Otonom Araştırma Asistanı — Profesyonel Streamlit UI

Pipeline:
Planner → Literature → Embed → PDF Fetcher → Synthesis
"""

import re
import sys
import os
import time
import json
import html
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from loguru import logger


# =============================================================================
# Path & Env
# =============================================================================

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for _env_path in [ROOT / ".env", ROOT.parent.parent.parent / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break


# =============================================================================
# Loguru → Streamlit session_state bridge (DÜZELTMELİ KISIM)
# =============================================================================

class _StreamlitLogSink:
    """Loguru mesajlarını Streamlit session_state içine yönlendirir."""

    def write(self, message):
        try:
            record = message.record
            level = record["level"].name
            text = str(record["message"])
            timestamp = record["time"].strftime("%H:%M:%S")
            step = st.session_state.get("_active_step", "")

            entry = {
                "time": timestamp,
                "level": level,
                "text": text,
                "step": step,
            }

            st.session_state.setdefault("live_logs", [])
            st.session_state["live_logs"].append(entry)

            if step:
                st.session_state.setdefault("step_logs", {})
                st.session_state["step_logs"].setdefault(step, [])
                st.session_state["step_logs"][step].append(entry)

        except Exception:
            pass


_sink_id = None


def _install_log_sink():
    global _sink_id
    if _sink_id is None:
        _sink_id = logger.add(_StreamlitLogSink(), format="{message}", level="DEBUG")


def _remove_log_sink():
    global _sink_id
    if _sink_id is not None:
        logger.remove(_sink_id)
        _sink_id = None


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Otonom Araştırma Asistanı",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Constants
# =============================================================================

APP_NAME = "Otonom Araştırma Asistanı"
APP_SUBTITLE = "Multi-agent literatür tarama, embedding ve grounded sentez sistemi"

STEPS = {
    "planner": {
        "icon": "🧠",
        "label": "Planlama Ajanı",
        "short": "Planlama",
        "desc": "Araştırma stratejisi ve arama sorguları üretir.",
    },
    "literature": {
        "icon": "📚",
        "label": "Literatür Ajanı",
        "short": "Literatür",
        "desc": "arXiv / Scopus / Zotero kütüphanesinden makaleleri toplar ve filtreler.",
    },
    "embed": {
        "icon": "🗄️",
        "label": "Embedding Ajanı",
        "short": "Embedding",
        "desc": "Makaleleri vektör veritabanına kaydeder.",
    },
    "pdf_fetcher": {
        "icon": "📄",
        "label": "PDF & Chunk Ajanı",
        "short": "PDF",
        "desc": "PDF'leri indirir, chunk'lara böler ve chunk-level RAG için indeksler.",
    },
    "synthesis": {
        "icon": "🔬",
        "label": "Hiyerarşik Sentez Ajanı",
        "short": "Sentez",
        "desc": "Per-paper extraction + cross-paper sentez (multi-pass derin RAG).",
    },
}


def _fresh_defaults() -> Dict[str, Any]:
    return {
        "running": False,
        "done": False,
        "query": "",
        "messages": [],
        "papers": [],
        "synthesis": {},
        "research_plan": "",
        "search_queries": [],
        "embedded_count": 0,
        "pdf_enriched_count": 0,
        "error": None,
        "step_logs": {},
        "live_logs": [],
        "step_status": {},
        "step_times": {},
        "current_step": "",
        "_active_step": "",
        "pipeline_start": None,
        "total_time": 0.0,
        "filters": {},
    }


for k, v in _fresh_defaults().items():
    if k not in st.session_state:
        st.session_state[k] = v


# =============================================================================
# CSS
# =============================================================================

st.markdown(
    """
<style>
/* ==========================================================================
   Global
   ========================================================================== */

:root {
    --app-bg: #f6f8fb;
    --card-bg: #ffffff;
    --card-bg-soft: #f9fafb;
    --border: #e5e7eb;
    --border-strong: #d1d5db;
    --text: #111827;
    --muted: #6b7280;
    --muted-2: #9ca3af;

    --blue: #2563eb;
    --blue-soft: #eff6ff;
    --green: #16a34a;
    --green-soft: #ecfdf5;
    --red: #dc2626;
    --red-soft: #fef2f2;
    --yellow: #d97706;
    --yellow-soft: #fffbeb;
    --purple: #7c3aed;
    --purple-soft: #f5f3ff;

    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
    --shadow-md: 0 10px 24px rgba(15, 23, 42, 0.08);
}

/* Streamlit spacing */
.block-container {
    padding-top: 1.8rem;
    padding-bottom: 3rem;
}

[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid var(--border);
}

hr {
    margin-top: 1.25rem;
    margin-bottom: 1.25rem;
}

/* ==========================================================================
   Hero
   ========================================================================== */

.hero {
    background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.16), transparent 32%),
        linear-gradient(135deg, #ffffff 0%, #f8fafc 52%, #eef2ff 100%);
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: 28px 32px;
    margin-bottom: 22px;
    box-shadow: var(--shadow-md);
}

.hero-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 24px;
}

.hero-title {
    font-size: 2.05rem;
    line-height: 1.15;
    font-weight: 800;
    letter-spacing: -0.035em;
    color: var(--text);
    margin-bottom: 8px;
}

.hero-subtitle {
    color: var(--muted);
    font-size: 1rem;
    max-width: 820px;
    line-height: 1.55;
}

.hero-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 18px;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.85);
    color: #374151;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 7px 11px;
    font-size: 0.78rem;
    font-weight: 600;
    box-shadow: var(--shadow-sm);
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 0.78rem;
    font-weight: 700;
    white-space: nowrap;
    border: 1px solid var(--border);
    background: #ffffff;
    color: #374151;
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
}

/* ==========================================================================
   Search panel
   ========================================================================== */

.search-panel {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 20px;
    box-shadow: var(--shadow-sm);
    margin-bottom: 20px;
}

.panel-title {
    font-size: 1rem;
    font-weight: 750;
    color: var(--text);
    margin-bottom: 4px;
}

.panel-desc {
    color: var(--muted);
    font-size: 0.88rem;
    margin-bottom: 14px;
}

/* ==========================================================================
   Cards and Metrics
   ========================================================================== */

.metric-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px;
    box-shadow: var(--shadow-sm);
}

.metric-label {
    font-size: 0.78rem;
    color: var(--muted);
    font-weight: 650;
    margin-bottom: 6px;
}

.metric-value {
    font-size: 1.65rem;
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.025em;
}

.metric-help {
    font-size: 0.76rem;
    color: var(--muted-2);
    margin-top: 2px;
}

[data-testid="stMetric"] {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 15px !important;
    box-shadow: var(--shadow-sm);
}

/* ==========================================================================
   Step Tracker
   ========================================================================== */

.step-wrap {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 14px;
    box-shadow: var(--shadow-sm);
}

.step-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 13px;
    border-radius: 13px;
    margin-bottom: 8px;
    border: 1px solid transparent;
    transition: all .2s ease;
}

.step-row:last-child {
    margin-bottom: 0;
}

.step-icon {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    font-size: 1.25rem;
    background: #f3f4f6;
    flex: 0 0 auto;
}

.step-main {
    flex: 1;
    min-width: 0;
}

.step-name {
    font-weight: 750;
    font-size: 0.92rem;
    color: var(--text);
}

.step-desc {
    color: var(--muted);
    font-size: 0.76rem;
    margin-top: 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.step-time {
    font-size: 0.76rem;
    color: var(--muted);
    min-width: 48px;
    text-align: right;
}

.step-status {
    font-size: 0.72rem;
    padding: 5px 9px;
    border-radius: 999px;
    font-weight: 750;
    white-space: nowrap;
}

.step-row.pending {
    background: #ffffff;
    border-color: var(--border);
}

.step-row.pending .step-icon {
    background: #f3f4f6;
}

.step-status.pending {
    background: #f3f4f6;
    color: #6b7280;
}

.step-row.running {
    background: var(--blue-soft);
    border-color: rgba(37, 99, 235, 0.24);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.06);
}

.step-row.running .step-icon {
    background: #dbeafe;
}

.step-status.running {
    background: #dbeafe;
    color: var(--blue);
}

.step-row.done {
    background: var(--green-soft);
    border-color: rgba(22, 163, 74, 0.22);
}

.step-row.done .step-icon {
    background: #dcfce7;
}

.step-status.done {
    background: #dcfce7;
    color: var(--green);
}

.step-row.error {
    background: var(--red-soft);
    border-color: rgba(220, 38, 38, 0.22);
}

.step-row.error .step-icon {
    background: #fee2e2;
}

.step-status.error {
    background: #fee2e2;
    color: var(--red);
}

/* ==========================================================================
   Agent Card
   ========================================================================== */

.agent-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-left: 5px solid var(--blue);
    border-radius: 16px;
    padding: 16px 18px;
    box-shadow: var(--shadow-sm);
}

.agent-card.done {
    border-left-color: var(--green);
}

.agent-card.error {
    border-left-color: var(--red);
}

.agent-title {
    font-weight: 800;
    color: var(--text);
    font-size: 1rem;
    margin-bottom: 6px;
}

.agent-detail {
    color: var(--muted);
    font-size: 0.88rem;
    line-height: 1.55;
}

.query-chip {
    display: inline-block;
    background: #f3f4f6;
    border: 1px solid var(--border);
    color: #374151;
    border-radius: 999px;
    padding: 5px 9px;
    margin: 3px 4px 3px 0;
    font-size: 0.77rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

/* ==========================================================================
   Papers
   ========================================================================== */

.paper-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 17px;
    margin-bottom: 12px;
    box-shadow: var(--shadow-sm);
    transition: all .18s ease;
}

.paper-card:hover {
    border-color: rgba(37, 99, 235, 0.45);
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
    transform: translateY(-1px);
}

.paper-card {
    display: grid;
    grid-template-columns: 48px 1fr;
    gap: 12px;
    align-items: start;
}

.paper-index {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: var(--blue-soft);
    color: var(--blue);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 0.95rem;
}

.paper-title {
    color: var(--text);
    font-size: 1rem;
    font-weight: 780;
    line-height: 1.38;
    margin-bottom: 6px;
}

.paper-meta {
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.45;
}

.paper-abstract {
    color: #374151;
    font-size: 0.86rem;
    line-height: 1.55;
    margin-top: 9px;
}

.paper-links {
    margin-top: 11px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.paper-link {
    text-decoration: none !important;
    color: var(--blue) !important;
    border: 1px solid #bfdbfe;
    background: #eff6ff;
    padding: 5px 9px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
}

/* ==========================================================================
   Synthesis
   ========================================================================== */

.synthesis-section {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px;
    box-shadow: var(--shadow-sm);
    margin-bottom: 14px;
}

.synthesis-title {
    font-weight: 820;
    color: var(--text);
    font-size: 1.02rem;
    margin-bottom: 9px;
}

.synthesis-body {
    color: #374151;
    line-height: 1.65;
    font-size: 0.92rem;
}

/* ==========================================================================
   Logs (DÜZELTMELİ)
   ========================================================================== */

.live-log-panel {
    background: #0b1220;
    border: 1px solid #172033;
    border-radius: 16px;
    padding: 12px;
    max-height: 380px;
    overflow-y: auto;
    box-shadow: var(--shadow-sm);
}

/* HTML span/div yerine Streamlit container kullanacağız, bu yüzden stil basitleştirildi */
.log-entry {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.76rem;
    padding: 4px 0; /* Padding azaltıldı, div container ile halledilecek */
    display: flex;
    gap: 9px;
}

.log-time {
    color: #64748b;
    min-width: 58px;
}

.log-level {
    min-width: 62px;
    font-weight: 800;
}

.log-level-DEBUG { color: #94a3b8; }
.log-level-INFO { color: #93c5fd; }
.log-level-WARNING { color: #fbbf24; }
.log-level-ERROR { color: #fca5a5; }

.log-text {
    flex: 1;
    word-break: break-word;
    color: #d1d5db;
}

/* ==========================================================================
   Empty state
   ========================================================================== */

.empty-state {
    text-align: center;
    padding: 42px 20px 22px 20px;
}

.empty-icon {
    font-size: 3.2rem;
    margin-bottom: 14px;
}

.empty-title {
    color: var(--text);
    font-size: 1.28rem;
    font-weight: 800;
    margin-bottom: 8px;
}

.empty-desc {
    color: var(--muted);
    max-width: 720px;
    margin: 0 auto;
    line-height: 1.6;
}

.feature-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: var(--shadow-sm);
    min-height: 164px;
}

.feature-icon {
    font-size: 2rem;
    margin-bottom: 10px;
}

.feature-title {
    color: var(--text);
    font-weight: 800;
    margin-bottom: 5px;
}

.feature-desc {
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.45;
}

/* ==========================================================================
   Small utility
   ========================================================================== */

.small-muted {
    color: var(--muted);
    font-size: 0.83rem;
}

.section-heading {
    font-size: 1.1rem;
    font-weight: 820;
    color: var(--text);
    margin: 8px 0 12px 0;
}

.warning-box {
    background: var(--yellow-soft);
    border: 1px solid #fde68a;
    border-radius: 14px;
    padding: 13px 15px;
    color: #92400e;
    font-size: 0.88rem;
    line-height: 1.55;
}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# Helper Functions
# =============================================================================

def _e(value: Any) -> str:
    """HTML escape helper."""
    return html.escape(str(value if value is not None else ""), quote=True)


def _reset_for_new_run(query: str, filters: Dict[str, Any]):
    fresh = _fresh_defaults()
    for k, v in fresh.items():
        st.session_state[k] = v

    st.session_state["running"] = True
    st.session_state["done"] = False
    st.session_state["query"] = query.strip()
    st.session_state["filters"] = filters
    st.session_state["pipeline_start"] = time.time()

    for s in STEPS:
        st.session_state["step_logs"][s] = []
        st.session_state["step_status"][s] = "pending"


def _status_label(status: str) -> str:
    return {
        "pending": "Bekliyor",
        "running": "Çalışıyor",
        "done": "Tamamlandı",
        "error": "Hata",
    }.get(status, status)


def _render_step_tracker(step_status: dict, step_times: dict, current_step: str) -> str:
    parts = ['<div class="step-wrap">']

    for key, info in STEPS.items():
        status = step_status.get(key, "pending")

        if key == current_step and status not in ["done", "error"]:
            status = "running"

        elapsed = step_times.get(key, {})
        time_str = ""

        if elapsed.get("duration") is not None:
            time_str = f"{elapsed['duration']:.1f}s"
        elif elapsed.get("start") and status == "running":
            time_str = f"{time.time() - elapsed['start']:.0f}s..."

        parts.append(
            (
                f'<div class="step-row {status}">'
                f'<div class="step-icon">{info["icon"]}</div>'
                '<div class="step-main">'
                f'<div class="step-name">{_e(info["label"])}</div>'
                f'<div class="step-desc">{_e(info["desc"])}</div>'
                '</div>'
                f'<div class="step-time">{_e(time_str)}</div>'
                f'<div class="step-status {status}">{_status_label(status)}</div>'
                '</div>'
            )
        )

    parts.append("</div>")
    return "\n".join(parts)


def _render_agent_card(
    title: str,
    detail: str,
    icon: str = "⚙️",
    status: str = "",
    queries: List[str] | None = None,
) -> str:
    cls = f"agent-card {status}".strip()

    query_html = ""
    if queries:
        chips = "".join([f'<span class="query-chip">{_e(q)}</span>' for q in queries])
        query_html = f'<div style="margin-top:10px;">{chips}</div>'

    return f"""
    <div class="{cls}">
        <div class="agent-title">{icon} {_e(title)}</div>
        <div class="agent-detail">{detail}</div>
        {query_html}
    </div>
    """


def _render_paper_card(p: Dict[str, Any], idx: int | None = None) -> str:
    authors = p.get("authors", []) or []
    author_str = ", ".join(authors[:3])
    if len(authors) > 3:
        author_str += " et al."

    source = p.get("source", "arxiv")
    cats = ", ".join((p.get("categories", []) or [])[:3])
    venue = p.get("venue", "")
    meta_extra = venue if source == "scopus" else (cats or "")
    year = p.get("year", "?")
    abstract = p.get("abstract", "") or ""
    abstract_short = abstract[:430] + "..." if len(abstract) > 430 else abstract

    links = []
    if source == "arxiv":
        arxiv_url = p.get("arxiv_url", "")
        pdf_url = p.get("pdf_url", "")
        if arxiv_url:
            links.append(f'<a class="paper-link" href="{_e(arxiv_url)}" target="_blank">arXiv</a>')
        if pdf_url:
            links.append(f'<a class="paper-link" href="{_e(pdf_url)}" target="_blank">PDF</a>')
    elif source == "zotero":
        doi_url = p.get("doi_url", "")
        if doi_url:
            links.append(f'<a class="paper-link" href="{_e(doi_url)}" target="_blank">DOI</a>')
    elif source == "drive":
        doi_url = p.get("doi_url", "")
        fname = p.get("drive_filename", "")
        if doi_url:
            links.append(f'<a class="paper-link" href="{_e(doi_url)}" target="_blank">DOI</a>')
        if fname:
            links.append(f'<span class="paper-link" style="background:#f3e8ff;color:#6b21a8;border-color:#d8b4fe;">{_e(fname)}</span>')
    else:
        scopus_url = p.get("scopus_url", "")
        doi_url = p.get("doi_url", "")
        if scopus_url:
            links.append(f'<a class="paper-link" href="{_e(scopus_url)}" target="_blank">Scopus</a>')
        if doi_url:
            links.append(f'<a class="paper-link" href="{_e(doi_url)}" target="_blank">DOI</a>')

    if source == "scopus":
        source_badge = (
            '<span style="background:#fef9c3;color:#854d0e;border:1px solid #fde68a;'
            'border-radius:999px;padding:2px 8px;font-size:0.72rem;font-weight:700;margin-left:6px;">Scopus</span>'
        )
    elif source == "zotero":
        source_badge = (
            '<span style="background:#fdf2f8;color:#9d174d;border:1px solid #fbcfe8;'
            'border-radius:999px;padding:2px 8px;font-size:0.72rem;font-weight:700;margin-left:6px;">Zotero</span>'
        )
    elif source == "drive":
        source_badge = (
            '<span style="background:#f3e8ff;color:#6b21a8;border:1px solid #d8b4fe;'
            'border-radius:999px;padding:2px 8px;font-size:0.72rem;font-weight:700;margin-left:6px;">Drive</span>'
        )
    else:
        source_badge = (
            '<span style="background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;'
            'border-radius:999px;padding:2px 8px;font-size:0.72rem;font-weight:700;margin-left:6px;">arXiv</span>'
        )

    link_html = "".join(links)
    index_html = f"<div class=\"paper-index\">{idx}</div>" if idx is not None else ""

    return f"""
    <div class="paper-card">
        {index_html}
        <div>
            <div class="paper-title">{_e(p.get("title", ""))}{source_badge}</div>
            <div class="paper-meta">
                {_e(author_str or "Yazar bilgisi yok")} · {_e(year)} · {_e(meta_extra or "—")}
            </div>
            <div class="paper-abstract">{_e(abstract_short)}</div>
            <div class="paper-links">{link_html}</div>
        </div>
    </div>
    """


def _papers_to_df(papers: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for p in papers:
        source = p.get("source", "")
        url = p.get("arxiv_url", "") or p.get("scopus_url", "") or p.get("doi_url", "")
        rows.append(
            {
                "title": p.get("title", ""),
                "year": p.get("year", ""),
                "authors": ", ".join((p.get("authors", []) or [])[:5]),
                "source": source,
                "venue/category": p.get("venue", "") or ", ".join(p.get("categories", []) or []),
                "url": url,
                "pdf_url": p.get("pdf_url", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_report_markdown() -> str:
    query = st.session_state.get("query", "")
    plan = st.session_state.get("research_plan", "")
    queries = st.session_state.get("search_queries", [])
    papers = st.session_state.get("papers", [])
    synthesis = st.session_state.get("synthesis", {})
    total_time = st.session_state.get("total_time", 0)

    md = []
    md.append(f"# Otonom Araştırma Raporu\n")
    md.append(f"**Araştırma Sorusu:** {query}\n")
    md.append(f"**Oluşturulma Tarihi:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    md.append(f"**Toplam Süre:** {total_time:.1f}s\n")

    if plan:
        md.append("\n## Araştırma Planı\n")
        md.append(str(plan))

    if queries:
        md.append("\n## Arama Sorguları\n")
        for q in queries:
            md.append(f"- `{q}`")

    if synthesis:
        md.append("\n## Sentez\n")
        if synthesis.get("summary"):
            md.append("\n### Genel Değerlendirme\n")
            md.append(str(synthesis.get("summary", "")))

        gap = synthesis.get("gap_analysis", {})
        if gap:
            md.append("\n### Gap Analizi\n")
            for title, key in [
                ("Çözülmüş Problemler", "solved_problems"),
                ("Açık Problemler", "open_problems"),
                ("Araştırma Boşlukları", "research_gaps"),
            ]:
                if gap.get(key):
                    md.append(f"\n#### {title}\n")
                    for item in gap[key]:
                        md.append(f"- {item}")

        trend = synthesis.get("trend_analysis", {})
        if trend:
            md.append("\n### Trend Analizi\n")
            if trend.get("emerging_methods"):
                md.append("\n#### Yükselen Yöntemler\n")
                for item in trend["emerging_methods"]:
                    md.append(f"- {item}")
            if trend.get("hot_topics"):
                md.append("\n#### Güncel Konular\n")
                for item in trend["hot_topics"]:
                    md.append(f"- {item}")
            if trend.get("temporal_shift"):
                md.append("\n#### Zamansal Değişim\n")
                md.append(str(trend["temporal_shift"]))

    if papers:
        md.append("\n## Bulunan Makaleler\n")
        for i, p in enumerate(papers, 1):
            title = p.get("title", "")
            year = p.get("year", "?")
            url = p.get("arxiv_url") or p.get("scopus_url") or p.get("doi_url") or p.get("pdf_url") or ""
            md.append(f"{i}. **{title}** ({year})  ")
            if url:
                md.append(f"   {url}")

    return "\n".join(md)


def _render_synthesis_section(title: str, body: str, icon: str = "🔬"):
    st.markdown(
        f"""
        <div class="synthesis-section">
            <div class="synthesis-title">{icon} {_e(title)}</div>
            <div class="synthesis-body">{_e(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_cited_item(text: str) -> str:
    """[N] ve [N, M] gibi atıfları renkli badge olarak HTML'e çevirir."""
    def _badge(m):
        nums = m.group(0)
        return f'<span style="display:inline-block;background:#dbeafe;color:#1d4ed8;border-radius:4px;padding:0 5px;font-size:0.78em;font-weight:600;margin:0 1px;">{nums}</span>'
    return re.sub(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', _badge, _e(text))


def _render_metric_card(label: str, value: Any, help_text: str = ""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{_e(label)}</div>
            <div class="metric-value">{_e(value)}</div>
            <div class="metric-help">{_e(help_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# API Anahtarları — İlk açılış popup'ı + sonradan erişim
# =============================================================================

from src.config import api_keys as _api_keys


@st.dialog("🔑 API Anahtarları", width="large")
def _api_keys_dialog():
    st.markdown(
        "Anahtarlar projenin kök dizinindeki **`.env`** dosyasına kaydedilir. "
        "Sadece **Gemini** zorunludur; Zotero ve Scopus yalnızca o kaynakları "
        "kullanacaksan gerekir."
    )
    st.caption(
        "Güvenlik: kayıtlı anahtarlar burada tam gösterilmez, yalnızca son 4 hanesi "
        "maskeli görünür. Yeni değer girersen eskisinin üzerine yazılır."
    )
    st.divider()

    pending_updates: Dict[str, str] = {}
    pending_deletes: List[str] = []

    for spec in _api_keys.API_KEYS:
        env = spec["env"]
        configured = _api_keys.is_configured(env)
        label = spec["label"] + ("  *(zorunlu)*" if spec.get("required") else "")

        st.markdown(f"**{label}**")

        if configured:
            st.markdown(
                f'<span style="color:#16a34a;font-size:0.8rem;">✓ Kayıtlı: '
                f'<code>{_e(_api_keys.mask_value(_api_keys.get_value(env)))}</code></span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span style="color:#9ca3af;font-size:0.8rem;">○ Henüz tanımlı değil</span>',
                unsafe_allow_html=True,
            )

        new_val = st.text_input(
            spec["label"],
            type="password",
            value="",
            key=f"setkey_{env}",
            placeholder=("Yeni anahtar gir (değiştirmek için)" if configured else spec["placeholder"]),
            label_visibility="collapsed",
        )
        if new_val.strip():
            pending_updates[env] = new_val.strip()

        btn_cols = st.columns([1, 1])
        with btn_cols[0]:
            with st.popover("❓ Nasıl bulurum?", use_container_width=True):
                st.markdown(spec["help"])
                st.markdown(f"🔗 [Anahtar sayfasını aç]({spec['help_url']})")
        with btn_cols[1]:
            if configured:
                if st.checkbox("🗑️ Bu anahtarı sil", key=f"delkey_{env}"):
                    pending_deletes.append(env)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    st.divider()

    # Yeni değer girilen anahtarda silme işaretliyse güncelleme önceliklidir
    pending_deletes = [e for e in pending_deletes if e not in pending_updates]

    action_cols = st.columns([1, 1])
    with action_cols[0]:
        if st.button("💾 Kaydet", type="primary", use_container_width=True):
            if not pending_updates and not pending_deletes:
                st.warning("Değişiklik yok. Yeni bir anahtar gir veya silme işaretle.")
            else:
                try:
                    path = _api_keys.save_keys(pending_updates, pending_deletes)
                    # Girilen değerleri session'dan temizle
                    for spec in _api_keys.API_KEYS:
                        st.session_state.pop(f"setkey_{spec['env']}", None)
                        st.session_state.pop(f"delkey_{spec['env']}", None)
                    st.session_state["show_settings"] = False
                    st.session_state["settings_dismissed"] = True
                    st.session_state["_settings_saved_to"] = str(path)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Kaydedilemedi: {ex}")
    with action_cols[1]:
        if st.button("Kapat", use_container_width=True):
            st.session_state["show_settings"] = False
            st.session_state["settings_dismissed"] = True
            st.rerun()


# İlk açılışta zorunlu anahtar yoksa popup otomatik açılır.
if _api_keys.needs_setup() and not st.session_state.get("settings_dismissed"):
    st.session_state["show_settings"] = True

if st.session_state.pop("_settings_saved_to", None):
    st.toast("API anahtarları .env dosyasına kaydedildi.", icon="✅")

if st.session_state.get("show_settings"):
    _api_keys_dialog()


# =============================================================================
# Sidebar
# =============================================================================

with st.sidebar:
    # -------- Brand --------
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:10px;margin:2px 0 4px 0;">
            <div style="font-size:1.65rem;">🔬</div>
            <div>
                <div style="font-weight:800;font-size:1.05rem;line-height:1.15;color:#111827;">Research Assistant</div>
                <div style="font-size:0.74rem;color:#6b7280;">Multi-agent · RAG · Grounded</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ===========================================================
    # 0) API ANAHTARLARI
    # ===========================================================
    _missing_required = [e for e in _api_keys.REQUIRED_KEYS if not _api_keys.is_configured(e)]
    if st.button(
        "🔑 API Anahtarları",
        use_container_width=True,
        type="primary" if _missing_required else "secondary",
        help="Gemini / Zotero / Scopus anahtarlarını gir veya güncelle.",
    ):
        st.session_state["show_settings"] = True
        st.rerun()
    if _missing_required:
        st.caption("⚠️ Gemini API anahtarı eksik — eklemeden araştırma çalışmaz.")

    st.divider()

    # ===========================================================
    # 1) MODE — Web vs Library (mutually exclusive üst seçim)
    # ===========================================================
    st.markdown(
        '<div style="font-weight:700;font-size:0.85rem;color:#374151;margin:2px 0 6px;letter-spacing:0.02em;text-transform:uppercase;">1 · Kaynak Modu</div>',
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "Mod",
        options=["web", "library"],
        format_func=lambda v: "🌐 Web Arama (arXiv / Scopus)" if v == "web" else "📂 Kütüphane (Zotero / Drive)",
        index=0,
        label_visibility="collapsed",
        key="source_mode",
        horizontal=False,
    )

    library_mode = (mode == "library")

    # ---- Web sub-options ----
    if not library_mode:
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:0.78rem;color:#6b7280;margin-bottom:6px;">Açık akademik kaynaklarda planner sorgularıyla tarama</div>',
                unsafe_allow_html=True,
            )
            use_arxiv = st.checkbox("arXiv", value=st.session_state.get("src_arxiv", True), key="src_arxiv")
            use_scopus = st.checkbox("Scopus", value=st.session_state.get("src_scopus", False), key="src_scopus")
            if use_scopus and not os.getenv("SCOPUS_API_KEY", ""):
                st.warning("`.env`'e `SCOPUS_API_KEY` ekle.", icon="⚠️")
        use_zotero = False
        use_drive = False
        zotero_collection_key = ""
        zotero_collection_name = ""
        drive_folder_url = ""
    else:
        use_arxiv = False
        use_scopus = False
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:0.78rem;color:#6b7280;margin-bottom:6px;">Kendi koleksiyonun · Zotero ve Drive birlikte seçilebilir (otomatik dedup)</div>',
                unsafe_allow_html=True,
            )
            use_zotero = st.checkbox("Zotero", value=st.session_state.get("src_zotero", False), key="src_zotero")
            use_drive = st.checkbox("Google Drive", value=st.session_state.get("src_drive", False), key="src_drive")

        # --- Zotero detayları ---
        zotero_collection_key = ""
        zotero_collection_name = ""
        if use_zotero:
            with st.container(border=True):
                st.markdown(
                    '<div style="font-weight:650;font-size:0.82rem;color:#9d174d;margin-bottom:4px;">Zotero Collection</div>',
                    unsafe_allow_html=True,
                )
                if not os.getenv("ZOTERO_API_KEY", "") or not os.getenv("ZOTERO_USER_ID", ""):
                    st.warning(
                        "`.env`'e `ZOTERO_API_KEY` ve `ZOTERO_USER_ID` ekle. "
                        "[Anahtar al](https://www.zotero.org/settings/keys)",
                        icon="⚠️",
                    )
                else:
                    @st.cache_data(ttl=300, show_spinner="Collection'lar yükleniyor…")
                    def _load_zotero_collections():
                        from src.tools.zotero_tool import list_collections
                        return list_collections()

                    try:
                        cols = _load_zotero_collections()
                    except Exception as ex:
                        st.error(f"Zotero hatası: {ex}")
                        cols = []

                    if cols:
                        labels = [f"{c['name']}  ·  {c['num_items']} item" for c in cols]
                        keys = [c["key"] for c in cols]
                        names = [c["name"] for c in cols]
                        pick = st.selectbox(
                            "Collection",
                            options=list(range(len(labels))),
                            format_func=lambda i: labels[i],
                            key="zotero_col_idx",
                            label_visibility="collapsed",
                        )
                        zotero_collection_key = keys[pick]
                        zotero_collection_name = names[pick]
                    else:
                        st.info("Collection bulunamadı.")

        # --- Drive detayları ---
        drive_folder_url = ""
        if use_drive:
            with st.container(border=True):
                st.markdown(
                    '<div style="font-weight:650;font-size:0.82rem;color:#6b21a8;margin-bottom:4px;">Drive Klasör Linki</div>',
                    unsafe_allow_html=True,
                )
                drive_folder_url = st.text_input(
                    "Drive linki",
                    value=st.session_state.get("drive_folder_url_input", ""),
                    key="drive_folder_url_input",
                    placeholder="https://drive.google.com/drive/folders/…",
                    label_visibility="collapsed",
                    help="Klasör 'Bağlantıya sahip herkes' olarak paylaşılmalı.",
                )
                if drive_folder_url:
                    from src.tools.gdrive_tool import extract_folder_id
                    fid = extract_folder_id(drive_folder_url)
                    if not fid:
                        st.error("Geçerli bir Drive klasör linki değil.", icon="⚠️")
                        drive_folder_url = ""
                    else:
                        st.markdown(
                            f'<div style="font-size:0.72rem;color:#6b7280;margin-top:4px;">✓ Klasör ID: <code>{_e(fid[:18])}…</code></div>',
                            unsafe_allow_html=True,
                        )

    # --- Genel kaynak validasyonu ---
    any_source_selected = (
        use_arxiv or use_scopus
        or (use_zotero and zotero_collection_key)
        or (use_drive and drive_folder_url)
    )
    any_checkbox_on = use_arxiv or use_scopus or use_zotero or use_drive

    if not any_checkbox_on:
        st.error("En az bir kaynak seçilmelidir.", icon="❌")
    elif use_zotero and not zotero_collection_key and not use_drive:
        st.warning("Zotero için bir collection seç.", icon="⚠️")
    elif use_drive and not drive_folder_url and not use_zotero:
        st.warning("Drive klasör linki gir.", icon="⚠️")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ===========================================================
    # 2) FILTERS — Yıl / Sayı / Sıralama
    # ===========================================================
    st.markdown(
        '<div style="font-weight:700;font-size:0.85rem;color:#374151;margin:4px 0 6px;letter-spacing:0.02em;text-transform:uppercase;">2 · Filtreler</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        max_results = st.slider(
            "Maks. makale sayısı",
            min_value=5,
            max_value=100,
            value=st.session_state.get("filter_max_results", 25),
            step=5,
            key="filter_max_results",
            help="Çoklu kaynak seçildiyse kaynak başına eşit bölünür.",
        )

        year_from, year_to = st.slider(
            "Yıl aralığı",
            min_value=1990,
            max_value=datetime.now().year,
            value=st.session_state.get("filter_year_range", (2020, datetime.now().year)),
            key="filter_year_range",
        )

        sort_mode = st.selectbox(
            "Sıralama",
            ["Yeni → Eski", "Eski → Yeni", "Varsayılan"],
            index=0,
            key="filter_sort_mode",
        )

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ===========================================================
    # 3) GÖRÜNÜM (kompakt)
    # ===========================================================
    with st.expander("🎛️ Görünüm Ayarları", expanded=False):
        show_abstracts = st.toggle("Makale kartlarında özet göster", value=True, key="ui_show_abs")

    
    # ===========================================================
    # 5) STACK (en kompakt)
    # ===========================================================
    active_sources_badges = []
    if use_arxiv: active_sources_badges.append("arXiv")
    if use_scopus: active_sources_badges.append("Scopus")
    if use_zotero: active_sources_badges.append("Zotero")
    if use_drive: active_sources_badges.append("Drive")
    badge_html = "".join(
        f'<span style="display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;'
        f'border-radius:999px;padding:2px 8px;font-size:0.7rem;font-weight:700;margin:2px 3px 2px 0;">{s}</span>'
        for s in active_sources_badges
    ) or '<span style="color:#9ca3af;font-size:0.78rem;">Henüz kaynak seçilmedi</span>'

    st.markdown(
        f"""
        <div style="margin-top:14px;padding:10px 12px;background:#f9fafb;border:1px solid #e5e7eb;
                    border-radius:12px;">
            <div style="font-size:0.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;
                        font-weight:700;margin-bottom:6px;">Aktif kaynaklar</div>
            <div>{badge_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ===========================================================
    # 6) TEMİZLE
    # ===========================================================
    if st.button("🧹 Oturumu Temizle", use_container_width=True):
        fresh = _fresh_defaults()
        for k, v in fresh.items():
            st.session_state[k] = v
        st.rerun()

    st.markdown(
        '<div style="text-align:center;font-size:0.7rem;color:#9ca3af;margin-top:18px;">'
        'LangGraph · Gemini · Qdrant · MiniLM</div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# Header / Hero
# =============================================================================

status_text = "Çalışıyor" if st.session_state.get("running") else "Hazır"
dot_color = "#2563eb" if st.session_state.get("running") else "#16a34a"

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-top">
            <div>
                <div class="hero-title">🔬 {APP_NAME}</div>
                <div class="hero-subtitle">
                    {APP_SUBTITLE}. Araştırma sorusunu gir, sistem otomatik olarak
                    araştırma planı oluştursun, akademik literatürü tarasın (arXiv / Scopus),
                    vektör veritabanına kaydetsin ve sentez raporu üretsin.
                </div>
                <div class="hero-badges">
                    <span class="badge">🧠 Planner Agent</span>
                    <span class="badge">📚 Literature Agent</span>
                    <span class="badge">🗄️ Qdrant RAG</span>
                    <span class="badge">🔬 Synthesis Agent</span>
                    <span class="badge">⚡ Streamlit UI</span>
                </div>
            </div>
            <div class="status-pill">
                <span class="status-dot" style="background:{dot_color};"></span>
                Sistem: {status_text}
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Search Form
# =============================================================================

st.markdown('<div class="search-panel">', unsafe_allow_html=True)
st.markdown('<div class="panel-title">Yeni araştırma başlat</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="panel-desc">Araştırma konusunu mümkün olduğunca açık yaz. Örn: yöntem, alan, problem ve uygulama bağlamı.</div>',
    unsafe_allow_html=True,
)

with st.form("search_form", clear_on_submit=False):
    query_default = st.session_state.get("query", "")

    query = st.text_area(
        "Araştırma sorusu",
        value=query_default,
        placeholder="Örn: retrieval augmented generation evaluation methods for reducing hallucination in LLM agents",
        height=95,
        label_visibility="collapsed",
    )

    form_cols = st.columns([1.3, 1, 1, 1])
    with form_cols[0]:
        submitted = st.form_submit_button(
            "🔍 Araştırmayı Başlat",
            use_container_width=True,
            type="primary",
            disabled=st.session_state.get("running", False),
        )
    with form_cols[1]:
        st.caption(f"Maks. makale: {max_results}")
    with form_cols[2]:
        st.caption(f"Yıl: {year_from}-{year_to}")
    with form_cols[3]:
        st.caption(f"Sıralama: {sort_mode}")

st.markdown("</div>", unsafe_allow_html=True)

if submitted:
    if not query.strip():
        st.warning("Lütfen bir araştırma sorusu girin.")
    else:
        selected_sources = []
        if use_arxiv:
            selected_sources.append("arxiv")
        if use_scopus:
            selected_sources.append("scopus")
        if use_zotero and zotero_collection_key:
            selected_sources.append("zotero")
        if use_drive and drive_folder_url:
            selected_sources.append("drive")
        if not selected_sources:
            selected_sources = ["arxiv"]

        filters = {
            "max_results": max_results,
            "year_from": year_from,
            "year_to": year_to,
            "sort_mode": sort_mode,
            "sources": selected_sources,
            "zotero_collection_key": zotero_collection_key,
            "zotero_collection_name": zotero_collection_name,
            "drive_folder_url": drive_folder_url,
        }
        _reset_for_new_run(query=query, filters=filters)
        st.rerun()


# =============================================================================
# Running Pipeline
# =============================================================================

if st.session_state.get("running") and not st.session_state.get("done"):
    query_val = st.session_state.get("query", "")
    filters = st.session_state.get("filters", {})

    progress_placeholder = st.empty()
    tracker_col, detail_col = st.columns([1.05, 1.55], gap="large")

    with tracker_col:
        st.markdown('<div class="section-heading">📊 Pipeline Durumu</div>', unsafe_allow_html=True)
        tracker_placeholder = st.empty()
        tracker_placeholder.markdown(
            _render_step_tracker(
                st.session_state["step_status"],
                st.session_state["step_times"],
                st.session_state.get("current_step", ""),
            ),
            unsafe_allow_html=True,
        )

        st.markdown('<div class="section-heading">📋 Canlı Loglar</div>', unsafe_allow_html=True)
        log_placeholder = st.empty()

    with detail_col:
        st.markdown('<div class="section-heading">🔄 Ajan Detayları</div>', unsafe_allow_html=True)
        detail_placeholder = st.empty()
        detail_placeholder.markdown(
            _render_agent_card(
                title="Pipeline başlatılıyor",
                detail=f"Sorgu: <b>{_e(query_val)}</b>",
                icon="🚀",
            ),
            unsafe_allow_html=True,
        )

    _install_log_sink()

    try:
        from src.graph.research_graph import build_graph

        graph = build_graph()

        initial_state = {
            "query": query_val,
            "filters": filters,
            "max_results": filters.get("max_results", max_results),
            "year_from": filters.get("year_from", year_from),
            "year_to": filters.get("year_to", year_to),
            "sources": filters.get("sources", ["arxiv"]),
            "zotero_collection_key": filters.get("zotero_collection_key", ""),
            "zotero_collection_name": filters.get("zotero_collection_name", ""),
            "drive_folder_url": filters.get("drive_folder_url", ""),
            "research_plan": "",
            "search_queries": [],
            "papers": [],
            "embedded_count": 0,
            "pdf_enriched_count": 0,
            "chunk_count": 0,
            "synthesis": {},
            "messages": [],
            "current_step": "",
            "error": None,
        }

        completed_count = 0
        total_steps = len(STEPS)

        progress_placeholder.progress(0, text="Pipeline başlatılıyor...")

        # Her node'un gerçek çalışma süresi: event önceki event'in bittiği andan itibaren ölçülür.
        # LangGraph stream_mode="updates" event'i node tamamlandıktan sonra gönderir,
        # bu yüzden step_start = son event'in tamamlandığı an = bu node'un başlangıcıdır.
        last_event_time = st.session_state.get("pipeline_start") or time.time()

        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                step_start = last_event_time  # Bu node'un gerçek başlangıcı

                st.session_state["current_step"] = node_name
                st.session_state["_active_step"] = node_name
                st.session_state["step_status"][node_name] = "running"
                st.session_state["step_times"][node_name] = {"start": step_start}

                step_info = STEPS.get(
                    node_name,
                    {
                        "icon": "⚙️",
                        "label": node_name,
                        "desc": "",
                    },
                )

                progress_placeholder.progress(
                    min(completed_count / total_steps, 0.95),
                    text=f"{step_info['label']} çalışıyor...",
                )

                tracker_placeholder.markdown(
                    _render_step_tracker(
                        st.session_state["step_status"],
                        st.session_state["step_times"],
                        node_name,
                    ),
                    unsafe_allow_html=True,
                )

                detail_placeholder.markdown(
                    _render_agent_card(
                        title=f"{step_info['label']} çalışıyor",
                        detail=_e(step_info["desc"]),
                        icon=step_info["icon"],
                    ),
                    unsafe_allow_html=True,
                )

                # Update state from node output
                msgs = node_output.get("messages", []) or []
                for m in msgs:
                    st.session_state["messages"].append(str(m))

                if node_name == "planner":
                    st.session_state["research_plan"] = node_output.get("research_plan", "")
                    st.session_state["search_queries"] = node_output.get("search_queries", [])

                    plan = st.session_state["research_plan"]
                    queries = st.session_state["search_queries"]

                    detail_placeholder.markdown(
                        _render_agent_card(
                            title="Planlama tamamlandı",
                            detail=f"<b>Strateji:</b> {_e(plan)}",
                            icon="🧠",
                            status="done",
                            queries=queries,
                        ),
                        unsafe_allow_html=True,
                    )

                elif node_name == "literature":
                    st.session_state["papers"] = node_output.get("papers", [])
                    paper_count = len(st.session_state["papers"])

                    detail_placeholder.markdown(
                        _render_agent_card(
                            title="Literatür taraması tamamlandı",
                            detail=f"<b>{paper_count}</b> benzersiz makale bulundu.",
                            icon="📚",
                            status="done",
                        ),
                        unsafe_allow_html=True,
                    )

                elif node_name == "embed":
                    st.session_state["embedded_count"] = node_output.get("embedded_count", 0)
                    embed_count = st.session_state["embedded_count"]

                    detail_placeholder.markdown(
                        _render_agent_card(
                            title="Embedding tamamlandı",
                            detail=f"<b>{embed_count}</b> makale vektör veritabanına kaydedildi.",
                            icon="🗄️",
                            status="done",
                        ),
                        unsafe_allow_html=True,
                    )

                elif node_name == "pdf_fetcher":
                    enriched = node_output.get("pdf_enriched_count", 0)
                    chunks_n = node_output.get("chunk_count", 0)
                    st.session_state["pdf_enriched_count"] = enriched
                    st.session_state["chunk_count"] = chunks_n

                    detail_placeholder.markdown(
                        _render_agent_card(
                            title="PDF & Chunk zenginleştirme tamamlandı",
                            detail=f"<b>{enriched}</b> makale tam PDF, <b>{chunks_n}</b> chunk indekslendi.",
                            icon="📄",
                            status="done",
                        ),
                        unsafe_allow_html=True,
                    )

                elif node_name == "synthesis":
                    st.session_state["synthesis"] = node_output.get("synthesis", {})
                    synth = st.session_state["synthesis"]

                    if synth.get("error"):
                        detail_placeholder.markdown(
                            _render_agent_card(
                                title="Sentez hatası",
                                detail=_e(synth.get("error")),
                                icon="🔬",
                                status="error",
                            ),
                            unsafe_allow_html=True,
                        )
                    else:
                        summary_preview = synth.get("summary", "") or ""
                        summary_preview = summary_preview[:260] + "..." if len(summary_preview) > 260 else summary_preview

                        detail_placeholder.markdown(
                            _render_agent_card(
                                title="Sentez tamamlandı",
                                detail=_e(summary_preview or "Sentez sonucu üretildi."),
                                icon="🔬",
                                status="done",
                            ),
                            unsafe_allow_html=True,
                        )

                now = time.time()
                duration = now - step_start
                last_event_time = now  # Sonraki node'un başlangıç zamanı

                st.session_state["step_status"][node_name] = "done"
                st.session_state["step_times"][node_name] = {
                    "start": step_start,
                    "duration": duration,
                }

                st.session_state["current_step"] = ""
                st.session_state["_active_step"] = ""

                completed_count += 1

                tracker_placeholder.markdown(
                    _render_step_tracker(
                        st.session_state["step_status"],
                        st.session_state["step_times"],
                        "",
                    ),
                    unsafe_allow_html=True,
                )

                # DÜZELTMELİ: Logları HTML yerine Streamlit container içinde render et
                with log_placeholder.container():
                    logs = st.session_state.get("live_logs", [])
                    # Son 50 logu al
                    for entry in logs[-50:]:
                        level = entry.get("level", "INFO")
                        color_class = f"log-level-{level}"
                        
                        # Renk ve stil inline olarak veriliyor
                        st.markdown(
                            f"""
                            <div class="log-entry">
                                <span class="log-time">{_e(entry.get("time", ""))}</span>
                                <span class="log-level {color_class}">{level}</span>
                                <span class="log-text">{_e(entry.get("text", ""))}</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

        total_time = time.time() - (st.session_state.get("pipeline_start") or time.time())

        progress_placeholder.progress(1.0, text="Pipeline tamamlandı.")

        st.session_state["running"] = False
        st.session_state["done"] = True
        st.session_state["total_time"] = total_time

    except Exception as e:
        logger.exception(f"Pipeline hatası: {e}")

        st.session_state["error"] = str(e)
        st.session_state["running"] = False
        st.session_state["done"] = True

        current = st.session_state.get("current_step")
        if current:
            st.session_state["step_status"][current] = "error"

    finally:
        _remove_log_sink()

    st.rerun()


# =============================================================================
# Results
# =============================================================================

if st.session_state.get("done"):
    if st.session_state.get("error"):
        st.error(f"Pipeline Hatası: {st.session_state['error']}")

        with st.expander("📋 Pipeline Logları", expanded=True):
            # Hata durumunda da logları düzgün göster
            logs = st.session_state.get("live_logs", [])
            for entry in logs:
                level = entry.get("level", "INFO")
                color_class = f"log-level-{level}"
                st.markdown(
                    f"""
                    <div class="log-entry">
                        <span class="log-time">{_e(entry.get("time", ""))}</span>
                        <span class="log-level {color_class}">{level}</span>
                        <span class="log-text">{_e(entry.get("text", ""))}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    else:
        papers = st.session_state.get("papers", [])
        synthesis = st.session_state.get("synthesis", {})
        plan = st.session_state.get("research_plan", "")
        queries = st.session_state.get("search_queries", [])
        embedded = st.session_state.get("embedded_count", 0)
        pdf_enriched = st.session_state.get("pdf_enriched_count", 0)
        chunk_count = st.session_state.get("chunk_count", 0)
        total_time = st.session_state.get("total_time", 0)

        arxiv_count = sum(1 for p in papers if p.get("source") == "arxiv")
        scopus_count = sum(1 for p in papers if p.get("source") == "scopus")
        zotero_count = sum(1 for p in papers if p.get("source") == "zotero")
        drive_count = sum(1 for p in papers if p.get("source") == "drive")
        source_detail = " · ".join(filter(None, [
            f"arXiv: {arxiv_count}" if arxiv_count else "",
            f"Scopus: {scopus_count}" if scopus_count else "",
            f"Zotero: {zotero_count}" if zotero_count else "",
            f"Drive: {drive_count}" if drive_count else "",
        ]))
        st.success(
            f"Pipeline başarıyla tamamlandı. {len(papers)} makale bulundu "
            f"({source_detail}), {embedded} kayıt vektör veritabanına eklendi, "
            f"{pdf_enriched} makale PDF ile zenginleştirildi."
        )

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            _render_metric_card("Bulunan Makale", len(papers), "literatür tarama sonucu")
        with m2:
            _render_metric_card("Vektör DB Kaydı", embedded, "Paper-level")
        with m3:
            _render_metric_card("PDF Zenginleştirme", pdf_enriched, "Tam metin eklenen")
        with m4:
            _render_metric_card("Chunk Sayısı", chunk_count, "Chunk-level RAG")
        with m5:
            _render_metric_card("Arama Sorgusu", len(queries), "Planner çıktısı")
        with m6:
            _render_metric_card("Toplam Süre", f"{total_time:.1f}s", "Pipeline çalışma süresi")

        st.divider()

        tab_report, tab_papers, tab_plan, tab_logs, tab_export = st.tabs(
            [
                "🔬 Sentez Raporu",
                "📄 Makaleler",
                "📋 Plan",
                "🧾 Loglar",
                "⬇️ Export",
            ]
        )

        # ---------------------------------------------------------------------
        # Synthesis Report
        # ---------------------------------------------------------------------
        with tab_report:
            if not synthesis or synthesis.get("error"):
                st.warning(synthesis.get("error", "Sentez sonucu bulunamadı."))
            else:
                if synthesis.get("summary"):
                    _render_synthesis_section(
                        "Genel Değerlendirme",
                        synthesis.get("summary", ""),
                        icon="🧭",
                    )

                gap = synthesis.get("gap_analysis", {})
                if gap:
                    g1, g2 = st.columns(2, gap="large")

                    with g1:
                        st.markdown("#### ✅ Çözülmüş Problemler")
                        solved = gap.get("solved_problems", [])
                        if solved:
                            for item in solved:
                                st.markdown(
                                    f"<div style='margin:2px 0'>▸ {_render_cited_item(item)}</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("Veri yok.")

                        st.markdown("#### ⚠️ Açık Problemler")
                        open_problems = gap.get("open_problems", [])
                        if open_problems:
                            for item in open_problems:
                                st.markdown(
                                    f"<div style='margin:2px 0'>▸ {_render_cited_item(item)}</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("Veri yok.")

                    with g2:
                        st.markdown("#### 🔴 Araştırma Boşlukları")
                        research_gaps = gap.get("research_gaps", [])
                        if research_gaps:
                            for item in research_gaps:
                                st.markdown(
                                    f"<div style='margin:2px 0'>▸ {_render_cited_item(item)}</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("Veri yok.")

                trend = synthesis.get("trend_analysis", {})
                if trend:
                    st.markdown("### 📈 Trend Analizi")

                    t1, t2 = st.columns(2, gap="large")

                    with t1:
                        st.markdown("#### Yükselen Yöntemler")
                        methods = trend.get("emerging_methods", [])
                        if methods:
                            for m in methods:
                                st.markdown(
                                    f"<div style='margin:2px 0'>▸ {_render_cited_item(m)}</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("Veri yok.")

                    with t2:
                        st.markdown("#### Güncel Konular")
                        topics = trend.get("hot_topics", [])
                        if topics:
                            for t in topics:
                                st.markdown(
                                    f"<div style='margin:2px 0'>▸ {_render_cited_item(t)}</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("Veri yok.")

                    if trend.get("temporal_shift"):
                        st.markdown("#### ⏳ Son 2-3 Yıldaki Değişim")
                        st.markdown(
                            f"<div style='padding:8px 12px;background:#f9fafb;border-left:3px solid #6366f1;border-radius:4px;'>"
                            f"{_render_cited_item(trend.get('temporal_shift', ''))}</div>",
                            unsafe_allow_html=True,
                        )

                method_landscape = synthesis.get("methodological_landscape", {})
                if method_landscape:
                    st.markdown("### 🧪 Metodolojik Manzara")
                    dominant = method_landscape.get("dominant_methods", [])
                    if dominant:
                        st.markdown("#### Baskın Yöntemler")
                        for m in dominant:
                            st.markdown(
                                f"<div style='margin:2px 0'>▸ {_render_cited_item(m)}</div>",
                                unsafe_allow_html=True,
                            )
                    clusters = method_landscape.get("method_clusters", [])
                    if clusters:
                        st.markdown("#### Yöntem Kümeleri")
                        for c in clusters:
                            ppl = c.get("papers", []) or []
                            ppl_str = ", ".join(f"[{x}]" for x in ppl)
                            st.markdown(
                                f"<div style='margin:3px 0;padding:6px 10px;background:#f9fafb;"
                                f"border-left:3px solid #7c3aed;border-radius:4px;'>"
                                f"<b>{_e(c.get('name','—'))}</b> {ppl_str} — {_e(c.get('description',''))}</div>",
                                unsafe_allow_html=True,
                            )

                thesis_recs = synthesis.get("thesis_recommendations", [])
                if thesis_recs:
                    st.markdown("### 🎓 Tez Çalışması Önerileri")
                    for r in thesis_recs:
                        st.markdown(
                            f"<div style='margin:4px 0;padding:8px 12px;background:#ecfdf5;"
                            f"border-left:3px solid #16a34a;border-radius:4px;'>{_render_cited_item(r)}</div>",
                            unsafe_allow_html=True,
                        )

                declining = (synthesis.get("trend_analysis") or {}).get("declining_approaches", [])
                if declining:
                    st.markdown("#### 📉 Azalan / Eleştirilen Yaklaşımlar")
                    for d in declining:
                        st.markdown(
                            f"<div style='margin:2px 0'>▸ {_render_cited_item(d)}</div>",
                            unsafe_allow_html=True,
                        )

                extractions = synthesis.get("extractions", [])
                if extractions:
                    with st.expander(f"🔍 Per-paper Extractions ({len(extractions)} makale)"):
                        for ext in extractions:
                            idx = ext.get("doc_index", "?")
                            st.markdown(
                                f"**[{idx}] {_e(ext.get('core_contribution',''))}**"
                            )
                            rel = ext.get("relevance_to_query", "")
                            if rel:
                                st.caption(f"İlgi: {rel}")
                            for key, label in [
                                ("key_findings", "Bulgular"),
                                ("methods", "Yöntemler"),
                                ("datasets", "Veri/test"),
                                ("limitations", "Sınırlamalar"),
                                ("open_questions", "Açık sorular"),
                            ]:
                                items = ext.get(key) or []
                                if items:
                                    st.markdown(
                                        f"- *{label}:* " + "; ".join(str(x) for x in items)
                                    )
                            st.markdown("---")

                researchers = synthesis.get("active_researchers", [])
                if researchers:
                    st.markdown("### 👥 Aktif Araştırmacılar")
                    for r in researchers:
                        if isinstance(r, str):
                            st.markdown(f"- {r}")
                            continue
                        aff = f" · {r.get('affiliation')}" if r.get("affiliation") else ""
                        st.markdown(
                            f"- **{r.get('name', '?')}**{aff} — {r.get('focus', '')}"
                        )

                key_papers = synthesis.get("key_papers", [])
                if key_papers:
                    st.markdown("### ⭐ Öne Çıkan Makaleler")
                    for kp in key_papers:
                        if isinstance(kp, str):
                            st.markdown(f"- {kp}")
                            continue
                        doc_idx = kp.get("doc_index")
                        idx_badge = (
                            f'<span style="background:#dbeafe;color:#1d4ed8;border-radius:4px;'
                            f'padding:0 6px;font-size:0.8em;font-weight:700;margin-right:4px;">[{doc_idx}]</span>'
                            if doc_idx else ""
                        )
                        st.markdown(
                            f"<div style='margin:4px 0'>{idx_badge}"
                            f"<b>{_e(kp.get('title', ''))}</b> "
                            f"({_e(kp.get('year', '?'))}) — {_render_cited_item(kp.get('why_important', ''))}</div>",
                            unsafe_allow_html=True,
                        )

                # --- Kullanılan kaynaklar bölümü ---
                rag_papers = synthesis.get("rag_papers", [])
                if rag_papers:
                    st.markdown("---")
                    st.markdown("### 📚 Bu Sentezde Kullanılan Kaynaklar")
                    st.caption(
                        "Aşağıdaki makaleler vektör veritabanından RAG ile seçilmiş ve sentezde kullanılmıştır. "
                        "Sentez metnindeki [N] numaraları, Makaleler sekmesindeki sıra numarasıyla eşleşir."
                    )
                    for rp in rag_papers:
                        idx = rp.get("global_index", "?")
                        title = rp.get("title", "")
                        authors = rp.get("authors", [])
                        year = rp.get("year", "?")
                        rp_source = rp.get("source", "arxiv")
                        author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")

                        if rp_source == "scopus":
                            link_url = rp.get("scopus_url", "") or rp.get("doi_url", "")
                            link_label = "Scopus" if rp.get("scopus_url") else "DOI"
                        else:
                            link_url = rp.get("arxiv_url", "")
                            link_label = "arXiv"

                        link_html = (
                            f' <a href="{_e(link_url)}" target="_blank" '
                            f'style="color:#2563eb;font-size:0.8em;">[{link_label}]</a>'
                            if link_url else ""
                        )
                        st.markdown(
                            f'<div style="margin:3px 0;font-size:0.88em;">'
                            f'<span style="background:#dbeafe;color:#1d4ed8;border-radius:4px;'
                            f'padding:0 6px;font-weight:700;margin-right:6px;">[{idx}]</span>'
                            f'<b>{_e(title)}</b> — {_e(author_str)} ({_e(year)}){link_html}</div>',
                            unsafe_allow_html=True,
                        )

                st.markdown(
                    """
                    <div class="warning-box">
                    Bu rapor otomatik olarak oluşturulmuştur. Sentezdeki tüm bulgular yalnızca yukarıdaki kaynaklara dayanmaktadır.
                    Akademik kullanım için orijinal makaleler kontrol edilmelidir.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # ---------------------------------------------------------------------
        # Papers
        # ---------------------------------------------------------------------
        with tab_papers:
            if not papers:
                st.info("Makale bulunamadı.")
            else:
                # Orijinal indeks haritası: paper id → 1-tabanlı sıra (sentez atıflarıyla eşleşir)
                orig_index_map = {
                    (p.get("id") or p.get("arxiv_id") or p.get("title", "")): i
                    for i, p in enumerate(papers, 1)
                }

                df = _papers_to_df(papers)

                if sort_mode == "Yeni → Eski" and "year" in df.columns:
                    sorted_papers = sorted(papers, key=lambda p: p.get("year", 0) or 0, reverse=True)
                elif sort_mode == "Eski → Yeni" and "year" in df.columns:
                    sorted_papers = sorted(papers, key=lambda p: p.get("year", 0) or 0)
                else:
                    sorted_papers = papers

                st.caption(
                    f"Toplam {len(papers)} makale. "
                    "Baştaki numara sentez raporundaki [N] atıf numarasıyla eşleşir."
                )

                view_mode = st.radio(
                    "Görünüm",
                    ["Kart", "Tablo"],
                    horizontal=True,
                    label_visibility="collapsed",
                )

                if view_mode == "Tablo":
                    df_sorted = _papers_to_df(sorted_papers)
                    # Orijinal indeks sütunu ekle
                    orig_indices = [
                        orig_index_map.get(
                            p.get("id") or p.get("arxiv_id") or p.get("title", ""), "?"
                        )
                        for p in sorted_papers
                    ]
                    df_sorted.insert(0, "#", orig_indices)
                    st.dataframe(
                        df_sorted,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    for p in sorted_papers:
                        orig_idx = orig_index_map.get(
                            p.get("id") or p.get("arxiv_id") or p.get("title", ""), "?"
                        )
                        if show_abstracts:
                            st.markdown(_render_paper_card(p, idx=orig_idx), unsafe_allow_html=True)
                        else:
                            p_copy = dict(p)
                            p_copy["abstract"] = ""
                            st.markdown(_render_paper_card(p_copy, idx=orig_idx), unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # Plan
        # ---------------------------------------------------------------------
        with tab_plan:
            st.markdown("### 📋 Araştırma Planı")
            if plan:
                st.write(plan)
            else:
                st.caption("Plan bilgisi bulunamadı.")

            st.markdown("### 🔎 Üretilen Arama Sorguları")
            if queries:
                for i, q in enumerate(queries, 1):
                    st.markdown(f"{i}. `{q}`")
            else:
                st.caption("Arama sorgusu bulunamadı.")

            st.markdown("### ⏱️ Adım Süreleri")
            time_cols = st.columns(len(STEPS))
            for i, (key, info) in enumerate(STEPS.items()):
                t = st.session_state.get("step_times", {}).get(key, {})
                dur = t.get("duration", 0)
                status = st.session_state.get("step_status", {}).get(key, "pending")
                status_icon = {
                    "done": "✅",
                    "error": "❌",
                    "pending": "⏳",
                    "running": "🔄",
                }.get(status, "⏳")

                time_cols[i].metric(
                    f"{info['icon']} {info['short']}",
                    f"{dur:.1f}s",
                    delta=status_icon,
                )

        # ---------------------------------------------------------------------
        # Logs
        # ---------------------------------------------------------------------
        with tab_logs:
            st.markdown("### 🧾 Pipeline Logları")
            logs = st.session_state.get("live_logs", [])
            
            # Logları döngü ile yazdır (HTML span/div karmaşasından kurtulduk)
            for entry in logs:
                level = entry.get("level", "INFO")
                color_class = f"log-level-{level}"
                st.markdown(
                    f"""
                    <div class="log-entry">
                        <span class="log-time">{_e(entry.get("time", ""))}</span>
                        <span class="log-level {color_class}">{level}</span>
                        <span class="log-text">{_e(entry.get("text", ""))}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # ---------------------------------------------------------------------
        # Export
        # ---------------------------------------------------------------------
        with tab_export:
            st.markdown("### ⬇️ Çıktıları İndir")

            report_md = _build_report_markdown()
            papers_df = _papers_to_df(papers)

            export_json = {
                "query": st.session_state.get("query", ""),
                "created_at": datetime.now().isoformat(),
                "research_plan": plan,
                "search_queries": queries,
                "papers": papers,
                "embedded_count": embedded,
                "synthesis": synthesis,
                "total_time": total_time,
            }

            c1, c2, c3 = st.columns(3)

            with c1:
                st.download_button(
                    "Markdown Rapor",
                    data=report_md.encode("utf-8"),
                    file_name="research_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            with c2:
                st.download_button(
                    "JSON Çıktı",
                    data=json.dumps(export_json, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name="research_output.json",
                    mime="application/json",
                    use_container_width=True,
                )

            with c3:
                csv_data = papers_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Makale CSV",
                    data=csv_data,
                    file_name="papers.csv",
                    mime="text/csv",
                    use_container_width=True,
                )


# =============================================================================
# Empty State
# =============================================================================

if not st.session_state.get("running") and not st.session_state.get("done"):
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-icon">🚀</div>
            <div class="empty-title">Araştırma pipeline'ını başlatmaya hazır</div>
            <div class="empty-desc">
                Yukarıdaki alana araştırma konunuzu girin. Sistem sırasıyla araştırma planı oluşturur,
                literatür tarar, sonuçları vektör veritabanına kaydeder ve sentez raporu üretir.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(STEPS), gap="large")

    for i, (_, info) in enumerate(STEPS.items()):
        with cols[i]:
            st.markdown(
                f"""
                <div class="feature-card">
                    <div class="feature-icon">{info["icon"]}</div>
                    <div class="feature-title">{_e(info["label"])}</div>
                    <div class="feature-desc">{_e(info["desc"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )