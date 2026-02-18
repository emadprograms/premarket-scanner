import streamlit as st
import pandas as pd
import concurrent.futures
from datetime import datetime, timedelta
import json
import sys
import os

# Ensure modules can be imported
sys.path.append(os.getcwd())

from backend.engine.processing import ticker_to_epic, get_live_bars_from_capital
from backend.engine.utils import AppLogger
from backend.engine.capital_api import create_capital_session_v2
from app import render_lightweight_chart_simple

st.set_page_config(page_title="Capital.com Diagnostic Terminal", page_icon="🖥️", layout="wide")

st.title("🖥️ Capital.com Diagnostic Terminal")
st.markdown("""
This terminal performs a **Stress Test** on the Capital.com API. 
It attempts to fetch live 1-min data for all 21 mapped Epics concurrently to verify connectivity, authentication, and data density.
""")

# --- CONFIG ---
MAPPED_TICKERS = [
    "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
    "PAXGUSDT", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "XLK", "XLE", "GLD", "NDAQ", "^VIX"
]

if 'diag_results' not in st.session_state:
    st.session_state.diag_results = {}

# --- ACTIONS ---
c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    if st.button("🚀 Run Stress Test", type="primary", use_container_width=True):
        st.session_state.diag_results = {} # Reset
        st.session_state.run_diag = True

with c2:
    granularity = st.selectbox("Resolution", ["MINUTE", "MINUTE_5", "MINUTE_15", "MINUTE_30", "HOUR", "DAY"], index=1)

if st.session_state.get('run_diag'):
    with st.status("Testing API Connectivity...", expanded=True) as status:
        # 1. AUTH CHECK
        status.write("Checking Authentication...")
        cst, xst = create_capital_session_v2()
        if not cst or not xst:
            status.update(label="Auth Failed", state="error")
            st.error("Capital.com Credentials are invalid. Check your Infisical secrets.")
            st.session_state.run_diag = False
            st.stop()
        
        # 2. SEQUENTIAL FETCH
        import time
        status.write(f"Fetching {len(MAPPED_TICKERS)} Epics sequentially ({granularity})...")
        
        # We use a simple loop instead of ThreadPoolExecutor to prevent Capital.com rate limits
        for t in MAPPED_TICKERS:
            try:
                epic = ticker_to_epic(t)
                # Avoid requesting too many bars (Max 1000). 
                # MINUTE: 1d (will be clamped to 16h) | MINUTE_5: 3d | others: 7d
                if granularity == "MINUTE":
                    lookback_days = 1
                elif granularity == "MINUTE_5":
                    lookback_days = 3
                else:
                    lookback_days = 7
                
                df = get_live_bars_from_capital(t, days=lookback_days, resolution=granularity)
                
                if df is not None and not df.empty:
                    res = {
                        "ticker": t,
                        "epic": epic,
                        "status": "PASS",
                        "rows": len(df),
                        "latest": df.iloc[-1]['close'] if 'close' in df.columns else df.iloc[-1]['Close'],
                        "df": df
                    }
                else:
                    res = {"ticker": t, "epic": epic, "status": "FAIL", "error": f"No data returned for {granularity}"}
            except Exception as e:
                import traceback
                error_msg = str(e)
                res = {"ticker": t, "epic": ticker_to_epic(t), "status": "ERROR", "error": error_msg}
            
            st.session_state.diag_results[t] = res
            status.write(f"Checking {t}... ({res['status']})")
            
            # CAPITAL.COM RATE LIMIT: 1 Request Per Second
            time.sleep(1)
        
        status.update(label="Diagnostic Complete", state="complete")
        st.session_state.run_diag = False

# --- RESULTS DISPLAY ---
if st.session_state.diag_results:
    # Summary Metrics
    results = list(st.session_state.diag_results.values())
    total = len(results)
    passed = len([r for r in results if r['status'] == "PASS"])
    failed = total - passed
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Tested", total)
    m2.metric("Passed", passed, delta=passed if passed > 0 else None)
    m3.metric("Failed", failed, delta=-failed if failed > 0 else None, delta_color="inverse")
    
    st.divider()
    
    # Detailed Matrix
    for t in MAPPED_TICKERS:
        res = st.session_state.diag_results.get(t)
        if not res: continue
        
        with st.expander(f"{'✅' if res['status'] == 'PASS' else '❌'} {t} (Epic: {res['epic']})", expanded=(res['status'] != 'PASS')):
            if res['status'] == "PASS":
                col_a, col_b = st.columns([1, 2])
                with col_a:
                    st.write(f"**Rows Fetched:** {res['rows']}")
                    st.write(f"**Latest Price:** {res['latest']}")
                    st.success("Data Connection Robust")
                with col_b:
                    # Render chart if we have data
                    render_lightweight_chart_simple(res['df'], t, height=200)
            else:
                st.error(f"Reason: {res.get('error', 'Unknown Error')}")
                st.info("Try checking if this Epic is active for your account tier in Capital.com.")

else:
    st.info("Click 'Run Stress Test' above to start diagnostics.")
