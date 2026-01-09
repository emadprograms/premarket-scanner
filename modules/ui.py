import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render_sidebar(available_models):
    with st.sidebar:
        # Fallback Init for Subpages
        import pytz
        if 'market_timezone' not in st.session_state:
             st.session_state.market_timezone = pytz.timezone('US/Eastern')
        
        st.header("⚙️ Mission Config")
        if 'key_manager_instance' in st.session_state and st.session_state.key_manager_instance:
            st.success("✅ Key Manager: Active")
        else:
            st.error("❌ Key Manager: Failed")

        selected_model = st.selectbox("AI Model", available_models, index=0)
        mode = st.radio("Operation Mode", ["Live", "Simulation"], index=0)

        if mode == "Live":
            simulation_cutoff_dt = datetime.now(st.session_state.market_timezone)
            st.success(f"🟢 Live Mode Active")
        else:
            st.warning(f"🟠 Simulation Mode")
            sim_date = st.date_input("Simulation Date")
            # Default time is 09:26 ET (Pre-Market)
            sim_time = st.time_input("Simulation Time (ET)", value=datetime.strptime("09:26", "%H:%M").time(), step=120)
            # FIX: Use localize for pytz timezones to handle DST/Offset correctly
            naive_dt = datetime.combine(sim_date, sim_time)
            simulation_cutoff_dt = st.session_state.market_timezone.localize(naive_dt)
            st.info(f"Time Travel To: {simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} ET")

        # FIX: Database stores timestamps in UTC.
        # We must convert the ET cutoff to UTC for the SQL query string.
        cutoff_utc = simulation_cutoff_dt.astimezone(pytz.utc)
        simulation_cutoff_str = cutoff_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        analysis_date = sim_date if mode == "Simulation" else simulation_cutoff_dt.date()
        st.write(f"Analysis Market Date: {analysis_date}")
        st.session_state.analysis_date = analysis_date

        return selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str

def render_main_content(mode, simulation_cutoff_dt):
    st.header("Step 1: Macro Context")
    pm_news = st.text_area("News Input", height=100, key="pm_news_input")
    
    st.markdown("---")
    return pm_news

def render_proximity_scan():
    # Header handled in Context_Engine.py

    pct_threshold = st.slider("Proximity %", 0.1, 5.0, 2.5)
    if st.button("Run Proximity Scan"):
        if not st.session_state.latest_macro_date:
            st.error("Generate Macro Card first.")
            st.stop()
        return pct_threshold
    return None

def render_battle_commander():
    st.header("Step 3: Head Trader Synthesis")
    return None