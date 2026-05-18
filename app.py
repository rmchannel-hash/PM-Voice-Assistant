"""
app.py — Phase 1 Stabilized
=============================
PMO Intelligence Platform — Multi-Tab Streamlit UI
Provider  : Anthropic Claude (via agents.py)
Phase     : 1 — Core Analysis Pipeline

Tabs:
  1. 📥 Input         — paste text or upload file
  2. 📊 Analysis      — structured project brief
  3. 🔄 Methodology   — delivery methodology recommendation
  4. ✅ Go/No-Go      — viability gate with scoring
  5. 🏗 Site Readiness — operational readiness assessment
  6. 📋 Executive Summary — board-ready synthesis

Architecture:
  - All AI work is in agents.py (never inline in UI).
  - UI layer is purely display + state management.
  - session_state is the single source of truth.
  - Progress callbacks bridge agent threads → UI feedback.

Phase 2 hooks (not active but wired):
  - Conversational AI: st.chat_input ready in sidebar
  - Multi-project support: project registry scaffold in session_state
  - Voice: launch point noted in Input tab
"""

import os
import io
import time
import threading
import logging
from datetime import datetime
from typing import Optional

import streamlit as st

# ── Internal modules ───────────────────────────────────────────────────────────
# agents.py is the only required import; others are gracefully optional
from agents import (
    AgentOrchestrator,
    ProjectContext,
    PipelineReport,
    AgentResult,
)

# ── Optional supporting modules (Phase 2 will use these fully) ─────────────────
try:
    from memory import OperationalMemory
    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False

try:
    from dependency_graph import DependencyGraph
    _DEPGRAPH_AVAILABLE = True
except ImportError:
    _DEPGRAPH_AVAILABLE = False

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG  (must be first Streamlit call)
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="PMO Intelligence Platform",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOM CSS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* ── Typography & base ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

