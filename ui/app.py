"""
Otonom Araştırma Asistanı — Streamlit UI

Kullanıcı bir araştırma sorusu girer.
LangGraph pipeline çalışır: Planner → Literature → Embed → Synthesis
Her agent adımı anlık olarak izlenir.
"""

import sys
import os
import time
import io
import contextlib
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
for _env_path in [ROOT / ".env", ROOT.parent.parent.parent / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

import streamlit as st
from loguru import logger

# ─── Loguru → session_state köprüsü ─────────────────────────────────────────

class _StreamlitLogSink:
    """Loguru mesajlarını session_state'e yönlendirir."""
    def write(self, message):
        record = message.record
        level = record["level"].name
        text = record["message"]
        timestamp = record["time"].strftime("%H:%M:%S")
        step = st.session_state.get("_active_step", "")

        entry = {
            "time": timestamp,
            "level": level,
            "text": text,
            "step": step,
        }

        if "live_logs" not in st.session_state:
            st.session_state["live_logs"] = []
        st.session_state["live_logs"].append(entry)

        if step and "step_logs" in st.session_state:
            st.session_state["step_logs"].setdefault(step, [])
            st.session_state["step_logs"][step].append(entry)

_sink_id = None

def _install_log_sink():
    global _sink_id
    if _sink_id is not None:
        return
    _sink_id = logger.add(_StreamlitLogSink(), format="{message}", level="DEBUG")

def _remove_log_sink():
    global _sink_id
    if _sink_id is not None:
        logger.remove(_sink_id)
        _sink_id = None


# ─── Sayfa ayarları ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Otonom Araştırma Asistanı",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
:root {
    --bg-card: linear-gradient(180deg, #11121a 0%, #1b1b25 100%);
    --bg-paper: linear-gradient(180deg,#0f1116 0%, #16161b 100%);
    --border-dim: #2b2f3a;
    --text-primary: #cdd6f4;
    --text-secondary: #9fb0d9;
    --accent-blue: #89b4fa;
    --accent-green: #a6e3a1;
    --accent-red: #f38ba8;
    --accent-yellow: #f9e2af;
    --accent-mauve: #cba6f7;
}

.agent-card, .paper-card, .synthesis-section, .step-row, .log-entry {
    color: var(--text-primary) !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
}

/* ── Step tracker ── */
.step-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border-radius: 10px;
    margin-bottom: 8px;
    transition: all .25s ease;
}
.step-row.pending {
    background: rgba(255,255,255,0.015);
    border-left: 4px solid #3b3f52;
}
.step-row.running {
    background: linear-gradient(90deg, rgba(137,180,250,0.06), rgba(137,180,250,0.01));
    border-left: 4px solid var(--accent-blue);
    animation: glow 2s ease-in-out infinite;
}
.step-row.done {
    background: linear-gradient(90deg, rgba(166,227,161,0.04), rgba(166,227,161,0.005));
    border-left: 4px solid var(--accent-green);
}
.step-row.error {
    background: linear-gradient(90deg, rgba(243,139,168,0.05), rgba(243,139,168,0.01));
    border-left: 4px solid var(--accent-red);
}
.step-icon { font-size: 1.3rem; width: 32px; text-align: center; }
.step-name { font-weight: 600; font-size: 0.95rem; flex: 1; }
.step-status { font-size: 0.8rem; padding: 3px 10px; border-radius: 12px; font-weight: 500; }
.step-status.pending { background: rgba(255,255,255,0.06); color: #7a7f99; }
.step-status.running { background: rgba(137,180,250,0.15); color: var(--accent-blue); }
.step-status.done { background: rgba(166,227,161,0.15); color: var(--accent-green); }
.step-status.error { background: rgba(243,139,168,0.15); color: var(--accent-red); }
.step-time { font-size: 0.78rem; color: var(--text-secondary); min-width: 48px; text-align: right; }

@keyframes glow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(137,180,250,0.05); }
    50% { box-shadow: 0 0 12px 2px rgba(137,180,250,0.08); }
}

/* ── Agent card ── */
.agent-card {
    background: var(--bg-card);
    border-left: 4px solid var(--accent-blue);
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
    font-size: 0.95rem;
}
.agent-card.done { border-color: var(--accent-green); }
.agent-card.error { border-color: var(--accent-red); }
.agent-card-title { font-weight: 700; margin-bottom: 6px; }
.agent-card-detail { font-size: 0.88rem; color: var(--text-secondary); }

/* ── Paper card ── */
.paper-card {
    background: var(--bg-paper);
    border-radius: 10px;
    padding: 16px;
    margin: 10px 0;
    border: 1px solid var(--border-dim);
    transition: border-color .2s;
}
.paper-card:hover { border-color: var(--accent-blue); }
.paper-title { font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.paper-meta { font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px; }
.paper-links a { color: var(--accent-blue); text-decoration: none; font-size: 0.85rem; }
.paper-links a:hover { text-decoration: underline; }

/* ── Synthesis ── */
.synthesis-section {
    background: var(--bg-paper);
    border-radius: 12px;
    padding: 18px;
    margin: 12px 0;
    border: 1px solid var(--border-dim);
}
.synthesis-title { font-size: 1.05rem; font-weight: 700; color: var(--accent-blue); margin-bottom: 10px; }

/* ── Log entries ── */
.log-entry {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem;
    padding: 4px 8px;
    border-radius: 4px;
    margin: 2px 0;
    display: flex;
    gap: 8px;
}
.log-entry.DEBUG { color: #6c7086; }
.log-entry.INFO { color: var(--text-primary); }
.log-entry.WARNING { color: var(--accent-yellow); }
.log-entry.ERROR { color: var(--accent-red); }
.log-time { color: #585b70; min-width: 60px; }
.log-level { min-width: 55px; font-weight: 600; }
.log-text { flex: 1; word-break: break-word; }

/* ── Live log panel ── */
.live-log-panel {
    background: #080b12;
    border: 1px solid #1a1d2e;
    border-radius: 10px;
    padding: 12px;
    max-height: 350px;
    overflow-y: auto;
}

/* ── Metric override ── */
[data-testid="stMetric"] {
    background: var(--bg-card);
    border-radius: 10px;
    padding: 14px !important;
    border: 1px solid var(--border-dim);
}
</style>
""", unsafe_allow_html=True)

# ─── Header ──────────────────────────────────────────────────────────────────

st.title("🔬 Otonom Araştırma Asistanı")
st.caption("LangGraph · Gemini 2.5 Flash · arXiv · Qdrant RAG")
st.divider()

# ─── Session state ───────────────────────────────────────────────────────────

STEPS = {
    "planner":    {"icon": "🧠", "label": "Planlama Ajanı", "desc": "Araştırma stratejisi ve arama sorguları üretir"},
    "literature": {"icon": "📚", "label": "Literatür Ajanı", "desc": "arXiv'de makale tarar ve toplar"},
    "embed":      {"icon": "🗄️", "label": "Embedding Ajanı", "desc": "Makaleleri vektör veritabanına kaydeder"},
    "synthesis":  {"icon": "🔬", "label": "Sentez Ajanı", "desc": "Gap analizi, trend tespiti ve sentez yapar"},
}

defaults = {
    "running": False,
    "done": False,
    "messages": [],
    "papers": [],
    "synthesis": {},
    "research_plan": "",
    "search_queries": [],
    "embedded_count": 0,
    "error": None,
    "step_logs": {},
    "live_logs": [],
    "step_status": {},
    "step_times": {},
    "current_step": "",
    "_active_step": "",
    "pipeline_start": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Yardımcı fonksiyonlar ───────────────────────────────────────────────────

def _render_step_tracker(step_status: dict, step_times: dict, current_step: str):
    """Adım takip panelini render et."""
    step_order = list(STEPS.keys())
    html_parts = []

    for key in step_order:
        info = STEPS[key]
        status = step_status.get(key, "pending")
        if key == current_step and status != "done" and status != "error":
            status = "running"

        status_labels = {
            "pending": "Bekliyor",
            "running": "Çalışıyor...",
            "done": "Tamamlandı",
            "error": "Hata",
        }
        status_label = status_labels.get(status, status)

        elapsed = step_times.get(key, {})
        time_str = ""
        if elapsed.get("duration"):
            time_str = f"{elapsed['duration']:.1f}s"
        elif elapsed.get("start") and status == "running":
            time_str = f"{time.time() - elapsed['start']:.0f}s..."

        html_parts.append(f"""
        <div class="step-row {status}">
            <div class="step-icon">{info['icon']}</div>
            <div class="step-name">{info['label']}<br><span style="font-weight:400;font-size:0.78rem;color:var(--text-secondary)">{info['desc']}</span></div>
            <div class="step-time">{time_str}</div>
            <div class="step-status {status}">{status_label}</div>
        </div>
        """)

    return "\n".join(html_parts)


def _render_log_panel(logs: list, max_lines: int = 50) -> str:
    """Canlı log panelini render et."""
    if not logs:
        return '<div class="live-log-panel"><span style="color:#585b70">Henüz log yok...</span></div>'

    entries = logs[-max_lines:]
    html_lines = []
    for entry in entries:
        level = entry.get("level", "INFO")
        html_lines.append(
            f'<div class="log-entry {level}">'
            f'<span class="log-time">{entry.get("time", "")}</span>'
            f'<span class="log-level">{level}</span>'
            f'<span class="log-text">{entry.get("text", "")}</span>'
            f'</div>'
        )

    return f'<div class="live-log-panel">{"".join(html_lines)}</div>'


# ─── Arama formu ─────────────────────────────────────────────────────────────

with st.form("search_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        query = st.text_input(
            "Araştırma sorusunu veya konusunu girin:",
            placeholder="Örn: multi-agent reinforcement learning for electric vehicle charging",
            label_visibility="collapsed",
        )
    with col2:
        submitted = st.form_submit_button("🔍 Araştır", use_container_width=True)

if submitted and query.strip():
    for k, v in defaults.items():
        st.session_state[k] = v
    st.session_state["running"] = True
    st.session_state["query"] = query.strip()
    st.session_state["pipeline_start"] = time.time()
    for s in STEPS:
        st.session_state["step_logs"][s] = []
        st.session_state["step_status"][s] = "pending"
    st.rerun()

# ─── Pipeline çalıştır ───────────────────────────────────────────────────────

if st.session_state.get("running") and not st.session_state.get("done"):
    query_val = st.session_state.get("query", "")

    # Ana layout: sol = adım tracker + loglar, sağ = detay
    tracker_col, detail_col = st.columns([2, 3], gap="large")

    with tracker_col:
        st.markdown("### 📊 Pipeline Durumu")
        tracker_placeholder = st.empty()
        tracker_placeholder.markdown(
            _render_step_tracker(
                st.session_state["step_status"],
                st.session_state["step_times"],
                st.session_state.get("current_step", ""),
            ),
            unsafe_allow_html=True,
        )

        st.markdown("### 📋 Canlı Loglar")
        log_placeholder = st.empty()
        log_placeholder.markdown(
            _render_log_panel(st.session_state.get("live_logs", [])),
            unsafe_allow_html=True,
        )

    with detail_col:
        st.markdown("### 🔄 Ajan Detayları")
        detail_placeholder = st.empty()
        detail_placeholder.info("Pipeline başlatılıyor...")

    _install_log_sink()

    try:
        from src.graph.research_graph import build_graph

        graph = build_graph()
        initial_state = {
            "query": query_val,
            "research_plan": "",
            "search_queries": [],
            "papers": [],
            "embedded_count": 0,
            "synthesis": {},
            "messages": [],
            "current_step": "",
            "error": None,
        }

        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                step_start = time.time()
                st.session_state["current_step"] = node_name
                st.session_state["_active_step"] = node_name
                st.session_state["step_status"][node_name] = "running"
                st.session_state["step_times"][node_name] = {"start": step_start}

                step_info = STEPS.get(node_name, {"icon": "⚙️", "label": node_name, "desc": ""})

                # Tracker güncelle
                tracker_placeholder.markdown(
                    _render_step_tracker(
                        st.session_state["step_status"],
                        st.session_state["step_times"],
                        node_name,
                    ),
                    unsafe_allow_html=True,
                )

                # Detay kartı — çalışıyor
                detail_placeholder.markdown(
                    f'<div class="agent-card">'
                    f'<div class="agent-card-title">{step_info["icon"]} {step_info["label"]} — Çalışıyor</div>'
                    f'<div class="agent-card-detail">{step_info["desc"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # State güncelle
                msgs = node_output.get("messages", []) or []
                for m in msgs:
                    st.session_state["messages"].append(str(m))

                if node_name == "planner":
                    st.session_state["research_plan"] = node_output.get("research_plan", "")
                    st.session_state["search_queries"] = node_output.get("search_queries", [])
                    queries = st.session_state["search_queries"]
                    plan = st.session_state["research_plan"]
                    detail_html = (
                        f'<div class="agent-card done">'
                        f'<div class="agent-card-title">🧠 Planlama Tamamlandı</div>'
                        f'<div class="agent-card-detail"><b>Strateji:</b> {plan}</div>'
                        f'<div class="agent-card-detail" style="margin-top:8px"><b>Üretilen Sorgular ({len(queries)}):</b></div>'
                    )
                    for i, q in enumerate(queries, 1):
                        detail_html += f'<div class="agent-card-detail">  {i}. {q}</div>'
                    detail_html += '</div>'
                    detail_placeholder.markdown(detail_html, unsafe_allow_html=True)

                elif node_name == "literature":
                    st.session_state["papers"] = node_output.get("papers", [])
                    paper_count = len(st.session_state["papers"])
                    detail_placeholder.markdown(
                        f'<div class="agent-card done">'
                        f'<div class="agent-card-title">📚 Literatür Taraması Tamamlandı</div>'
                        f'<div class="agent-card-detail"><b>{paper_count}</b> benzersiz makale bulundu</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                elif node_name == "embed":
                    st.session_state["embedded_count"] = node_output.get("embedded_count", 0)
                    embed_count = st.session_state["embedded_count"]
                    detail_placeholder.markdown(
                        f'<div class="agent-card done">'
                        f'<div class="agent-card-title">🗄️ Embedding Tamamlandı</div>'
                        f'<div class="agent-card-detail"><b>{embed_count}</b> makale vektör veritabanına kaydedildi</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                elif node_name == "synthesis":
                    st.session_state["synthesis"] = node_output.get("synthesis", {})
                    synth = st.session_state["synthesis"]
                    if synth.get("error"):
                        detail_placeholder.markdown(
                            f'<div class="agent-card error">'
                            f'<div class="agent-card-title">🔬 Sentez Hatası</div>'
                            f'<div class="agent-card-detail">{synth["error"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        summary_preview = synth.get("summary", "")[:200]
                        detail_placeholder.markdown(
                            f'<div class="agent-card done">'
                            f'<div class="agent-card-title">🔬 Sentez Tamamlandı</div>'
                            f'<div class="agent-card-detail">{summary_preview}...</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Adımı tamamla
                duration = time.time() - step_start
                st.session_state["step_status"][node_name] = "done"
                st.session_state["step_times"][node_name] = {
                    "start": step_start,
                    "duration": duration,
                }
                st.session_state["current_step"] = ""
                st.session_state["_active_step"] = ""

                # Tracker + log güncelle
                tracker_placeholder.markdown(
                    _render_step_tracker(
                        st.session_state["step_status"],
                        st.session_state["step_times"],
                        "",
                    ),
                    unsafe_allow_html=True,
                )
                log_placeholder.markdown(
                    _render_log_panel(st.session_state.get("live_logs", [])),
                    unsafe_allow_html=True,
                )

        # Pipeline tamamlandı
        total_time = time.time() - (st.session_state.get("pipeline_start") or time.time())
        st.session_state["running"] = False
        st.session_state["done"] = True
        st.session_state["total_time"] = total_time

    except Exception as e:
        logger.error(f"Pipeline hatası: {e}")
        st.session_state["error"] = str(e)
        st.session_state["running"] = False
        st.session_state["done"] = True
        if st.session_state.get("current_step"):
            st.session_state["step_status"][st.session_state["current_step"]] = "error"

    finally:
        _remove_log_sink()

    st.rerun()

# ─── Sonuçlar ────────────────────────────────────────────────────────────────

if st.session_state.get("done"):
    if st.session_state.get("error"):
        st.error(f"Pipeline Hatası: {st.session_state['error']}")

        # Hata durumunda da logları göster
        with st.expander("📋 Pipeline Logları", expanded=True):
            st.markdown(
                _render_log_panel(st.session_state.get("live_logs", []), max_lines=100),
                unsafe_allow_html=True,
            )
    else:
        papers = st.session_state.get("papers", [])
        synthesis = st.session_state.get("synthesis", {})
        plan = st.session_state.get("research_plan", "")
        queries = st.session_state.get("search_queries", [])
        embedded = st.session_state.get("embedded_count", 0)
        total_time = st.session_state.get("total_time", 0)

        # ── Pipeline özet metrikleri ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📄 Bulunan Makale", len(papers))
        c2.metric("🗄️ Vektör DB", embedded)
        c3.metric("🔍 Arama Sorgusu", len(queries))
        c4.metric("⏱️ Toplam Süre", f"{total_time:.1f}s")

        # ── Pipeline tamamlanma bilgisi ──
        st.success(
            f"Pipeline başarıyla tamamlandı! "
            f"{len(papers)} makale bulundu, {embedded} tanesi vektör veritabanına kaydedildi."
        )

        # ── Adım süreleri ──
        with st.expander("⏱️ Adım Süreleri & Loglar", expanded=False):
            step_times = st.session_state.get("step_times", {})
            time_cols = st.columns(len(STEPS))
            for i, (key, info) in enumerate(STEPS.items()):
                t = step_times.get(key, {})
                dur = t.get("duration", 0)
                status = st.session_state.get("step_status", {}).get(key, "pending")
                status_icon = {"done": "✅", "error": "❌", "pending": "⏳"}.get(status, "⏳")
                time_cols[i].metric(
                    f"{info['icon']} {info['label']}",
                    f"{dur:.1f}s",
                    delta=status_icon,
                )

            st.markdown("---")
            st.markdown("**Detaylı Loglar**")
            st.markdown(
                _render_log_panel(st.session_state.get("live_logs", []), max_lines=200),
                unsafe_allow_html=True,
            )

        st.divider()

        # ── İki sütun layout ──
        left, right = st.columns([1, 1], gap="large")

        # ── Sol: Araştırma planı + Makaleler ──
        with left:
            if plan:
                with st.expander("📋 Araştırma Planı", expanded=True):
                    st.write(plan)
                    if queries:
                        st.markdown("**Üretilen arama sorguları:**")
                        for q in queries:
                            st.markdown(f"- `{q}`")

            st.subheader(f"📄 Bulunan Makaleler ({len(papers)})")

            sorted_papers = sorted(papers, key=lambda p: p.get("year", 0), reverse=True)

            for p in sorted_papers:
                authors = p.get("authors", [])
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."
                cats = ", ".join(p.get("categories", [])[:2])
                pdf_url = p.get("pdf_url", "")
                arxiv_url = p.get("arxiv_url", "")

                links = []
                if arxiv_url:
                    links.append(f'<a href="{arxiv_url}" target="_blank">arXiv</a>')
                if pdf_url:
                    links.append(f'<a href="{pdf_url}" target="_blank">PDF</a>')
                link_html = " · ".join(links)

                abstract = p.get("abstract", "")
                abstract_short = abstract[:250] + "..." if len(abstract) > 250 else abstract

                st.markdown(f"""
<div class="paper-card">
  <div class="paper-title">{p.get('title', '')}</div>
  <div class="paper-meta">{author_str} · {p.get('year', '?')} · {cats}</div>
  <div class="paper-meta" style="margin-top:6px">{abstract_short}</div>
  <div class="paper-links" style="margin-top:8px">{link_html}</div>
</div>
""", unsafe_allow_html=True)

        # ── Sağ: Sentez sonuçları ──
        with right:
            st.subheader("🔬 Sentez & Analiz")

            if not synthesis or synthesis.get("error"):
                st.warning(synthesis.get("error", "Sentez sonucu yok."))
            else:
                if synthesis.get("summary"):
                    st.markdown(f"""
<div class="synthesis-section">
  <div class="synthesis-title">Genel Değerlendirme</div>
  {synthesis['summary']}
</div>
""", unsafe_allow_html=True)

                gap = synthesis.get("gap_analysis", {})
                if gap:
                    with st.expander("🔍 Gap Analizi", expanded=True):
                        if gap.get("solved_problems"):
                            st.markdown("**✅ Çözülmüş Problemler:**")
                            for item in gap["solved_problems"]:
                                st.markdown(f"- {item}")
                        if gap.get("open_problems"):
                            st.markdown("**⚠️ Açık Problemler:**")
                            for item in gap["open_problems"]:
                                st.markdown(f"- {item}")
                        if gap.get("research_gaps"):
                            st.markdown("**🔴 Araştırma Boşlukları:**")
                            for item in gap["research_gaps"]:
                                st.markdown(f"- {item}")

                trend = synthesis.get("trend_analysis", {})
                if trend:
                    with st.expander("📈 Trend Analizi", expanded=True):
                        if trend.get("emerging_methods"):
                            st.markdown("**Yükselen Yöntemler:**")
                            for m in trend["emerging_methods"]:
                                st.markdown(f"- {m}")
                        if trend.get("hot_topics"):
                            st.markdown("**Güncel Konular:**")
                            for t in trend["hot_topics"]:
                                st.markdown(f"- {t}")
                        if trend.get("temporal_shift"):
                            st.markdown(f"**Son 2-3 Yılda Ne Değişti:** {trend['temporal_shift']}")

                researchers = synthesis.get("active_researchers", [])
                if researchers:
                    with st.expander("👥 Aktif Araştırmacılar", expanded=False):
                        for r in researchers:
                            aff = f" · {r['affiliation']}" if r.get("affiliation") else ""
                            st.markdown(f"**{r.get('name', '?')}**{aff} — {r.get('focus', '')}")

                key_papers = synthesis.get("key_papers", [])
                if key_papers:
                    with st.expander("⭐ Öne Çıkan Makaleler", expanded=False):
                        for kp in key_papers:
                            st.markdown(
                                f"**{kp.get('title', '')}** ({kp.get('year', '?')}) — {kp.get('why_important', '')}"
                            )

# ─── Boş durum ───────────────────────────────────────────────────────────────

if not st.session_state.get("running") and not st.session_state.get("done"):
    st.markdown("""
<div style="text-align:center; padding: 40px 20px;">
    <div style="font-size: 3rem; margin-bottom: 16px;">🔬</div>
    <div style="font-size: 1.2rem; font-weight: 600; color: var(--text-primary); margin-bottom: 12px;">
        Araştırma konunuzu girin ve pipeline'ı başlatın
    </div>
    <div style="color: var(--text-secondary); font-size: 0.95rem; max-width: 600px; margin: 0 auto;">
        Sistem otomatik olarak 4 ajan ile çalışır:
    </div>
</div>
""", unsafe_allow_html=True)

    cols = st.columns(4)
    for i, (key, info) in enumerate(STEPS.items()):
        with cols[i]:
            st.markdown(f"""
<div style="text-align:center; padding: 20px 12px; background: var(--bg-paper); border-radius: 12px; border: 1px solid var(--border-dim);">
    <div style="font-size: 2rem; margin-bottom: 8px;">{info['icon']}</div>
    <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 4px;">{info['label']}</div>
    <div style="font-size: 0.82rem; color: var(--text-secondary);">{info['desc']}</div>
</div>
""", unsafe_allow_html=True)
