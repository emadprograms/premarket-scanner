import streamlit as st
import pandas as pd
import json
import re
import time
import random
from datetime import datetime

# --- Import from our new modules ---
try:
    from premarket_modules import config
    from premarket_modules.ui_components import (
        AppLogger,
        create_capital_session
    )
    from premarket_modules.db_utils import (
        create_turso_client,
        get_latest_economy_card_date,
        get_all_tickers_from_db,
        get_eod_card_data_for_screener, # This function implements the "Date Alignment"
        save_screener_output
    )
    from premarket_modules.data_processing import (
        get_capital_current_price, 
        get_capital_price_bars, 
        process_premarket_bars_to_summary
    )
    from premarket_modules.ai_services import (
        generate_premarket_economy_card_orchestrator,
        run_tactical_screener_orchestrator
    )
    
except ImportError as e:
    st.error(f"Error: Missing a required module. Please ensure all files are in `premarket_modules`. Details: {e}")
    st.stop()

# ---
# --- Initialize Session State
# ---
if 'capital_session' not in st.session_state:
    st.session_state.capital_session = {"cst": None, "xst": None}
if 'premarket_economy_card' not in st.session_state:
    st.session_state.premarket_economy_card = None
if 'latest_macro_date' not in st.session_state:
    st.session_state.latest_macro_date = None # Store the benchmark date
if 'proximity_scan_results' not in st.session_state:
    st.session_state.proximity_scan_results = []
if 'curated_tickers_for_screener' not in st.session_state:
    st.session_state.curated_tickers_for_screener = []
if 'premarket_screener_output' not in st.session_state:
    st.session_state.premarket_screener_output = None
if 'app_logger' not in st.session_state:
    # Initialize a dummy logger. The real one is set in the 'Logs' tab.
    st.session_state.app_logger = AppLogger(st.empty()) 

# --- === Main Application UI === ---
st.set_page_config(page_title="Pre-Market Analyst", layout="wide")
st.title("Pre-Market Analyst Workbench")

# --- Authentication Check (Capital.com) ---
if not st.session_state.capital_session.get("cst"):
    st.warning("You must be logged in to Capital.com to use the app.")
    auth_logger_container = st.expander("Logs", True)
    auth_logger = AppLogger(auth_logger_container)
    if st.button("Create Capital.com Session", use_container_width=True):
        cst, xst = create_capital_session(auth_logger)
        if cst and xst:
            st.session_state.capital_session = {"cst": cst, "xst": xst}
            st.rerun()
    st.stop()

# --- Main App Tabs ---
tab_preflight, tab_screener, tab_logs = st.tabs([
    "Step 1: Pre-Flight Check (Macro & Curation)", 
    "Step 2: Tactical Screener (Rank & Justify)",
    "Logs & Saved Briefings"
])

# --- TAB 3: Full Logs (Define Logger First) ---
with tab_logs:
    st.header("Full Application Logs")
    log_container = st.container(height=600)
    # This assigns the "real" logger for all other modules to use
    st.session_state.app_logger = AppLogger(log_container) 

# Use the globally accessible logger
logger = st.session_state.app_logger

