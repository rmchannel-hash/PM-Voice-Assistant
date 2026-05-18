"""
Multi-Agent PMO Command Center
==============================
Project-agnostic. Works on any project — paste any SOW, Bid Doc, or Status Report.
Multiple projects supported — each fully isolated with its own RAG stores.
Human-in-the-loop gating at every pipeline stage.

Setup:
  .streamlit/secrets.toml  →  ANTHROPIC_API_KEY = "your-key"
"""

import os
import streamlit as st
import anthropic
import json
import re
import threading
import time
from datetime import datetime

st.set_page_config(page_title="PMO Command Center", page_icon="⚓", layout="wide")

# ════════════════════════════════════════════════════════════════
#  API KEY RESOLUTION
# ════════════════════════════════════════════════════════════════

def get_api_key():
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
    return st.session_state.get("_api_key_input", "")

# ════════════════════════════════════════════════════════════════
#  PROJECT-AGNOSTIC PROMPTS
# ════════════════════════════════════════════════════════════════

ORCHESTRATOR_PROMPT = """You are Captain Sinbad Sailor — a hyper-structured Programme Director specialising in EVM, risk governance, and multi-domain project delivery.

You are FULLY PROJECT-AGNOSTIC. You work on any project in any sector — infrastructure, IT, construction, consulting, manufacturing, services. Analyse whatever document is given on its own terms.

STEP 1 — IDENTIFY:
Extract: project name, client, vendor, contract value + currency, duration, current period/status, scope summary. Note any gaps but continue.

STEP 2 — INGEST:
Strip filler language. Identify hard contractual requirements, scope boundaries, milestones, financial and schedule baselines.

STEP 3 — DATA SEPARATION (MANDATORY):
Source RAG Store = original documents, READ-ONLY. Agent Output Store = agent outputs only. Never mix.

STEP 4 — DELEGATE CONCURRENTLY to three agents:
- PM & CONTROLS AGENT: all financial figures, EVM data, schedules, resources, milestone dates
- TECHNICAL & RISK GOVERNANCE AGENT: technical constraints, dependencies, infra/regulatory blockers, assumptions
- STAKEHOLDER COMMUNICATION ADVISOR: all named people, client contacts, correspondence references, sign-off authorities

STEP 5 — FLAG CONFLICTS: Note any structural conflicts between data elements (e.g. timeline vs resource availability).

STEP 6 — ESCALATE: SPI < 0.95, CPI < 0.95, or any risk >=20 on 5x5 P×I → Director Escalation with named owner.

REVISION: If REVISION REQUEST is included, address each point explicitly first.

NEVER return NULL_STATE for an unfamiliar project. Analyse what is given. NULL_STATE only if input is empty or unreadable.

OUTPUT:
## Project Identified
[Name | Client | Vendor | Contract Value + Currency | Duration | Current Period]

## Data Routing
[Exactly what goes to each agent from this document]

## Critical Path Assessment
[3-5 sentences based on this document]

## Director Escalations
[Named escalations or: NONE]

## Conflict Flags
[Detected conflicts or: NONE DETECTED]"""

PM_PROMPT = """You are the Lead Project Controller — EVM specialist (ANSI/EIA-748) and WBS methodology expert.

You are PROJECT-AGNOSTIC. Work on whatever project document and director directive are provided.

INSTRUCTIONS:
1. Extract project name, contract value (BAC), currency, timeline, period from the document.
2. Build Level 2 WBS from deliverables/workstreams/packages in the document. Use document's own terminology for package names.
3. EVM: If actuals exist — SPI=EV/PV | CPI=EV/AC | CV=EV-AC | SV=EV-PV | EAC=BAC/CPI | TCPI=(BAC-EV)/(BAC-AC). Flag breach if SPI<0.95 or CPI<0.95.
   If actuals missing — set ev/ac/pv to 0 and list gap. Never fabricate numbers.
4. Flag resource over-allocation or under-deployment if mentioned.
5. Address REVISION REQUEST points explicitly if present.

OUTPUT: Return ONLY valid JSON — no prose, no markdown fences, no backticks:
{
  "agent": "PM_CONTROLS",
  "project_name": "from document",
  "currency": "e.g. INR or USD or AUD",
  "period": "e.g. M7 or Q2 or Week 12",
  "report_timestamp": "ISO8601",
  "evm_summary": {
    "bac": 0.0, "pv": 0.0, "ev": 0.0, "ac": 0.0,
    "spi": 0.0, "cpi": 0.0, "sv": 0.0, "cv": 0.0,
    "eac": 0.0, "tcpi": 0.0,
    "recovery_feasible": true, "governance_breach": false
  },
  "wbs_packages": [
    {
      "id": "1.1", "name": "Package name from document",
      "budget": 0.0, "spent": 0.0, "pct_complete": 0,
      "status": "GREEN", "resource_flag": null
    }
  ],
  "data_gaps": [],
  "escalations": []
}"""

