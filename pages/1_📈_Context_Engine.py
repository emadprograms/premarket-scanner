import streamlit as st
import pandas as pd
import json
import time
import re
from datetime import datetime, timezone, timedelta
from pytz import timezone as pytz_timezone

# ==============================================================================
# CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="Pre-Market Analyst (Context Engine)", layout="wide")

CORE_INTERMARKET_TICKERS = [
    "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
    "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "NDAQ", "^VIX"
]

# ==============================================================================
# LOCAL IMPORTS
# ==============================================================================
try:
    from modules.key_manager import KeyManager
    from modules.utils import AppLogger, get_turso_credentials
    from modules.database import (
        get_db_connection,
        init_db_schema,
        get_latest_economy_card_date,
        get_latest_economy_card_date,
        get_eod_economy_card,
        get_eod_card_data_for_screener, # New Import
    )
    from modules.processing import (
        get_latest_price_details,
        get_session_bars_from_db,
        analyze_market_context,      
        get_previous_session_stats   
    )
    from modules.gemini import call_gemini_with_rotation, AVAILABLE_MODELS
    from modules.ui import (
        render_sidebar,
        render_main_content,
        render_proximity_scan,
        render_battle_commander,
    )
except ImportError as e:
    st.error(f"❌ CRITICAL MISSING FILE: {e}")
    st.stop()

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def reset_application_state():
    """
    Clears all data-related session state variables to reset the page 
    as if nothing has been run yet.
    """
    keys_to_reset = [
        'premarket_economy_card', 
        'latest_macro_date', 
        'proximity_scan_results',
        'curated_tickers', 
        'final_briefing', 
        'xray_snapshot', 
        'glassbox_eod_card', 
        'glassbox_etf_data', 
        'glassbox_prompt', 
        'glassbox_raw_cards', # NEW: Ensure raw data is wiped on config change
        'audit_logs'
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    
    # Provide visual feedback
    st.toast("Configuration Changed - System Reset", icon="🔄")

def fetch_watchlist(client, logger):
    """Fetches list of stock tickers from DB to filter scan."""
    try:
        rs = client.execute("SELECT ticker FROM Stocks")
        if rs.rows:
            return [r[0] for r in rs.rows]
        return []
    except Exception as e:
        logger.log(f"Watchlist Fetch Error: {e}")
        return []


# ==============================================================================
# MAIN APPLICATION LOGIC
# ==============================================================================

def main():
    st.title("Pre-Market Context Engine (Impact & Migration)")

    # --- Session State Initialization ---
    if 'premarket_economy_card' not in st.session_state: st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state: st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state: st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state: st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state: st.session_state.final_briefing = None
    if 'xray_snapshot' not in st.session_state: st.session_state.xray_snapshot = None
    if 'app_logger' not in st.session_state: st.session_state.app_logger = AppLogger(None)

    if 'glassbox_eod_card' not in st.session_state: st.session_state.glassbox_eod_card = None
    if 'glassbox_eod_date' not in st.session_state: st.session_state.glassbox_eod_date = None # NEW: Track Date
    if 'glassbox_etf_data' not in st.session_state: st.session_state.glassbox_etf_data = []
    if 'glassbox_raw_cards' not in st.session_state: st.session_state.glassbox_raw_cards = {} # NEW: Store full data for scanning
    if 'glassbox_prompt' not in st.session_state: st.session_state.glassbox_prompt = None
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

    # --- FORCE RELOAD FOR BUGFIX (Stale Object in Session State) ---
    if 'key_manager_v3_fix' not in st.session_state:
        # If the object exists from a previous run (where it didn't have logger arg), delete it.
        if 'key_manager_instance' in st.session_state:
            del st.session_state['key_manager_instance']
        st.session_state.key_manager_v3_fix = True

    if 'key_manager_instance' not in st.session_state:
        st.session_state.key_manager_instance = KeyManager(db_url=db_url, auth_token=auth_token)

    # --- Render Sidebar & Capture Config ---
    selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str = render_sidebar(AVAILABLE_MODELS)

    # --- STATE MANAGEMENT: RESET ON CONFIG CHANGE ---
    # MODIFIED: We remove 'selected_model' from the signature so changing the model
    # does NOT wipe the screen. We only wipe if MODE or DATE changes.
    if mode == "Simulation":
        current_config_signature = (mode, simulation_cutoff_str)
    else:
        current_config_signature = (mode,)

    # Check against history
    if 'last_config_signature' not in st.session_state:
        st.session_state.last_config_signature = current_config_signature
    
    if st.session_state.last_config_signature != current_config_signature:
        reset_application_state()
        st.session_state.last_config_signature = current_config_signature
        st.rerun() # Force immediate UI refresh to clear old data

    # --- AUTO-LOAD LOGIC ---
    # If the card is missing, try to fetch it passively.
    if not st.session_state.glassbox_eod_card and turso:
        # User Logic: Always fetch for PREVIOUS day (simulating Pre-Market/Morning of current day)
        lookup_cutoff = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

        latest_date = get_latest_economy_card_date(turso, lookup_cutoff, startup_logger)
        
        if latest_date:
            data = get_eod_economy_card(turso, latest_date, startup_logger)
            if data:
                st.session_state.glassbox_eod_card = data
                st.session_state.glassbox_eod_date = latest_date # Store for UI
                startup_logger.log(f"Auto-loaded EOD Card for {latest_date}")


    # --- Main Content ---
    tab1, tab2 = st.tabs(["Step 1: Context Monitor", "Step 2: Head Trader"])
    logger = st.session_state.app_logger

    # --- TAB 1: CONTEXT MONITOR ---
    with tab1:
        # Removed manual etf_placeholder = st.empty() from top, as it returns from UI function now
        pm_news, eod_placeholder, prompt_placeholder, etf_placeholder = render_main_content(mode, simulation_cutoff_dt)

        if st.button("Run Context Engine (Step 0)", key="btn_step0", type="primary"):
            st.session_state.glassbox_etf_data = []
            st.session_state.glassbox_raw_cards = {} # Reset
            etf_placeholder.empty()
            etf_json_cards = [] # Store full JSONs for AI context

            with st.status(f"Running Impact Analysis ({mode})...", expanded=True) as status:
                status.write("Fetching EOD Card...")
                
                # EOD Logic (Simulation aware)
                # EOD Logic
                # Always fetch the PREVIOUS day's economy card relative to the analysis date.
                # If Analysis Date is Dec 2, we need Dec 1 EOD Context.
                # DB Query `MAX(date) <= lookup_cutoff` handles weekends (e.g. looks for Fri if Sun).
                lookup_cutoff = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

                latest_date = get_latest_economy_card_date(turso, lookup_cutoff, logger)
                eod_card = {}
                if latest_date:
                    data = get_eod_economy_card(turso, latest_date, logger)
                    if data: 
                        eod_card = data
                        st.session_state.glassbox_eod_date = latest_date # Store for UI
                else:
                     st.session_state.glassbox_eod_date = None
                
                st.session_state.glassbox_eod_card = eod_card
                eod_placeholder.json(eod_card, expanded=False)

                status.write("Scanning Tickers (Impact Engine)...")
                benchmark_date_str = st.session_state.analysis_date.isoformat()
                
                # MERGE WATCHLIST
                watchlist = fetch_watchlist(turso, logger)
                full_ticker_list = sorted(list(set(CORE_INTERMARKET_TICKERS + watchlist)))
                
                status.write(f"Analyzing {len(full_ticker_list)} assets ({len(watchlist)} from DB Watchlist)...")

                for epic in full_ticker_list:
                    latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)
                    
                    if latest_price:
                        # 1. Get Bars
                        df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                        
                        # 2. Get Yesterday's Stats (Context)
                        ref_levels = get_previous_session_stats(turso, epic, benchmark_date_str, logger)

                        if df is not None and not df.empty:
                            # 3. RUN THE ENGINE
                            card = analyze_market_context(df, ref_levels, ticker=epic)
                            
                            # Store for AI
                            etf_json_cards.append(json.dumps(card))
                            
                            # Store for Proximity Scan
                            st.session_state.glassbox_raw_cards[epic] = card

                            # Update UI Table
                            mig_count = len(card.get('value_migration_log', []))
                            imp_count = len(card.get('key_level_rejections', [])) # Use correct key name
                            
                            # Calculate freshness for UI bar
                            freshness_score = 0.0
                            try:
                                if price_ts:
                                    ts_clean = str(price_ts).replace("Z", "+00:00").replace(" ", "T")
                                    ts_obj = datetime.fromisoformat(ts_clean)
                                    if ts_obj.tzinfo is None: ts_obj = ts_obj.replace(tzinfo=timezone.utc)
                                    lag_minutes = (simulation_cutoff_dt - ts_obj).total_seconds() / 60.0
                                    freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                            except: pass

                            new_row = {
                                "Ticker": epic,
                                "Price": f"${latest_price:.2f}",
                                "Freshness": freshness_score,
                                "Audit: Date": f"{price_ts} (UTC)",
                                "Migration Blocks": mig_count,
                                "Impact Levels": imp_count,
                            }
                            st.session_state.glassbox_etf_data.append(new_row)
                            etf_placeholder.dataframe(pd.DataFrame(st.session_state.glassbox_etf_data), use_container_width=True)
                            time.sleep(0.02)

                if not etf_json_cards:
                    status.update(label="Scan Aborted: No Data", state="error")
                    if mode == "Simulation":
                        st.error(f"⚠️ No simulation data found for {simulation_cutoff_str} (UTC). Please run Data Harvester for this historical timeframe.")
                    else:
                        st.error("⚠️ No live data found. Please run the Data Harvester to fetch the latest market data.")
                    st.stop()

                status.write("Synthesizing Observation Cards...")
                
                # NEW PROMPT STRUCTURE FOR IMPACT ENGINE
                prompt = f"""
                [SYSTEM]
                You are a Market Auction Theorist. You analyze Market Structure via Time and Impact.
                
                [INPUTS]
                1. EOD Context: {json.dumps(eod_card)}
                2. NEWS: {pm_news}
                3. LIVE AUCTION DATA (JSON OBSERVATION CARDS):
                {etf_json_cards}
                
                [TASK]
                Synthesize the 'State of the Auction'.
                - Identify the Value Migration (Are POCs stepping up/down?).
                - Identify the Impact Zones (Where is the hard rejection?).
                - Output standard Economy Card JSON (marketNarrative, marketBias, sectorRotation).
                """
                
                st.session_state.glassbox_prompt = prompt
                prompt_placeholder.text_area("Prompt Preview", prompt, height=150)

                resp, error_msg = call_gemini_with_rotation(prompt, "You are an Auction Theorist.", logger, selected_model, st.session_state.key_manager_instance)

                if resp:
                    try:
                        clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
                        st.session_state.premarket_economy_card = json.loads(clean)
                        st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
                        status.update(label="Macro Card Generated", state="complete")
                        st.rerun()
                    except Exception as e:
                        status.update(label="JSON Parse Error", state="error")
                        st.error(f"AI Error: {e}")
                else:
                    status.update(label="AI Failed", state="error")
                    st.error(error_msg)

        if st.session_state.premarket_economy_card:
            st.success("Macro Card Ready")
            with st.expander("View Final AI Output"):
                st.json(st.session_state.premarket_economy_card)

        # --- PROXIMITY SCAN LOGIC (DB-BASED) ---
        scan_threshold = render_proximity_scan()
        if scan_threshold:
            # 1. Determine Watchlist
            whitelist = fetch_watchlist(turso, logger)
            if not whitelist:
                st.warning("⚠️ No watchlist found in DB (table: Stocks). Cannot run scan.")
            else:
                # 2. Determine Reference Date (Yesterday relative to Analysis Date)
                # If Analysis Date is 2025-12-03, we need plans from 2025-12-02
                analysis_dt = st.session_state.analysis_date
                ref_date_dt = analysis_dt - timedelta(days=1)
                ref_date_str = ref_date_dt.strftime('%Y-%m-%d')
                
                st.write(f"🔍 Loading Strategic Plans from **{ref_date_str}** for {len(whitelist)} tickers...")
                
                # 3. Fetch Stored Plans (S/R Levels)
                db_plans = get_eod_card_data_for_screener(turso, whitelist, ref_date_str, logger)
                
                if not db_plans:
                     st.error(f"❌ No Strategic Plans found in DB for {ref_date_str}. Please ensure 'Head Trader' ran for that date.")
                else:
                    results = []
                    # 4. Scan
                    progress_bar = st.progress(0)
                    idx = 0
                    for ticker in whitelist:
                        # Update Progress
                        idx += 1
                        progress_bar.progress(idx / len(whitelist))

                        # Get Plan Levels
                        plan = db_plans.get(ticker)
                        if not plan: continue
                        
                        s_levels = plan.get('s_levels', [])
                        r_levels = plan.get('r_levels', [])
                        if not s_levels and not r_levels: continue

                        # Get Live Price
                        # Ensure we use the simulation settings
                        # FIX: Use the local variable strictly passed from sidebar, do not rely on missing session state
                        sim_cutoff_str = simulation_cutoff_str 
                        latest_price, _ = get_latest_price_details(turso, ticker, sim_cutoff_str, logger)
                        
                        if not latest_price: continue
                        
                        # Find Best Match (Closest Level)
                        best_match = None
                        min_dist = float('inf')

                        # Check Support
                        for lvl in s_levels:
                            dist_pct = abs(latest_price - lvl) / latest_price * 100
                            if dist_pct <= scan_threshold:
                                if dist_pct < min_dist:
                                    min_dist = dist_pct
                                    best_match = {
                                        "Ticker": ticker,
                                        "Price": f"${latest_price:.2f}",
                                        "Type": "SUPPORT",
                                        "Level": lvl,
                                        "Dist %": round(dist_pct, 2),
                                        "Source": f"Plan {ref_date_str}"
                                    }

                        # Check Resistance
                        for lvl in r_levels:
                            dist_pct = abs(latest_price - lvl) / latest_price * 100
                            if dist_pct <= scan_threshold:
                                if dist_pct < min_dist:
                                    min_dist = dist_pct
                                    best_match = {
                                        "Ticker": ticker,
                                        "Price": f"${latest_price:.2f}",
                                        "Type": "RESISTANCE",
                                        "Level": lvl,
                                        "Dist %": round(dist_pct, 2),
                                        "Source": f"Plan {ref_date_str}"
                                    }
                        
                        if best_match:
                            results.append(best_match)

                    progress_bar.empty()

                    if results:
                        st.success(f"🎯 Found {len(results)} Proximity Alerts (vs. Strategic Plan)")
                        results.sort(key=lambda x: x['Dist %'])
                        st.session_state.proximity_scan_results = results
                        st.dataframe(pd.DataFrame(results), use_container_width=True)
                    else:
                        st.info(f"✅ No tickers within {scan_threshold}% of Strategic Levels ({ref_date_str}).") 

    # --- TAB 2: HEAD TRADER ---
    with tab2:
        render_battle_commander()
        
        if not st.session_state.glassbox_raw_cards:
            st.info("ℹ️ run 'Context Engine (Step 0)' first to generate market data for ranking.")
        else:
            # 1. Selection
            col1, col2 = st.columns([3, 1])
            with col1:
                available_tickers = sorted(list(st.session_state.glassbox_raw_cards.keys()))
                
                # AUTO-SELECT: Use Proximity Scan Results if available
                default_tickers = available_tickers[:3] if len(available_tickers) >= 3 else available_tickers
                if st.session_state.proximity_scan_results:
                    prox_tickers = [x['Ticker'] for x in st.session_state.proximity_scan_results]
                    # Only keep those that actually have data (Step 0 ran for them)
                    valid_prox = [t for t in prox_tickers if t in available_tickers]
                    if valid_prox:
                        default_tickers = valid_prox

                selected_tickers = st.multiselect(
                    "Select Tickers for Head Trader Analysis", 
                    options=available_tickers,
                    default=default_tickers
                )
            with col2:
                # Local Model Selector for Head Trader
                ht_model = st.selectbox(
                    "Head Trader Model", 
                    ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-exp-1206"], 
                    index=0
                )
            
            # 2. Action
            if st.button("🧠 Run Head Trader (Rank Setups)", type="primary"):
                if not selected_tickers:
                    st.error("Select at least one ticker.")
                else:
                    # Prepare Data Packet
                    # ------------------------------------------------------------------
                    # 1. GATHER MACRO CONTEXT (THE "WIND")
                    # ------------------------------------------------------------------
                    # Priority: Pre-Market Card > EOD Card > None
                    macro_context = st.session_state.premarket_economy_card
                    if not macro_context:
                        macro_context = st.session_state.glassbox_eod_card
                    
                    macro_summary = "No Macro Context Available."
                    if macro_context:
                        macro_summary = {
                            "bias": macro_context.get('marketBias', 'Neutral'),
                            "narrative": macro_context.get('marketNarrative', 'N/A'),
                            "sector_rotation": macro_context.get('sectorRotation', {}),
                            "key_action": macro_context.get('marketKeyAction', 'N/A')
                        }

                    # ------------------------------------------------------------------
                    # 2. GATHER STRATEGIC PLANS (THE "MAP")
                    # ------------------------------------------------------------------
                    # Fetch EOD cards from DB for selected tickers to get the "Thesis"
                    strategic_plans = {}
                    
                    # Safe Fetch Function (Corrected Table Schema)
                    def fetch_plan_safe(client_obj, ticker):
                        query = """
                            SELECT cc.company_card_json, s.historical_level_notes 
                            FROM company_cards cc
                            JOIN stocks s ON cc.ticker = s.ticker
                            WHERE cc.ticker = ? 
                            ORDER BY cc.date DESC 
                            LIMIT 1
                        """
                        try:
                            rows = client_obj.execute(query, [ticker]).rows
                            if rows and rows[0]:
                                json_str, notes = rows[0][0], rows[0][1]
                                card_data = json.loads(json_str) if json_str else {}
                                return {
                                    "narrative_note": card_data.get('marketNote', 'N/A'),
                                    "strategic_bias": card_data.get('basicContext', {}).get('priceTrend', 'N/A'),
                                    "full_briefing": card_data.get('screener_briefing', 'N/A'), # The User requested specific context for AI
                                    "key_levels_note": notes,
                                    "planned_support": card_data.get('technicalStructure', {}).get('majorSupport', 'N/A'),
                                    "planned_resistance": card_data.get('technicalStructure', {}).get('majorResistance', 'N/A')
                                }
                        except Exception as e:
                            # Return Exception object so we can detect it
                            return e
                        return "No Plan Found in DB"

                    fetch_errors = [] # Track errors for UI Reporting

                    try:
                        # Standard Fetch Loop
                        for tkr in selected_tickers:
                            result = fetch_plan_safe(turso, tkr)
                            
                            # Check if result is an Exception (Error)
                            if isinstance(result, Exception):
                                error_msg = str(result)
                                # Retry Logic
                                try: 
                                    from libsql_client import create_client_sync
                                    fresh_url = db_url.replace("libsql://", "https://") 
                                    if not fresh_url.startswith("https://"): fresh_url = f"https://{fresh_url}"
                                    fresh_db = create_client_sync(url=fresh_url, auth_token=auth_token)
                                    retry_res = fetch_plan_safe(fresh_db, tkr)
                                    fresh_db.close()
                                    
                                    if isinstance(retry_res, Exception):
                                        raise retry_res # Retry also failed
                                    else:
                                        strategic_plans[tkr] = retry_res # Success on retry
                                except Exception as final_e:
                                    # BOTH ATTEMPTS FAILED - REPORT LOUDLY
                                    fetch_errors.append(f"{tkr}: {str(final_e)}")
                                    strategic_plans[tkr] = "DATA FETCH FAILED" # Placeholder for AI
                            else:
                                strategic_plans[tkr] = result

                    except Exception as e:
                        st.error(f"Critical Error in Plan Fetching Logic: {e}")

                    # ------------------------------------------------------------------
                    # ERROR REPORTING (LOUD)
                    # ------------------------------------------------------------------
                    if fetch_errors:
                        st.error("⚠️ DATA FETCH ERRORS DETECTED:")
                        for err in fetch_errors:
                            st.write(f"❌ {err}")
                        st.warning("Proceeding with incomplete data... (AI may lack strategic context for these tickers)")

                    # ------------------------------------------------------------------
                    # 3. BUILD THE PACKET (STRATEGY vs REALITY)
                    # ------------------------------------------------------------------
                    context_packet = []
                    for t in selected_tickers:
                        card = st.session_state.glassbox_raw_cards[t]
                        
                        # FILTER: Strictly Pre-Market Data (Up to Simulation Time)
                        # 1. Get Simulation Time (UTC) to match Data Logs (UTC)
                        sim_dt_utc = simulation_cutoff_dt
                        sim_time_str = sim_dt_utc.strftime('%H:%M') # e.g. "14:00" for 09:00 ET
                        
                        # DEBUG: Show what the filter sees
                        with st.expander(f"Debug Filter for {t}", expanded=False):
                            st.write(f"Sim Time (UTC): **{sim_time_str}**")
                            
                            col_d1, col_d2 = st.columns(2)
                            with col_d1:
                                st.markdown("#### 🗺️ Strategic Plan (The Map)")
                                st.json(strategic_plans.get(t, {}))
                            with col_d2:
                                st.markdown("#### 📼 Tactical Reality (The Tape)")
                                st.json(card)

                        raw_migration = card['value_migration_log']
                        pm_migration = []
                        for block in raw_migration:
                            try:
                                # Format is "HH:MM - HH:MM"
                                start_time = block['time_window'].split(' - ')[0].strip()
                                
                                # Logic: Keep only if block STARTS before the cutoff time
                                if start_time < sim_time_str:
                                    pm_migration.append(block)
                            except Exception:
                                continue 

                        # Construct the "Courtroom Evidence"
                        evidence = {
                            "ticker": t,
                            "STRATEGIC_PLAN (The Thesis)": strategic_plans.get(t, "No Plan Found"),
                            "TACTICAL_REALITY (The Tape)": {
                                "current_price": card['reference_levels']['current_price'],
                                "premarket_structure": pm_migration,
                                "impact_zones_found": card['key_level_rejections']
                            }
                        }
                        context_packet.append(evidence)
                    
                    # ------------------------------------------------------------------
                    # 4. HEAD TRADER PROMPT (THE "NARRATIVE SYNTHESIZER")
                    # ------------------------------------------------------------------
                    head_trader_prompt = f"""
                    [ROLE]
                    You are the Head Trader of a proprietary trading desk. Your job is NOT just to find "movers", but to validate **Thesis Alignment**.
                    
                    [GLOBAL MACRO CONTEXT]
                    (The "Wind" - Only take trades that sail WITH this wind)
                    {json.dumps(macro_summary, indent=2)}
                    
                    [CANDIDATE ANALYSIS]
                    For each ticker, compare the "STRATEGIC_PLAN" (What we wanted to happen) with the "TACTICAL_REALITY" (What is actually happening).
                    {json.dumps(context_packet, indent=2)}
                    
                    [TASK]
                    Rank these setups from BEST to WORST based on the **3-Layer Validation Model**:
                    
                    1. **Macro Alignment**: Does the ticker's direction/sector match the Global Macro Context? (e.g. If Macro says "Tech Weakness", a Long Tech setup is DANGEROUS).
                    2. **Structural Confluence**: Do the "Impact Zones" found in Pre-Market MATCH the "Planned Support/Resistance" in the Strategic Plan? 
                       - *High Rank*: Pre-Market rejected exactly at Planned Support (Confirmed Level).
                       - *Low Rank*: Pre-Market structure is random or far from Planned Levels.
                    3. **Narrative Consistency**: Does the price action confirm the `narrative_note`? (e.g. If note says "Flagging for Breakout", is it breaking out? If note says "Overextended", is it reversing?)
                    
                    [OUTPUT FORMAT]
                    Provide a standard "Head Trader Brief":
                    1. **Rank #1 (Top Pick)**: Ticker | Direction.
                       - *Why?*: Explicitly cite the Macro Match + Level Confluence. "Pre-Market confirms Strategic Support at $XYZ."
                       - *Plan*: Entry, Stop, Target.
                    2. **Rank #2**: ...
                    3. ...
                    """

                    # Display Prompt for User Review
                    with st.expander("👁️ View Head Trader Prompt (Debug)", expanded=False):
                        st.code(head_trader_prompt, language="text")

                    with st.spinner(f"Head Trader ({ht_model}) is analyzing Market Structure..."):
                        # Call AI
                        ht_response, err = call_gemini_with_rotation(
                            head_trader_prompt, 
                            "You are a Head Trader.", 
                            logger, 
                            ht_model, # Use local selection 
                            st.session_state.key_manager_instance
                        )
                        
                        if ht_response:
                            st.markdown("### 🏆 Head Trader's Ranking")
                            st.markdown(ht_response)
                        else:
                            st.error(f"Head Trader Failed: {err}")

if __name__ == "__main__":
    main()
