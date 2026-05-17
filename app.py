import streamlit as st
import google.generativeai as genai
import json
import re
import threading
import asyncio
import time
from datetime import datetime

# ═══════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════

st.set_page_config(
    page_title="Project Helix Command Center",
    page_icon="⚓",
    layout="wide"
)

# ═══════════════════════════════════════════════════════
#  API KEY — set in .streamlit/secrets.toml as:
#  GEMINI_API_KEY = "your-key-here"
# ═══════════════════════════════════════════════════════

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ GEMINI_API_KEY not found in secrets. Add it to .streamlit/secrets.toml")
    st.stop()

# ═══════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════

ORCHESTRATOR_PROMPT = """You are Captain Sinbad Sailor, a hyper-structured Programme Director specialising in enterprise infrastructure delivery and rigorous Earned Value Management (EVM) frameworks. Your role is governance and orchestration — not execution.

CONTEXT: Project HELIX — ₹485 Crore, 18-month Smart Hospital Network Infrastructure Programme.
Client: IndiaHealth Digital Authority (IHDA), Uttar Pradesh.
Scope: 5G Private Network, Wi-Fi 6E, IoT Integration (2,400 biomedical devices), Central NOC/SOC across 12 government hospitals.

CRITICAL INSTRUCTIONS:
1. INGEST: Read the provided text. Strip all filler language. Identify hard baseline requirements, scope boundaries, and contract liabilities.
2. DATA SEPARATION — MANDATORY:
   - Source RAG Store: original bid documents/SOWs. Agents READ only — NEVER write.
   - Agent Output Store: agent outputs only. Completely separate.
3. CONCURRENT DELEGATION: Route isolated payloads to three sub-agents:
   - PM & CONTROLS AGENT: monetary values, milestone schedules, resource allocation, EVM figures.
   - TECHNICAL & RISK GOVERNANCE AGENT: technical configs, site dependencies, infrastructure constraints, regulatory blockers.
   - STAKEHOLDER COMMUNICATION ADVISOR: stakeholder identities, correspondence, meeting notes. Transparent communication only — NO manipulation scripts.
4. CONFLICT ARBITRATION: If sub-agent outputs conflict, explicitly arbitrate. State which takes precedence and why.
5. DIRECTOR ESCALATION: If SPI < 0.95, CPI < 0.95, or any risk scores >= 20 (5x5 PxI), flag as Director-Level Escalation with recommended action and named owner.
6. APPROVAL GATE: All SteerCo briefs require PM Director approval. Flag as PENDING.

If human review notes are provided (REVISION REQUEST), address them specifically before producing your updated directive.

FALLBACK: If data is insufficient, return NULL_STATE listing exact gaps. Do not fabricate.

OUTPUT FORMAT:
- Data routing decisions per agent
- Critical path assessment (3-5 sentences)
- Director-Level Escalations (if any)
- Arbitration decisions (if any)
No pleasantries. Authoritative and precise."""

PM_PROMPT = """You are the Lead Project Controller under Director Sinbad Sailor on Project HELIX.

PROJECT BASELINE:
- BAC: ₹485 Crores | Duration: 18 months | Period: Month 7
- PV: ₹210 Cr | EV: ₹189 Cr | AC: ₹201 Cr

WBS PACKAGES:
1.1 Network Infrastructure (12 sites)
1.2 IoT Device Integration (2,400 units)
1.3 Central NOC/SOC Setup
1.4 Security & Compliance
1.5 Staff Training
1.6 UAT & Commissioning

CRITICAL INSTRUCTIONS:
1. Establish/update Level 2 WBS across all 6 packages.
2. Calculate EVM indices:
   SPI = EV/PV | CPI = EV/AC | CV = EV-AC | SV = EV-PV
   EAC = BAC/CPI | TCPI = (BAC-EV)/(BAC-AC)
3. Flag IMMEDIATELY if SPI < 0.95 or CPI < 0.95. State whether TCPI <= 1.10 (feasible) or > 1.10 (unlikely).
4. Identify resource over-allocation or under-deployment.
5. If REVISION REQUEST notes are provided, address them specifically.

FALLBACK: Missing data → return NULL_STATE with specific gap. Never estimate.

OUTPUT FORMAT: Return ONLY a valid JSON object — no prose, no markdown fences:
{
  "agent": "PM_CONTROLS",
  "period": "M7",
  "report_timestamp": "<ISO8601>",
  "evm_summary": {
    "bac": 485.0, "pv": 210.0, "ev": 189.0, "ac": 201.0,
    "spi": 0.90, "cpi": 0.94, "sv": -21.0, "cv": -12.0,
    "eac": 515.95, "tcpi": 1.042,
    "recovery_feasible": true, "governance_breach": true
  },
  "wbs_packages": [
    {
      "id": "1.1", "name": "Network Infrastructure",
      "budget_cr": 185.0, "spent_cr": 168.0, "pct_complete": 72,
      "status": "AMBER", "resource_flag": null
    }
  ],
  "data_gaps": [],
  "escalations": []
}"""