# ---
# --- TAB 1: Pre-Flight Check (Step 0 & 1)
# ---
with tab_preflight:
    st.header("Step 1: Pre-Flight Check")
    
    # --- Step 0: Generate Pre-Market Economy Card ---
    st.subheader("A. Generate 'Macro Why' (Step 0)")
    with st.container(border=True):
        premarket_macro_news_input = st.text_area(
            "Enter Pre-Market Macro News (The 'Why'):", 
            placeholder="e.g., UK CPI hotter than expected, German ZEW survey weak, Trump tariff threats on XLI...", 
            height=100, 
            key="pm_macro_news"
        )
        
        if st.button("Generate Pre-Market Economy Card", use_container_width=True, key="gen_pm_eco_card"):
            logger.log("Button clicked: 'Generate Pre-Market Economy Card'")
            with st.spinner("Generating 'Macro Why'... (LLM Call #1)"):
                cst = st.session_state.capital_session.get("cst")
                xst = st.session_state.capital_session.get("xst")
                api_key = random.choice(config.API_KEYS)
                
                # Create a Turso client for this operation
                turso_client = create_turso_client(logger)
                
                if cst and xst and api_key and turso_client:
                    new_economy_card = generate_premarket_economy_card_orchestrator(
                        turso_client=turso_client, 
                        premarket_macro_news=premarket_macro_news_input,
                        logger=logger,
                        cst=cst,
                        xst=xst,
                        api_key=api_key # Pass the simple random key
                    )
                    
                    st.session_state.premarket_economy_card = new_economy_card
                    
                    if new_economy_card:
                        logger.log("--- Success: Pre-Market Economy Card generated and saved to session state. ---")
                        # Also save the benchmark date
                        st.session_state.latest_macro_date = new_economy_card.get('date')
                    else:
                        logger.log("--- Error: Failed to generate Pre-Market Economy Card. AI returned None. ---")
                    
                    st.rerun()
                else:
                    logger.log("Error: Missing CST, XST, API Key, or Turso Client. Cannot generate card.")

    # Display the generated card for confirmation
    if st.session_state.premarket_economy_card:
        st.success("Pre-Market Economy Card is loaded.")
        with st.expander("View Generated Pre-Market Economy Card", expanded=False):
            st.json(st.session_state.premarket_economy_card)
    else:
        st.info("Pre-Market Economy Card has not been generated yet.")

    st.markdown("---")

    # --- Step 1: Proximity Scan & Curation ---
    st.subheader("B. Find & Curate 'In-Play' Stocks (Step 1)")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            proximity_pct = st.slider("Proximity Filter (%)", 0.1, 10.0, 2.5, 0.1, help="Filter for stocks trading within this % distance of a major S/R level.")
        
        with col2:
            if st.button("Scan All Watchlist Tickers", use_container_width=True):
                # Prerequisite check: Must have Economy Card first to get date
                if not st.session_state.latest_macro_date:
                    st.error("Error: You must generate the Pre-Market Economy Card first to get the benchmark date.")
                    st.stop()
                
                with st.spinner("Scanning all tickers for proximity..."):
                    benchmark_date = st.session_state.latest_macro_date
                    
                    turso_client = create_turso_client(logger)
                    if not turso_client:
                        st.error("Failed to create Turso client. Check logs.")
                        st.stop()
                        
                    all_tickers = get_all_tickers_from_db(turso_client, logger)
                    if not all_tickers:
                        logger.log("Error: No tickers found in the database. Please add stocks to the 'stocks' table.")
                        st.warning("No tickers found in the database. Please add stocks to the 'stocks' table.")
                        st.stop()
                    
                    # This function now *only* returns in-sync stocks
                    eod_data_map = get_eod_card_data_for_screener(turso_client, all_tickers, benchmark_date, logger)
                    
                    scan_results = []
                    cst = st.session_state.capital_session["cst"]
                    xst = st.session_state.capital_session["xst"]
                    
                    # We only loop through the tickers that were in-sync
                    for i, ticker in enumerate(eod_data_map.keys()):
                        bid, offer = get_capital_current_price(ticker, cst, xst, logger)
                        if not bid:
                            continue 
                        
                        live_price = (bid + offer) / 2
                        eod_data = eod_data_map[ticker]
                        all_levels = eod_data.get('s_levels', []) + eod_data.get('r_levels', [])
                        
                        if not all_levels:
                            logger.log(f"Warn: Ticker {ticker} has no S/R levels. Skipping.")
                            continue 
                            
                        # Filter out level 0 to avoid ZeroDivisionError
                        all_levels = [lvl for lvl in all_levels if lvl != 0]
                        if not all_levels:
                            logger.log(f"Warn: Ticker {ticker} only has levels at 0. Skipping.")
                            continue

                        min_dist_pct = min([abs(live_price - level) / level for level in all_levels]) * 100
                        
                        if min_dist_pct <= proximity_pct:
                            scan_results.append({
                                "Ticker": ticker,
                                "Proximity (%)": f"{min_dist_pct:.2f}",
                                "Live Price": f"${live_price:.2f}"
                            })
                        if i < len(eod_data_map.keys()) - 1:
                            time.sleep(config.LOOP_DELAY)
                    
                    st.session_state.proximity_scan_results = sorted(scan_results, key=lambda x: float(x['Proximity (%)']))
                    logger.log(f"Proximity scan complete. Found {len(scan_results)} tickers in play.")
                    st.rerun()

    # Display scan results and curation form
    if st.session_state.proximity_scan_results:
        st.markdown("##### **Curation List**")
        st.dataframe(pd.DataFrame(st.session_state.proximity_scan_results), use_container_width=True)
        
        scan_tickers = [res['Ticker'] for res in st.session_state.proximity_scan_results]
        
        st.session_state.curated_tickers_for_screener = st.multiselect(
            "Select tickers to send to the 'Head Trader' AI:", 
            options=scan_tickers, 
            default=scan_tickers # Default to all "in play" stocks
        )
        st.success(f"{len(st.session_state.curated_tickers_for_screener)} tickers are ready for Step 2.")
    else:
        st.info("Run the proximity scan to find stocks that are in play.")


