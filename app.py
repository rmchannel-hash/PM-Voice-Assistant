import streamlit as st
from streamlit_mic_recorder import speech_to_text
import google.generativeai as genai

st.set_page_config(page_title="PD Captain: Sinbad Sailor", layout="wide")

# App Header
st.title("🎙️ PD_Captain: Sinbad Sailor")
st.markdown("### *Account-Level Governance & Strategic Command*")

# Sidebar Configuration
st.sidebar.header("⚓ Command Settings")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Navigation Tabs for the Full Suite
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Account Portfolio Tracker", 
        "🎙️ Voice RAID Log & Decisions", 
        "📝 Report & Meeting Prep", 
        "🧠 Sinbad's Strategic Advisory"
    ])

    with tab1:
        st.subheader("🌐 Consolidated Account Portfolio")
        st.write("Maintain top-level visibility across all tracking tracks under the account.")
        
        # Simple interactive portfolio matrix
        portfolio_data = [
            {"Project Stream": "Site Migration / Infrastructure", "Status": "Ample Warning", "Next Milestone": "Hot Cut Deployment"},
            {"Project Stream": "Consultant & Resource Alignment", "Status": "On Track", "Next Milestone": "LLD & IP Sign-off"},
            {"Project Stream": "Procurement & Hardware Delivery", "Status": "Critical Risk", "Next Milestone": "Mounting Bracket Resolution"}
        ]
        st.table(portfolio_data)

    with tab2:
        st.subheader("🎙️ Voice-to-RAID & Daily Decisions")
        st.write("Capture real-time site updates or high-impact operational changes.")
        
        text = speech_to_text(language='en', use_container_width=True, key='raid_stt')
        
        if text:
            st.info(f"Captured Update: {text}")
            with st.spinner("Captain Sinbad is parsing the deck..."):
                prompt = f"""
                You are Project Director Sinbad Sailor. Analyze this operational update: '{text}'.
                1. Categorize it clearly within the RAID framework (Risk, Action, Issue, Dependency).
                2. Formulate a precise, executive-level entry for the master dashboard.
                3. Provide an immediate directive or daily decision for the project team.
                """
                response = model.generate_content(contents=prompt)
                st.success("Analysis Complete")
                st.markdown(response.text)

    with tab3:
        st.subheader("📋 Executive Report & Meeting Prep")
        st.write("Generate clean briefing bullet points for SteerCo decks or weekly syncs.")
        
        raw_notes = st.text_area("Paste your rough notes, raw consultant updates, or bullet points here:")
        report_type = st.selectbox("Select Output Type", ["Weekly Progress Report Draft", "SteerCo Meeting Agenda & Talking Points", "Escalation Memo"])
        
        if st.button("Generate Executive Artifact") and raw_notes:
            with st.spinner("Drafting..."):
                prompt = f"""
                Act as an elite Project Director. Transform these rough notes into a professional {report_type}:
                
                Notes:
                {raw_notes}
                
                Ensure the tone is highly professional, concise, structured for quick scanning, and highlights critical paths and dependencies.
                """
                response = model.generate_content(contents=prompt)
                st.markdown(response.text)

    with tab4:
        st.subheader("🧠 Sinbad's Strategic Advisory")
        st.write("Consult the Captain directly on complex account-level issues, team management, or technical constraints.")
        
        user_query = st.text_input("Ask Captain Sinbad for advice on a situation:")
        if user_query:
            with st.spinner("Analyzing cross-project impact..."):
                prompt = f"""
                You are Project Director Sinbad Sailor. Provide seasoned, strategic advice on this account scenario: '{user_query}'.
                Address risk management, stakeholder positioning, and clear operational next steps.
                """
                response = model.generate_content(contents=prompt)
                st.markdown(response.text)
else:
    st.warning("👈 Please enter your Google AI Studio API Key in the sidebar to initialize the account dashboard.")