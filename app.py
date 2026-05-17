import streamlit as st
import google.generativeai as genai
import json

st.set_page_config(page_title="PD Command Center", layout="wide")
st.title("⚓ PD Command Center: Hardened Swarm")

# Sidebar for Setup
st.sidebar.header("⚙️ Core Configuration")
api_key = st.sidebar.text_input("Enter API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)
    
    # Tier 1: Deep Reasoning Models for Orchestration & Soft Skills
    orchestrator_model = genai.GenerativeModel('gemini-3-flash') # In production tier, swap to Pro
    cognitive_model = genai.GenerativeModel('gemini-3-flash') 
    
    # Tier 2: Fast, Highly Accurate Extraction Models for Structured Data
    pm_model = genai.GenerativeModel('gemini-3-flash')
    tech_model = genai.GenerativeModel('gemini-3-flash')

    # Centralized Memory Initialization
    if "central_knowledge_base" not in st.session_state:
        st.session_state.central_knowledge_base = {
            "wbs_metrics": None,
            "raid_raci_logs": None,
            "stakeholder_sentiment": None,
            "supervisor_approved": False
        }

    tab1, tab2 = st.tabs(["📂 Ingestion & Processing", "🔍 Supervisor Validation Gate"])

    with tab1:
        st.subheader("📥 Enterprise Data Ingestion")
        uploaded_file = st.file_uploader("Upload Project Dossier", type=["txt", "md"])
        
        # Simulated Actuals Feed Connector (Addresses Claude's Point #1)
        st.markdown("### 🔌 Connected Feeds")
        actuals_connected = st.checkbox("Link live execution feeds (Jira / SAP Cost Ledgers)", value=False)
        actuals_payload = "ACTUALS_FEED_STATUS: None provided" if not actuals_connected else "ACTUALS_FEED: PV=10000, EV=9500, AC=9800"

        if uploaded_file and st.button("Run Multi-Agent Analysis"):
            raw_text = uploaded_file.read().decode("utf-8")
            
            # Phase 1: Orchestration Execution
            with st.spinner("Captain Sinbad routing contexts..."):
                directive = orchestrator_model.generate_content(f"{SINBAD_SYSTEM}\n\nInput:\n{raw_text}").text
                st.info("🚢 **Orchestrator Directive Issued.**")
            
            # Phase 2: Execution Streams (Simulating parallel backend processing sequentially for safety)
            with st.spinner("Processing sub-agent pipelines..."):
                # Pass both the text and the actuals feed status to prevent calculation hallucinations
                pm_res = pm_model.generate_content(f"{PM_SYSTEM}\n\nContext:\n{raw_text}\n\n{actuals_payload}").text
                tech_res = tech_model.generate_content(f"{TECH_SYSTEM}\n\nContext:\n{raw_text}").text
                cog_res = cognitive_model.generate_content(f"{COGNITIVE_SYSTEM}\n\nContext:\n{raw_text}").text
                
                # Write back immediately to Central Memory Layer
                st.session_state.central_knowledge_base["wbs_metrics"] = pm_res
                st.session_state.central_knowledge_base["raid_raci_logs"] = tech_res
                st.session_state.central_knowledge_base["stakeholder_sentiment"] = cog_res
                st.session_state.central_knowledge_base["supervisor_approved"] = False
                st.success("Target analysis stored in central database cache.")

    with tab2:
        st.subheader("🛡️ Supervisor Review & Sign-Off")
        
        if st.session_state.central_knowledge_base["wbs_metrics"]:
            st.warning("⚠️ Critical Governance Check: Review agent data outputs before compiling executive decks.")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("#### 📊 Parsed PM Metrics JSON")
                st.text_area("PM Agent Raw", st.session_state.central_knowledge_base["wbs_metrics"], height=250)
            with col2:
                st.markdown("#### 🛡️ Parsed Technical RAID JSON")
                st.text_area("Tech Agent Raw", st.session_state.central_knowledge_base["raid_raci_logs"], height=250)
            with col3:
                st.markdown("#### 🧠 Parsed Advisor JSON")
                st.text_area("Cognitive Agent Raw", st.session_state.central_knowledge_base["stakeholder_sentiment"], height=250)
            
            st.markdown("---")
            # The Gatekeeper Switch (Addresses Claude's Point #5)
            approval = st.checkbox("Verify and Approve Swarm Telemetry Data Integrity")
            if approval:
                st.session_state.central_knowledge_base["supervisor_approved"] = True
                st.success("🔒 Telemetry Verified. Cleared for SteerCo Reporting Engine compilation.")
        else:
            st.info("No active telemetry found. Please run the Ingestion pipeline.")