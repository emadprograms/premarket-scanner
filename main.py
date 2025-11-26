import streamlit as st
import pandas as pd
import json
import re
import time
from datetime import datetime, timezone, timedelta

# --- LOCAL IMPORTS ---
try:
    from key_manager import KeyManager
    from src.utils import AppLogger, get_turso_credentials
    from src.database import (
        get_db_connection,
        init_db_schema,
        get_latest_economy_card_date,
        get_eod_economy_card,
        get_eod_card_data_for_screener,
        get_all_tickers_from_db,
        save_snapshot,
    )
    from src.processing import (
        get_latest_price_details,
        get_session_bars_from_db,
        process_session_data_to_summary,
    )
    from src.gemini import call_gemini_with_rotation, AVAILABLE_MODELS
    from src.ui import (
        render_sidebar,
        render_main_content,
        render_proximity_scan,
        render_battle_commander,
    )
except ImportError as e:
    st.error(f"❌ CRITICAL MISSING FILE: {e}")
    st.stop()

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================

st.set_page_config(page_title="Pre-Market Analyst (Glass Box)", layout="wide")

CORE_INTERMARKET_TICKERS = [
    "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
    "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "NDAQ", "^VIX"
]

# ==============================================================================
# 6. MAIN APPLICATION LOGIC
# ==============================================================================

