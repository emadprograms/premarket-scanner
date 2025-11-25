import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import json
import time
import re
from . import database as db
from . import processing
from . import gemini
from .utils import AppLogger

def setup_sidebar(logger: AppLogger):
    with st.sidebar:
        st.header("⚙️ Mission Config")

        if gemini.KEY_MANAGER_INSTANCE:
            st.success("✅ Key Manager: Active")
        else:
            st.error("❌ Key Manager: Failed")

        selected_model = st.selectbox(
            "AI Model",
            gemini.AVAILABLE_MODELS,
            index=0,
            help="Select the specific model to use for generation. This determines which Key Quota bucket is checked."
        )

        mode = st.radio("Operation Mode", ["Live", "Simulation"], index=0)

        if mode == "Live":
            simulation_cutoff_dt = datetime.now(timezone.utc)
            st.success("🟢 Live Mode Active")
            sim_date = simulation_cutoff_dt.date()
        else:
            st.warning("🟠 Simulation Mode")
            sim_date = st.date_input("Simulation Date")
            sim_time = st.time_input("Simulation Time (UTC)", value=datetime.strptime("13:00", "%H:%M").time())
            simulation_cutoff_dt = datetime.combine(sim_date, sim_time).replace(tzinfo=timezone.utc)
            st.info(f"Time Travel To: {simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        simulation_cutoff_str = simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
        analysis_date = sim_date
        st.write(f"Analysis Market Date: {analysis_date}")
        st.session_state.analysis_date = analysis_date

        return selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str

def render_step_1(turso, logger: AppLogger, selected_model: str, mode: str, simulation_cutoff_dt: datetime, simulation_cutoff_str: str):
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
            eod_placeholder.info("Waiting for EOD Card...")

    with col2:
        st.caption("3. Constructed AI Prompt")
        prompt_placeholder = st.empty()
        if st.session_state.glassbox_prompt:
            prompt_placeholder.text_area(
                "Prompt Preview",
                st.session_state.glassbox_prompt,
                height=150,
                key="glassbox_prompt_view"
            )
        else:
            prompt_placeholder.info("Waiting for final prompt construction...")

    st.caption("2. Intermarket Data Build (Updating Live)")
    etf_placeholder = st.empty()
    if st.session_state.glassbox_etf_data:
        etf_placeholder.dataframe(
            pd.DataFrame(st.session_state.glassbox_etf_data),
            use_container_width=True,
            column_config={
                "Freshness": st.column_config.ProgressColumn(
                    f"Freshness (vs {simulation_cutoff_dt.strftime('%H:%M')})",
                    help="Full Bar = Data is current to simulation time.",
                    format=" ",
                    min_value=0,
                    max_value=1,
                    width="small",
                ),
                "Audit: Date": st.column_config.TextColumn(
                    "Data Timestamp (UTC)",
                    help="Raw timestamp of the fetched price",
                ),
                "Audit: Bars": st.column_config.NumberColumn(
                    "Bars",
                    help="Number of 5m bars found for session",
                ),
            },
        )
    else:
        etf_placeholder.error(
            "🚨 **CRITICAL: NO LIVE DATA DETECTED**\n\n"
            "The system cannot find fresh market data for this timeframe in the database.\n\n"
            "**REQUIRED ACTIONS:**\n"
            "1. Navigate to the **Data Harvester** page.\n"
            "2. Run a fresh fetch for the Core Intermarket Tickers.\n"
            "3. Return here and click **'Generate Economy Card (Step 0)'**."
        )

    st.markdown("---")

    if st.button("Generate Economy Card (Step 0)", key="btn_step0", type="primary"):
        st.session_state.glassbox_etf_data = []
        st.session_state.audit_logs = []
        etf_placeholder.empty()

        with st.status(f"Running Macro Scan ({mode})...", expanded=True) as status:
            status.write("Fetching EOD Card...")

            if mode == "Simulation":
                eod_search_date = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                eod_search_date = simulation_cutoff_dt.strftime('%Y-%m-%d')

            latest_date = db.get_latest_economy_card_date(turso, simulation_cutoff_str, logger)
            eod_card = db.get_eod_economy_card(turso, latest_date, logger) if latest_date else {}

            st.session_state.glassbox_eod_card = eod_card
            eod_placeholder.json(eod_card, expanded=False)

            status.write("Scanning Intermarket Tickers...")
            etf_summaries = []
            benchmark_date_str = st.session_state.analysis_date.isoformat()

            CORE_INTERMARKET_TICKERS = [
                "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
                "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
                "UUP", "XLC", "XLF", "XLI", "XLP",
                "XLU", "XLV", "NDAQ", "^VIX"
            ]

            for epic in CORE_INTERMARKET_TICKERS:
                latest_price, price_ts = processing.get_latest_price_details(turso, epic, simulation_cutoff_str, logger)

                if latest_price:
                    df = processing.get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                    bar_count = len(df) if df is not None else 0

                    freshness_score = 0.0
                    try:
                        if price_ts:
                            ts_clean = price_ts.replace("Z", "+00:00").replace(" ", "T")
                            ts_obj = datetime.fromisoformat(ts_clean)
                            if ts_obj.tzinfo is None:
                                ts_obj = ts_obj.replace(tzinfo=timezone.utc)
                            lag_minutes = (simulation_cutoff_dt - ts_obj).total_seconds() / 60.0
                            freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                    except Exception:
                        freshness_score = 0.0

                    if df is not None:
                        processed_data = processing.process_session_data_to_summary(
                            epic,
                            df,
                            latest_price,
                            logger,
                        )
                        summary_text = processed_data["summary_text"]
                        etf_summaries.append(summary_text)

                        new_row = {
                            "Ticker": epic,
                            "Price": f"${latest_price:.2f}",
                            "Freshness": freshness_score,
                            "Audit: Date": f"{price_ts} (UTC)",
                            "Audit: Bars": bar_count,
                            "PM VWAP": f"${processed_data['pm_vwap']:.2f}",
                            "Signal": processed_data["divergence"],
                        }
                        st.session_state.glassbox_etf_data.append(new_row)

                        etf_placeholder.dataframe(
                            pd.DataFrame(st.session_state.glassbox_etf_data),
                            use_container_width=True,
                            column_config={
                                "Freshness": st.column_config.ProgressColumn(
                                    f"Freshness (vs {simulation_cutoff_dt.strftime('%H:%M')})",
                                    help="Full Bar = Data is current to simulation time.",
                                    format=" ",
                                    min_value=0,
                                    max_value=1,
                                    width="small",
                                ),
                                "Audit: Date": st.column_config.TextColumn(
                                    "Data Timestamp (UTC)",
                                    help="Raw timestamp of the fetched price",
                                ),
                                "Audit: Bars": st.column_config.NumberColumn(
                                    "Bars",
                                    help="Number of 5m bars found for session",
                                ),
                            },
                        )
                        time.sleep(0.02)

            if not etf_summaries:
                status.update(label="Scan Aborted: No Data", state="error", expanded=True)
                st.error(
                    "🚨 **ABORTING: NO LIVE DATA DETECTED**\n\n"
                    "The system scanned for Core Intermarket Tickers but found **zero** valid data points for this timeframe.\n\n"
                    "**API CALL BLOCKED:** The AI generation has been stopped to save credits.\n\n"
                    "**REQUIRED ACTIONS:**\n"
                    "1. Navigate to the **Data Harvester** page.\n"
                    "2. Run a fresh fetch for the Core Intermarket Tickers.\n"
                    "3. Return here and try again."
                )
                st.stop()

            status.write("Synthesizing AI Prompt...")
            mode_str = f"PRE-MARKET PREP ({mode})"
            prompt = f"""
            [INPUTS]
            EOD Context: {json.dumps(eod_card)}
            Live Intermarket Data: {etf_summaries}
            News: {pm_news}
            Mode: {mode_str}
            [TASK] Act as Macro Strategist. Synthesize EOD Context + Live Data + News.
            """
            st.session_state.glassbox_prompt = prompt
            prompt_placeholder.text_area("Prompt Preview", prompt, height=150, key="glassbox_prompt_preview")

            status.write(f"Calling Gemini ({selected_model})...")
            system_prompt = (
                "You are an expert Macro Strategist. Output valid JSON only with "
                "keys: marketNarrative, marketBias, sectorRotation."
            )

            resp, error_msg = gemini.call_gemini_with_rotation(
                prompt=prompt,
                system_prompt=system_prompt,
                logger=logger,
                model_name=selected_model
            )

            if resp:
                try:
                    json_match = re.search(r"(\{.*\})", resp, re.DOTALL)
                    json_str = json_match.group(1) if json_match else resp
                    new_card = json.loads(json_str)
                    new_card['date'] = st.session_state.analysis_date.isoformat()
                    st.session_state.premarket_economy_card = new_card
                    st.session_state.latest_macro_date = new_card['date']
                    status.update(
                        label="Macro Card Generated",
                        state="complete",
                        expanded=False,
                    )
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

    st.markdown("---")
    st.header("B. Proximity Scan (Step 1)")
    pct_threshold = st.slider("Proximity %", 0.1, 5.0, 2.5)
    if st.button("Run Proximity Scan"):
        if not st.session_state.latest_macro_date:
            st.error("Generate Macro Card first.")
            st.stop()

        benchmark_date_for_scan = st.session_state.latest_macro_date

        with st.status(f"Scanning Market ({mode})...", expanded=True) as status:
            tickers = db.get_all_tickers_from_db(turso, logger)

            eod_data = db.get_eod_card_data_for_screener(
                turso,
                tickers,
                benchmark_date_for_scan,
                logger,
            )
            results = []
            for tkr, data in eod_data.items():
                price, _ = processing.get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)

                if not price:
                    continue
                levels = [l for l in data['s_levels'] + data['r_levels'] if l > 0]
                if not levels:
                    continue
                dist = min([abs(price - l) / l for l in levels]) * 100
                if dist <= pct_threshold:
                    results.append(
                        {
                            "Ticker": tkr,
                            "Price": f"${price:.2f}",
                            "Dist%": f"{dist:.2f}",
                        }
                    )
            st.session_state.proximity_scan_results = sorted(
                results,
                key=lambda x: float(x['Dist%']),
            )
            status.update(label="Scan Complete", state="complete", expanded=False)
            st.rerun()

    if st.session_state.proximity_scan_results:
        df_res = pd.DataFrame(st.session_state.proximity_scan_results)
        st.dataframe(df_res, use_container_width=True)
        opts = [r['Ticker'] for r in st.session_state.proximity_scan_results]
        st.session_state.curated_tickers = st.multiselect(
            "Curate List",
            opts,
            default=opts,
        )