RISK_PROMPT = """You are the Technical PMO Lead and Risk Governance Agent — ISO 31000 standards. You are PROJECT-AGNOSTIC.

INSTRUCTIONS:
1. Extract all technical risks, dependencies, constraints, site issues, regulatory blockers, and assumptions from the document.
2. RAID register: for each item assign ONE named owner (individual from document — if unknown use UNASSIGNED), target closure date, P(1-5) x I(1-5) = exposure score, severity (>=20 CRITICAL, 10-19 HIGH, 5-9 MEDIUM, <5 LOW). Director escalation if score >=20.
3. RACI matrix from document roles — ONE Accountable per WBS package, no exceptions.
4. Address REVISION REQUEST points if present.

OUTPUT: Return ONLY valid JSON — no prose, no markdown fences:
{
  "agent": "TECHNICAL_RISK",
  "project_name": "from document",
  "period": "from document",
  "raid_items": [
    {
      "id": "R-001", "type": "RISK",
      "description": "specific risk from document",
      "probability": 3, "impact": 4, "exposure_score": 12,
      "severity": "HIGH",
      "owner": "name from document",
      "target_closure": "date or week",
      "status": "OPEN",
      "director_escalation": false
    }
  ],
  "raci_matrix": [
    {
      "wbs_id": "1.1", "wbs_name": "Package name",
      "roles": {"role_name": "A", "role_name_2": "R"}
    }
  ],
  "governance_gaps": [],
  "escalations": []
}"""

COGNITIVE_PROMPT = """You are the Stakeholder Communication Advisor — transparent engagement only. No manipulation. You are PROJECT-AGNOSTIC.

INSTRUCTIONS:
1. Extract all named stakeholders, client contacts, sign-off authorities from the document.
2. Engagement Score (0-100): based on recency/substance of contact references in the document. Flag OVERDUE if >7 days no contact.
3. For each stakeholder: stated concerns, inferable concerns, outstanding commitments.
4. Recommended engagement: transparent, professional advice only. No psychological scripts.
5. Identify what could delay acceptance milestones (UAT, sign-off, commissioning).
6. Address REVISION REQUEST if present. If no stakeholders named, return one entry noting the gap.

OUTPUT: Return ONLY valid JSON — no prose, no markdown fences:
{
  "agent": "STAKEHOLDER_ADVISOR",
  "project_name": "from document",
  "period": "from document",
  "stakeholders": [
    {
      "name": "Full name", "role": "role",
      "authority": "what they sign off",
      "engagement_score": 50, "status": "AMBER",
      "last_contact_days": 0, "overdue_flag": false,
      "stated_concerns": [],
      "inferable_concerns": [],
      "outstanding_commitments": [],
      "recommended_engagement": "specific transparent advice"
    }
  ],
  "uat_handshake_gaps": [],
  "immediate_attention_required": [],
  "data_gaps": []
}"""

REPORTING_PROMPT = """You are the Executive Communications Specialist — project-agnostic. Convert structured agent data into boardroom-ready briefs.

INSTRUCTIONS:
1. Use ONLY the agent outputs provided. Do not invent data. Missing = explicit gap in brief.
2. Address REVISION REQUEST points if present.
3. Produce:

A. DAILY PROGRESS BRIEF
Project: [name] | Period: [period] | Date: [today]
- Completions this period
- Critical blockers (top 3)
- Next critical path actions
- RAG status per workstream

B. WEEKLY STEERCO DECK
- Executive summary (3-4 sentences)
- Overall RAG status table
- EVM table: BAC | PV | EV | AC | SPI | CPI | EAC | TCPI | Currency
- Top 3 RAID items with owner and target
- Stakeholder engagement table
- Priority actions: action | owner | due | priority

MANDATORY FINAL LINE (exactly):
STATUS: PENDING PM DIRECTOR APPROVAL — DO NOT DISTRIBUTE

OUTPUT FORMAT: Structured markdown with tables."""

ARBITRATION_PROMPT = """You are Captain Sinbad Sailor. Arbitrate conflicts between three agent outputs. Project-agnostic.

CHECK:
1. PM says recovery feasible but Risk has unresolved CRITICAL blocker → conflict
2. Cost overrun but client unaware → communication gap
3. Risk owner vs RACI accountability mismatch → governance conflict
4. Escalation in one agent not reflected in others

For each conflict: state the signals, decide precedence, issue corrective directive.
Address REVISION REQUEST if present.
If no conflicts: NO CONFLICTS DETECTED

Concise. Authoritative."""

