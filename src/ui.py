import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render_sidebar(available_models):
    with st.sidebar:
        st.header("⚙️ Mission Config")
        if 'key_manager_instance' in st.session_state and st.session_state.key_manager_instance:
            st.success("✅ Key Manager: Active")
        else:
            st.error("❌ Key Manager: Failed")

        selected_model = st.selectbox("AI Model", available_models, index=0)
        mode = st.radio("Operation Mode", ["Live", "Simulation"], index=0)

        if mode == "Live":
            simulation_cutoff_dt = datetime.now(st.session_state.utc_timezone)
            st.success(f"🟢 Live Mode Active")
        else:
            st.warning(f"🟠 Simulation Mode")
            sim_date = st.date_input("Simulation Date")
            sim_time = st.time_input("Simulation Time (UTC)", value=datetime.strptime("13:00", "%H:%M").time())
            simulation_cutoff_dt = datetime.combine(sim_date, sim_time).replace(tzinfo=st.session_state.utc_timezone)
            st.info(f"Time Travel To: {simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        simulation_cutoff_str = simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
        analysis_date = sim_date if mode == "Simulation" else simulation_cutoff_dt.date()
        st.write(f"Analysis Market Date: {analysis_date}")
        st.session_state.analysis_date = analysis_date

        return selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str

def render_main_content(mode, simulation_cutoff_dt, etf_placeholder):
    st.header("A. Macro Context (Step 0)")
    pm_news = st.text_area("News Input", height=100, key="pm_news_input")

    st.markdown(f"### 🛠️ Glass Box: Data Stream ({mode})")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.caption("1. Retrieved EOD Context")
        eod_placeholder = st.empty()
        if st.session_state.glassbox_eod_card:
            eod_placeholder.json(st.session_state.glassbox_eod_card, expanded=False)
        else:
            eod_placeholder.info("Click **'Generate Economy Card'** below to fetch the latest End-of-Day context.")
    with col2:
        st.caption("3. Constructed AI Prompt")
        prompt_placeholder = st.empty()
        if st.session_state.glassbox_prompt:
            prompt_placeholder.text_area("Prompt Preview", st.session_state.glassbox_prompt, height=150, key="glassbox_prompt_view")
        else:
            prompt_placeholder.info("Click **'Generate Economy Card'** below to construct the AI prompt.")

    st.caption("2. Intermarket Data Build (Updating Live)")
    if st.session_state.glassbox_etf_data:
        etf_placeholder.dataframe(
            pd.DataFrame(st.session_state.glassbox_etf_data), use_container_width=True,
            column_config={
                "Freshness": st.column_config.ProgressColumn(f"Freshness (vs {simulation_cutoff_dt.strftime('%H:%M')})", format=" ", min_value=0, max_value=1, width="small"),
                "Audit: Date": st.column_config.TextColumn("Data Timestamp (UTC)"),
                "Audit: Bars": st.column_config.NumberColumn("Bars"),
            },
        )
    else:
        etf_placeholder.info("Ready to scan. Click **'Generate Economy Card (Step 0)'** to fetch live market data.")

    if st.session_state.glassbox_etf_data:
        with st.expander("🔍 View Raw Data Strings sent to AI"):
            st.info("Check the Live Logs or 'Prompt Preview' above to see the full generated reports.")

    st.markdown("---")

    return pm_news, eod_placeholder, prompt_placeholder

def render_proximity_scan():
    st.header("B. Proximity Scan (Step 1)")
    pct_threshold = st.slider("Proximity %", 0.1, 5.0, 2.5)
    if st.button("Run Proximity Scan"):
        if not st.session_state.latest_macro_date:
            st.error("Generate Macro Card first.")
            st.stop()
        return pct_threshold
    return None

def render_battle_commander():
    st.header("Step 2: Head Trader Synthesis")
    if not st.session_state.curated_tickers:
        st.warning("Complete Step 1 first.")
        st.stop()
    focus_input = st.text_area("Executor's Focus", height=80)
    return focus_input