RISK_PROMPT = """You are the Technical PMO Lead and Risk Governance Agent on Project HELIX. ISO 31000 standards. Absolute accountability.

CRITICAL INSTRUCTIONS:
1. Parse technical documentation and deployment constraints.
2. Log every technical dependency, incompatibility, site gap, regulatory blocker into RAID.
3. For EVERY RAID item:
   a. Assign ONE named owner (individual, not team)
   b. Assign target closure date on critical path
   c. Exposure score = Probability(1-5) x Impact(1-5)
   d. Score >= 20 = CRITICAL; 10-19 = HIGH
4. RACI matrix across all 6 WBS packages. ONE Accountable per package — no exceptions.
5. Score >= 20: escalate to Orchestrator immediately.
6. If REVISION REQUEST notes are provided, address them specifically.

FALLBACK: No owner available → "UNASSIGNED — Director action required". Flag as governance gap.

OUTPUT FORMAT: Return ONLY a valid JSON object — no prose, no markdown fences:
{
  "agent": "TECHNICAL_RISK",
  "period": "M7",
  "raid_items": [
    {
      "id": "R-001", "type": "RISK",
      "description": "Hospital 7 site access blocked by PWD contractor.",
      "probability": 4, "impact": 4, "exposure_score": 16,
      "severity": "HIGH", "owner": "A. Sharma",
      "target_closure": "Wk 32", "status": "OPEN",
      "director_escalation": false
    }
  ],
  "raci_matrix": [
    {
      "wbs_id": "1.1", "wbs_name": "Network Infrastructure",
      "roles": {
        "pm_controller": "A", "tech_lead": "R",
        "sha_secretary": "I", "sha_it_director": "C", "hospital_md": "I"
      }
    }
  ],
  "governance_gaps": [],
  "escalations": []
}"""

COGNITIVE_PROMPT = """You are the Stakeholder Communication Advisor on Project HELIX. Transparent engagement. No manipulation.

CRITICAL INSTRUCTIONS:
1. Analyse client correspondence, transcripts, MoMs in your payload.
2. Identify concerns, engagement metrics, outstanding commitments per stakeholder.
3. Engagement Score (0-100): recency + substance of contact. >7 days no contact = OVERDUE.
4. ETHICAL BOUNDARY: Advisor only. No psychological scripts or emotional positioning. Focus on clarity, expectation management, transparent dispute resolution.
5. If REVISION REQUEST notes are provided, address them specifically.

FALLBACK: Insufficient data → NULL_STATE with specific gap. Never infer sentiment from no data.

OUTPUT FORMAT: Return ONLY a valid JSON object — no prose, no markdown fences:
{
  "agent": "STAKEHOLDER_ADVISOR",
  "period": "M7",
  "stakeholders": [
    {
      "name": "Dr. Anjali Mehta", "role": "SHA Secretary",
      "authority": "Programme final sign-off",
      "engagement_score": 62, "status": "AMBER",
      "last_contact_days": 3, "overdue_flag": false,
      "stated_concerns": ["Timeline commitments", "Budget overrun exposure"],
      "inferable_concerns": ["Political pressure"],
      "outstanding_commitments": ["Submit detailed recovery schedule"],
      "recommended_engagement": "Lead with NOC/SOC wins. Frame TCPI as manageable."
    }
  ],
  "uat_handshake_gaps": [],
  "immediate_attention_required": [],
  "data_gaps": []
}"""

REPORTING_PROMPT = """You are the Executive Communications Specialist and Reporting Engine on Project HELIX.

CRITICAL INSTRUCTIONS:
1. Read from AGENT OUTPUT STORE ONLY. Never from Source RAG Store.
2. DO NOT invent data. Missing data = explicit gap in brief. No filler.
3. Consolidate exactly: EVM metrics, RAID items, Stakeholder status, Director escalations.
4. If REVISION REQUEST notes are provided, address them specifically before producing the brief.
5. Produce:
   A. Daily Progress Brief: Completions, blockers, next-day critical path. Max 1 page.
   B. Weekly SteerCo Deck: RAG status per workstream, EVM table, top 3 risks, stakeholder status, action table.
6. MANDATORY final line (exactly as written):
   STATUS: PENDING PM DIRECTOR APPROVAL — DO NOT DISTRIBUTE

OUTPUT FORMAT: Structured markdown. Clear section headers. Use tables."""

ARBITRATION_PROMPT = """You are Captain Sinbad Sailor. Review the three agent outputs below and perform conflict arbitration.

Identify any conflicts between agent outputs (e.g. PM says recovery feasible but Risk flags unresolved CRITICAL blocker that makes it impossible). For each conflict:
- State the conflicting signals
- Decide which takes precedence and why
- Issue a corrective directive to the affected agent if needed

If REVISION REQUEST notes are provided, incorporate them into your arbitration.

If no conflicts exist, state: NO CONFLICTS DETECTED

Be concise. Authoritative. No pleasantries."""

