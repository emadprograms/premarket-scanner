import streamlit as st
import pandas as pd
import json
import time
import re
from datetime import datetime, timezone, timedelta
from pytz import timezone as pytz_timezone
import plotly.graph_objects as go

st.set_page_config(
    page_title="Context Engine",
    page_icon="🧠",
    layout="wide"
)

# Global Timezone Init
if 'market_timezone' not in st.session_state:
    st.session_state.market_timezone = pytz_timezone('US/Eastern')

# ==============================================================================
# HELPER: VISUALIZE STRUCTURE FOR USER
# ==============================================================================
def render_market_structure_chart(card_data):
    """
    Visualizes the raw JSON data sent to the AI:
    - X-Axis: 30m Time Blocks
    - Y-Axis: Price (Block Range)
    - Elements: Range Bars (High/Low), POC Dots (Migration), Key Levels (Support/Resistance)
    """
    try:
        if isinstance(card_data, str):
            card_data = json.loads(card_data)
        
        ticker = card_data.get('meta', {}).get('ticker', 'Unknown')
        
        # 1. Extract Block Data
        blocks = card_data.get('value_migration_log', [])
        if not blocks: return None
        
        x_vals = []
        highs = []
        lows = []
        pocs = []
        hover_texts = []
        
        for b in blocks:
            obs = b.get('observations', {})
            x_vals.append(b.get('time_window', f"Block {b.get('block_id')}"))
            highs.append(obs.get('block_high'))
            lows.append(obs.get('block_low'))
            pocs.append(obs.get('most_traded_price_level'))
            hover_attrs = [f"{k}: {v}" for k,v in obs.items() if k != 'price_action_nature']
            hover_texts.append("<br>".join(hover_attrs))

        # 2. Build Plot
        fig = go.Figure()
        
        # Range Bars (Candle-like)
        fig.add_trace(go.Bar(
            x=x_vals, 
            y=[h-l for h,l in zip(highs, lows)],
            base=lows,
            marker_color='rgba(100, 149, 237, 0.6)',
            name='Block Range',
            hoverinfo='skip'
        ))
        
        # POC Migration Path
        fig.add_trace(go.Scatter(
            x=x_vals, 
            y=pocs,
            mode='lines+markers',
            marker=dict(size=8, color='#00CC96'),
            line=dict(color='#00CC96', width=2),
            name='Value Migration (POC)',
            text=hover_texts,
            hoverinfo='text+y'
        ))
        
        # 3. Add Key Levels
        rejections = card_data.get('key_level_rejections', [])
        for r in rejections:
            color = '#FF4136' if r['type'] == 'RESISTANCE' else '#0074D9'
            fig.add_hline(
                y=r['level'], 
                line_dash="dot", 
                line_color=color,
                annotation_text=f"{r['type']} ({r['strength_score']})", 
                annotation_position="top right"
            )

        fig.update_layout(
            title=f"AI Data Visualizer: {ticker}",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis_title="Time Blocks",
            yaxis_title="Price",
            template="plotly_dark",
            showlegend=True
        )
        return fig
    except Exception as e:
        return None

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
    if 'glassbox_prompt_structure' not in st.session_state: st.session_state.glassbox_prompt_structure = {} # NEW: For Clean JSON Display
    if 'macro_index_data' not in st.session_state: st.session_state.macro_index_data = [] # NEW: Visual Table
    if 'macro_etf_structures' not in st.session_state: st.session_state.macro_etf_structures = [] # NEW: AI Data
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
    # REFACTORED: 3 Tabs Strategy
    tab1, tab2, tab3 = st.tabs([
        "Step 1: Macro Context", 
        "Step 2: Stock Selection", 
        "Step 3: Stock Ranking"
    ])
    logger = st.session_state.app_logger

    # ==============================================================================
    # TAB 1: MACRO CONTEXT (STEP 1)
    # ==============================================================================
    with tab1:
        pm_news = render_main_content(mode, simulation_cutoff_dt)
        
        # --- STEP 1: MACRO CONTEXT ---
        
        # 1. Action Button
        if st.button("Generate Macro Context (Step 1)", type="primary"):
            # RESET MACRO STATE
            st.session_state.macro_index_data = [] 
            st.session_state.macro_etf_structures = [] 
            
            with st.status(f"Synthesizing Macro Narrative...", expanded=True) as status:
                
                # A. FETCH EOD
                status.write("1. Retrieving End-of-Day Context...")
                lookup_cutoff = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                latest_date = get_latest_economy_card_date(turso, lookup_cutoff, logger)
                
                eod_card = {}
                if latest_date:
                    data = get_eod_economy_card(turso, latest_date, logger)
                    if data: 
                        eod_card = data
                        st.session_state.glassbox_eod_date = latest_date
                st.session_state.glassbox_eod_card = eod_card

                # B. SCAN INDICES
                status.write("2. Scanning Core Indices (Structure)...")
                benchmark_date_str = st.session_state.analysis_date.isoformat()
                
                progress_bar = st.progress(0)
                for idx, epic in enumerate(CORE_INTERMARKET_TICKERS):
                    latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)
                    print(f"DEBUG: Step 1 Scan | {epic} | Price: {latest_price} | Cutoff: {simulation_cutoff_str}") # DEBUG LOG
                    if latest_price:
                         df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                         ref_levels = get_previous_session_stats(turso, epic, benchmark_date_str, logger)
                         if df is not None and not df.empty:
                            card = analyze_market_context(df, ref_levels, ticker=epic)
                            st.session_state.macro_etf_structures.append(json.dumps(card))
                            
                            mig_count = len(card.get('value_migration_log', []))
                            imp_count = len(card.get('key_level_rejections', []))
                            freshness = 0.0
                            try:
                                if price_ts:
                                    ts_clean = str(price_ts).replace("Z", "+00:00").replace(" ", "T")
                                    ts_obj = datetime.fromisoformat(ts_clean)
                                    # FIX: DB timestamps are UTC. Simulation is ET.
                                    if ts_obj.tzinfo is None: 
                                        utc_tz = pytz_timezone('UTC')
                                        ts_obj = utc_tz.localize(ts_obj)
                                    
                                    # Convert to ET for comparison
                                    ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern'))
                                    
                                    lag_minutes = (simulation_cutoff_dt - ts_et).total_seconds() / 60.0
                                    freshness = max(0.0, 1.0 - (lag_minutes / 60.0))
                            except: pass

                            st.session_state.macro_index_data.append({
                                "Ticker": epic,
                                "Price": f"${latest_price:.2f}",
                                "Freshness": freshness,
                                "Lag (m)": f"{lag_minutes:.1f}" if price_ts else "N/A", # DEBUG
                                "DB Time": str(price_ts) if price_ts else "N/A",       # DEBUG
                                "Migration Steps": mig_count,
                                "Impact Zones": imp_count
                            })
                    progress_bar.progress((idx + 1) / len(CORE_INTERMARKET_TICKERS))
                progress_bar.empty()

                # CRITICAL CHECK: PREVENT EMPTY API CALLS
                if not st.session_state.macro_etf_structures:
                    status.update(label="Aborted: No DB Data", state="error")
                    st.error("❌ No Market Data found in DB (Core Indices). Aborting AI Call to save credits.")
                    st.stop()

                # --- C. BUILD & SHOW PROMPT ---
                
                # Parse ETF Structures for Clean Display
                clean_etf_structures = []
                for s in st.session_state.macro_etf_structures:
                    try:
                        clean_etf_structures.append(json.loads(s))
                    except:
                        clean_etf_structures.append(s) 

                # Construct Structured Debug Object
                prompt_debug_data = {
                    "system_role": "You are a Global Macro Strategist. Your goal is to synthesize an OBJECTIVE 'Market Narrative' (The Story) based on the evidence. Do not force a bias if the market is mixed.",
                    "inputs": {
                         "1_eod_context": eod_card,
                         "2_indices_structure": clean_etf_structures,
                         "3_overnight_news": pm_news
                    },
                    "task_instructions": [
                        "Synthesize the 'State of the Market' into a clear Narrative.",
                        "ASSUME EFFICIENT MARKETS: The news is already priced in. Focus on the *reaction* to the news (e.g. Good news + Drop = Bearish).",
                        "Analyze the ETF Structure: Are indices confirming a direction or is it mixed/choppy?",
                        "Identify the dominant story driving price (e.g., Inflation Fear, Tech Earnings, Geopolitics).",
"Output RAW JSON ONLY. No markdown formatting, no code blocks, no trailing text. Schema: { 'marketNarrative': string, 'marketBias': string, 'sectorRotation': dict, 'marketKeyAction': string }."
                    ]
                }
                st.session_state.glassbox_prompt_structure = prompt_debug_data

                status.write("3. Running AI Synthesis...")
                prompt = f"""
                [SYSTEM]
                {prompt_debug_data['system_role']}
                
                [INPUTS]
                1. PREVIOUS CLOSING CONTEXT (EOD): {json.dumps(eod_card)}
                2. CORE INDICES STRUCTURE (Pre-Market): 
                   (Analysis of SPY, QQQ, IWM, VIX etc. - Look for Migration & Rejections)
                   {st.session_state.macro_etf_structures}
                3. OVERNIGHT NEWS: {pm_news}
                
                [TASK]
                {chr(10).join(['- ' + t for t in prompt_debug_data['task_instructions']])}
                """
                st.session_state.glassbox_prompt = prompt 
                
                resp, error_msg = call_gemini_with_rotation(prompt, "You are a Macro Strategist.", logger, selected_model, st.session_state.key_manager_instance)

                if resp:
                    try:
                        clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
                        st.session_state.premarket_economy_card = json.loads(clean)
                        st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
                        status.update(label="Macro Context Generated", state="complete")
                        st.rerun()
                    except Exception as e:
                        status.update(label="JSON Parse Error", state="error")
                        st.error(f"AI Error: {e}")
                        with st.expander("Diagnostic: Raw AI Output (Failed to Parse)"):
                            st.code(resp)
                else:
                    status.update(label="AI Failed", state="error")
                    st.error(error_msg)

        # 2. Results Display (Vertical Stack)
        if st.session_state.premarket_economy_card:
            st.divider()
            st.markdown("### ✅ Step 1 Results: Macro Context")
            
            # A. EOD Context
            st.subheader("1. Previous Session Context (The Foundation)")
            with st.expander("View EOD Details", expanded=False):
                if st.session_state.glassbox_eod_card:
                    st.json(st.session_state.glassbox_eod_card)
                else:
                    st.info("No EOD Card Found.")

            # B. Index Structure
            st.subheader("2. Pre-Market Index Structure (The Evidence)")
            if st.session_state.macro_index_data:
                time_label = simulation_cutoff_dt.strftime('%H:%M')
                st.dataframe(
                    pd.DataFrame(st.session_state.macro_index_data),
                    width="stretch",
                    column_config={
                         "Freshness": st.column_config.ProgressColumn(f"Freshness ({time_label})", min_value=0, max_value=1, format=" ")
                    }
                )
            else:
                st.warning("⚠️ No Index Structure Data Captured. (Check DB for SPY/QQQ data)")
            
            # C. Prompt Packet (Visualized)
            st.subheader("3. AI Prompt Packet (Transparency)")
            
            with st.expander("View Full Prompt Inputs (Visualized)", expanded=False):
                # 3.1 EOD
                st.markdown("**1. Previous Session Context (EOD)**")
                if st.session_state.glassbox_eod_card:
                    st.json(st.session_state.glassbox_eod_card, expanded=False)
                else:
                    st.info("No EOD Context")

                # 3.2 INDICES (GRAPHS)
                st.markdown("**2. Core Indices Structure (Visual Verification)**")
                structures = st.session_state.glassbox_prompt_structure.get('inputs', {}).get('2_indices_structure', [])
                if not structures and st.session_state.macro_etf_structures:
                     # Fallback to raw list if dict missing
                     structures = st.session_state.macro_etf_structures

                if structures:
                    for s in structures:
                        fig = render_market_structure_chart(s)
                        if fig:
                            st.plotly_chart(fig, width="stretch")
                        else:
                            # Fallback if chart fails (e.g. malformed data)
                            st.text(str(s)[:200] + "...") 
                else:
                    st.warning("No Index Structure Data sent to AI.")

                # 3.3 NEWS
                st.markdown("**3. Overnight News**")
                st.text(pm_news)

                # 3.4 TASK INSTRUCTIONS
                st.markdown("**4. Task Instructions**")
                instructions = st.session_state.glassbox_prompt_structure.get('task_instructions', [])
                if instructions:
                    for i in instructions:
                        st.markdown(f"- {i}")
                else:
                    st.text("Standard Macro Synthesis Task")

            # D. Final Output (Refactored for Narrative Focus)
            st.subheader("4. The Market Narrative (The Story)")
            
            # Narrative First
            narrative = st.session_state.premarket_economy_card.get('marketNarrative', 'N/A')
            st.info(f"**📖 Narrative**: {narrative}")

            # Bias as a Metric
            bias = st.session_state.premarket_economy_card.get('marketBias', 'Neutral')
            st.metric("Market Bias (Technical Label)", bias)

            with st.expander("View Full Context JSON"):
                st.json(st.session_state.premarket_economy_card)


    # ==============================================================================
    # TAB 2: STOCK SELECTION (STEP 2)
    # ==============================================================================
    with tab2:
        # --- SECTION B: STRUCTURE SCANNER (STEP 2a) ---
        st.header("Step 2a: Structural Scanner")
        
        # Display Table Here
        etf_placeholder = st.empty()
        if st.session_state.glassbox_etf_data:
             # Format the cutoff time for the column header
            time_label = simulation_cutoff_dt.strftime('%H:%M')
            etf_placeholder.dataframe(
                pd.DataFrame(st.session_state.glassbox_etf_data), 
                width="stretch",
                column_config={
                    "Freshness": st.column_config.ProgressColumn(
                        f"Freshness (vs {time_label})", 
                        format=" ", 
                        min_value=0, 
                        max_value=1, 
                        width="small"
                    ),
                    "Migration Blocks": st.column_config.NumberColumn("Migration Steps", help="Number of 30m blocks analyzed"),
                    "Impact Levels": st.column_config.NumberColumn("Impact Zones", help="Number of significant rejection levels found"),
                },
            )
        else:
             etf_placeholder.info("Ready to Scan Watchlist Structures...")

        if st.button("Run Structure Scanner (Step 2a)", type="secondary"):
            if not st.session_state.premarket_economy_card:
                st.warning("⚠️ Please Generate Macro Context (Step 1) first.")
            else:
                st.session_state.glassbox_etf_data = []
                st.session_state.glassbox_raw_cards = {} # Reset
                etf_placeholder.empty()
                
                with st.status(f"Scanning Watchlist Structures ({mode})...", expanded=True) as status:
                    benchmark_date_str = st.session_state.analysis_date.isoformat()
                    watchlist = fetch_watchlist(turso, logger)
                    # STEP 1: FOCUS ON WATCHLIST (COMPANIES) ONLY
                    # Core ETFs are handled in Step 1 for Macro Context.
                    full_ticker_list = sorted(list(set(watchlist)))
                    
                    status.write(f"Analyzing {len(full_ticker_list)} assets...")

                    for epic in full_ticker_list:
                        # Use simulation time logic
                        latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)
                        
                        if latest_price:
                            df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                            ref_levels = get_previous_session_stats(turso, epic, benchmark_date_str, logger)

                            if df is not None and not df.empty:
                                # RUN THE ALGO
                                card = analyze_market_context(df, ref_levels, ticker=epic)
                                
                                # Store for Proximity Scan
                                st.session_state.glassbox_raw_cards[epic] = card

                                # Update Table
                                mig_count = len(card.get('value_migration_log', []))
                                imp_count = len(card.get('key_level_rejections', []))
                                
                                freshness_score = 0.0
                                try:
                                    if price_ts:
                                        ts_clean = str(price_ts).replace("Z", "+00:00").replace(" ", "T")
                                        ts_obj = datetime.fromisoformat(ts_clean)
                                        # FIX: DB timestamps are UTC. Simulation is ET.
                                        if ts_obj.tzinfo is None: 
                                            utc_tz = pytz_timezone('UTC')
                                            ts_obj = utc_tz.localize(ts_obj)
                                        
                                        # Convert to ET for comparison
                                        ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern'))
                                        
                                        lag_minutes = (simulation_cutoff_dt - ts_et).total_seconds() / 60.0
                                        freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                                except: pass

                                new_row = {
                                    "Ticker": epic,
                                    "Price": f"${latest_price:.2f}",
                                    "Freshness": freshness_score,
                                    "Lag (m)": f"{lag_minutes:.1f}" if price_ts else "N/A", # DEBUG
                                    "Audit: Date": f"{price_ts}",
                                    "Migration Blocks": mig_count,
                                    "Impact Levels": imp_count,
                                }
                                st.session_state.glassbox_etf_data.append(new_row)
                                etf_placeholder.dataframe(pd.DataFrame(st.session_state.glassbox_etf_data), width="stretch")
                    
                    status.update(label="Scanning Complete", state="complete")
        
        # VISUALIZATION (New Feature)
        if st.session_state.glassbox_raw_cards:
            with st.expander("🔍 View Company Structure Charts (Visualized)", expanded=False):
                companies = sorted(list(st.session_state.glassbox_raw_cards.keys()))
                st.caption(f"Visualizing {len(companies)} Asset Structures:")
                
                for tkr in companies:
                    st.markdown(f"### {tkr}")
                    card_data = st.session_state.glassbox_raw_cards[tkr]
                    fig = render_market_structure_chart(card_data)
                    if fig:
                        st.plotly_chart(fig, width="stretch")
                    else:
                        st.warning(f"No chart data for {tkr}")
                    st.divider()

        st.divider()

        # --- PROXIMITY SCAN LOGIC (DB-BASED) ---
        st.header("Step 2b: Proximity Logic")
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
                
                # 3. Fetch Stored Plans (S/R Levels)
                with st.spinner(f"Searching for Strategic Plans (Target: {ref_date_str})..."):
                    db_plans = get_eod_card_data_for_screener(turso, whitelist, ref_date_str, logger)
                
                if not db_plans:
                     st.error(f"❌ No Strategic Plans found in DB (<= {ref_date_str}). Please ensure 'Head Trader' ran recently.")
                else:
                    # Identify Actual Dates
                    found_dates = sorted(list(set(d.get('plan_date', 'Unknown') for d in db_plans.values())))
                    date_display = ", ".join(found_dates)
                    st.write(f"🔍 **Loaded Strategic Plans from: {date_display}** ({len(db_plans)} tickers)")
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
                                        "Source": f"Plan {plan.get('plan_date', ref_date_str)}"
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
                                        "Source": f"Plan {plan.get('plan_date', ref_date_str)}"
                                    }
                        
                        if best_match:
                            results.append(best_match)

                    progress_bar.empty()

                    if results:
                        st.success(f"🎯 Found {len(results)} Proximity Alerts (vs. Strategic Plan)")
                        results.sort(key=lambda x: x['Dist %'])
                        st.session_state.proximity_scan_results = results
                        st.dataframe(pd.DataFrame(results), width="stretch")
    
                    else:
                        st.info(f"✅ No tickers within {scan_threshold}% of Strategic Levels ({ref_date_str}).") 

    # ==============================================================================
    # TAB 3: STOCK RANKING (STEP 3)
    # ==============================================================================
    with tab3: 

        render_battle_commander()
        
        if not st.session_state.glassbox_raw_cards:
            st.info("ℹ️ run 'Context Engine (Step 1)' first to generate market data for ranking.")
        else:
            # 1. Selection
            col1, col2 = st.columns([3, 1])
            with col1:
                available_tickers = sorted(list(st.session_state.glassbox_raw_cards.keys()))
                
                # AUTO-SELECT: Use Proximity Scan Results if available
                default_tickers = available_tickers[:3] if len(available_tickers) >= 3 else available_tickers
                if st.session_state.proximity_scan_results:
                    prox_tickers = [x['Ticker'] for x in st.session_state.proximity_scan_results]
                    # Only keep those that actually have data (Step 1 ran for them)
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
                    options=["gemini-2.5-pro", "gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.0-flash", "gemini-exp-1206"], 
                    index=0
                )
            
            # 2. Action Buttons
            col_act1, col_act2 = st.columns([1, 1])
            
            run_ai_clicked = col_act1.button("🧠 Run Head Trader", type="primary", use_container_width=True)
            copy_prompt_clicked = col_act2.button("📋 Generate Prompt Only", type="secondary", use_container_width=True)

            if run_ai_clicked or copy_prompt_clicked:
                if not selected_tickers:
                    st.error("Select at least one ticker.")
                else:
                    # ------------------------------------------------------------------
                    # SHARED LOGIC: GENERATE INTELLIGENCE PACKET
                    # ------------------------------------------------------------------
                    
                    # 1. GATHER MACRO CONTEXT (THE "WIND")
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

                    # 2. GATHER STRATEGIC PLANS (THE "MAP")
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
                                    "full_briefing": card_data.get('screener_briefing', 'N/A'),
                                    "key_levels_note": notes,
                                    "planned_support": card_data.get('technicalStructure', {}).get('majorSupport', 'N/A'),
                                    "planned_resistance": card_data.get('technicalStructure', {}).get('majorResistance', 'N/A')
                                }
                        except Exception as e:
                            return e
                        return "No Plan Found in DB"

                    fetch_errors = [] 

                    try:
                        # Standard Fetch Loop
                        for tkr in selected_tickers:
                            print(f"DEBUG: Fetching Strategic Plan for {tkr}...") 
                            result = fetch_plan_safe(turso, tkr)
                            
                            if isinstance(result, Exception):
                                error_msg = str(result)
                                print(f"DEBUG: Initial fetch failed for {tkr}: {error_msg}")
                                # Retry
                                try: 
                                    from libsql_client import create_client_sync
                                    fresh_url = db_url.replace("libsql://", "https://") 
                                    if not fresh_url.startswith("https://"): fresh_url = f"https://{fresh_url}"
                                    fresh_db = create_client_sync(url=fresh_url, auth_token=auth_token)
                                    retry_res = fetch_plan_safe(fresh_db, tkr)
                                    fresh_db.close()
                                    if isinstance(retry_res, Exception): raise retry_res 
                                    else: strategic_plans[tkr] = retry_res 
                                except Exception as final_e:
                                    fetch_errors.append(f"{tkr}: {str(final_e)}")
                                    strategic_plans[tkr] = "DATA FETCH FAILED" 
                            else:
                                strategic_plans[tkr] = result
                    except Exception as e:
                        st.error(f"Critical Error in Plan Fetching Logic: {e}")

                    # Error Reporting
                    if fetch_errors:
                        st.error("⚠️ DATA FETCH ERRORS DETECTED:")
                        for err in fetch_errors: st.write(f"❌ {err}")
                        st.warning("Proceeding with incomplete data...")

                    # 3. BUILD THE PACKET
                    context_packet = []
                    for t in selected_tickers:
                        card = st.session_state.glassbox_raw_cards[t]
                        
                        # Filter Pre-Market Data
                        sim_dt_utc = simulation_cutoff_dt
                        sim_time_str = sim_dt_utc.strftime('%H:%M') 
                        
                        raw_migration = card['value_migration_log']
                        pm_migration = []
                        for block in raw_migration:
                            try:
                                start_time = block['time_window'].split(' - ')[0].strip()
                                if start_time < sim_time_str:
                                    pm_migration.append(block)
                            except: continue 

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
                    # 4. CONSTRUCT PROMPT (MODULAR)
                    # ------------------------------------------------------------------
                    
                    # PART 1: CONTEXT & ROLE
                    prompt_part_1 = f"""
                    [ROLE]
                    You are the Head Trader of a proprietary trading desk. Your job is NOT just to find "movers", but to validate **Thesis Alignment**.
                    
                    [GLOBAL MACRO CONTEXT]
                    (The "Wind" - Only take trades that sail WITH this wind)
                    {json.dumps(macro_summary, indent=2)}
                    """

                    # PART 2: DATA PACKET (CHUNKS)
                    # Split context_packet into smaller chunks (e.g. 3 tickers per chunk)
                    chunk_size = 3
                    p2_chunks = []
                    
                    for i in range(0, len(context_packet), chunk_size):
                        chunk = context_packet[i:i + chunk_size]
                        chunk_str = f"""
                        [CANDIDATE ANALYSIS - BATCH {len(p2_chunks) + 1}]
                        For this batch of tickers, compare "STRATEGIC_PLAN" with "TACTICAL_REALITY".
                        {json.dumps(chunk, indent=2)}
                        """
                        p2_chunks.append(chunk_str)

                    # CONSTRUCT FULL PART 2 (For API)
                    prompt_part_2_full = "\n".join(p2_chunks)

                    # PART 3: TASK & OUTPUT
                    prompt_part_3 = f"""
                    [TASK]
                    Rank ALL tickers provided in previous batches from BEST to WORST based on the **3-Layer Validation Model**.
                    
                    **CRITICAL PHILOSOPHY**:
                    - **Efficient Markets**: The news is priced in. Do not chase headlines.
                    - **The Edge**: We trade the **PARTICIPATION GAP** (the dislocation between the Pre-Market Move and the Open).
                    - *Ideal Setup*: A ticker has reacted to news, moved to a Strategic Support Level, and is now waiting for the Open to reverse.

                    **CONSTRAINTS**:
                    - **NO EXTERNAL DATA**: You must NOT browse the internet or use outside knowledge. Rank these tickers SOLELY based on the "STRATEGIC_PLAN" and "TACTICAL_REALITY" provided in the input.

                    **RANKING CRITERIA**:
                    
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

                    # Combine for AI
                    head_trader_prompt = prompt_part_1 + "\n" + prompt_part_2_full + "\n" + prompt_part_3
                    
                    # SAVE TO SESSION STATE (Persist for UI Toggles)
                    st.session_state.ht_prompt_parts = {
                        "p1": prompt_part_1,
                        "p2_chunks": p2_chunks, # List of strings
                        "p3": prompt_part_3,
                        "full": head_trader_prompt
                    }
                    st.session_state.ht_ready = True

                    # ------------------------------------------------------------------
                    # EXECUTION (Only if 'Run' clicked)
                    # ------------------------------------------------------------------
                    if run_ai_clicked:
                        with st.spinner(f"Head Trader ({ht_model}) is analyzing Market Structure..."):
                            ht_response, err = call_gemini_with_rotation(
                                head_trader_prompt, 
                                "You are a Head Trader.", 
                                logger, 
                                ht_model, 
                                st.session_state.key_manager_instance
                            )
                            
                            if ht_response:
                                st.markdown("### 🏆 Head Trader's Ranking")
                                st.markdown(ht_response)
                            else:
                                st.error(f"Head Trader Failed: {err}")

            # ------------------------------------------------------------------
            # PERSISTENT DISPLAY LOGIC (Outside Button Block)
            # ------------------------------------------------------------------
            if st.session_state.get("ht_ready"):
                st.success("✅ Prompt Generated!")
                st.markdown("### 📋 AI Prompt (Copy/Paste)")
                
                parts = st.session_state.ht_prompt_parts
                split_mode = st.checkbox("✂️ Split into Parts (for Limited Context AIs)", value=False)
                
                if split_mode:
                    # PART 1
                    st.caption("Part 1: Macro Context")
                    p1_wait = parts['p1'] + "\n\n[SYSTEM NOTE: PART 1. READ THE CONTEXT, DO NOT GENERATE OUTPUT. REPLY 'READY FOR DATA'.]"
                    st.code(p1_wait, language="text")
                    
                    # PART 2 (CHUNKS)
                    chunks = parts.get('p2_chunks', [])
                    for i, chunk in enumerate(chunks):
                        st.caption(f"Part 2-{i+1}: Candidate Batch {i+1}/{len(chunks)}")
                        chunk_wait = chunk + f"\n\n[SYSTEM NOTE: DATA BATCH {i+1} OF {len(chunks)}. DO NOT GENERATE OUTPUT YET. REPLY 'READY FOR NEXT BATCH'.]"
                        st.code(chunk_wait, language="text")
                    
                    # PART 3
                    st.caption("Part 3: Ranking Logic")
                    st.code(parts['p3'], language="text")
                else:
                    st.code(parts['full'], language="text")

if __name__ == "__main__":
    main()