/* ── Status badge components ────────────────────────────────────── */
.badge-go        { background:#1a7a4a; color:#fff; padding:2px 10px; border-radius:4px; font-weight:600; font-size:13px; }
.badge-nogo      { background:#b91c1c; color:#fff; padding:2px 10px; border-radius:4px; font-weight:600; font-size:13px; }
.badge-cond      { background:#92400e; color:#fff; padding:2px 10px; border-radius:4px; font-weight:600; font-size:13px; }
.badge-insuff    { background:#374151; color:#fff; padding:2px 10px; border-radius:4px; font-weight:600; font-size:13px; }

/* ── Metric card ─────────────────────────────────────────────────── */
.metric-card {
    background: var(--background-color, #1e2130);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 8px;
}
.metric-label { font-size: 11px; font-weight: 500; text-transform: uppercase;
                letter-spacing: 0.08em; opacity: 0.6; margin-bottom: 4px; }
.metric-value { font-size: 26px; font-weight: 600; font-family: 'IBM Plex Mono', monospace; }
.metric-sub   { font-size: 12px; opacity: 0.55; margin-top: 4px; }

/* ── Agent status pills ─────────────────────────────────────────── */
.agent-pill-running { color:#f59e0b; font-size:12px; }
.agent-pill-done    { color:#10b981; font-size:12px; }
.agent-pill-error   { color:#ef4444; font-size:12px; }

/* ── Section header ─────────────────────────────────────────────── */
.section-header {
    border-left: 3px solid #3b82f6;
    padding-left: 12px;
    margin: 20px 0 12px;
    font-weight: 600;
    font-size: 15px;
    letter-spacing: 0.02em;
}

/* ── Tab content padding ────────────────────────────────────────── */
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 20px;
}

/* ── Readiness score bar ────────────────────────────────────────── */
.readiness-bar-wrap { background: rgba(255,255,255,0.07); border-radius: 6px;
                      height: 10px; margin: 8px 0; overflow: hidden; }
.readiness-bar-fill { height: 100%; border-radius: 6px;
                      background: linear-gradient(90deg, #f59e0b, #10b981); }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _init_state() -> None:
    defaults = {
        # Core analysis state
        "report":            None,        # PipelineReport | None
        "is_running":        False,       # lock while pipeline executes
        "run_timestamp":     None,        # datetime of last run
        "project_text":      "",          # last analysed text
        "source_filename":   None,        # if uploaded file

        # Agent progress tracking (for live UI feedback)
        "agent_progress": {
            "ProjectSummaryAgent":    "idle",
            "MethodologyAgent":       "idle",
            "GoNoGoAgent":            "idle",
            "SiteReadinessAgent":     "idle",
            "ExecutiveSummaryAgent":  "idle",
        },

        # Phase 2 scaffold: conversational history
        "conversation_history": [],

        # Phase 2 scaffold: project registry
        "project_registry": {},

        # Active tab tracking
        "active_tab": 0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ══════════════════════════════════════════════════════════════════════════════
#  API KEY RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_api_key() -> Optional[str]:
    """Priority: env var → streamlit secrets → sidebar input."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return st.session_state.get("_sidebar_api_key", "")


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE RUNNER  (called in background thread)
# ══════════════════════════════════════════════════════════════════════════════

def _progress_cb(agent_name: str, status: str) -> None:
    """Thread-safe progress update hook."""
    if "agent_progress" in st.session_state:
        st.session_state["agent_progress"][agent_name] = status


def _run_pipeline(
    text: str,
    api_key: str,
    source_type: str = "text",
    filename: Optional[str] = None,
) -> None:
    """Execute the full agent pipeline and store report in session_state."""
    st.session_state["is_running"] = True
    st.session_state["report"]     = None

    # Reset agent progress
    for name in st.session_state["agent_progress"]:
        st.session_state["agent_progress"][name] = "idle"

    try:
        orchestrator = AgentOrchestrator(api_key=api_key)
        report = orchestrator.run_pipeline(
            raw_text=text,
            source_type=source_type,
            filename=filename,
            progress_callback=_progress_cb,
        )
        st.session_state["report"]        = report
        st.session_state["project_text"]  = text
        st.session_state["source_filename"] = filename
        st.session_state["run_timestamp"] = datetime.now()
    except Exception as exc:
        logger.error(f"Pipeline failed: {exc}")
        st.session_state["_pipeline_error"] = str(exc)
    finally:
        st.session_state["is_running"] = False


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER RENDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _render_agent_error(result: AgentResult) -> None:
    st.error(
        f"**{result.agent_name}** encountered an error: `{result.error}`\n\n"
        "Check your API key and network connection, then re-run."
    )


def _render_elapsed(result: AgentResult) -> None:
    st.caption(f"⏱ {result.elapsed_ms:,.0f} ms · {result.agent_name}")


def _go_badge(decision: str) -> str:
    d = decision.upper()
    if "NO-GO" in d:
        return '<span class="badge-nogo">NO-GO ❌</span>'
    if "CONDITIONAL" in d:
        return '<span class="badge-cond">CONDITIONAL GO ⚠️</span>'
    if "INSUFFICIENT" in d:
        return '<span class="badge-insuff">INSUFFICIENT DATA ❓</span>'
    return '<span class="badge-go">GO ✅</span>'


def _readiness_bar(pct: Optional[float]) -> str:
    if pct is None:
        return ""
    colour = "#ef4444" if pct < 50 else "#f59e0b" if pct < 75 else "#10b981"
    return (
        f'<div class="readiness-bar-wrap">'
        f'<div class="readiness-bar-fill" style="width:{pct:.0f}%; background:{colour};"></div>'
        f'</div>'
    )


def _metric_card(label: str, value: str, sub: str = "") -> str:
    return (
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'{"<div class=metric-sub>" + sub + "</div>" if sub else ""}'
        f'</div>'
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🧭 PMO Intelligence")
    st.caption("Phase 1 · Powered by Anthropic Claude")
    st.divider()

    # ── API Key ──────────────────────────────────────────────────────────────
    api_key = _resolve_api_key()
    if not api_key:
        st.markdown("### 🔑 API Key")
        typed_key = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="Set ANTHROPIC_API_KEY env var to avoid entering this each session.",
            label_visibility="collapsed",
        )
        if typed_key:
            st.session_state["_sidebar_api_key"] = typed_key
            api_key = typed_key
        if not api_key:
            st.warning("API key required to run analysis.")
        st.divider()
    else:
        st.success("🔑 API key detected", icon="✅")
        st.divider()

    # ── Run Status ───────────────────────────────────────────────────────────
    if st.session_state["is_running"]:
        st.markdown("### ⚙️ Agent Pipeline")
        progress_map = st.session_state["agent_progress"]
        status_icons = {"idle": "⬜", "running": "🟡", "done": "✅", "error": "🔴"}
        agent_labels = {
            "ProjectSummaryAgent":    "📊 Project Analysis",
            "MethodologyAgent":       "🔄 Methodology",
            "GoNoGoAgent":            "✅ Go/No-Go",
            "SiteReadinessAgent":     "🏗 Site Readiness",
            "ExecutiveSummaryAgent":  "📋 Executive Summary",
        }
        for name, label in agent_labels.items():
            status = progress_map.get(name, "idle")
            icon   = status_icons.get(status, "⬜")
            st.caption(f"{icon} {label}")
        st.divider()

    # ── Last Run Summary ─────────────────────────────────────────────────────
    if st.session_state["report"] and st.session_state["run_timestamp"]:
        report: PipelineReport = st.session_state["report"]
        ts = st.session_state["run_timestamp"].strftime("%d %b %Y %H:%M")
        st.markdown("### 📌 Last Run")
        st.caption(f"**{ts}**")

        # Project name
        if report.project_summary.succeeded and isinstance(report.project_summary.output, dict):
            pname = report.project_summary.output.get("project_name", "")
            if pname:
                st.caption(f"📁 {pname}")

        # Go/No-Go quick badge
        if report.go_no_go.succeeded and isinstance(report.go_no_go.output, dict):
            dec = report.go_no_go.output.get("decision", "")
            st.markdown(_go_badge(dec), unsafe_allow_html=True)

        # Readiness quick score
        if report.site_readiness.succeeded and isinstance(report.site_readiness.output, dict):
            pct = report.site_readiness.output.get("readiness_pct")
            if pct is not None:
                st.markdown(
                    f"🏗 Readiness: **{pct:.0f}%**"
                    + _readiness_bar(pct),
                    unsafe_allow_html=True,
                )

        st.caption(f"⏱ {report.total_elapsed_ms / 1000:.1f}s total pipeline")
        st.divider()

    # ── About ────────────────────────────────────────────────────────────────
    with st.expander("ℹ️ About Phase 1"):
        st.markdown("""
**PMO Intelligence Platform — Phase 1**

Five specialist AI agents analyse any project document:
- **Project Summary** — structured brief extraction
- **Methodology** — delivery framework recommendation
- **Go/No-Go** — viability gate with scoring
- **Site Readiness** — operational readiness check
- **Executive Summary** — board-ready synthesis

**Phase 2 (coming):** Conversational AI, multi-project workspace, voice input, RAG memory.
        """)

    # ── Phase 2 Hook: Conversational AI placeholder ──────────────────────────
    # Phase 2: replace this block with st.chat_input + agent router
    st.markdown("---")
    st.caption("💬 Conversational AI — Phase 2")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN HEADER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# 🧭 PMO Intelligence Platform")
st.caption("Multi-agent project analysis · Anthropic Claude · Phase 1")

if st.session_state["is_running"]:
    st.info("⚙️ Analysis pipeline running — results will appear below when complete.")
    st.rerun()  # Streamlit polling to reflect agent progress

if st.session_state.get("_pipeline_error"):
    st.error(
        f"**Pipeline Error:** {st.session_state['_pipeline_error']}\n\n"
        "Check your API key and try again."
    )
    del st.session_state["_pipeline_error"]

# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════

TAB_LABELS = [
    "📥 Input",
    "📊 Analysis",
    "🔄 Methodology",
    "✅ Go/No-Go",
    "🏗 Site Readiness",
    "📋 Executive Summary",
]

tabs = st.tabs(TAB_LABELS)


# ═══════════════════════════════════════════════════════════
#  TAB 0 — INPUT
# ═══════════════════════════════════════════════════════════

with tabs[0]:
    st.markdown(
        '<div class="section-header">Project Input</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Paste any project document — SOW, bid doc, status report, meeting notes, "
        "brief — or upload a text file. Works on any project in any sector."
    )

    # ── Input method ──────────────────────────────────────────────────────────
    input_method = st.radio(
        "Input method:",
        ["✏️ Paste text", "📎 Upload file"],
        horizontal=True,
        label_visibility="collapsed",
    )

    project_text  = ""
    source_type   = "text"
    upload_name   = None

    if input_method == "✏️ Paste text":
        project_text = st.text_area(
            "Project document",
            height=320,
            placeholder=(
                "Paste your project document here...\n\n"
                "Examples:\n"
                "• Statement of Work (SOW)\n"
                "• Bid or tender document\n"
                "• Project status report\n"
                "• Meeting minutes / MoM\n"
                "• Project brief or charter\n"
                "• Discovery findings\n\n"
                "The agents extract objectives, risks, stakeholders, milestones, "
                "and constraints from whatever you provide."
            ),
            label_visibility="collapsed",
        )
        source_type = "text"

    else:
        uploaded = st.file_uploader(
            "Upload project document",
            type=["txt", "md", "csv"],
            help="Plain text files only (Phase 1). PDF and DOCX support in Phase 2.",
            label_visibility="collapsed",
        )
        if uploaded:
            try:
                project_text = io.StringIO(
                    uploaded.read().decode("utf-8", errors="ignore")
                ).read()
                source_type  = "file"
                upload_name  = uploaded.name
                st.success(
                    f"✅ Loaded: **{uploaded.name}** "
                    f"({len(project_text):,} characters)"
                )
                with st.expander("Preview (first 500 chars)"):
                    st.text(project_text[:500] + ("..." if len(project_text) > 500 else ""))
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

        # Phase 2 note
        st.caption(
            "📌 Phase 2: PDF, DOCX, and voice note upload coming. "
            "Plain text and Markdown supported now."
        )

    st.divider()

    # ── Validation & Run ──────────────────────────────────────────────────────
    col_btn, col_info = st.columns([2, 5])

    with col_btn:
        run_clicked = st.button(
            "🚀 Analyse Project",
            type="primary",
            use_container_width=True,
            disabled=st.session_state["is_running"] or not api_key,
        )

    with col_info:
        if not api_key:
            st.warning("⚠️ Add your Anthropic API key in the sidebar to run.")
        elif not project_text.strip():
            st.info("Paste or upload project content above, then click Analyse.")
        elif st.session_state["report"]:
            ts = st.session_state["run_timestamp"].strftime("%H:%M:%S")
            st.success(
                f"✅ Analysis complete ({ts}). "
                "Navigate tabs to review results, or run again with new input."
            )

    if run_clicked:
        text = project_text.strip()
        if not text:
            st.error("No content to analyse. Paste text or upload a file first.")
        elif not api_key:
            st.error("API key missing. Add it in the sidebar.")
        else:
            # Launch pipeline in background thread so Streamlit stays responsive
            t = threading.Thread(
                target=_run_pipeline,
                kwargs={
                    "text":        text,
                    "api_key":     api_key,
                    "source_type": source_type,
                    "filename":    upload_name,
                },
                daemon=True,
            )
            t.start()
            st.rerun()

    # ── Placeholder content when no results yet ───────────────────────────────
    if not st.session_state["report"] and not st.session_state["is_running"]:
        st.divider()
        st.markdown(
            '<div class="section-header">What the platform delivers</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""
**📊 Structured Analysis**
Extracts objectives, stakeholders, scope, constraints, risks, and gaps from any unstructured text.
            """)
        with c2:
            st.markdown("""
**🔄 Methodology Fit**
Recommends Agile, Waterfall, Hybrid, PRINCE2, SAFe, or Iterative based on project characteristics.
            """)
        with c3:
            st.markdown("""
**✅ Go/No-Go Gate**
Scores five viability dimensions and issues a clear GO / NO-GO / CONDITIONAL decision.
            """)
        c4, c5, c6 = st.columns(3)
        with c4:
            st.markdown("""
**🏗 Site Readiness**
Checks infrastructure, staffing, access, approvals, vendors, and tooling before you commit to delivery.
            """)
        with c5:
            st.markdown("""
**📋 Executive Summary**
Board-ready synthesis: decision, top risks, and recommended actions — in 90 seconds of reading.
            """)
        with c6:
            st.markdown("""
**🔮 Phase 2 Ready**
Conversational AI, RAG memory, multi-project workspace, and voice input are wired in, not bolted on.
            """)


# ═══════════════════════════════════════════════════════════
#  TAB 1 — PROJECT ANALYSIS
# ═══════════════════════════════════════════════════════════

with tabs[1]:
    st.markdown(
        '<div class="section-header">Project Analysis</div>',
        unsafe_allow_html=True,
    )

    report: Optional[PipelineReport] = st.session_state["report"]

    if st.session_state["is_running"]:
        with st.spinner("📊 Project Summary Agent is running..."):
            st.stop()

    if not report:
        st.info("Run an analysis from the **📥 Input** tab to see results here.")
        st.stop()

    result = report.project_summary

    if not result.succeeded:
        _render_agent_error(result)
        st.stop()

    data = result.output if isinstance(result.output, dict) else {}
    brief = data.get("full_brief", str(result.output))

    # Project name callout
    pname = data.get("project_name", "")
    if pname:
        st.success(f"**Project identified:** {pname}")

    # Agent reasoning (collapsible)
    with st.expander("🧠 Agent Reasoning", expanded=False):
        st.caption(result.reasoning)

    st.markdown(brief)
    _render_elapsed(result)


# ═══════════════════════════════════════════════════════════
#  TAB 2 — METHODOLOGY
# ═══════════════════════════════════════════════════════════

with tabs[2]:
    st.markdown(
        '<div class="section-header">Delivery Methodology Recommendation</div>',
        unsafe_allow_html=True,
    )

    if st.session_state["is_running"]:
        with st.spinner("🔄 Methodology Agent is running..."):
            st.stop()

    if not report:
        st.info("Run an analysis from the **📥 Input** tab to see results here.")
        st.stop()

    result = report.methodology

    if not result.succeeded:
        _render_agent_error(result)
        st.stop()

    data = result.output if isinstance(result.output, dict) else {}
    methodology = data.get("methodology", "Undetermined")
    confidence  = data.get("confidence", "Medium")
    full_text   = data.get("full_analysis", str(result.output))

    # Headline metric
    col_m, col_c, col_sp = st.columns([3, 2, 4])
    with col_m:
        st.markdown(
            _metric_card("Recommended Methodology", methodology),
            unsafe_allow_html=True,
        )
    with col_c:
        conf_colour = {"High": "#10b981", "Medium": "#f59e0b", "Low": "#ef4444"}.get(
            confidence, "#6b7280"
        )
        st.markdown(
            _metric_card(
                "Confidence",
                confidence,
                sub=f"<span style='color:{conf_colour}'>●</span> {confidence} confidence",
            ),
            unsafe_allow_html=True,
        )

    st.divider()

    with st.expander("🧠 Agent Reasoning", expanded=False):
        st.caption(result.reasoning)

    st.markdown(full_text)
    _render_elapsed(result)


# ═══════════════════════════════════════════════════════════
#  TAB 3 — GO / NO-GO
# ═══════════════════════════════════════════════════════════

with tabs[3]:
    st.markdown(
        '<div class="section-header">Go / No-Go Assessment</div>',
        unsafe_allow_html=True,
    )

    if st.session_state["is_running"]:
        with st.spinner("✅ Go/No-Go Agent is running..."):
            st.stop()

    if not report:
        st.info("Run an analysis from the **📥 Input** tab to see results here.")
        st.stop()

    result = report.go_no_go

    if not result.succeeded:
        _render_agent_error(result)
        st.stop()

    data      = result.output if isinstance(result.output, dict) else {}
    decision  = data.get("decision", "INSUFFICIENT DATA")
    comp_pct  = data.get("composite_pct")
    full_text = data.get("full_analysis", str(result.output))

    # Decision headline
    col_d, col_s, col_sp = st.columns([3, 2, 4])
    with col_d:
        st.markdown(
            f"### Decision\n\n{_go_badge(decision)}",
            unsafe_allow_html=True,
        )
    with col_s:
        if comp_pct is not None:
            score_colour = (
                "#10b981" if comp_pct >= 70
                else "#f59e0b" if comp_pct >= 45
                else "#ef4444"
            )
            st.markdown(
                _metric_card(
                    "Composite Score",
                    f"{comp_pct:.0f}%",
                    sub=f"<span style='color:{score_colour}'>{'▲ Strong' if comp_pct >= 70 else '▼ Concern' if comp_pct < 45 else '~ Moderate'}</span>",
                ),
                unsafe_allow_html=True,
            )

    # Alert banner for NO-GO
    if "NO-GO" in decision.upper() and "CONDITIONAL" not in decision.upper():
        st.error(
            "🚨 **NO-GO** — Delivery cannot proceed until critical blockers are resolved. "
            "See the full assessment below."
        )
    elif "CONDITIONAL" in decision.upper():
        st.warning(
            "⚠️ **CONDITIONAL GO** — Conditions must be formally met and signed off "
            "before committing to delivery. See conditions in the full assessment."
        )
    elif decision.upper() == "GO":
        st.success("✅ **GO** — Project assessed as viable to proceed.")

    st.divider()

    with st.expander("🧠 Agent Reasoning", expanded=False):
        st.caption(result.reasoning)

    st.markdown(full_text)
    _render_elapsed(result)


# ═══════════════════════════════════════════════════════════
#  TAB 4 — SITE READINESS
# ═══════════════════════════════════════════════════════════

with tabs[4]:
    st.markdown(
        '<div class="section-header">Site & Operational Readiness</div>',
        unsafe_allow_html=True,
    )

    if st.session_state["is_running"]:
        with st.spinner("🏗 Site Readiness Agent is running..."):
            st.stop()

    if not report:
        st.info("Run an analysis from the **📥 Input** tab to see results here.")
        st.stop()

    result = report.site_readiness

    if not result.succeeded:
        _render_agent_error(result)
        st.stop()

    data       = result.output if isinstance(result.output, dict) else {}
    read_pct   = data.get("readiness_pct")
    full_text  = data.get("full_analysis", str(result.output))

    # Readiness score headline
    if read_pct is not None:
        col_r, col_rb, col_sp = st.columns([2, 4, 3])
        with col_r:
            label_colour = (
                "#ef4444" if read_pct < 50
                else "#f59e0b" if read_pct < 75
                else "#10b981"
            )
            status_label = (
                "Not Ready" if read_pct < 50
                else "Partially Ready" if read_pct < 75
                else "Ready"
            )
            st.markdown(
                _metric_card(
                    "Overall Readiness",
                    f"{read_pct:.0f}%",
                    sub=f"<span style='color:{label_colour}'>● {status_label}</span>",
                ),
                unsafe_allow_html=True,
            )
        with col_rb:
            st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
            st.markdown(
                _readiness_bar(read_pct),
                unsafe_allow_html=True,
            )
            st.caption(f"Readiness score: {read_pct:.0f} / 100")

        if read_pct < 50:
            st.error(
                "🚨 **Low readiness** — Significant gaps exist. "
                "Do not commit to delivery start until blockers are resolved."
            )
        elif read_pct < 75:
            st.warning(
                "⚠️ **Partial readiness** — Key domains require attention "
                "before delivery can proceed safely."
            )
        else:
            st.success("✅ **Operationally ready** — No critical readiness blockers identified.")

    st.divider()

    with st.expander("🧠 Agent Reasoning", expanded=False):
        st.caption(result.reasoning)

    st.markdown(full_text)
    _render_elapsed(result)


# ═══════════════════════════════════════════════════════════
#  TAB 5 — EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════

with tabs[5]:
    st.markdown(
        '<div class="section-header">Executive Summary</div>',
        unsafe_allow_html=True,
    )

    if st.session_state["is_running"]:
        with st.spinner(
            "📋 Executive Summary Agent synthesising all outputs..."
        ):
            st.stop()

    if not report:
        st.info("Run an analysis from the **📥 Input** tab to see results here.")
        st.stop()

    result = report.executive_summary

    if not result.succeeded:
        _render_agent_error(result)
        st.stop()

    data         = result.output if isinstance(result.output, dict) else {}
    dec_label    = data.get("decision_label", "")
    full_summary = data.get("full_summary", str(result.output))

    # Pipeline performance summary (board context)
    if dec_label:
        st.markdown(
            f"**Top-line decision:** {_go_badge(dec_label)}",
            unsafe_allow_html=True,
        )

    # Timestamp and pipeline stats
    if st.session_state["run_timestamp"]:
        ts = st.session_state["run_timestamp"].strftime("%d %b %Y at %H:%M")
        col_ts, col_tp = st.columns([3, 2])
        col_ts.caption(f"📅 Analysis run: {ts}")
        col_tp.caption(f"⏱ Total pipeline: {report.total_elapsed_ms / 1000:.1f}s")

    st.divider()

    # Full executive summary output
    with st.expander("🧠 Agent Reasoning", expanded=False):
        st.caption(result.reasoning)

    st.markdown(full_summary)

    st.divider()

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">Export</div>',
        unsafe_allow_html=True,
    )
    col_dl, col_cp = st.columns([2, 3])

    # Build full markdown export
    full_export_parts = ["# PMO Intelligence Report\n"]
    full_export_parts.append(
        f"**Generated:** {st.session_state['run_timestamp'].strftime('%d %b %Y %H:%M') if st.session_state['run_timestamp'] else 'N/A'}\n"
    )
    full_export_parts.append("---\n")

    section_map = [
        ("📊 Project Analysis",      report.project_summary,  "full_brief"),
        ("🔄 Methodology",           report.methodology,      "full_analysis"),
        ("✅ Go/No-Go Assessment",   report.go_no_go,         "full_analysis"),
        ("🏗 Site Readiness",        report.site_readiness,   "full_analysis"),
        ("📋 Executive Summary",     report.executive_summary,"full_summary"),
    ]

    for heading, ag_result, key in section_map:
        full_export_parts.append(f"## {heading}\n")
        if ag_result.succeeded and isinstance(ag_result.output, dict):
            content = ag_result.output.get(key, "")
        elif ag_result.succeeded:
            content = str(ag_result.output)
        else:
            content = f"*Error: {ag_result.error}*"
        full_export_parts.append(content + "\n\n---\n")

    export_md = "\n".join(full_export_parts)

    with col_dl:
        st.download_button(
            label="⬇️ Download Full Report (.md)",
            data=export_md,
            file_name=f"pmo_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_cp:
        st.text_area(
            "Copy report text:",
            value=full_summary,
            height=150,
            label_visibility="visible",
        )

    _render_elapsed(result)