# ════════════════════════════════════════════════════════════════
#  DATA LAYER
# ════════════════════════════════════════════════════════════════

class DualRAGStore:
    def __init__(self, project_name):
        self.project_name = project_name
        self.source_store = {}
        self.agent_output_store = {}
        self.audit_log = []

    def ingest_source(self, content, label="document"):
        doc_id = f"SRC_{datetime.utcnow().strftime('%H%M%S')}"
        self.source_store[doc_id] = {
            "label": label, "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._log(f"SOURCE: {doc_id} ({label})")
        return doc_id

    def write_agent_output(self, agent_id, output):
        self.agent_output_store[agent_id] = {
            "data": output, "timestamp": datetime.utcnow().isoformat()
        }
        self._log(f"AGENT: {agent_id}")

    def read_agent_output(self, agent_id):
        return self.agent_output_store.get(agent_id, {}).get("data")

    def get_all_source_text(self):
        return "\n\n---\n\n".join(
            f"[{v['label']}]\n{v['content']}"
            for v in self.source_store.values()
        )

    def _log(self, msg):
        self.audit_log.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")


class ProjectWorkspace:
    def __init__(self, name, created):
        self.name = name
        self.created = created
        self.rag = DualRAGStore(name)
        self.stage = 0
        self.orchestrator_out = None
        self.pm_out = None
        self.risk_out = None
        self.cog_out = None
        self.arbitration_out = None
        self.report_out = None
        self.raw_pm = self.raw_risk = self.raw_cog = ""
        self.gates = {1: "pending", 2: "pending", 3: "pending", 4: "pending"}
        self.notes = {1: "", 2: "", 3: "", 4: ""}
        self.revisions = {1: 0, 2: 0, 3: 0, 4: 0}
        self.detected_name = ""
        self.detected_client = ""

# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def safe_parse_json(raw, fallback):
    if not raw or any(raw.startswith(x) for x in ["ERROR", "QUOTA"]):
        return {**fallback, "data_gaps": [raw or "Empty agent response"]}
    clean = raw.strip()
    if "```" in clean:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
        clean = m.group(1).strip() if m else clean.replace("```", "").strip()
    s, e = clean.find("{"), clean.rfind("}")
    if s != -1 and e > s:
        clean = clean[s:e+1]
    try:
        return json.loads(clean)
    except Exception:
        return {**fallback, "data_gaps": [f"JSON parse failed. Raw preview: {raw[:150]}"]}

def safe_num(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d

def safe_pct(v):
    try:
        return max(0, min(100, int(float(v or 0))))
    except (TypeError, ValueError):
        return 0

def pm_fallback(name=""):
    return {
        "agent": "PM_CONTROLS", "project_name": name,
        "currency": "", "period": "M1",
        "report_timestamp": datetime.utcnow().isoformat(),
        "evm_summary": {
            "bac": 0.0, "pv": 0.0, "ev": 0.0, "ac": 0.0,
            "spi": 0.0, "cpi": 0.0, "sv": 0.0, "cv": 0.0,
            "eac": 0.0, "tcpi": 0.0,
            "recovery_feasible": True, "governance_breach": False
        },
        "wbs_packages": [],
        "data_gaps": ["Could not parse agent output — check Debug tab."],
        "escalations": []
    }

def risk_fallback(name=""):
    return {
        "agent": "TECHNICAL_RISK", "project_name": name, "period": "M1",
        "raid_items": [], "raci_matrix": [],
        "governance_gaps": ["Could not parse agent output — check Debug tab."],
        "escalations": []
    }

def cog_fallback(name=""):
    return {
        "agent": "STAKEHOLDER_ADVISOR", "project_name": name, "period": "M1",
        "stakeholders": [], "uat_handshake_gaps": [],
        "immediate_attention_required": [],
        "data_gaps": ["Could not parse agent output — check Debug tab."]
    }

# ════════════════════════════════════════════════════════════════
#  ANTHROPIC CALLER  (replaces Gemini)
# ════════════════════════════════════════════════════════════════

def call_claude(system_prompt, user_msg):
    """Call Anthropic Claude API with retry and error handling."""
    key = get_api_key()
    if not key:
        return "ERROR: No API key. Add ANTHROPIC_API_KEY to .streamlit/secrets.toml"

    client = anthropic.Anthropic(api_key=key)
    backoff = [5, 15, 30, 60]

    for attempt in range(4):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < 3:
                wait = backoff[attempt]
                st.toast(f"Rate limit — waiting {wait}s (retry {attempt+1}/3)", icon="⏳")
                time.sleep(wait)
                continue
            return "ERROR: Rate limit exceeded after retries."
        except anthropic.AuthenticationError:
            return "ERROR: Invalid API key. Check ANTHROPIC_API_KEY in secrets.toml"
        except Exception as e:
            return f"ERROR: {str(e)}"

    return "ERROR: Max retries exceeded."


def call_parallel(payloads):
    """Run multiple Claude calls concurrently via threads."""
    results = [None] * len(payloads)

    def worker(i, sp, um):
        results[i] = call_claude(sp, um)

    threads = [
        threading.Thread(target=worker, args=(i, sp, um))
        for i, (sp, um) in enumerate(payloads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results

# ════════════════════════════════════════════════════════════════
#  PIPELINE RUNNERS
# ════════════════════════════════════════════════════════════════

def run_orchestrator(ws, revision=""):
    src = ws.rag.get_all_source_text()
    msg = f"REVISION REQUEST:\n{revision}\n\n---\nSOURCE:\n{src}" if revision else src
    with st.spinner("🎖 Captain Sinbad — analysing document..."):
        ws.orchestrator_out = call_claude(ORCHESTRATOR_PROMPT, msg)
    ws.gates[1] = "pending"
    ws.stage = 1

def run_agents(ws, revision=""):
    src = ws.rag.get_all_source_text()
    d = ws.orchestrator_out or ""
    def pay(label):
        base = f"DIRECTOR DIRECTIVE:\n{d}\n\nROUTE: {label}\n\nSOURCE:\n{src}"
        return f"REVISION REQUEST:\n{revision}\n\n---\n{base}" if revision else base
    with st.spinner("📊 🛡 🧠  Running 3 agents in parallel..."):
        r = call_parallel([
            (PM_PROMPT,        pay("PM_CONTROLS")),
            (RISK_PROMPT,      pay("TECHNICAL_RISK")),
            (COGNITIVE_PROMPT, pay("STAKEHOLDER")),
        ])
    ws.raw_pm, ws.raw_risk, ws.raw_cog = r
    pname = ws.detected_name or ws.name
    ws.pm_out   = safe_parse_json(r[0], pm_fallback(pname))
    ws.risk_out = safe_parse_json(r[1], risk_fallback(pname))
    ws.cog_out  = safe_parse_json(r[2], cog_fallback(pname))
    ws.rag.write_agent_output("pm",   ws.pm_out)
    ws.rag.write_agent_output("risk", ws.risk_out)
    ws.rag.write_agent_output("cog",  ws.cog_out)
    if ws.pm_out.get("project_name"):
        ws.detected_name = ws.pm_out["project_name"]
    ws.gates[2] = "pending"
    ws.stage = 2

def run_arbitration(ws, revision=""):
    msg = (f"PM:\n{json.dumps(ws.pm_out, indent=2)}\n\n"
           f"RISK:\n{json.dumps(ws.risk_out, indent=2)}\n\n"
           f"STAKEHOLDER:\n{json.dumps(ws.cog_out, indent=2)}")
    if revision:
        msg = f"REVISION REQUEST:\n{revision}\n\n---\n{msg}"
    with st.spinner("⚖️ Conflict arbitration..."):
        ws.arbitration_out = call_claude(ARBITRATION_PROMPT, msg)
    ws.gates[3] = "pending"
    ws.stage = 3

def run_reporting(ws, revision=""):
    msg = (f"ARBITRATION:\n{ws.arbitration_out}\n\n"
           f"PM DATA:\n{json.dumps(ws.pm_out, indent=2)}\n\n"
           f"RISK DATA:\n{json.dumps(ws.risk_out, indent=2)}\n\n"
           f"STAKEHOLDER DATA:\n{json.dumps(ws.cog_out, indent=2)}")
    if revision:
        msg = f"REVISION REQUEST:\n{revision}\n\n---\n{msg}"
    with st.spinner("📋 Building SteerCo brief..."):
        ws.report_out = call_claude(REPORTING_PROMPT, msg)
    ws.gates[4] = "pending"
    ws.stage = 4

# ════════════════════════════════════════════════════════════════
#  GATE COMPONENT
# ════════════════════════════════════════════════════════════════

def render_gate(ws, gate_n, approve_label, sendback_label, on_approve, on_sendback):
    state = ws.gates[gate_n]
    if state == "approved":
        st.success("✅ Gate approved — pipeline advancing")
        return
    if state == "sent_back":
        st.warning(f"↩️ Revision {ws.revisions[gate_n]} sent — agent reprocessing...")
        return
    st.info("🔎 **Your turn — review critically before advancing. You are the provocateur.**")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button(f"✅ {approve_label}", type="primary",
                     key=f"app_{gate_n}_{ws.name}"):
            ws.gates[gate_n] = "approved"
            on_approve()
            st.rerun()
    with c2:
        notes = st.text_area("📝 Revision notes — be specific:",
                             key=f"nt_{gate_n}_{ws.name}", height=70,
                             placeholder="What exactly must change? Name the field, the error, the missing item.")
        if st.button(f"↩️ {sendback_label}", key=f"sb_{gate_n}_{ws.name}"):
            if notes.strip():
                ws.notes[gate_n] = notes.strip()
                ws.revisions[gate_n] += 1
                ws.gates[gate_n] = "sent_back"
                on_sendback()
                st.rerun()
            else:
                st.error("Add specific notes before sending back.")

# ════════════════════════════════════════════════════════════════
#  SESSION STATE INIT
# ════════════════════════════════════════════════════════════════

if "registry" not in st.session_state:
    st.session_state.registry = {}
if "active_id" not in st.session_state:
    st.session_state.active_id = None

def active_ws():
    return st.session_state.registry.get(st.session_state.active_id)

# ════════════════════════════════════════════════════════════════
#  SIDEBAR — PROJECT REGISTRY
# ════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚓ PMO Command Center")
    st.caption("Multi-project · Project-agnostic · Any sector")
    st.divider()

    # API Key input (if not set via env/secrets)
    api_key = get_api_key()
    if not api_key:
        st.markdown("### 🔑 API Key")
        st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            label_visibility="collapsed",
            key="_api_key_input",
            help="Or add ANTHROPIC_API_KEY to .streamlit/secrets.toml"
        )
        st.warning("⚠️ API key required to run analysis.")
        st.divider()
    else:
        st.success("🔑 API key loaded", icon="✅")
        st.divider()

    st.markdown("### ➕ New Project")
    new_name = st.text_input("Project name:",
                              placeholder="e.g. Amcor DC Hosting, Bridge Phase 2",
                              key="new_name", label_visibility="collapsed")
    if st.button("Create Project", use_container_width=True, type="primary"):
        if new_name.strip():
            pid = f"proj_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
            st.session_state.registry[pid] = ProjectWorkspace(
                name=new_name.strip(),
                created=datetime.now().strftime("%d %b %Y %H:%M")
            )
            st.session_state.active_id = pid
            st.rerun()
        else:
            st.error("Enter a project name.")

    st.divider()
    reg = st.session_state.registry
    if reg:
        st.markdown("### 📁 Projects")
        for pid, ws in reg.items():
            is_active = pid == st.session_state.active_id
            icons = ["📄","🎖","⚙️","⚖️","📋","✅"]
            s_icon = icons[min(ws.stage, 5)]
            if st.button(
                f"{'▶ ' if is_active else ''}{ws.name}\n{s_icon} Stage {ws.stage}",
                key=f"sel_{pid}", use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                st.session_state.active_id = pid
                st.rerun()
            if is_active:
                if st.button("🗑 Delete", key=f"del_{pid}", use_container_width=True):
                    del st.session_state.registry[pid]
                    remaining = list(st.session_state.registry.keys())
                    st.session_state.active_id = remaining[0] if remaining else None
                    st.rerun()
    else:
        st.info("No projects yet.\nCreate one above ☝")

    st.divider()
    ws_sidebar = active_ws()
    if ws_sidebar and ws_sidebar.rag.audit_log:
        st.markdown("### 📋 Audit Log")
        for entry in ws_sidebar.rag.audit_log[-8:]:
            st.caption(entry)

# ════════════════════════════════════════════════════════════════
#  WELCOME SCREEN (no project selected)
# ════════════════════════════════════════════════════════════════

ws = active_ws()
if ws is None:
    st.title("⚓ Multi-Agent PMO Command Center")
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    col1.markdown("""
**🎖 Captain Sinbad**
Orchestrator — parses any project document, routes data to specialist agents, arbitrates conflicts
    """)
    col2.markdown("""
**⚙️ Three Parallel Agents**
PM Controls (EVM + WBS) · Risk & Tech (RAID + RACI) · Stakeholder Advisor — run concurrently
    """)
    col3.markdown("""
**🔎 Human Gating**
You approve or send back at every stage. You are the provocateur — the system does the work, you validate
    """)
    st.info("👈 **Create a project in the sidebar to begin.** Works on any SOW, Bid Doc, Status Report or Voice Note.")
    st.stop()

# ════════════════════════════════════════════════════════════════
#  ACTIVE PROJECT — HEADER
# ════════════════════════════════════════════════════════════════

st.title(f"⚓ {ws.name}")
info_parts = [f"Created: {ws.created}"]
if ws.detected_name and ws.detected_name != ws.name:
    info_parts.insert(0, f"Detected: {ws.detected_name}")
if ws.detected_client:
    info_parts.insert(1, f"Client: {ws.detected_client}")
st.caption("  |  ".join(info_parts))

# Stage progress bar
stage_labels = [("📄","Input"),("🎖","Orchestrate"),("⚙️","Agents"),
                ("⚖️","Arbitrate"),("📋","Report"),("✅","Released")]
cols = st.columns(6)
for i, (col, (icon, label)) in enumerate(zip(cols, stage_labels)):
    if i == ws.stage:
        col.markdown(f"<div style='text-align:center;padding:5px;background:#378ADD18;border:1.5px solid #378ADD;border-radius:8px;font-size:12px;font-weight:500'>{icon}<br>{label}</div>", unsafe_allow_html=True)
    elif i < ws.stage:
        col.markdown(f"<div style='text-align:center;padding:5px;background:#1D9E7518;border:1px solid #1D9E75;border-radius:8px;font-size:12px;color:#1D9E75'>✓<br>{label}</div>", unsafe_allow_html=True)
    else:
        col.markdown(f"<div style='text-align:center;padding:5px;border:1px solid #ccc;border-radius:8px;font-size:12px;color:#aaa'>{icon}<br>{label}</div>", unsafe_allow_html=True)

st.divider()

# ════════════════════════════════════════════════════════════════
#  STAGE 0 — INPUT
# ════════════════════════════════════════════════════════════════

with st.expander("📄 Stage 0 — Input Document", expanded=(ws.stage == 0)):
    existing = ws.rag.source_store
    if existing:
        st.success(f"✅ {len(existing)} document(s) loaded for this project.")
        for doc in existing.values():
            st.caption(f"📄 {doc['label']} — {doc['timestamp'][:19]}")
        st.markdown("**Add another document** (optional — appends to project context):")

    raw_input = st.text_area(
        "Paste your document:",
        height=200,
        key=f"inp_{ws.name}",
        placeholder=(
            "Paste any project document — SOW, bid doc, status report, MoM, voice note transcript...\n\n"
            "Works on any project in any sector. The agents will extract:\n"
            "• Financial baselines + EVM metrics\n"
            "• RAID register + RACI matrix\n"
            "• Stakeholder profiles + engagement plan\n"
            "• SteerCo-ready brief\n\n"
            "No hardcoded project — fully adapts to whatever you paste."
        )
    )
    doc_label = st.text_input("Document label:",
                              value="SOW", key=f"lbl_{ws.name}",
                              placeholder="SOW, Status Report, MoM, Voice Note, Bid Doc")

    if st.button("🚀 Run Pipeline", type="primary", key=f"run_{ws.name}"):
        if not get_api_key():
            st.error("⚠️ No API key found. Add ANTHROPIC_API_KEY to .streamlit/secrets.toml")
        elif raw_input.strip():
            ws.rag.ingest_source(raw_input.strip(), doc_label or "document")
            ws.stage = 0
            ws.orchestrator_out = ws.pm_out = ws.risk_out = None
            ws.cog_out = ws.arbitration_out = ws.report_out = None
            ws.raw_pm = ws.raw_risk = ws.raw_cog = ""
            ws.gates = {1:"pending", 2:"pending", 3:"pending", 4:"pending"}
            ws.notes = {1:"", 2:"", 3:"", 4:""}
            ws.revisions = {1:0, 2:0, 3:0, 4:0}
            run_orchestrator(ws)
            st.rerun()
        else:
            st.error("Paste a document before running.")

# ════════════════════════════════════════════════════════════════
#  STAGE 1 — ORCHESTRATOR + GATE 1
# ════════════════════════════════════════════════════════════════

if ws.stage >= 1 and ws.orchestrator_out:
    icon = "✅" if ws.gates[1] == "approved" else "🔎"
    with st.expander(f"🎖 Stage 1 — Orchestrator Directive {icon}",
                     expanded=(ws.stage == 1)):
        if ws.revisions[1]:
            st.caption(f"Revision {ws.revisions[1]}: _{ws.notes[1]}_")
        st.markdown(ws.orchestrator_out)
        st.divider()
        render_gate(ws, 1,
            "Approve routing — dispatch agents",
            "Send back to Orchestrator",
            on_approve=lambda: run_agents(ws),
            on_sendback=lambda: run_orchestrator(ws, ws.notes[1])
        )

# ════════════════════════════════════════════════════════════════
#  STAGE 2 — AGENTS + GATE 2
# ════════════════════════════════════════════════════════════════

if ws.stage >= 2 and ws.pm_out:
    icon = "✅" if ws.gates[2] == "approved" else "🔎"
    with st.expander(f"⚙️ Stage 2 — Agent Outputs {icon}",
                     expanded=(ws.stage == 2)):
        if ws.revisions[2]:
            st.caption(f"Revision {ws.revisions[2]}: _{ws.notes[2]}_")

        t_pm, t_risk, t_cog, t_dbg = st.tabs(
            ["📊 PM & Controls", "🛡 Risk & Tech", "🧠 Stakeholder", "🔍 Debug"])

        with t_pm:
            pm = ws.pm_out
            evm = pm.get("evm_summary", {})
            cur = pm.get("currency", "")
            if pm.get("project_name"):
                ws.detected_name = pm["project_name"]
                st.info(f"📌 **{pm['project_name']}** | {cur} | Period: {pm.get('period','?')}")

            spi = safe_num(evm.get("spi"))
            cpi = safe_num(evm.get("cpi"))

            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("BAC", f"{cur} {safe_num(evm.get('bac')):,.1f}")
            c2.metric("SPI", f"{spi:.3f}",
                      delta="⚠ BREACH" if 0 < spi < 0.95 else ("N/A" if spi==0 else "OK"),
                      delta_color="inverse" if 0 < spi < 0.95 else "off")
            c3.metric("CPI", f"{cpi:.3f}",
                      delta="⚠ BREACH" if 0 < cpi < 0.95 else ("N/A" if cpi==0 else "OK"),
                      delta_color="inverse" if 0 < cpi < 0.95 else "off")
            c4.metric("EAC", f"{cur} {safe_num(evm.get('eac')):,.1f}")
            c5.metric("TCPI", f"{safe_num(evm.get('tcpi')):.3f}")

            if evm.get("governance_breach"):
                st.error("🚨 Governance breach — SPI or CPI below 0.95")

            pkgs = pm.get("wbs_packages", [])
            if pkgs:
                st.subheader("WBS Packages")
                for p in pkgs:
                    pct = safe_pct(p.get("pct_complete"))
                    status = p.get("status","AMBER")
                    s_icon = {"GREEN":"🟢","AMBER":"🟡","RED":"🔴"}.get(status,"🟡")
                    st.markdown(f"**{p.get('id','?')} — {p.get('name','?')}** {s_icon}")
                    ca, cb, cc = st.columns([4,1,1])
                    ca.progress(pct/100)
                    cb.write(f"**{pct}%**")
                    cc.write(f"{cur} {safe_num(p.get('spent')):,.1f} / {safe_num(p.get('budget')):,.1f}")
                    if p.get("resource_flag"):
                        st.caption(f"⚠ {p['resource_flag']}")
            else:
                st.info("No WBS packages found — check document or Debug tab.")

            for gap in pm.get("data_gaps", []):
                if gap: st.warning(f"Gap: {gap}")
            for esc in pm.get("escalations", []):
                if esc: st.error(f"🚨 {esc}")

        with t_risk:
            risk = ws.risk_out
            raid = risk.get("raid_items", [])
            sev_icon = {"CRITICAL":"🔴","HIGH":"🟡","MEDIUM":"🔵","LOW":"🟢"}

            if raid:
                st.subheader(f"RAID Register — {len(raid)} items")
                for item in raid:
                    sev = item.get("severity","MEDIUM")
                    esc_flag = " 🚨 **Director escalation**" if item.get("director_escalation") else ""
                    st.markdown(
                        f"{sev_icon.get(sev,'•')} **{item.get('id','?')} "
                        f"[{item.get('type','?')}]** — Score {item.get('exposure_score','?')} "
                        f"({item.get('probability','?')}×{item.get('impact','?')}) — *{sev}*"
                    )
                    st.markdown(f"> {item.get('description','No description')}")
                    st.caption(
                        f"Owner: **{item.get('owner','?')}** | "
                        f"Target: {item.get('target_closure','?')} | "
                        f"Status: {item.get('status','?')}{esc_flag}"
                    )
                    st.divider()
            else:
                st.info("No RAID items found — check document or Debug tab.")

            for gap in risk.get("governance_gaps", []):
                if gap: st.warning(f"⚠ Governance gap: {gap}")

            raci = risk.get("raci_matrix", [])
            if raci:
                with st.expander("RACI Matrix"):
                    for row in raci:
                        roles = row.get("roles", {})
                        st.markdown(f"**{row.get('wbs_id','?')} — {row.get('wbs_name','?')}**")
                        st.markdown(" | ".join(f"{k}: **{v}**" for k,v in roles.items()))
                    st.caption("A=Accountable · R=Responsible · C=Consulted · I=Informed")

        with t_cog:
            cog = ws.cog_out
            stks = cog.get("stakeholders", [])
            if stks:
                for s in stks:
                    score = safe_pct(s.get("engagement_score", 50))
                    status = s.get("status","AMBER")
                    s_icon = {"GREEN":"🟢","AMBER":"🟡","RED":"🔴"}.get(status,"🟡")
                    st.markdown(f"{s_icon} **{s.get('name','?')}** — {s.get('role','?')}")
                    ca, cb = st.columns([3,1])
                    ca.progress(score/100, text=f"Engagement {score}/100")
                    days = safe_num(s.get("last_contact_days",0))
                    if s.get("overdue_flag"):
                        cb.error(f"⚠ OVERDUE\n{int(days)}d ago")
                    else:
                        cb.success(f"Active\n{int(days)}d ago")
                    with st.expander(f"Profile — {s.get('name','?')}"):
                        st.caption(f"Authority: {s.get('authority','?')}")
                        if s.get("stated_concerns"):
                            st.markdown("**Concerns:** " + " · ".join(s["stated_concerns"]))
                        if s.get("outstanding_commitments"):
                            st.markdown("**Outstanding:** " + " · ".join(s["outstanding_commitments"]))
                        if s.get("recommended_engagement"):
                            st.info(s["recommended_engagement"])
                    st.divider()
            else:
                st.info("No stakeholders found — check document or Debug tab.")

            for item in cog.get("immediate_attention_required", []):
                if item: st.error(f"🚨 Immediate: {item}")
            for gap in cog.get("data_gaps", []):
                if gap: st.warning(f"Gap: {gap}")

        with t_dbg:
            st.caption("Raw LLM responses — use to diagnose parse failures")
            st.text_area("PM Raw", ws.raw_pm, height=120, key="dbg_pm")
            st.text_area("Risk Raw", ws.raw_risk, height=120, key="dbg_risk")
            st.text_area("Cognitive Raw", ws.raw_cog, height=120, key="dbg_cog")

        st.divider()
        render_gate(ws, 2,
            "Approve all outputs — proceed to arbitration",
            "Send agents back for revision",
            on_approve=lambda: run_arbitration(ws),
            on_sendback=lambda: run_agents(ws, ws.notes[2])
        )

# ════════════════════════════════════════════════════════════════
#  STAGE 3 — ARBITRATION + GATE 3
# ════════════════════════════════════════════════════════════════

if ws.stage >= 3 and ws.arbitration_out:
    icon = "✅" if ws.gates[3] == "approved" else "🔎"
    with st.expander(f"⚖️ Stage 3 — Conflict Arbitration {icon}",
                     expanded=(ws.stage == 3)):
        if ws.revisions[3]:
            st.caption(f"Revision {ws.revisions[3]}: _{ws.notes[3]}_")
        arb = ws.arbitration_out
        if "NO CONFLICTS DETECTED" in arb.upper():
            st.success("✅ No conflicts — all agent outputs are consistent.")
        else:
            st.warning("⚖️ Conflicts found and arbitrated:")
        st.markdown(arb)
        st.divider()
        render_gate(ws, 3,
            "Approve arbitration — generate SteerCo brief",
            "Re-arbitrate with additional notes",
            on_approve=lambda: run_reporting(ws),
            on_sendback=lambda: run_arbitration(ws, ws.notes[3])
        )

# ════════════════════════════════════════════════════════════════
#  STAGE 4 — REPORTING + GATE 4
# ════════════════════════════════════════════════════════════════

if ws.stage >= 4 and ws.report_out:
    gate_txt = "✅ APPROVED" if ws.gates[4] == "approved" else "🔒 PENDING APPROVAL"
    with st.expander(f"📋 Stage 4 — SteerCo Brief — {gate_txt}",
                     expanded=(ws.stage >= 4)):
        if ws.revisions[4]:
            st.caption(f"Revision {ws.revisions[4]}: _{ws.notes[4]}_")
        if ws.gates[4] != "approved":
            st.error("🔒 PENDING PM DIRECTOR APPROVAL — DO NOT DISTRIBUTE\n\n"
                     "You are the final checkpoint. Review every section before approving.")
        st.markdown(ws.report_out)
        st.divider()
        if ws.gates[4] == "approved":
            ws.stage = 5
            st.success("🎉 Approved and cleared for client distribution.")
        else:
            render_gate(ws, 4,
                "FINAL APPROVAL — I have reviewed and cleared for distribution",
                "Send back to Reporting Engine",
                on_approve=lambda: setattr(ws, "stage", 5),
                on_sendback=lambda: run_reporting(ws, ws.notes[4])
            )

# ════════════════════════════════════════════════════════════════
#  STAGE 5 — COMPLETE
# ════════════════════════════════════════════════════════════════

if ws.stage == 5:
    st.success(f"🎉 **{ws.name} — Complete. SteerCo brief approved for distribution.**")
    if st.button("🔄 Run again with updated document", key="rerun_btn"):
        ws.stage = 0
        ws.gates = {1:"pending",2:"pending",3:"pending",4:"pending"}
        ws.orchestrator_out=ws.pm_out=ws.risk_out=None
        ws.cog_out=ws.arbitration_out=ws.report_out=None
        st.rerun()
