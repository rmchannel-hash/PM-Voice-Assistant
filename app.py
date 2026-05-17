import streamlit as st
import google.generativeai as genai
import json

st.set_page_config(page_title="PD Captain: Sinbad Sailor", layout="wide")

st.title("⚓ PD_Captain: Sinbad Sailor")
st.markdown("### *Hierarchical Multi-Agent Account Governance*")

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("⚙️ Swarm Core Settings")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

# Ruthless System Instructions
SINBAD_SYSTEM = """You are Captain Sinbad Sailor, a ruthless, hyper-structured Project Director specializing in high-maturity account delivery (CMMI Level 5) and strict Earned Value Management (EVM) frameworks. Your role is to analyze raw multi-page project telemetry/bid documents, enforce absolute accountability, and delegate isolated work payloads to sub-agents without crossing context wires.
Route monetary/milestones to PM Agent. Route design/readiness to Technical Agent. Route text/emails to Cognitive Agent."""

PM_SYSTEM = """You are the Lead Project Controller. Your domain is mathematical precision, resource efficiency, and financial truth (ANSI/EIA-748 EVM).
Analyze your delegated payload. Output a strict JSON structure containing: Level 2 WBS, Planned Value (PV), SPI, CPI, and Resource allocation adjustments."""

TECH_SYSTEM = """You are the Technical PMO Lead and Risk Governance Agent. Enforce absolute alignment with ISO 31000 Risk Management standards.
Parse technical designs, LLD details, and deployment constraints. Output a strict JSON structure containing a comprehensive RAID register with assigned owners, target closure dates, and a definitive RACI Matrix footprint."""

COGNITIVE_SYSTEM = """You are the Behavioral Science & Client Account Director. Your domain is high-stakes stakeholder psychology, sentiment telemetry, and predictive relationship engineering. 
Ingest emails/transcripts. Output a structured behavioral brief containing: Customer Sentiment Score, Top 3 Relationship Risks, and an explicit UAT Handshake Strategy with scripted talking points."""

# --- INITIALIZE AGENTS ---
if api_key:
    genai.configure(api_key=api_key)
    
    # Instantiate models with their respective ruthless system prompts
    sinbad_orchestrator = genai.GenerativeModel('gemini-2.5-flash', system_instruction=SINBAD_SYSTEM)
    pm_agent = genai.GenerativeModel('gemini-2.5-flash', system_instruction=PM_SYSTEM)
    tech_agent = genai.GenerativeModel('gemini-2.5-flash', system_instruction=TECH_SYSTEM)
    cognitive_agent = genai.GenerativeModel('gemini-2.5-flash', system_instruction=COGNITIVE_SYSTEM)

    # --- STATE MANAGEMENT (THE CENTRAL LOGICAL LOOP) ---
    if "central_knowledge_base" not in st.session_state:
        st.session_state.central_knowledge_base = {
            "wbs_metrics": {},
            "raid_raci_logs": {},
            "stakeholder_sentiment": {}
        }

    # --- UI TABS ---
    tab1, tab2 = st.tabs(["📂 Ingestion Engine", "📊 Master Dashboard"])

    with tab1:
        st.subheader("📥 Central Document Ingestion Pool")
        st.write("Upload your master Project Bid Document, Statement of Work (SOW), or LLD here.")
        
        uploaded_file = st.file_uploader("Drop project dossier here", type=["txt", "md"])
        
        if uploaded_file is not None:
            raw_document_text = uploaded_file.read().decode("utf-8")
            st.success("Document successfully loaded into memory cache.")
            
            if st.button("Activate Captain Sinbad: Execute Swarm Delegation"):
                with st.spinner("Captain Sinbad is running semantic breakdown and activating the swarm..."):
                    
                    # Step 1: Orchestrator routes the payloads
                    orchestrator_response = sinbad_orchestrator.generate_content(
                        f"Analyze and delegate this project dossier:\n\n{raw_document_text}"
                    )
                    
                    st.markdown("### 🚢 Captain Sinbad's Operational Directive")
                    st.info(orchestrator_response.text)
                    
                    # Step 2: Simulate parallel execution to sub-agents using the text block
                    # (In production, Sinbad extracts and routes clean text fields to each model)
                    with st.spinner("Sub-Agents analyzing parallel streams..."):
                        
                        pm_payload = pm_agent.generate_content(f"Process financial/milestone scope out of this context:\n\n{raw_document_text}")
                        tech_payload = tech_agent.generate_content(f"Extract technical risk/RACI from this context:\n\n{raw_document_text}")
                        cog_payload = cognitive_agent.generate_content(f"Analyze stakeholder communication from this context:\n\n{raw_document_text}")
                        
                        # Store outcomes in Central State Memory
                        st.session_state.central_knowledge_base["wbs_metrics"] = pm_payload.text
                        st.session_state.central_knowledge_base["raid_raci_logs"] = tech_payload.text
                        st.session_state.central_knowledge_base["stakeholder_sentiment"] = cog_payload.text
                        
                        st.success("🎯 All sub-agents have updated the Central RAG Database successfully!")

    with tab2:
        st.subheader("🌐 Real-Time Account Portfolio Matrix")
        st.write("Dynamic data states fetched straight from the central memory layer.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### 📊 Controls Data")
            st.code(st.session_state.central_knowledge_base["wbs_metrics"], language="json")
        with col2:
            st.markdown("### 🛡️ Governance & Risks")
            st.code(st.session_state.central_knowledge_base["raid_raci_logs"], language="json")
        with col3:
            st.markdown("### 🧠 Cognitive Sentiment")
            st.code(st.session_state.central_knowledge_base["stakeholder_sentiment"], language="json")
else:
    st.warning("👈 Please enter your Gemini API Key in the sidebar to power the orchestration ecosystem.")