# ═══════════════════════════════════════════════════════
#  FALLBACK SCHEMAS
# ═══════════════════════════════════════════════════════

PM_FALLBACK = {
    "agent": "PM_CONTROLS", "period": "M7",
    "report_timestamp": datetime.utcnow().isoformat(),
    "evm_summary": {
        "bac": 485.0, "pv": 0.0, "ev": 0.0, "ac": 0.0,
        "spi": 0.0, "cpi": 0.0, "sv": 0.0, "cv": 0.0,
        "eac": 485.0, "tcpi": 1.0,
        "recovery_feasible": True, "governance_breach": False
    },
    "wbs_packages": [],
    "data_gaps": ["Fallback: JSON parse failed. Check agent output."],
    "escalations": []
}

TECH_FALLBACK = {
    "agent": "TECHNICAL_RISK", "period": "M7",
    "raid_items": [], "raci_matrix": [],
    "governance_gaps": ["Fallback: JSON parse failed. Check agent output."],
    "escalations": []
}

COG_FALLBACK = {
    "agent": "STAKEHOLDER_ADVISOR", "period": "M7",
    "stakeholders": [], "uat_handshake_gaps": [],
    "immediate_attention_required": [],
    "data_gaps": ["Fallback: JSON parse failed. Check agent output."]
}

# ═══════════════════════════════════════════════════════
#  BUG FIX: SAFE JSON PARSER (fixed unterminated string)
# ═══════════════════════════════════════════════════════

def safe_parse_json(raw_text, fallback_schema):
    """
    Safely parse JSON from an LLM response.
    Handles markdown code fences (```json ... ``` or ``` ... ```)
    Falls back to schema if parsing fails.
    """
    if not raw_text:
        return fallback_schema

    clean_text = raw_text.strip()

    # FIX: Use triple-quoted raw string — never unterminated single-line r"
    if clean_text.startswith("```"):
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean_text)
        if match:
            clean_text = match.group(1).strip()
        else:
            # Fallback: strip all backtick markers manually
            clean_text = clean_text.replace("```json", "").replace("```", "").strip()

    # Find the first { and last } to isolate the JSON object
    start = clean_text.find("{")
    end = clean_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        clean_text = clean_text[start:end + 1]

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        return fallback_schema

# ═══════════════════════════════════════════════════════
#  DUAL RAG STORE
# ═══════════════════════════════════════════════════════

class DualRAGStore:
    """
    Two isolated stores:
    - source_store: READ-ONLY — bid docs, SOWs, raw inputs
    - agent_output_store: WRITE — agent-generated outputs only
    Agents NEVER write to source_store.
    """
    def __init__(self):
        self.source_store = {}
        self.agent_output_store = {}
        self.audit_log = []

    def ingest_source(self, content: str) -> str:
        doc_id = f"SRC_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.source_store[doc_id] = {
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.audit_log.append(f"[{datetime.utcnow().isoformat()}] SOURCE INGESTED: {doc_id}")
        return doc_id

    def write_agent_output(self, agent_id: str, output: dict):
        self.agent_output_store[agent_id] = {
            "data": output,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.audit_log.append(f"[{datetime.utcnow().isoformat()}] AGENT OUTPUT STORED: {agent_id}")

    def read_agent_output(self, agent_id: str):
        return self.agent_output_store.get(agent_id, {}).get("data")

    def get_all_source_text(self) -> str:
        return "\n\n---\n\n".join(
            v["content"] for v in self.source_store.values()
        )

# ═══════════════════════════════════════════════════════
#  ASYNC-SAFE GEMINI CALLER
#  Uses threading to avoid Streamlit event loop conflicts
# ═══════════════════════════════════════════════════════

def call_gemini_sync(system_prompt: str, user_message: str, model_name: str = "gemini-2.5-flash") -> str:
    """
    Calls Gemini API synchronously with exponential backoff retry.
    Handles 429 quota errors gracefully — retries up to 4 times.
    Safe for Streamlit — no asyncio conflicts.
    """
    MAX_RETRIES = 4
    BACKOFF_SECONDS = [10, 20, 40, 60]

    for attempt in range(MAX_RETRIES + 1):
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt
            )
            response = model.generate_content(user_message)
            return response.text

        except Exception as e:
            err_str = str(e)

            # 429 quota / rate limit — wait and retry
            if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_SECONDS[attempt]
                    delay_match = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*s", err_str, re.IGNORECASE)
                    if delay_match:
                        wait = min(int(float(delay_match.group(1))) + 5, 90)
                    time.sleep(wait)
                    continue
                else:
                    return (
                        "QUOTA_EXCEEDED: Gemini free tier limit reached after retries. "
                        "Enable billing at https://aistudio.google.com — costs less than Rs 5 for a demo. "
                        "Original error: " + err_str
                    )

            # Any other error — fail immediately
            return f"ERROR: {err_str}"

    return "ERROR: Max retries exceeded."