# ---
# --- TAB 2: Tactical Screener (Step 2)
# ---
with tab_screener:
    st.header("Step 2: 'Head Trader' AI Rank & Justify")
    
    # Check for prerequisites
    if not st.session_state.premarket_economy_card:
        st.error("Please generate the 'Pre-Market Economy Card' in Step 1 first.")
        st.stop()
        
    curated_tickers = st.session_state.get('curated_tickers_for_screener', [])
    if not curated_tickers:
        st.error("Please run the 'Proximity Scan' and 'Curate' a list of tickers in Step 1 first.")
        st.stop()
    
    benchmark_date = st.session_state.latest_macro_date
    st.success(f"**Ready to rank {len(curated_tickers)} tickers:** {', '.join(curated_tickers)}")
    st.info(f"All company cards will be aligned to the Macro Benchmark Date: **{benchmark_date}**")
    
    # Get the "Executor's Focus"
    market_condition_input = st.text_area(
        "Enter Your Personal 'Executor's Focus':", 
        placeholder="e.g., 'Macro is bearish, but I see relative strength in semis. Looking for longs there or clean shorts in lagging sectors.'", 
        height=100, 
        key="executor_focus"
    )
    
    if st.button("Run 'Head Trader' AI Screener (Step 2)", use_container_width=True, key="run_head_trader"):
        if not market_condition_input:
            st.warning("Please provide your 'Executor's Focus' to help guide the AI.")
        else:
            with st.spinner(f"AI 'Head Trader' is synthesizing {len(curated_tickers)} tickers..."):
                cst = st.session_state.capital_session["cst"]
                xst = st.session_state.capital_session["xst"]
                api_key = random.choice(config.API_KEYS)
                
                # Create one Turso client for this entire operation
                turso_client = create_turso_client(logger)
                if not turso_client:
                    st.error("Failed to create Turso client. Check logs.")
                    st.stop()
                
                # --- Data Gatherer Step ---
                logger.log(f"Starting 'Data Gatherer' step for {len(curated_tickers)} tickers...")
                
                # This function respects the benchmark_date
                eod_data_map = get_eod_card_data_for_screener(turso_client, curated_tickers, benchmark_date, logger)
                
                candidate_dossiers = []
                
                for i, ticker in enumerate(curated_tickers):
                    logger.log(f"--- Processing Dossier for {ticker} ---")
                    
                    # This check is now redundant but safe
                    if ticker not in eod_data_map:
                        logger.log(f"   ...Warn: No EOD data for {ticker} on {benchmark_date}. Skipping.")
                        continue
                    
                    eod_briefing_text = eod_data_map[ticker].get('screener_briefing_text', 'N/A')
                    
                    bid, offer = get_capital_current_price(ticker, cst, xst, logger)
                    if not bid:
                        logger.log(f"   ...Warn: No live price for {ticker}. Skipping.")
                        continue
                    live_price = (bid + offer) / 2
                    
                    df_pm = get_capital_price_bars(ticker, cst, xst, "MINUTE_5", logger)
                    
                    live_pm_summary = "Live PM data fetch failed or was empty."
                    if df_pm is not None: 
                        live_pm_summary = process_premarket_bars_to_summary(
                            ticker=ticker,
                            df_pm=df_pm,
                            live_price=live_price,
                            logger=logger
                        )
                    
                    dossier = f"""
                    ---
                    **Ticker:** {ticker}
                    **EOD Briefing (From {benchmark_date}):**
                    {eod_briefing_text}
                    ---
                    **Live Pre-Market Action:**
                    {live_pm_summary}
                    ---
                    """
                    candidate_dossiers.append(dossier)
                    if i < len(curated_tickers) - 1:
                        time.sleep(config.LOOP_DELAY)

                # --- "Head Trader" AI Call (Step 2) ---
                if not candidate_dossiers:
                    st.error("Failed to gather any candidate data. Check logs.")
                else:
                    final_briefing = run_tactical_screener_orchestrator(
                        market_condition=market_condition_input,
                        economy_card=st.session_state.premarket_economy_card,
                        candidate_data=candidate_dossiers,
                        api_key=api_key, # Pass the simple random key
                        logger=logger
                    )
                    st.session_state.premarket_screener_output = final_briefing
                    
                    # --- Save to DB ---
                    if final_briefing:
                        save_screener_output(turso_client, final_briefing, logger)
                    
                    st.rerun() # Rerun to display the output

    # Display the final screener output
    if st.session_state.premarket_screener_output:
        st.markdown("---")
        st.subheader("Head Trader's Briefing")
        st.markdown(st.session_state.premarket_screener_output, unsafe_allow_html=True)

