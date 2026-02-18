import streamlit as st
import pandas as pd
import json
import concurrent.futures
from backend.engine.time_utils import to_et, now_et, get_staleness_score
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from archive.legacy_streamlit.ui.common import AuditLogger, render_market_structure_chart
from backend.engine.database import get_eod_card_data_for_screener, save_deep_dive_card
from backend.engine.processing import get_session_bars_routed, get_previous_session_stats
from backend.engine.analysis.detail_engine import update_company_card

def analyze_ticker_unified_worker(ticker_to_scan, turso, benchmark_date_str, simulation_cutoff_str, simulation_cutoff_dt, mode, scan_threshold, st_ctx=None):
    """Unified Worker: Fetches AND analyzes data in parallel."""
    if st_ctx: add_script_run_ctx(ctx=st_ctx)
    try:
        df, staleness = get_session_bars_routed(turso, ticker_to_scan, benchmark_date_str, simulation_cutoff_str, mode=mode, logger=None, db_fallback=st.session_state.get('db_fallback', False), premarket_only=False, days=2.9, resolution="MINUTE_5")
        if df is None or df.empty: return {"ticker": ticker_to_scan, "error": "Fetch failed", "missing_data": True}
        
        from backend.engine.processing import analyze_market_context
        latest_row = df.iloc[-1]
        l_price = float(latest_row['Close'])
        p_ts = latest_row['timestamp'] if 'timestamp' in df.columns else latest_row.get('dt_eastern')
        
        ref_levels = get_previous_session_stats(turso, ticker_to_scan, benchmark_date_str, logger=None)
        card = analyze_market_context(df, ref_levels, ticker=ticker_to_scan, session_start_dt=simulation_cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0))
        
        mig_count = len(card.get('value_migration_log', []))
        imp_count = len(card.get('key_level_rejections', []))
        
        l_minutes = 999.0; freshness_p = 0.0
        if p_ts:
            l_minutes = get_staleness_score(p_ts)
            freshness_p = max(0.0, 1.0 - (l_minutes / 60.0))

        prox_alert = None
        plan_data = st.session_state.db_plans.get(ticker_to_scan)
        if plan_data:
            levels = [(lvl, "SUPPORT") for lvl in plan_data.get('s_levels', [])] + [(lvl, "RESISTANCE") for lvl in plan_data.get('r_levels', [])]
            best_dist = float('inf')
            for lvl, l_type in levels:
                dist_pct = abs(l_price - lvl) / l_price * 100
                if dist_pct <= scan_threshold and dist_pct < best_dist:
                    best_dist = dist_pct
                    prox_alert = {"Ticker": ticker_to_scan, "Price": f"${l_price:.2f}", "Type": l_type, "Level": lvl, "Dist %": round(dist_pct, 2), "Source": f"Plan {plan_data.get('plan_date')}"}

        ts_u = str(df['dt_utc'].iloc[-1]) if 'dt_utc' in df.columns else str(p_ts)
        return {
            "ticker": ticker_to_scan, "card": card, "prox_alert": prox_alert, "lag_min": l_minutes, "latest_ts_utc": ts_u,
            "table_row": {"Ticker": ticker_to_scan, "Freshness": freshness_p, "Price": f"${l_price:.2f}", "Timestamp (UTC)": ts_u, "Lag (m)": f"{l_minutes:.1f}" if p_ts else "N/A", "Migration Blocks": mig_count, "Impact Levels": imp_count}
        }
    except Exception as e: return {"ticker": ticker_to_scan, "error": str(e), "failed_analysis": True}

def process_deep_dive(ticker, turso, key_mgr, macro_summary, date_obj, model, static_data, st_status, st_ctx):
    """Worker for Deep Dive AI Analysis."""
    if st_ctx: add_script_run_ctx(ctx=st_ctx)
    class StreamlitThreadLogger:
        def __init__(self, tkr, status): self.ticker = tkr; self.status = status
        def log(self, msg):
            colors = ["blue", "green", "orange", "red", "violet", "gray"]
            t_color = colors[hash(self.ticker) % len(colors)]
            self.status.write(f"**:{t_color}[{self.ticker}]** {msg}")
    local_logger = StreamlitThreadLogger(ticker, st_status)
    try:
        data = static_data.get(ticker, {})
        json_result = update_company_card(ticker=ticker, previous_card_json=data.get("previous_card", "{}"), previous_card_date=str(date_obj - timedelta(days=1)), historical_notes="", new_eod_summary="", new_eod_date=date_obj, model_name=model, key_manager=key_mgr, pre_fetched_context=data.get("impact_context", "{}"), market_context_summary=macro_summary, logger=local_logger)
        if json_result: save_deep_dive_card(turso, ticker, str(date_obj), json_result, local_logger)
        return ticker, json_result
    except Exception as e:
        local_logger.log(f"❌ Worker EXCEPTION: {e}")
        return ticker, None

