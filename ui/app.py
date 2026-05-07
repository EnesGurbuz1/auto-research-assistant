"""
Otonom Araştırma Asistanı — Streamlit UI

Kullanıcı bir araştırma sorusu girer.
LangGraph pipeline çalışır: Planner → Literature → Embed → Synthesis
Her agent adımı anlık olarak izlenir.
"""

import sys
import os
from pathlib import Path

# Proje kökünü Python path'e ekle
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
# Worktree veya parent'ta .env ara
for _env_path in [ROOT / ".env", ROOT.parent.parent.parent / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

import streamlit as st

# ─── Sayfa ayarları ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Otonom Araştırma Asistanı",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.agent-card {
    background: #1e1e2e;
    border-left: 4px solid #89b4fa;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 6px 0;
    font-size: 0.9rem;
}
.agent-card.done {
    border-color: #a6e3a1;
}
.agent-card.error {
    border-color: #f38ba8;
}
.paper-card {
    background: #181825;
    border-radius: 8px;
    padding: 14px;
    margin: 8px 0;
    border: 1px solid #313244;
}
.paper-title {
    font-size: 1rem;
    font-weight: 600;
    color: #cdd6f4;
}
.paper-meta {
    font-size: 0.8rem;
    color: #a6adc8;
    margin-top: 4px;
}
.synthesis-section {
    background: #1e1e2e;
    border-radius: 10px;
    padding: 16px;
    margin: 10px 0;
    border: 1px solid #45475a;
}
.synthesis-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #89b4fa;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

# ─── Header ───────────────────────────────────────────────────────────────────

st.title("🔬 Otonom Araştırma Asistanı")
st.caption("LangGraph · Gemini 2.0 Flash · arXiv · Qdrant RAG")

st.divider()

# ─── Session state başlangıç değerleri ────────────────────────────────────────

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
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Arama formu ──────────────────────────────────────────────────────────────

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
    # Önceki sonuçları temizle
    for k, v in defaults.items():
        st.session_state[k] = v
    st.session_state["running"] = True
    st.session_state["query"] = query.strip()
    st.rerun()

# ─── Pipeline çalıştır ────────────────────────────────────────────────────────

if st.session_state.get("running") and not st.session_state.get("done"):
    query_val = st.session_state.get("query", "")

    st.subheader("Ajan İlerlemesi")
    progress_container = st.container()

    step_icons = {
        "planner":    "🧠 Planlama Ajanı",
        "literature": "📚 Literatür Ajanı",
        "embed":      "🗄️ Embedding & RAG",
        "synthesis":  "🔬 Sentez Ajanı",
    }
    step_status = {k: "pending" for k in step_icons}

    step_placeholders = {}
    with progress_container:
        for key, label in step_icons.items():
            step_placeholders[key] = st.empty()
            step_placeholders[key].markdown(
                f'<div class="agent-card">⏳ {label}</div>', unsafe_allow_html=True
            )

    detail_placeholder = st.empty()

    # Graph'ı import et ve çalıştır
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
                # Adımı "running" yap
                step_placeholders[node_name].markdown(
                    f'<div class="agent-card">🔄 {step_icons.get(node_name, node_name)} — çalışıyor...</div>',
                    unsafe_allow_html=True,
                )

                # State güncelle
                msgs = node_output.get("messages", [])
                if msgs:
                    st.session_state["messages"].extend(msgs)
                    detail_placeholder.info(msgs[-1])

                if node_name == "planner":
                    st.session_state["research_plan"] = node_output.get("research_plan", "")
                    st.session_state["search_queries"] = node_output.get("search_queries", [])
                elif node_name == "literature":
                    st.session_state["papers"] = node_output.get("papers", [])
                elif node_name == "embed":
                    st.session_state["embedded_count"] = node_output.get("embedded_count", 0)
                elif node_name == "synthesis":
                    st.session_state["synthesis"] = node_output.get("synthesis", {})

                # Adımı "done" yap
                step_placeholders[node_name].markdown(
                    f'<div class="agent-card done">✅ {step_icons.get(node_name, node_name)} — tamamlandı</div>',
                    unsafe_allow_html=True,
                )

        detail_placeholder.empty()
        st.session_state["running"] = False
        st.session_state["done"] = True

    except Exception as e:
        st.session_state["error"] = str(e)
        st.session_state["running"] = False
        st.session_state["done"] = True

    st.rerun()

