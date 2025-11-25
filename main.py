import streamlit as st
from src import ui, database, gemini
from src.utils import AppLogger

def main():
    st.set_page_config(page_title="Pre-Market Analyst (Glass Box)", layout="wide")

    if 'premarket_economy_card' not in st.session_state:
        st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state:
        st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state:
        st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state:
        st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state:
        st.session_state.final_briefing = None
    if 'xray_snapshot' not in st.session_state:
        st.session_state.xray_snapshot = None
    if 'app_logger' not in st.session_state or not hasattr(st.session_state.app_logger, 'flush'):
        st.session_state.app_logger = AppLogger(None)
    if 'glassbox_eod_card' not in st.session_state:
        st.session_state.glassbox_eod_card = None
    if 'glassbox_etf_data' not in st.session_state:
        st.session_state.glassbox_etf_data = []
    if 'glassbox_prompt' not in st.session_state:
        st.session_state.glassbox_prompt = None
    if 'audit_logs' not in st.session_state:
        st.session_state.audit_logs = []

    st.title("Pre-Market Analyst Workbench (Glass Box)")

    logger = st.session_state.app_logger
    turso = database.get_db_connection()

    if turso:
        database.init_db_schema(turso, logger)
    else:
        st.error("DB Connection Failed.")
        st.stop()

    try:
        gemini.initialize_key_manager(database.TURSO_DB_URL_HTTPS, database.TURSO_AUTH_TOKEN)
    except Exception as e:
        st.error(f"❌ Critical Initialization Error: {e}")
        st.stop()

    selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str = ui.setup_sidebar(logger)

    tab1, tab2 = st.tabs(["Step 1: Live Market Monitor", "Step 2: Battle Commander"])

    with tab1:
        ui.render_step_1(turso, logger, selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str)
        ui.render_log_container()

    with tab2:
        ui.render_step_2(turso, logger, selected_model, simulation_cutoff_str)

if __name__ == "__main__":
    main()
