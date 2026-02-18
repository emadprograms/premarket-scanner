import streamlit as st
import pandas as pd
import json
import time
import concurrent.futures
import re
from backend.engine.time_utils import to_et, now_et, get_staleness_score, format_time_et
from archive.legacy_streamlit.ui.common import AuditLogger, display_view_economy_card, render_lightweight_chart_simple
from backend.engine.database import get_latest_economy_card_date, get_eod_economy_card
from backend.engine.processing import get_session_bars_routed, get_previous_session_stats
from backend.engine.sentiment_engine import analyze_headline_sentiment
from backend.engine.gemini import call_gemini_with_rotation

def analyze_macro_worker(ticker, df, turso, benchmark_date_str, simulation_cutoff_dt, mode, session_start_dt=None):
    """Worker for Macro Indices."""
    try:
        from backend.engine.processing import analyze_market_context
        latest_row = df.iloc[-1]
        latest_price = latest_row['Close']
        p_ts = latest_row['timestamp']
        
        ref_levels = get_previous_session_stats(turso, ticker, benchmark_date_str, logger=None)
        card = analyze_market_context(df, ref_levels, ticker=ticker, session_start_dt=session_start_dt)
        
        mig_count = len(card.get('value_migration_log', []))
        imp_count = len(card.get('key_level_rejections', []))
        
        freshness = 0.0
        lag_min = 999.0
        try:
            if p_ts:
                lag_min = get_staleness_score(p_ts)
                freshness = max(0.0, 1.0 - (lag_min / 60.0))
        except Exception: pass

        data_source = df['source'].iloc[0] if 'source' in df.columns else ('Capital.com' if mode == 'Live' else 'DB')
        ts_utc = str(df['dt_utc'].iloc[-1]) if 'dt_utc' in df.columns else str(p_ts)
        freshness_progress = max(0.0, 1.0 - (lag_min / 60.0))
        
        return {
            "ticker": ticker, "card": card, "latest_price": latest_price, "latest_ts_utc": ts_utc,
            "data_source": data_source, "mig_count": mig_count, "imp_count": imp_count,
            "freshness_score": freshness_progress, "lag_min": lag_min, "df": df
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "failed_analysis": True}

def run_macro_synthesis(status_obj, eod_card, news_text, bench_date, logger_obj, model_name, km_instance):
    """Reusable block for Macro Integrity Lab Gemini Synthesis."""
    from backend.engine.analysis.macro_engine import generate_economy_card_prompt
    status_obj.write("4. Synthesizing Macro Narrative (Gemini Masterclass)...")
    rolling_log = eod_card.get('keyActionLog', []) if eod_card else []

    summarized_context = None
    if len(rolling_log) > 10:
        status_obj.write("   📜 Summarizing Long Market History...")
        summary_prompt = f"Summarize the following market log into a concise 'Macro Arc':\n{json.dumps(rolling_log, indent=2)}"
        try:
            sum_resp, _ = call_gemini_with_rotation(summary_prompt, "Summarize History", logger_obj, model_name, km_instance)
            if sum_resp: summarized_context = sum_resp
        except: pass

    # --- Automated Sentiment Engine ---
    sentiment_results = None
    if news_text and len(news_text) > 50:
        status_obj.write("   🧠 Analyzing Sentiment of Headlines...")
        sentiment_results = analyze_headline_sentiment(news_text, model_name, km_instance, logger_obj)
        if sentiment_results:
            logger_obj.success(f"Sentiment Analysis Complete: {sentiment_results.get('overall_sentiment', 0)}")

    macro_prompt, macro_system = generate_economy_card_prompt(
        eod_card=eod_card,
        etf_structures=[json.loads(s) for s in st.session_state.macro_etf_structures],
        news_input=news_text,
        analysis_date_str=bench_date,
        logger=logger_obj,
        rolling_log=rolling_log,
        pre_summarized_context=summarized_context,
        sentiment_data=sentiment_results
    )
    st.session_state.glassbox_prompt = macro_prompt
    st.session_state.glassbox_prompt_system = macro_system

    resp, error_msg = call_gemini_with_rotation(macro_prompt, macro_system, logger_obj, model_name, km_instance)
    if resp:
        try:
            clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
            st.session_state.premarket_economy_card = json.loads(clean)
            st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
            logger_obj.log("✅ Step 1: Synthesis Complete.")
            status_obj.update(label="Step 1 Complete!", state="complete")
        except Exception as e: st.error(f"JSON Parse Error: {e}")
    else: st.error(error_msg)