def render_step_2(turso, logger: AppLogger, selected_model: str, simulation_cutoff_str: str):
    st.header("Step 2: Head Trader Synthesis")

    if not st.session_state.curated_tickers:
        st.warning("Complete Step 1 first.")
        st.stop()

    focus_input = st.text_area("Executor's Focus", height=80)

    if st.button("Run Synthesis", type="primary"):
        benchmark_date_str = st.session_state.analysis_date.isoformat()
        xray_data = []
        dossiers = []
        live_stats_log = []

        with st.status("Processing...", expanded=True) as status:
            eod_map = db.get_eod_card_data_for_screener(
                turso,
                st.session_state.curated_tickers,
                benchmark_date_str,
                logger,
            )

            for tkr in st.session_state.curated_tickers:
                if tkr not in eod_map:
                    continue

                strat = eod_map.get(tkr, {}).get("screener_briefing_text", "N/A")

                price, _ = processing.get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)

                if price:
                    df = processing.get_session_bars_from_db(
                        turso,
                        tkr,
                        benchmark_date_str,
                        simulation_cutoff_str,
                        logger,
                    )
                    if df is not None:
                        processed_data = processing.process_session_data_to_summary(
                            tkr,
                            df,
                            price,
                            logger,
                        )

                        xray_data.append(
                            {
                                "Ticker": tkr,
                                "Mode": processed_data["mode"],
                                "Price": f"${price:.2f}",
                                "PM VWAP": f"${processed_data['pm_vwap']:.2f}",
                                "Signal": processed_data["divergence"],
                            }
                        )

                        dossiers.append(
                            f"TICKER: {tkr}\n[STRATEGY]:\n{strat}\n"
                            f"[TACTICS]:\n{processed_data['summary_text']}\n---"
                        )

                        live_stats_log.append(processed_data["summary_text"])

            st.session_state.xray_snapshot = xray_data
            status.update(label="Data Gathered", state="complete")

        if xray_data:
            st.info("🔍 **Tactical X-Ray:**")
            st.dataframe(pd.DataFrame(xray_data), use_container_width=True)

        with st.spinner(f"Head Trader Categorizing ({selected_model})..."):
            prompt = (
                "[INPUTS]\n"
                f"Macro: {json.dumps(st.session_state.premarket_economy_card)}\n"
                f"Focus: {focus_input}\n"
                f"DOSSIERS:\n{''.join(dossiers)}\n"
                "Task: Triage into Tiers 1/2/3."
            )

            briefing, error_msg = gemini.call_gemini_with_rotation(
                prompt,
                "You are an elite Head Trader.",
                logger,
                selected_model
            )

            if briefing:
                st.session_state.final_briefing = briefing

                db.save_snapshot(
                    turso,
                    str(st.session_state.get("pm_news_input", "")),
                    st.session_state.premarket_economy_card,
                    json.dumps(live_stats_log),
                    briefing,
                    logger,
                )

                st.success("Briefing Saved!")
                st.rerun()
            else:
                st.error(f"AI Failed: {error_msg}")

    if st.session_state.final_briefing:
        st.markdown(st.session_state.final_briefing)

def render_log_container():
    st.markdown("---")
    st.subheader("Live Logs")
    log_container = st.container(height=200)
    st.session_state.app_logger.container = log_container
    st.session_state.app_logger.flush()