def main():
    st.title("Pre-Market Analyst Workbench (Glass Box)")

    # --- Session State ---
    if 'premarket_economy_card' not in st.session_state: st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state: st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state: st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state: st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state: st.session_state.final_briefing = None
    if 'xray_snapshot' not in st.session_state: st.session_state.xray_snapshot = None
    if 'app_logger' not in st.session_state or not hasattr(st.session_state.app_logger, 'flush'):
        st.session_state.app_logger = AppLogger(None)

    if 'glassbox_eod_card' not in st.session_state: st.session_state.glassbox_eod_card = None
    if 'glassbox_etf_data' not in st.session_state: st.session_state.glassbox_etf_data = []
    if 'glassbox_prompt' not in st.session_state: st.session_state.glassbox_prompt = None
    if 'audit_logs' not in st.session_state: st.session_state.audit_logs = []
    if 'utc_timezone' not in st.session_state: st.session_state.utc_timezone = timezone.utc

    # --- Startup ---
    startup_logger = st.session_state.app_logger
    db_url, auth_token = get_turso_credentials()
    turso = get_db_connection(db_url, auth_token)
    if turso:
        init_db_schema(turso, startup_logger)
    else:
        st.error("DB Connection Failed.")
        st.stop()

    if 'key_manager_instance' not in st.session_state:
        st.session_state.key_manager_instance = KeyManager(db_url=db_url, auth_token=auth_token)

    selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str = render_sidebar(AVAILABLE_MODELS)

    tab1, tab2 = st.tabs(["Step 1: Live Market Monitor", "Step 2: Battle Commander"])
    logger = st.session_state.app_logger

    with tab1:
        etf_placeholder = st.empty()
        pm_news, eod_placeholder, prompt_placeholder = render_main_content(mode, simulation_cutoff_dt, etf_placeholder)

        if st.button("Generate Economy Card (Step 0)", key="btn_step0", type="primary"):
            st.session_state.glassbox_etf_data = []
            etf_placeholder.empty()

            with st.status(f"Running Macro Scan ({mode})...", expanded=True) as status:
                status.write("Fetching EOD Card...")
                if mode == "Simulation":
                    eod_search_date = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    eod_search_date = simulation_cutoff_dt.strftime('%Y-%m-%d')

                latest_date = get_latest_economy_card_date(turso, simulation_cutoff_str, logger)
                eod_card = {}
                if latest_date:
                    eod_card_data = get_eod_economy_card(turso, latest_date, logger)
                    if eod_card_data:
                        eod_card = eod_card_data
                        eod_placeholder.json(eod_card, expanded=False)
                    else:
                        eod_placeholder.warning(f"⚠️ Found record for {latest_date} but data was empty/corrupt.")
                else:
                    eod_placeholder.warning(f"⚠️ No EOD Economy Card found on or before {simulation_cutoff_str.split(' ')[0]}.")

                st.session_state.glassbox_eod_card = eod_card
                status.write("Scanning Intermarket Tickers...")
                etf_summaries = []
                benchmark_date_str = st.session_state.analysis_date.isoformat()

                for epic in CORE_INTERMARKET_TICKERS:
                    latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)
                    if latest_price:
                        df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                        bar_count = len(df) if df is not None else 0
                        freshness_score = 0.0
                        try:
                            if price_ts:
                                ts_clean = price_ts.replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: ts_obj = ts_obj.replace(tzinfo=timezone.utc)
                                lag_minutes = (simulation_cutoff_dt - ts_obj).total_seconds() / 60.0
                                freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                        except Exception: freshness_score = 0.0

                        if df is not None:
                            processed_data = process_session_data_to_summary(epic, df, latest_price, logger)
                            summary_text = processed_data["summary_text"]
                            etf_summaries.append(summary_text)

                            new_row = {
                                "Ticker": epic,
                                "Price": f"${latest_price:.2f}",
                                "Freshness": freshness_score,
                                "Audit: Date": f"{price_ts} (UTC)",
                                "Audit: Bars": bar_count,
                                "Slope": processed_data["slope"],
                                "High Dwell": processed_data["time_zone"],
                            }
                            st.session_state.glassbox_etf_data.append(new_row)
                            
                            etf_placeholder.dataframe(pd.DataFrame(st.session_state.glassbox_etf_data), use_container_width=True)
                            time.sleep(0.02)

                if not etf_summaries:
                    status.update(label="Scan Aborted: No Data", state="error", expanded=True)
                    st.error("⚠️ **No Live Data Found:** Please run the **Data Harvester** to update market data, then click the button again.")
                    st.stop()

                status.write("Synthesizing AI Prompt...")
                mode_str = f"PRE-MARKET PREP ({mode})"
                prompt = f"""
                [INPUTS]
                EOD Context: {json.dumps(eod_card)}
                
                Live Intermarket Data (Price Action & Time Analysis): 
                {json.dumps(etf_summaries, indent=2)}
                
                News: {pm_news}
                Mode: {mode_str}
                [TASK] Act as Macro Strategist. Synthesize EOD Context + Live Data + News.
                """
                st.session_state.glassbox_prompt = prompt
                prompt_placeholder.text_area("Prompt Preview", prompt, height=150, key="glassbox_prompt_preview")

                status.write(f"Calling Gemini ({selected_model})...")
                system_prompt = "You are an expert Macro Strategist. Output valid JSON only with keys: marketNarrative, marketBias, sectorRotation."
                
                resp, error_msg = call_gemini_with_rotation(prompt, system_prompt, logger, selected_model, st.session_state.key_manager_instance)

                if resp:
                    try:
                        json_match = re.search(r"(\{.*\})", resp, re.DOTALL)
                        json_str = json_match.group(1) if json_match else resp
                        new_card = json.loads(json_str)
                        new_card['date'] = st.session_state.analysis_date.isoformat()
                        st.session_state.premarket_economy_card = new_card
                        st.session_state.latest_macro_date = new_card['date']
                        status.update(label="Macro Card Generated", state="complete", expanded=False)
                        st.rerun()
                    except Exception as e:
                        status.update(label="JSON Parse Error", state="error")
                        st.error(f"AI Error: {e}")
                else:
                    status.update(label="AI Failed", state="error")
                    st.error(error_msg)

        if st.session_state.premarket_economy_card:
            st.success(f"Macro Card Ready: {st.session_state.latest_macro_date}")
            with st.expander("View Final AI Output"):
                st.json(st.session_state.premarket_economy_card)

        pct_threshold = render_proximity_scan()
        if pct_threshold is not None:
            logger = st.session_state.app_logger
            benchmark_date_for_scan = st.session_state.latest_macro_date
            
            with st.status(f"Scanning Market ({mode})...", expanded=True) as status:
                tickers = get_all_tickers_from_db(turso, logger)
                eod_data = get_eod_card_data_for_screener(turso, tickers, benchmark_date_for_scan, logger)
                results = []
                for tkr, data in eod_data.items():
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    if not price: continue
                    levels = [l for l in data['s_levels'] + data['r_levels'] if l > 0]
                    if not levels: continue
                    dist = min([abs(price - l) / l for l in levels]) * 100
                    if dist <= pct_threshold:
                        results.append({"Ticker": tkr, "Price": f"${price:.2f}", "Dist%": f"{dist:.2f}"})
                st.session_state.proximity_scan_results = sorted(results, key=lambda x: float(x['Dist%']))
                status.update(label="Scan Complete", state="complete", expanded=False)
                st.rerun()

        if st.session_state.proximity_scan_results:
            df_res = pd.DataFrame(st.session_state.proximity_scan_results)
            st.dataframe(df_res, use_container_width=True)
            opts = [r['Ticker'] for r in st.session_state.proximity_scan_results]
            st.session_state.curated_tickers = st.multiselect("Curate List", opts, default=opts)

        st.markdown("---")
        st.subheader("Live Logs")
        log_container = st.container(height=200)
        st.session_state.app_logger.container = log_container
        st.session_state.app_logger.flush()

    with tab2:
        focus_input = render_battle_commander()
        if st.button("Run Synthesis", type="primary"):
            benchmark_date_str = st.session_state.analysis_date.isoformat()
            xray_data = []
            dossiers = []
            live_stats_log = []

            with st.status("Processing...", expanded=True) as status:
                eod_map = get_eod_card_data_for_screener(turso, st.session_state.curated_tickers, benchmark_date_str, logger)
                for tkr in st.session_state.curated_tickers:
                    if tkr not in eod_map: continue
                    strat = eod_map.get(tkr, {}).get("screener_briefing_text", "N/A")
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    
                    if price:
                        df = get_session_bars_from_db(turso, tkr, benchmark_date_str, simulation_cutoff_str, logger)
                        if df is not None:
                            processed_data = process_session_data_to_summary(tkr, df, price, logger)
                            
                            xray_data.append({
                                "Ticker": tkr,
                                "Price": f"${price:.2f}",
                                "Slope": processed_data["slope"],
                                "High Dwell": processed_data["time_zone"],
                            })

                            dossiers.append(f"TICKER: {tkr}\n[STRATEGY]:\n{strat}\n[TACTICS]:\n{processed_data['summary_text']}\n---")
                            live_stats_log.append(processed_data["summary_text"])

                st.session_state.xray_snapshot = xray_data
                status.update(label="Data Gathered", state="complete")

            if xray_data:
                st.info("🔍 **Tactical X-Ray:**")
                st.dataframe(pd.DataFrame(xray_data), use_container_width=True)

            if dossiers:
                with st.expander("📂 View Dossiers Sent to Head Trader"):
                    st.text("\n".join(dossiers))

            with st.spinner(f"Head Trader Categorizing ({selected_model})..."):
                prompt = (
                    "[INPUTS]\n"
                    f"Macro: {json.dumps(st.session_state.premarket_economy_card)}\n"
                    f"Focus: {focus_input}\n"
                    f"DOSSIERS:\n{''.join(dossiers)}\n"
                    "Task: Triage into Tiers 1/2/3."
                )

                briefing, error_msg = call_gemini_with_rotation(prompt, "You are an elite Head Trader.", logger, selected_model, st.session_state.key_manager_instance)

                if briefing:
                    st.session_state.final_briefing = briefing
                    save_snapshot(turso, str(pm_news), st.session_state.premarket_economy_card, json.dumps(live_stats_log), briefing, logger)
                    st.success("Briefing Saved!")
                    st.rerun()
                else:
                    st.error(f"AI Failed: {error_msg}")

        if st.session_state.final_briefing:
            st.markdown(st.session_state.final_briefing)

if __name__ == "__main__":
    main()