def render_step_macro(turso, mode, simulation_cutoff_dt, simulation_cutoff_str, benchmark_date_str, selected_model, CORE_INTERMARKET_TICKERS):
    """Renders Step 1: Macro Context Tab."""
    st.header("Step 1: Macro Context Analysis")
    st.caption("📝 Overnight News / Context")
    pm_news = st.text_area("Paste relevant headlines/catalysts here...", height=100, key="pm_news_input", label_visibility="collapsed")
    st.info("ℹ️ **Engine Inputs**: Synthesis uses **Overnight News**, the latest **Strategic Plan** from DB, and structural scans of **20+ Indices**.")
    
    def clear_step1_state():
        st.session_state.macro_index_data = []
        st.session_state.macro_raw_dfs = {}
        st.session_state.macro_etf_structures = []
        st.session_state.macro_context_alerts = {}
        st.session_state.macro_stale_alerts = []
        st.session_state.step1_data_ready = False
        st.session_state.premarket_economy_card = None 
        st.session_state.macro_audit_log = []
        st.session_state.macro_audit_log_has_errors = False
        st.session_state.macro_missing_tickers = []
        st.session_state.macro_analysis_failures = []

    if st.button("✨ Run Step 1: Full Analysis", type="primary", on_click=clear_step1_state):
        with st.status(f"Fetching Macro Data...", expanded=True) as status:
            a_logger = AuditLogger('macro_audit_log')
            a_logger.log("🚀 Starting Macro Scan 1a...")
            status.write("1. Retrieving End-of-Day Context...")
            lookup_cutoff = (simulation_cutoff_dt).strftime('%Y-%m-%d %H:%M:%S')
            latest_date = get_latest_economy_card_date(turso, lookup_cutoff, st.session_state.app_logger)
            
            eod_card = {}
            if latest_date:
                status.write(f"   ✅ Found Strategic Plan from: **{latest_date}**")
                data = get_eod_economy_card(turso, latest_date, st.session_state.app_logger)
                if data: 
                    eod_card = data
                    st.session_state.glassbox_eod_date = latest_date
            else:
                status.write("   ⚠️ No Strategic Plan found for this window.")
                st.error("Stopping: Strategic Plan (EOD Card) is required for context.")
                status.update(label="Missing Context", state="error")
                st.stop()
            st.session_state.glassbox_eod_card = eod_card

            status.write("2. Gathering Market Data (Sequential Fetches)...")
            raw_datafeeds = {}
            st.session_state.macro_missing_tickers = []
            progress_bar = st.progress(0)
            for idx, t in enumerate(CORE_INTERMARKET_TICKERS):
                df, staleness = get_session_bars_routed(turso, t, benchmark_date_str, simulation_cutoff_str, mode=mode, logger=a_logger, db_fallback=st.session_state.get('db_fallback', False), days=2.9, resolution="MINUTE_5")
                if df is not None and not df.empty: raw_datafeeds[t] = df
                else:
                    st.session_state.macro_missing_tickers.append(t)
                    a_logger.error(f"{t}: Failed to fetch data.")
                
                if mode == "Live" and not st.session_state.get('db_fallback', False): time.sleep(1)
                progress_bar.progress((idx + 1) / len(CORE_INTERMARKET_TICKERS))

            status.write("3. Analyzing Market Structure (Parallel Engine)...")
            session_start_dt = simulation_cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0)
            macro_results = []
            st.session_state.macro_analysis_failures = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(analyze_macro_worker, t, df, turso, benchmark_date_str, simulation_cutoff_dt, mode, session_start_dt) for t, df in raw_datafeeds.items()]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res:
                        if res.get('failed_analysis'):
                            st.session_state.macro_analysis_failures.append(res['ticker'])
                            a_logger.log(f"⚠️ {res['ticker']}: Analysis Failure - {res['error']}")
                        else: macro_results.append(res)
            
            macro_results = sorted(macro_results, key=lambda x: x['ticker'])
            analysis_date_str = st.session_state.analysis_date.strftime('%Y-%m-%d')
            context_map = {}
            for r in macro_results:
                if r['latest_ts_utc'] != "N/A":
                    dt_str = r['latest_ts_utc'][:10]
                    if dt_str != analysis_date_str:
                        if dt_str not in context_map: context_map[dt_str] = []
                        context_map[dt_str].append(r['ticker'])
            if context_map:
                st.session_state.macro_context_alerts = context_map
            
            stale_1h = [r['ticker'] for r in macro_results if r['lag_min'] > 60]
            if stale_1h: st.session_state.macro_stale_alerts = stale_1h

            for res in macro_results:
                st.session_state.macro_etf_structures.append(json.dumps(res['card']))
                st.session_state.macro_raw_dfs[res['ticker']] = res['df']
                st.session_state.macro_index_data.append({"Ticker": res['ticker'], "Freshness": res['freshness_score'], "Price": f"${res['latest_price']:.2f}", "Timestamp (UTC)": res['latest_ts_utc'], "Lag (m)": f"{res['lag_min']:.1f}", "Source": res['data_source']})

            if not st.session_state.macro_etf_structures:
                status.update(label="Aborted: No Data", state="error")
                st.stop()
            
            st.session_state.step1_data_ready = True
            if (st.session_state.macro_missing_tickers or st.session_state.macro_analysis_failures or stale_1h):
                status.update(label="⚠️ Gaps/Stale Data Detected", state="error")
                st.rerun()
            else:
                run_macro_synthesis(status, eod_card, pm_news, benchmark_date_str, st.session_state.app_logger, selected_model, st.session_state.key_manager_instance)
                st.rerun()

    st.markdown("---")
    if st.session_state.step1_data_ready:
        if not st.session_state.premarket_economy_card: st.markdown("### 🔍 Data Integrity Verification")
        else: st.markdown("### ✅ Macro Context Results")

        has_critical_gaps = bool(st.session_state.macro_missing_tickers) or bool(st.session_state.macro_analysis_failures)
        has_stale_data = bool(st.session_state.get('macro_stale_alerts'))
        
        if (has_critical_gaps or has_stale_data) and not st.session_state.premarket_economy_card:
            if has_critical_gaps: st.error("🚨 **Gaps Detected in Market Data**")
            if has_stale_data: st.warning(f"⏰ **Stale Data Alert**: {', '.join(st.session_state.macro_stale_alerts or [])}")
            st.info("💡 **Decision Required**: Synthesis is paused.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🚀 Proceed Anyway", type="primary", width="stretch"):
                    with st.status("Manual Synthesis Triggered...", expanded=True) as status_man:
                        run_macro_synthesis(status_man, st.session_state.glassbox_eod_card, st.session_state.pm_news_input, benchmark_date_str, st.session_state.app_logger, selected_model, st.session_state.key_manager_instance)
                        st.rerun()
            with c2:
                if st.button("🔄 Clean & Retry", type="secondary", width="stretch"):
                    clear_step1_state(); st.rerun()

        if st.session_state.premarket_economy_card:
            display_view_economy_card(st.session_state.premarket_economy_card)
            with st.expander("📝 Summary Table & Details", expanded=False):
                st.dataframe(pd.DataFrame(st.session_state.macro_index_data))
                if st.session_state.macro_raw_dfs:
                    for t, df in st.session_state.macro_raw_dfs.items():
                        st.markdown(f"**{t}**")
                        render_lightweight_chart_simple(df, t, height=200)