def render_step_scanner(turso, mode, simulation_cutoff_dt, simulation_cutoff_str, benchmark_date_str, selected_model, fetch_watchlist):
    """Renders Step 2: Selection Hub Tab."""
    st.title("Step 2: Selection Hub")
    with st.expander("🧠 Deep Preparation: Masterclass Model (Optional)"):
        watchlist = fetch_watchlist(turso, st.session_state.app_logger)
        selected_deep_dive = st.multiselect("Tickers for deep-dive Preparation:", sorted(list(set(watchlist))), key="deep_dive_multiselect")
        if st.button("Generate Detailed Preparation Cards"):
            if not st.session_state.premarket_economy_card: st.warning("⚠️ Step 1 first."); st.stop()
            pre_fetched_data = {}
            from backend.engine.analysis.impact_engine import get_or_compute_context
            with st.status("Fetching Data Context...") as status_io:
                for ticker in selected_deep_dive:
                    context_card = get_or_compute_context(turso, ticker, str(st.session_state.analysis_date), st.session_state.app_logger)
                    pre_fetched_data[ticker] = {"impact_context": json.dumps(context_card), "previous_card": "{}"}
            
            deep_results = {}
            ctx = get_script_run_ctx()
            with st.status("Generating Cards...") as status_deep:
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    futures = {executor.submit(process_deep_dive, t, turso, st.session_state.key_manager_instance, json.dumps(st.session_state.premarket_economy_card), st.session_state.analysis_date, selected_model, pre_fetched_data, status_deep, ctx): t for t in selected_deep_dive}
                    for future in concurrent.futures.as_completed(futures):
                        tkr, res = future.result()
                        if res: deep_results[tkr] = json.loads(res)
            st.session_state.detailed_premarket_cards.update(deep_results); st.rerun()

    st.subheader("Unified Selection Scanner")
    prox_col1, prox_col2 = st.columns([2, 1])
    scan_threshold = prox_col1.slider("Proximity %", 0.1, 5.0, 2.5)
    if prox_col2.button("Run Unified Selection Scan", type="primary", width="stretch"):
        if not st.session_state.premarket_economy_card: st.warning("⚠️ Step 1 first.")
        else:
            st.session_state.glassbox_etf_data = []; st.session_state.glassbox_raw_cards = {}; st.session_state.proximity_scan_results = []
            with st.status("Running Unified Scan...") as status:
                u_logger = AuditLogger('unified_audit_log')
                watchlist = fetch_watchlist(turso, u_logger)
                full_ticker_list = sorted(list(set(watchlist)))
                st.session_state.db_plans = get_eod_card_data_for_screener(turso, tuple(full_ticker_list), st.session_state.analysis_date.strftime('%Y-%m-%d'), u_logger)
                ctx = get_script_run_ctx()
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(analyze_ticker_unified_worker, t, turso, benchmark_date_str, simulation_cutoff_str, simulation_cutoff_dt, mode, scan_threshold, ctx): t for t in full_ticker_list}
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        if res and not res.get('error'):
                            st.session_state.glassbox_raw_cards[res['ticker']] = res['card']
                            st.session_state.glassbox_etf_data.append(res['table_row'])
                            if res['prox_alert']: st.session_state.proximity_scan_results.append(res['prox_alert'])
            st.session_state.glassbox_etf_data = sorted(st.session_state.glassbox_etf_data, key=lambda x: x['Ticker']); st.rerun()

    if st.session_state.glassbox_etf_data:
        st.dataframe(pd.DataFrame(st.session_state.glassbox_etf_data), width="stretch")
    if st.session_state.proximity_scan_results:
        st.success(f"🎯 {len(st.session_state.proximity_scan_results)} Proximity Alerts")
        st.dataframe(pd.DataFrame(st.session_state.proximity_scan_results).sort_values("Dist %"), width="stretch")
    if st.session_state.glassbox_raw_cards:
        with st.expander("🔍 View Charts"):
            for tkr in sorted(st.session_state.glassbox_raw_cards.keys()):
                st.plotly_chart(render_market_structure_chart(st.session_state.glassbox_raw_cards[tkr]), width="stretch")
