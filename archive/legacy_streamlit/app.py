import streamlit as st
import pandas as pd
import json
import pytz
from datetime import datetime
from backend.engine.utils import AppLogger, get_turso_credentials
from backend.engine.key_manager import KeyManager
from backend.engine.database import get_db_connection, init_db_schema, fetch_watchlist
from backend.engine.sync_engine import sync_turso_to_local
from backend.engine.gemini import AVAILABLE_MODELS

# UI Modules
from archive.legacy_streamlit.ui.common import render_mission_config
from archive.legacy_streamlit.ui.step_macro import render_step_macro
from archive.legacy_streamlit.ui.step_scanner import render_step_scanner
from archive.legacy_streamlit.ui.step_ranking import render_step_ranking

# Page Config
st.set_page_config(page_title="Pre-Market Analyst (Context Engine)", page_icon="🧠", layout="wide")

# ==============================================================================
# INITIALIZATION
# ==============================================================================
def init_session_state():
    defaults = {
        'market_timezone': pytz.timezone('US/Eastern'),
        'detailed_premarket_cards': {},
        'db_plans': {},
        'macro_missing_tickers': [],
        'unified_missing_tickers': [],
        'macro_analysis_failures': [],
        'unified_analysis_failures': [],
        'macro_audit_log': [],
        'unified_audit_log': [],
        'glassbox_raw_cards': {},
        'glassbox_etf_data': [],
        'proximity_scan_results': [],
        'step1_data_ready': False,
        'app_logger': AppLogger(None)
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def main():
    init_session_state()
    
    # 1. Database & Key Manager
    db_url, auth_token = get_turso_credentials()
    turso = get_db_connection(db_url, auth_token)
    if not turso:
        st.error("❌ Database Connection Failed."); st.stop()
    init_db_schema(turso, st.session_state.app_logger)

    if 'key_manager_instance' not in st.session_state:
        st.session_state.key_manager_instance = KeyManager(db_url, auth_token)

    # 2. Local Sync Logic
    if st.session_state.get('trigger_sync'):
        with st.spinner("Syncing Turso to Local..."):
            sync_turso_to_local(turso, "data/local_turso.db", st.session_state.app_logger)
            st.session_state.trigger_sync = False
            st.toast("Sync Complete", icon="✅"); st.rerun()

    # 3. Sidebar / Mission Config
    model_labels = {
        "gemini-2.0-flash-exp": "Gemini 2.0 Flash (Fast)",
        "gemini-2.0-pro-exp-02-05": "Gemini 2.0 Pro (Deep)",
        "gemini-1.5-pro": "Gemini 1.5 Pro"
    }
    selected_model, logic_mode, sim_cutoff_dt, sim_cutoff_str = render_mission_config(AVAILABLE_MODELS, model_labels)
    
    benchmark_date_str = st.session_state.analysis_date.strftime('%Y-%m-%d')
    
    # 4. Tab Layout
    tab1, tab2, tab3 = st.tabs(["Step 1: Macro Context", "Step 2: Selection Hub", "Step 3: Stock Ranking"])

    with tab1:
        CORE_INTERMARKET_TICKERS = ["SPY", "NDAQ", "IWM", "PAXGUSDT", "BTCUSDT", "EURUSDT", "CL=F", "UUP", "TLT", "SMH", "^VIX", "XLF", "XLK", "XLV", "XLE", "XLI", "XLP", "XLY", "XLC", "XLB", "XLU"]
        render_step_macro(turso, logic_mode, sim_cutoff_dt, sim_cutoff_str, benchmark_date_str, selected_model, CORE_INTERMARKET_TICKERS)

    with tab2:
        render_step_scanner(turso, logic_mode, sim_cutoff_dt, sim_cutoff_str, benchmark_date_str, selected_model, fetch_watchlist)

    with tab3:
        render_step_ranking(turso, db_url, auth_token, logic_mode, sim_cutoff_dt, sim_cutoff_str)

    # 5. System Logs (Bottom)
    st.divider()
    with st.expander("🛠️ System Audit Log", expanded=False):
        st.session_state.app_logger.container = st.empty()
        st.session_state.app_logger.flush()

if __name__ == "__main__":
    main()