# ─── Sonuçlar ─────────────────────────────────────────────────────────────────

if st.session_state.get("done"):
    if st.session_state.get("error"):
        st.error(f"Hata: {st.session_state['error']}")

    else:
        papers = st.session_state.get("papers", [])
        synthesis = st.session_state.get("synthesis", {})
        plan = st.session_state.get("research_plan", "")
        queries = st.session_state.get("search_queries", [])
        embedded = st.session_state.get("embedded_count", 0)

        # Özet metrikler
        c1, c2, c3 = st.columns(3)
        c1.metric("Bulunan Makale", len(papers))
        c2.metric("Vektör DB'ye Yüklenen", embedded)
        c3.metric("Araştırma Sorgusu", len(queries))

        st.divider()

        # İki sütun layout
        left, right = st.columns([1, 1], gap="large")

        # ── Sol: Araştırma planı + Makaleler ──────────────────────────────────
        with left:
            if plan:
                with st.expander("📋 Araştırma Planı", expanded=True):
                    st.write(plan)
                    if queries:
                        st.markdown("**Üretilen arama sorguları:**")
                        for q in queries:
                            st.markdown(f"- `{q}`")

            st.subheader(f"📄 Bulunan Makaleler ({len(papers)})")

            # Yıla göre sırala (yeni→eski)
            sorted_papers = sorted(papers, key=lambda p: p.get("year", 0), reverse=True)

            for p in sorted_papers:
                authors = p.get("authors", [])
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."
                cats = ", ".join(p.get("categories", [])[:2])
                pdf_url = p.get("pdf_url", "")
                arxiv_url = p.get("arxiv_url", "")

                link_md = ""
                if arxiv_url:
                    link_md += f"[arXiv]({arxiv_url})"
                if pdf_url:
                    link_md += f" · [PDF]({pdf_url})"

                abstract = p.get("abstract", "")
                abstract_short = abstract[:250] + "..." if len(abstract) > 250 else abstract

                st.markdown(f"""
<div class="paper-card">
  <div class="paper-title">{p.get('title', '')}</div>
  <div class="paper-meta">{author_str} · {p.get('year', '?')} · {cats}</div>
  <div class="paper-meta" style="margin-top:6px">{abstract_short}</div>
  <div class="paper-meta" style="margin-top:6px">{link_md}</div>
</div>
""", unsafe_allow_html=True)

        # ── Sağ: Sentez sonuçları ──────────────────────────────────────────────
        with right:
            st.subheader("🔬 Sentez & Analiz")

            if not synthesis or synthesis.get("error"):
                st.warning(synthesis.get("error", "Sentez sonucu yok."))
            else:
                # Özet
                if synthesis.get("summary"):
                    st.markdown(f"""
<div class="synthesis-section">
  <div class="synthesis-title">Genel Değerlendirme</div>
  {synthesis['summary']}
</div>
""", unsafe_allow_html=True)

                # Gap Analizi
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

                # Trend Analizi
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

                # Aktif Araştırmacılar
                researchers = synthesis.get("active_researchers", [])
                if researchers:
                    with st.expander("👥 Aktif Araştırmacılar", expanded=False):
                        for r in researchers:
                            aff = f" · {r['affiliation']}" if r.get("affiliation") else ""
                            st.markdown(f"**{r.get('name', '?')}**{aff} — {r.get('focus', '')}")

                # Önemli Makaleler
                key_papers = synthesis.get("key_papers", [])
                if key_papers:
                    with st.expander("⭐ Öne Çıkan Makaleler", expanded=False):
                        for kp in key_papers:
                            st.markdown(
                                f"**{kp.get('title', '')}** ({kp.get('year', '?')}) — {kp.get('why_important', '')}"
                            )

# ─── Boş durum ────────────────────────────────────────────────────────────────

if not st.session_state.get("running") and not st.session_state.get("done"):
    st.info(
        "Yukarıdaki arama kutusuna bir araştırma konusu yazın ve **Araştır** butonuna tıklayın.\n\n"
        "Sistem otomatik olarak:\n"
        "1. **Planlama Ajanı** ile arama stratejisi belirler\n"
        "2. **Literatür Ajanı** ile arXiv'de makale tarar\n"
        "3. **Embedding** ile makaleleri vektör veritabanına kaydeder\n"
        "4. **Sentez Ajanı** ile gap analizi ve trend tespiti yapar"
    )