# ---
# --- TAB 3: Saved Briefings
# ---
with tab_logs:
    st.markdown("---", help="This divider separates the live logs from the saved briefings")
    st.header("Step 3: Saved Briefings Log")
    
    st.info("This is where your 'Step 3: Deep-Dive Planner' will go. For now, it shows a log of past 'Head Trader' briefings.")
    
    if st.button("Refresh Briefing Log", use_container_width=True):
        st.cache_data.clear() # Clear cache to get fresh data
        st.rerun()

    @st.cache_data(ttl=60) # Cache for 60 seconds
    def get_briefing_log():
        logger.log("Fetching briefing log from database...")
        turso_client = create_turso_client(logger)
        if not turso_client:
            return []
        
        try:
            # We must ensure the table exists, as you removed the schema file
            turso_client.execute("""
                CREATE TABLE IF NOT EXISTS screener_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    briefing_text TEXT NOT NULL
                );
            """)
            
            rs = turso_client.execute("SELECT id, timestamp, briefing_text FROM screener_log ORDER BY timestamp DESC LIMIT 10")
            # Convert rows to dictionaries for easy access
            return [dict(zip([col[0] for col in rs.cols], row)) for row in rs.rows]
        except Exception as e:
            logger.log(f"DB Error getting briefing log: {e}")
            return []

    briefings = get_briefing_log()
    if not briefings:
        st.warning("No saved briefings found in the database.")
    else:
        for briefing in briefings:
            with st.expander(f"Briefing #{briefing['id']} - {briefing['timestamp']}"):
                st.markdown(briefing['briefing_text'], unsafe_allow_html=True)