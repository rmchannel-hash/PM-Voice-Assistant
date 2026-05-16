import streamlit as st
from streamlit_mic_recorder import speech_to_text
import google.generativeai as genai

st.set_page_config(page_title="PM Voice Assistant", layout="wide")

st.title("🎙️ PM Orchestrator: Voice-to-RAID")
st.sidebar.header("Settings")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    st.subheader("Daily Status & Decision Support")
    st.write("Click the mic, speak your update (e.g., 'Add a risk: The WAN consultant is delayed'), and wait for analysis.")

    # The magic browser-based microphone
    text = speech_to_text(language='en', use_container_width=True, key='my_stt')

    if text:
        st.info(f"Detected Speech: {text}")
        
        with st.spinner("Analyzing project impact..."):
            prompt = f"""
            You are a Senior Project Manager. Analyze this voice input: '{text}'.
            1. Categorize it (Risk, Action, Issue, or Dependency).
            2. Suggest a concise entry for a RAID dashboard.
            3. Provide a 'Next Step' recommendation for the PM.
            """
            response = model.generate_content(prompt)
            st.success("Analysis Complete")
            st.markdown(response.text)
else:
    st.warning("👈 Please enter your Google AI Studio API Key in the sidebar to begin.")