def call_agents_concurrent(payloads: list) -> list:
    """
    Runs multiple Gemini calls concurrently using threads.
    payloads: list of (system_prompt, user_message, model_name) tuples
    Returns list of response strings in same order.
    """
    results = [None] * len(payloads)

    def worker(idx, system_prompt, user_message, model_name):
        results[idx] = call_gemini_sync(system_prompt, user_message, model_name)

    threads = []
    for i, (sp, um, mn) in enumerate(payloads):
        t = threading.Thread(target=worker, args=(i, sp, um, mn))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return results

# ═══════════════════════════════════════════════════════
#  SESSION STATE INITIALISATION
# ═══════════════════════════════════════════════════════

def init_state():
    defaults = {
        "rag": DualRAGStore(),
        "stage": 0,
        # Stage outputs
        "orchestrator_output": None,
        "pm_output": None,
        "risk_output": None,
        "cog_output": None,
        "arbitration_output": None,
        "report_output": None,
        # Gate states: "pending" | "approved" | "sent_back"
        "gate_1": "pending",   # After orchestrator
        "gate_2": "pending",   # After parallel agents
        "gate_3": "pending",   # After arbitration
        "gate_4": "pending",   # After reporting (final)
        # Revision notes per gate
        "notes_1": "",
        "notes_2": "",
        "notes_3": "",
        "notes_4": "",
        # Revision counters
        "rev_1": 0,
        "rev_2": 0,
        "rev_3": 0,
        "rev_4": 0,
        # Raw LLM text (for debug)
        "raw_pm": "",
        "raw_risk": "",
        "raw_cog": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ═══════════════════════════════════════════════════════
#  UI HELPERS
# ═══════════════════════════════════════════════════════

STATUS_COLOURS = {
    "GREEN":    ("#1D9E75", "✅"),
    "AMBER":    ("#EF9F27", "⚠️"),
    "RED":      ("#D85A30", "🔴"),
    "CRITICAL": ("#D85A30", "🚨"),
    "HIGH":     ("#EF9F27", "⚠️"),
    "MEDIUM":   ("#378ADD", "🔵"),
    "OPEN":     ("#D85A30", "🔴"),
    "WATCH":    ("#EF9F27", "⚠️"),
    "CLOSED":   ("#1D9E75", "✅"),
}

def status_badge(status: str) -> str:
    colour, icon = STATUS_COLOURS.get(status.upper(), ("#888", "•"))
    return f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{icon} {status}</span>'

def render_gate(gate_key: str, notes_key: str, rev_key: str,
                approve_label: str, sendback_label: str,
                approve_callback, sendback_callback):
    """
    Renders the human gate UI — approve or send back with notes.
    """
    gate_val = st.session_state[gate_key]

    if gate_val == "approved":
        st.success(f"✅ **Gate approved** — pipeline advancing")
        return

    if gate_val == "sent_back":
        st.warning(f"↩️ **Revision requested** (attempt {st.session_state[rev_key]}) — agent reprocessing...")
        return

    # Gate is pending — show controls
    st.info("🔎 **Human Review Required** — You are the provocateur. Review the output above critically before advancing.")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button(f"✅ {approve_label}", type="primary", key=f"btn_approve_{gate_key}"):
            st.session_state[gate_key] = "approved"
            approve_callback()
            st.rerun()

    with col_b:
        notes = st.text_area(
            "📝 Revision notes (be specific — what must change):",
            key=f"ta_{notes_key}",
            placeholder="e.g. EVM numbers don't match last week's actuals. R-002 owner should be R. Rajan not A. Sharma. Stakeholder Dr Gupta is missing.",
            height=80
        )
        if st.button(f"↩️ {sendback_label}", key=f"btn_sendback_{gate_key}"):
            if notes.strip():
                st.session_state[notes_key] = notes.strip()
                st.session_state[rev_key] += 1
                st.session_state[gate_key] = "sent_back"
                sendback_callback()
                st.rerun()
            else:
                st.error("Please add specific revision notes before sending back.")

# ═══════════════════════════════════════════════════════
#  PIPELINE STAGE RUNNERS
# ═══════════════════════════════════════════════════════

def run_orchestrator(revision_notes: str = ""):
    rag = st.session_state["rag"]
    source_text = rag.get_all_source_text()

    user_msg = source_text
    if revision_notes:
        user_msg = f"REVISION REQUEST FROM PM DIRECTOR:\n{revision_notes}\n\n---\nORIGINAL SOURCE:\n{source_text}"

    with st.spinner("🎖 Captain Sinbad Sailor — ingesting and routing..."):
        output = call_gemini_sync(ORCHESTRATOR_PROMPT, user_msg, "gemini-2.5-flash")

    st.session_state["orchestrator_output"] = output
    st.session_state["gate_1"] = "pending"
    st.session_state["stage"] = 1


def run_parallel_agents(revision_notes: str = ""):
    rag = st.session_state["rag"]
    source_text = rag.get_all_source_text()
    directive = st.session_state.get("orchestrator_output", "")

    def build_payload(route_label):
        base = f"DIRECTOR DIRECTIVE:\n{directive}\n\nROUTE: {route_label}\n\nSOURCE DATA:\n{source_text}"
        if revision_notes:
            base = f"REVISION REQUEST FROM PM DIRECTOR:\n{revision_notes}\n\n---\n" + base
        return base

    payloads = [
        (PM_PROMPT,        build_payload("PM_CONTROLS_PAYLOAD"),       "gemini-2.5-flash"),
        (RISK_PROMPT,      build_payload("TECHNICAL_RISK_PAYLOAD"),     "gemini-2.5-flash"),
        (COGNITIVE_PROMPT, build_payload("STAKEHOLDER_ADVISOR_PAYLOAD"),"gemini-2.5-flash"),
    ]

    with st.spinner("📊🛡🧠 Running 3 agents concurrently (threaded)..."):
        raw_results = call_agents_concurrent(payloads)

    raw_pm, raw_risk, raw_cog = raw_results
    st.session_state["raw_pm"]   = raw_pm
    st.session_state["raw_risk"] = raw_risk
    st.session_state["raw_cog"]  = raw_cog

    pm_data   = safe_parse_json(raw_pm,   PM_FALLBACK)
    risk_data = safe_parse_json(raw_risk, TECH_FALLBACK)
    cog_data  = safe_parse_json(raw_cog,  COG_FALLBACK)

    rag.write_agent_output("pm_agent",   pm_data)
    rag.write_agent_output("risk_agent", risk_data)
    rag.write_agent_output("cog_agent",  cog_data)

    st.session_state["pm_output"]   = pm_data
    st.session_state["risk_output"] = risk_data
    st.session_state["cog_output"]  = cog_data
    st.session_state["gate_2"]      = "pending"
    st.session_state["stage"]       = 2


def run_arbitration(revision_notes: str = ""):
    pm_data   = st.session_state.get("pm_output", {})
    risk_data = st.session_state.get("risk_output", {})
    cog_data  = st.session_state.get("cog_output", {})

    user_msg = (
        f"PM CONTROLS OUTPUT:\n{json.dumps(pm_data, indent=2)}\n\n"
        f"RISK & TECH OUTPUT:\n{json.dumps(risk_data, indent=2)}\n\n"
        f"STAKEHOLDER ADVISOR OUTPUT:\n{json.dumps(cog_data, indent=2)}"
    )
    if revision_notes:
        user_msg = f"REVISION REQUEST FROM PM DIRECTOR:\n{revision_notes}\n\n---\n" + user_msg

    with st.spinner("⚖️ Captain Sinbad — conflict arbitration..."):
        output = call_gemini_sync(ARBITRATION_PROMPT, user_msg, "gemini-2.5-flash")

    st.session_state["arbitration_output"] = output
    st.session_state["gate_3"]             = "pending"
    st.session_state["stage"]              = 3


def run_reporting(revision_notes: str = ""):
    rag = st.session_state["rag"]
    pm_data   = rag.read_agent_output("pm_agent")   or {}
    risk_data = rag.read_agent_output("risk_agent") or {}
    cog_data  = rag.read_agent_output("cog_agent")  or {}
    arb       = st.session_state.get("arbitration_output", "")

    user_msg = (
        f"ARBITRATION DECISION:\n{arb}\n\n"
        f"PM CONTROLS DATA:\n{json.dumps(pm_data, indent=2)}\n\n"
        f"RISK & TECH DATA:\n{json.dumps(risk_data, indent=2)}\n\n"
        f"STAKEHOLDER DATA:\n{json.dumps(cog_data, indent=2)}"
    )
    if revision_notes:
        user_msg = f"REVISION REQUEST FROM PM DIRECTOR:\n{revision_notes}\n\n---\n" + user_msg

    with st.spinner("📋 Reporting Engine — consolidating SteerCo brief..."):
        output = call_gemini_sync(REPORTING_PROMPT, user_msg, "gemini-2.5-flash")

    st.session_state["report_output"] = output
    st.session_state["gate_4"]        = "pending"
    st.session_state["stage"]         = 4

# ═══════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════

st.title("⚓ Project Helix: Multi-Agent PMO Command Center")
st.caption("Smart Hospital Network Infrastructure Programme • IndiaHealth Digital Authority (IHDA), Uttar Pradesh")

# Pipeline stage indicator
stage_labels = ["Input", "Orchestrator", "Agents", "Arbitration", "Reporting", "✅ Released"]
stage_icons  = ["📄",    "🎖",           "⚙️",     "⚖️",         "📋",         "🎉"]
cols = st.columns(len(stage_labels))
for i, (col, label, icon) in enumerate(zip(cols, stage_labels, stage_icons)):
    active = i == st.session_state["stage"]
    done   = i < st.session_state["stage"]
    if active:
        col.markdown(f"<div style='text-align:center;padding:6px;background:#378ADD22;border:1.5px solid #378ADD;border-radius:8px;font-size:13px;font-weight:500'>{icon}<br>{label}</div>", unsafe_allow_html=True)
    elif done:
        col.markdown(f"<div style='text-align:center;padding:6px;background:#1D9E7522;border:1px solid #1D9E75;border-radius:8px;font-size:13px;color:#1D9E75'>✓<br>{label}</div>", unsafe_allow_html=True)
    else:
        col.markdown(f"<div style='text-align:center;padding:6px;border:1px solid #ccc;border-radius:8px;font-size:13px;color:#aaa'>{icon}<br>{label}</div>", unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════
#  STAGE 0 — INPUT
# ═══════════════════════════════════════════════════════

with st.expander("📄 Stage 0 — Input: SOW / Bid Document / Voice Note", expanded=(st.session_state["stage"] == 0)):
    raw_input = st.text_area(
        "Paste your project document below:",
        height=220,
        placeholder="Paste SOW, bid document, or voice note transcript here...\n\nExample: PROJECT HELIX — Contract ₹485 Cr, 18 months. Client: IHDA UP. Scope: 5G private network, Wi-Fi 6E, IoT (2,400 biomedical units), NOC/SOC. Month 7 status: PV ₹210 Cr, EV ₹189 Cr, AC ₹201 Cr. Risks: Hospital 7 access blocked, Siemens API incompatibility, 5G spectrum approval pending..."
    )

    if st.button("🚀 Start Pipeline — Dispatch to Captain Sinbad", type="primary"):
        if raw_input.strip():
            st.session_state["rag"] = DualRAGStore()   # fresh store per run
            st.session_state["rag"].ingest_source(raw_input.strip())
            # Reset all gate states
            for k in ["gate_1","gate_2","gate_3","gate_4"]:
                st.session_state[k] = "pending"
            for k in ["notes_1","notes_2","notes_3","notes_4"]:
                st.session_state[k] = ""
            for k in ["rev_1","rev_2","rev_3","rev_4"]:
                st.session_state[k] = 0
            for k in ["orchestrator_output","pm_output","risk_output",
                      "cog_output","arbitration_output","report_output"]:
                st.session_state[k] = None

            run_orchestrator()
            st.rerun()
        else:
            st.error("Please paste your project document before starting the pipeline.")

# ═══════════════════════════════════════════════════════
#  STAGE 1 — ORCHESTRATOR + GATE 1
# ═══════════════════════════════════════════════════════

if st.session_state["stage"] >= 1 and st.session_state.get("orchestrator_output"):
    with st.expander(
        f"🎖 Stage 1 — Orchestrator Directive {'✅' if st.session_state['gate_1']=='approved' else '🔎'}",
        expanded=(st.session_state["stage"] == 1)
    ):
        rev_count = st.session_state["rev_1"]
        if rev_count > 0:
            st.caption(f"Revision {rev_count} — applied notes: _{st.session_state['notes_1']}_")

        st.markdown(st.session_state["orchestrator_output"])
        st.divider()

        def gate1_approve():
            run_parallel_agents()

        def gate1_sendback():
            run_orchestrator(st.session_state["notes_1"])

        render_gate(
            gate_key="gate_1", notes_key="notes_1", rev_key="rev_1",
            approve_label="Approve routing directive — dispatch agents",
            sendback_label="Send back to Orchestrator for revision",
            approve_callback=gate1_approve,
            sendback_callback=gate1_sendback
        )

# ═══════════════════════════════════════════════════════
#  STAGE 2 — PARALLEL AGENTS + GATE 2
# ═══════════════════════════════════════════════════════

if st.session_state["stage"] >= 2 and st.session_state.get("pm_output"):
    with st.expander(
        f"⚙️ Stage 2 — Parallel Agent Outputs {'✅' if st.session_state['gate_2']=='approved' else '🔎'}",
        expanded=(st.session_state["stage"] == 2)
    ):
        rev_count = st.session_state["rev_2"]
        if rev_count > 0:
            st.caption(f"Revision {rev_count} — applied notes: _{st.session_state['notes_2']}_")

        tab_pm, tab_risk, tab_cog = st.tabs(["📊 PM & Controls", "🛡 Risk & Tech", "🧠 Stakeholder"])

        # ── PM Tab ──────────────────────────────────────
        with tab_pm:
            pm = st.session_state["pm_output"]
            evm = pm.get("evm_summary", {})

            m1, m2, m3, m4 = st.columns(4)
            # Safe numeric coercion — AI may return None or string for any field
            def safe_num(val, default=0.0):
                try:
                    return float(val) if val is not None else default
                except (TypeError, ValueError):
                    return default
            spi_val = safe_num(evm.get("spi"), 0.0)
            cpi_val = safe_num(evm.get("cpi"), 0.0)
            m1.metric("SPI", f"{spi_val:.2f}", delta="⚠ BREACH" if spi_val < 0.95 else "OK",
                      delta_color="inverse" if spi_val < 0.95 else "normal")
            m2.metric("CPI", f"{cpi_val:.2f}", delta="⚠ BREACH" if cpi_val < 0.95 else "OK",
                      delta_color="inverse" if cpi_val < 0.95 else "normal")
            m3.metric("EAC ₹Cr", f"{safe_num(evm.get('eac')):.1f}")
            m4.metric("TCPI", f"{safe_num(evm.get('tcpi')):.3f}")

            if evm.get("governance_breach"):
                st.error("🚨 Governance breach — SPI or CPI below 0.95 threshold")

            wbs = pm.get("wbs_packages", [])
            if wbs:
                st.subheader("WBS Packages")
                for pkg in wbs:
                    # Safely coerce pct_complete — AI may return None, string, or float
                    try:
                        pct = max(0, min(100, int(float(pkg.get("pct_complete") or 0))))
                    except (TypeError, ValueError):
                        pct = 0
                    st.markdown(f"**{pkg.get('id','?')} — {pkg.get('name','Unknown')}**")
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.progress(pct / 100)
                    c2.markdown(f"**{pct}%**")
                    c3.markdown(status_badge(pkg.get("status","AMBER")), unsafe_allow_html=True)
                    if pkg.get("resource_flag"):
                        st.caption(f"⚠ Resource flag: {pkg['resource_flag']}")

            gaps = pm.get("data_gaps", [])
            if gaps and gaps != []:
                st.warning("Data gaps: " + " | ".join(gaps))

        # ── Risk Tab ────────────────────────────────────
        with tab_risk:
            risk = st.session_state["risk_output"]
            raid = risk.get("raid_items", [])

            if raid:
                st.subheader(f"RAID Register — {len(raid)} items")
                for item in raid:
                    sev  = item.get("severity","MEDIUM")
                    col_map = {"CRITICAL": "🔴", "HIGH": "🟡", "MEDIUM": "🔵", "LOW": "🟢"}
                    icon = col_map.get(sev, "•")
                    with st.container():
                        st.markdown(
                            f"{icon} **{item.get('id')} [{item.get('type')}]** — "
                            f"Score {item.get('exposure_score')} "
                            f"({item.get('probability')}×{item.get('impact')}) — "
                            f"*{sev}*"
                        )
                        st.markdown(f"> {item.get('description')}")
                        st.caption(
                            f"Owner: **{item.get('owner')}** | "
                            f"Target: {item.get('target_closure')} | "
                            f"Status: {item.get('status')}"
                            + (" | 🚨 Director escalation" if item.get("director_escalation") else "")
                        )
                        st.divider()
            else:
                st.info("No RAID items parsed — check raw output below.")

            gaps = risk.get("governance_gaps", [])
            if gaps:
                st.warning("Governance gaps: " + " | ".join(gaps))

            with st.expander("Raw RACI Matrix JSON"):
                st.json(risk.get("raci_matrix", []))

        # ── Cognitive Tab ───────────────────────────────
        with tab_cog:
            cog = st.session_state["cog_output"]
            stks = cog.get("stakeholders", [])

            if stks:
                for s in stks:
                    score = s.get("engagement_score", 0)
                    status = s.get("status", "AMBER")
                    colour = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(status, "🟡")
                    st.markdown(f"{colour} **{s.get('name')}** — {s.get('role')}")

                    c1, c2 = st.columns([2, 1])
                    c1.progress(score / 100, text=f"Engagement {score}/100")
                    if s.get("overdue_flag"):
                        c2.error(f"⚠ OVERDUE — {s.get('last_contact_days')} days")
                    else:
                        c2.success(f"Last contact: {s.get('last_contact_days')}d ago")

                    with st.expander(f"Profile — {s.get('name')}"):
                        st.markdown(f"**Authority:** {s.get('authority')}")
                        st.markdown(f"**Stated concerns:** {', '.join(s.get('stated_concerns', []))}")
                        if s.get("outstanding_commitments"):
                            st.markdown(f"**Outstanding commitments:** {', '.join(s.get('outstanding_commitments', []))}")
                        st.info(f"**Recommended approach:** {s.get('recommended_engagement','')}")
                    st.divider()
            else:
                st.info("No stakeholders parsed — check raw output below.")

            imm = cog.get("immediate_attention_required", [])
            if imm:
                st.error("🚨 Immediate attention: " + " | ".join(imm))

        with st.expander("🔍 Debug — Raw LLM Outputs"):
            st.text_area("PM Raw", st.session_state.get("raw_pm",""), height=120)
            st.text_area("Risk Raw", st.session_state.get("raw_risk",""), height=120)
            st.text_area("Cognitive Raw", st.session_state.get("raw_cog",""), height=120)

        st.divider()

        def gate2_approve():
            run_arbitration()

        def gate2_sendback():
            run_parallel_agents(st.session_state["notes_2"])

        render_gate(
            gate_key="gate_2", notes_key="notes_2", rev_key="rev_2",
            approve_label="Approve agent outputs — proceed to arbitration",
            sendback_label="Send all three agents back for revision",
            approve_callback=gate2_approve,
            sendback_callback=gate2_sendback
        )

# ═══════════════════════════════════════════════════════
#  STAGE 3 — ARBITRATION + GATE 3
# ═══════════════════════════════════════════════════════

if st.session_state["stage"] >= 3 and st.session_state.get("arbitration_output"):
    with st.expander(
        f"⚖️ Stage 3 — Conflict Arbitration {'✅' if st.session_state['gate_3']=='approved' else '🔎'}",
        expanded=(st.session_state["stage"] == 3)
    ):
        rev_count = st.session_state["rev_3"]
        if rev_count > 0:
            st.caption(f"Revision {rev_count} — applied notes: _{st.session_state['notes_3']}_")

        arb_text = st.session_state["arbitration_output"]
        if "NO CONFLICTS DETECTED" in arb_text.upper():
            st.success("✅ No conflicts between agent outputs — all data consistent.")
        else:
            st.warning("⚖️ Conflicts detected and arbitrated:")
        st.markdown(arb_text)
        st.divider()

        def gate3_approve():
            run_reporting()

        def gate3_sendback():
            run_arbitration(st.session_state["notes_3"])

        render_gate(
            gate_key="gate_3", notes_key="notes_3", rev_key="rev_3",
            approve_label="Approve arbitration — generate SteerCo brief",
            sendback_label="Send back — re-arbitrate with additional notes",
            approve_callback=gate3_approve,
            sendback_callback=gate3_sendback
        )

# ═══════════════════════════════════════════════════════
#  STAGE 4 — REPORTING + GATE 4 (FINAL APPROVAL)
# ═══════════════════════════════════════════════════════

if st.session_state["stage"] >= 4 and st.session_state.get("report_output"):
    with st.expander(
        f"📋 Stage 4 — SteerCo Brief {'✅ APPROVED & RELEASED' if st.session_state['gate_4']=='approved' else '🔒 PENDING DIRECTOR APPROVAL'}",
        expanded=(st.session_state["stage"] >= 4)
    ):
        rev_count = st.session_state["rev_4"]
        if rev_count > 0:
            st.caption(f"Revision {rev_count} — applied notes: _{st.session_state['notes_4']}_")

        if st.session_state["gate_4"] != "approved":
            st.error(
                "🔒 **PENDING PM DIRECTOR APPROVAL — DO NOT DISTRIBUTE**\n\n"
                "Review the brief below carefully before approving. "
                "You are the final checkpoint before this reaches the client."
            )

        st.markdown(st.session_state["report_output"])
        st.divider()

        if st.session_state["gate_4"] == "approved":
            st.session_state["stage"] = 5
            st.success("🎉 **Brief approved and cleared for client distribution.**")
        else:
            def gate4_approve():
                st.session_state["stage"] = 5

            def gate4_sendback():
                run_reporting(st.session_state["notes_4"])

            render_gate(
                gate_key="gate_4", notes_key="notes_4", rev_key="rev_4",
                approve_label="FINAL APPROVAL — I have reviewed and cleared this for client distribution",
                sendback_label="Send back to Reporting Engine for revision",
                approve_callback=gate4_approve,
                sendback_callback=gate4_sendback
            )

# ═══════════════════════════════════════════════════════
#  STAGE 5 — RELEASED
# ═══════════════════════════════════════════════════════

if st.session_state["stage"] == 5:
    st.success("🎉 **Pipeline complete — SteerCo brief cleared for distribution.**")

# ═══════════════════════════════════════════════════════
#  SIDEBAR — AUDIT TRAIL & CONTROLS
# ═══════════════════════════════════════════════════════

with st.sidebar:
    st.subheader("⚓ Pipeline Controls")

    if st.button("🔄 Reset — New Analysis", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.divider()
    st.subheader("📋 Audit Trail")
    rag = st.session_state.get("rag")
    if rag and rag.audit_log:
        for entry in rag.audit_log:
            st.caption(entry)
    else:
        st.caption("No activity yet.")

    st.divider()
    st.subheader("📊 Gate Status")
    gates = {
        "Gate 1 — Orchestrator": "gate_1",
        "Gate 2 — Agents":       "gate_2",
        "Gate 3 — Arbitration":  "gate_3",
        "Gate 4 — SteerCo":      "gate_4",
    }
    for label, key in gates.items():
        val = st.session_state.get(key, "pending")
        icon = {"approved": "✅", "sent_back": "↩️", "pending": "⏳"}.get(val, "⏳")
        rev  = st.session_state.get(key.replace("gate_","rev_"), 0)
        rev_text = f" (rev {rev})" if rev > 0 else ""
        st.caption(f"{icon} {label}: **{val.upper()}**{rev_text}")
