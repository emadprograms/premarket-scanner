import streamlit as st
import pandas as pd
import json
import time
import concurrent.futures
import re
from datetime import datetime, timezone, timedelta
from pytz import timezone as pytz_timezone
import plotly.graph_objects as go
import yfinance as yf
from streamlit_lightweight_charts import renderLightweightCharts
import pandas as pd
import io

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
# ==============================================================================
# HELPER: VISUALIZE STRUCTURE (PLOTLY - INTERACTIVE)
# ==============================================================================
def render_market_structure_chart(card_data, trade_plan=None):
    """
    Visualizes the raw JSON data sent to the AI (30m Blocks):
    """
    try:
        if isinstance(card_data, str):
            card_data = json.loads(card_data)
        
        ticker = card_data.get('meta', {}).get('ticker', 'Unknown')
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

        fig = go.Figure()
        
        # Range Bars
        fig.add_trace(go.Bar(
            x=x_vals, y=[h-l for h,l in zip(highs, lows)], base=lows,
            marker_color='rgba(100, 149, 237, 0.6)', name='Block Range', hoverinfo='skip'
        ))
        
        # POCs
        fig.add_trace(go.Scatter(
            x=x_vals, y=pocs, mode='lines+markers',
            marker=dict(size=8, color='#00CC96'), line=dict(color='#00CC96', width=2),
            name='POC Migration', text=hover_texts
        ))
        
        # Key Levels
        rejections = card_data.get('key_level_rejections', [])
        for r in rejections:
            color = '#FF4136' if r['type'] == 'RESISTANCE' else '#0074D9'
            fig.add_hline(y=r['level'], line_dash="dot", line_color=color, annotation_text=r['type'])

        fig.update_layout(
            title=f"{ticker} Market Structure (30m Blocks)", height=400, template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        return fig
    except Exception:
        return None

# ==============================================================================
# HELPER: HEAD TRADER VISUALIZER (MATPLOTLIB - 1M CANDLES)
# ==============================================================================
# ==============================================================================
# HELPER: HEAD TRADER VISUALIZER (TRADINGVIEW LIGHTWEIGHT CHARTS)
# ==============================================================================
# ==============================================================================
# HELPER: HEAD TRADER VISUALIZER (TRADINGVIEW LIGHTWEIGHT CHARTS)
# ==============================================================================
def render_tradingview_chart(client, ticker, cutoff_str, mode="Simulation", trade_plan=None):
    """
    Renders an interactive TradingView-style chart using Turso DB OR Capital.com.
    """
    try:
        # 1. Fetch Data (Routed based on mode)
        df = get_historical_bars_for_chart(client, ticker, cutoff_str, days=5, mode=mode)
        
        if df is None or df.empty: 
            return None
        
        # Filter Visual (Last 150 candles)
        df = df.tail(150)
        
        # 2. Format Candle Data
        candles = []
        for _, row in df.iterrows():
            # Unix Timestamp
            ts = int(row['timestamp'].timestamp())
            candles.append({
                "time": ts,
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close']
            })

        # 3. Setup Series List
        series = []
        
        # Main Candle Series
        series.append({
            "type": "Candlestick",
            "data": candles,
            "options": {
                "upColor": "#26a69a",
                "downColor": "#ef5350",
                "borderVisible": False,
                "wickUpColor": "#26a69a",
                "wickDownColor": "#ef5350"
            }
        })
        
        # 4. Trade Plan Overlays
        if trade_plan:
            try:
                # Normalize
                plan_norm = {k.lower(): v for k,v in trade_plan.items()}
                
                def safe_float(val):
                    if isinstance(val, (int, float)): return float(val)
                    if isinstance(val, str): return float(val.replace('$','').replace(',','').strip())
                    return None

                entry = safe_float(plan_norm.get('entry'))
                stop = safe_float(plan_norm.get('stop'))
                target = safe_float(plan_norm.get('target'))
                
                # Create Line Data (Constant value across all timestamps)
                # This draws a horizontal line across the whole visible chart
                
                if entry:
                    series.append({
                        "type": "Line",
                        "data": [{"time": c["time"], "value": entry} for c in candles],
                        "options": {
                            "color": "#FFEB3B", # Yellow
                            "lineWidth": 2,
                            "lineStyle": 2, # Dashed
                            "priceLineVisible": False,
                            "lastValueVisible": False,
                            "title": "ENTRY"
                        }
                    })
                
                if stop:
                    series.append({
                        "type": "Line",
                        "data": [{"time": c["time"], "value": stop} for c in candles],
                        "options": {
                            "color": "#FF1744", # Red
                            "lineWidth": 2,
                            "priceLineVisible": False,
                            "lastValueVisible": False,
                            "title": "STOP"
                        }
                    })
                    
                if target:
                    series.append({
                        "type": "Line",
                        "data": [{"time": c["time"], "value": target} for c in candles],
                        "options": {
                            "color": "#00E676", # Green
                            "lineWidth": 2,
                            "priceLineVisible": False,
                            "lastValueVisible": False,
                            "title": "TARGET"
                        }
                    })

                # PROJECTED PATH (Current -> Entry -> Target)
                if entry and target:
                    last_c = candles[-1]
                    last_ts = last_c['time']
                    curr_price = last_c['close']
                    
                    # Future Timestamps (Widened for visual tilt - 60m / 180m)
                    ts_entry = last_ts + (60 * 60)   # +1 Hour
                    ts_target = last_ts + (180 * 60) # +3 Hours
                    
                    # 1. Approach: Current -> Entry (Dotted)
                    series.append({
                        "type": "Line",
                        "data": [
                            {"time": last_ts, "value": curr_price},
                            {"time": ts_entry, "value": entry}
                        ],
                        "options": {
                            "color": "cyan",
                            "lineWidth": 2,
                            "lineStyle": 2, # Dashed/Dotted
                            "title": "",
                            "crosshairMarkerVisible": False,
                            "priceLineVisible": False,
                            "lastValueVisible": False
                        },
                        "markers": [{
                            "time": ts_entry,
                            "position": "aboveBar" if entry < curr_price else "belowBar",
                            "color": "cyan",
                            "shape": "arrowDown" if entry < curr_price else "arrowUp",
                            "size": 2 # BIGGER ARROW
                        }]
                    })
                    
                    # 2. Execution: Entry -> Target (Solid)
                    series.append({
                        "type": "Line",
                        "data": [
                            {"time": ts_entry, "value": entry},
                            {"time": ts_target, "value": target}
                        ],
                        "options": {
                            "color": "cyan",
                            "lineWidth": 2,
                            "lineStyle": 0, # Solid
                            "title": "",
                            "crosshairMarkerVisible": False,
                            "priceLineVisible": False,
                            "lastValueVisible": False
                        },
                        "markers": [{
                            "time": ts_target,
                            "position": "aboveBar" if target < entry else "belowBar",
                            "color": "cyan",
                            "shape": "arrowDown" if target < entry else "arrowUp",
                            "size": 2 # BIGGER ARROW
                        }]
                    })

            except Exception as e:
                print(f"Overlay Error: {e}")

        # 5. Chart Options
        chartOptions = {
            "layout": {
                "textColor": "#d1d4dc",
                "background": {
                    "type": "solid",
                    "color": "#0E1117"
                }
            },
            "grid": {
                "vertLines": {"color": "rgba(42, 46, 57, 0.5)"},
                "horzLines": {"color": "rgba(42, 46, 57, 0.5)"}
            },
            "height": 500,
            "rightPriceScale": {
                "scaleMargins": {
                    "top": 0.1,
                    "bottom": 0.1,
                },
                "borderColor": "rgba(197, 203, 206, 0.8)",
            },
            "timeScale": {
                "borderColor": "rgba(197, 203, 206, 0.8)",
                "timeVisible": True,
                "secondsVisible": False
            }
        }
        
        # 6. Render
        st.subheader(f"📊 {ticker} (5m Interactive)")
        renderLightweightCharts([
            {
                "chart": chartOptions,
                "series": series
            }
        ], key=f"ht_chart_{ticker}")
        return True

    except Exception as e:
        st.error(f"Chart Error ({ticker}): {e}")
        return None

def render_lightweight_chart_simple(df, ticker, height=300):
    """
    Renders a simple interactive candlestick chart from a DataFrame.
    """
    try:
        if df is None or df.empty: 
            st.warning(f"No Data for {ticker}")
            return

        # DEBUG: Verify Data Availability
        # st.caption(f"Debug: {len(df)} rows found. Columns: {list(df.columns)}")

        # Normalize Columns to Lowercase for processing
        df_norm = df.copy()
        df_norm.columns = [c.lower() for c in df_norm.columns]
        
        # Ensure timestamp exists
        if 'timestamp' not in df_norm.columns:
             # Try index
             if isinstance(df.index, pd.DatetimeIndex):
                  df_norm['timestamp'] = df.index
             else:
                  # If we can't find time, we can't chart
                  st.warning(f"No timestamp column for {ticker}")
                  return

        # CRITICAL FIX: Sort and Dedup for Lightweight Charts (Likely cause of blank charts)
        df_norm['timestamp'] = pd.to_datetime(df_norm['timestamp'])
        df_norm.dropna(subset=['timestamp', 'open', 'high', 'low', 'close'], inplace=True)
        df_norm.sort_values('timestamp', inplace=True)
        df_norm.drop_duplicates(subset='timestamp', keep='last', inplace=True)
        
        if df_norm.empty:
            st.warning(f"No valid data points for {ticker}")
            return

        # Format Data
        candles = []
        for _, row in df_norm.iterrows():
            # Handle Timestamp (Explicit cast to int seconds)
            ts = int(row['timestamp'].timestamp())
            
            # Skip invalid values
            if pd.isna(row['open']): continue

            candles.append({
                "time": ts,
                "open": row.get('open', 0),
                "high": row.get('high', 0),
                "low": row.get('low', 0),
                "close": row.get('close', 0)
            })

        series = [{
            "type": "Candlestick",
            "data": candles,
            "options": {
                "upColor": "#26a69a",
                "downColor": "#ef5350",
                "borderVisible": False,
                "wickUpColor": "#26a69a",
                "wickDownColor": "#ef5350"
            }
        }]

        chart_options = {
            "layout": {
                "textColor": "#d1d4dc",
                "background": {"type": "solid", "color": "#131722"}
            },
            "grid": {
                "vertLines": {"color": "rgba(42, 46, 57, 0.5)"},
                "horzLines": {"color": "rgba(42, 46, 57, 0.5)"}
            },
            "height": height,
            "timeScale": { "timeVisible": True, "secondsVisible": False }
        }
        
        # Sanitize key for Streamlit (Stable key prevents blank-out on rerun)
        safe_ticker = ticker.replace("=", "_").replace("^", "").replace(".", "_")
        
        # 6. Render
        renderLightweightCharts([{"chart": chart_options, "series": series}], key=f"lc_{safe_ticker}")
        
    except Exception as e:
        st.error(f"Chart Render Error ({ticker}): {e}")

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
        get_session_bars_routed,
        analyze_market_context,      
        get_previous_session_stats,
        get_historical_bars_for_chart,
        ticker_to_epic
    )
    from modules.gemini import call_gemini_with_rotation, AVAILABLE_MODELS
    from modules.ui import (
        render_mission_config,
        render_main_content,
        render_proximity_scan,
        render_battle_commander,
    )
    from modules.sync_engine import sync_turso_to_local
except ImportError as e:
    st.error(f"[ERROR] CRITICAL MISSING FILE: {e}")
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
    if 'local_mode' not in st.session_state: st.session_state.local_mode = False
    if 'trigger_sync' not in st.session_state: st.session_state.trigger_sync = False
    if 'step1_data_ready' not in st.session_state: st.session_state.step1_data_ready = False # NEW: Workflow Split

    # --- Startup ---
    startup_logger = st.session_state.app_logger
    db_url, auth_token = get_turso_credentials()
    
    # Handle Sync Trigger before connecting (need fresh connection for sync)
    if st.session_state.trigger_sync:
        with st.status("📥 Syncing Database...", expanded=True) as status:
            temp_conn = get_db_connection(db_url, auth_token, local_mode=False)
            if temp_conn:
                success = sync_turso_to_local(temp_conn, "data/local_cache.db", startup_logger)
                if success:
                    status.update(label="✅ Sync Complete!", state="complete")
                    st.toast("Local database updated.")
                else:
                    status.update(label="❌ Sync Failed", state="error")
            else:
                status.update(label="❌ Connection Failed", state="error")
        st.session_state.trigger_sync = False
        st.rerun()

    turso = get_db_connection(db_url, auth_token, local_mode=st.session_state.local_mode)
    if turso:
        init_db_schema(turso, startup_logger)
    else:
        st.error("DB Connection Failed.")
        st.stop()

    # --- FORCE RELOAD FOR BUGFIX (Stale Object in Session State) ---
    if 'key_manager_v8_fix' not in st.session_state:
        # If the object exists from a previous run (where it didn't have V8 methods), delete it.
        if 'key_manager_instance' in st.session_state:
            del st.session_state['key_manager_instance']
        st.session_state.key_manager_v8_fix = True

    if 'key_manager_instance' not in st.session_state:
        st.session_state.key_manager_instance = KeyManager(db_url=db_url, auth_token=auth_token)

    # --- Render Sidebar & Capture Config ---
    # Generate Display Labels
    model_labels = {k: v['display'] for k, v in KeyManager.MODELS_CONFIG.items()}
    selected_model, mode, simulation_cutoff_dt, simulation_cutoff_str = render_mission_config(AVAILABLE_MODELS, formatter=model_labels)

    analysis_date = st.session_state.analysis_date
    benchmark_date_str = analysis_date.isoformat()
    
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
        # --- STEP 1a: MACRO DATA FETCH ---
        st.header("Step 1a: Macro Data Fetch")
        
        # News Input: Always Visible (User Request)
        st.caption("📝 Overnight News / Context")
        pm_news = st.text_area("Paste relevant headlines/catalysts here...", height=100, key="pm_news_input", label_visibility="collapsed")
        
        st.markdown("---") # UI CLEANUP: Separator
        
        # 1. Action Button: FETCH DATA ONLY
        def clear_step1_state():
            st.session_state.macro_index_data = [] 
            st.session_state.macro_etf_structures = [] 
            st.session_state.step1_data_ready = False
            st.session_state.premarket_economy_card = None 

        if st.button("Fetch Market Data (Step 1a)", type="primary", on_click=clear_step1_state):
            # State is already cleared by callback
            
            with st.status(f"Fetching Macro Data...", expanded=True) as status:
                
                # A. FETCH EOD
                status.write("1. Retrieving End-of-Day Context...")
                lookup_cutoff = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                latest_date = get_latest_economy_card_date(turso, lookup_cutoff, logger)
                
                eod_card = {}
                if latest_date:
                    status.write(f"   ✅ Found Strategic Plan from: **{latest_date}**")
                    data = get_eod_economy_card(turso, latest_date, logger)
                    if data: 
                        eod_card = data
                        st.session_state.glassbox_eod_date = latest_date
                else:
                    status.write("   ⚠️ No Strategic Plan found for this window.")
                    st.error("Stopping: Strategic Plan (EOD Card) is required for context.")
                    st.warning("If using **Local Mode**, please click **🔄 Sync Database** in the sidebar to download the latest plans.")
                    status.update(label="Missing Context", state="error")
                    st.stop()
                st.session_state.glassbox_eod_card = eod_card

                # B. SCAN INDICES
                status.write("2. Scanning Core Indices (Structure)...")
                
                # PRE-FLIGHT CHECK: Live Mode Authentication
                if mode == "Live":
                    from modules.capital_api import create_capital_session_v2
                    cst, xst = create_capital_session_v2()
                    if not cst or not xst:
                        status.update(label="Auth Failed", state="error")
                        st.error("❌ Capital.com Authentication Failed. Check Infisical Secrets (`capital_com_X_CAP_API_KEY`, `capital_com_IDENTIFIER`, `capital_com_PASSWORD`).")
                        st.stop()

                progress_bar = st.progress(0)
                def process_macro_parallel(t):
                    """Worker function for macro index structure scanning."""
                    try:
                        # ROUTED DATA FETCH (Live/Sim)
                        df = get_session_bars_routed(
                            turso, 
                            t, 
                            benchmark_date_str, 
                            simulation_cutoff_str, 
                            mode=mode, 
                            logger=None, # Avoid thread noise
                            db_fallback=st.session_state.get('db_fallback', False)
                        )
                        
                        if df is None or df.empty:
                            return None

                        latest_price = df.iloc[-1]['Close']
                        p_ts = df.iloc[-1]['timestamp']
                        
                        # Get Previous Close Reference
                        ref_levels = get_previous_session_stats(turso, t, benchmark_date_str, logger=None)
                        card = analyze_market_context(df, ref_levels, ticker=t)
                        
                        mig_count = len(card.get('value_migration_log', []))
                        imp_count = len(card.get('key_level_rejections', []))
                        freshness = 0.0
                        try:
                            if p_ts:
                                ts_clean = str(p_ts).replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: 
                                    ts_obj = pytz_timezone('UTC').localize(ts_obj)
                                
                                ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern'))
                                lag_min = (simulation_cutoff_dt - ts_et).total_seconds() / 60.0
                                freshness = max(0.0, 1.0 - (lag_min / 60.0))
                        except: pass

                        data_source = df['source'].iloc[0] if 'source' in df.columns else ('Capital.com' if mode == 'Live' else 'DB')
                        
                        return {
                            "ticker": t,
                            "card": card,
                            "df": df, # Needed for chart rendering after
                            "latest_price": latest_price,
                            "data_source": data_source,
                            "mig_count": mig_count,
                            "imp_count": imp_count,
                            "freshness": freshness
                        }
                    except Exception:
                        return None

                status.write("2. Scanning Core Indices (Parallel Structure Scan)...")
                
                # Use ThreadPoolExecutor for speed
                macro_results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(process_macro_parallel, t) for t in CORE_INTERMARKET_TICKERS]
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        if res:
                            macro_results.append(res)
                
                # Final Processing & UI Rendering (Main Thread)
                for idx, res in enumerate(macro_results):
                    st.session_state.macro_etf_structures.append(json.dumps(res['card']))
                    st.session_state.macro_index_data.append({
                        "Ticker": res['ticker'],
                        "Source": res['data_source'],
                        "Price": f"${res['latest_price']:.2f}",
                        "Migration Steps": res['mig_count'],
                        "Impact Zones": res['imp_count']
                    })
                    
                    # VISUAL VERIFICATION (Expanders)
                    with st.expander(f"📊 {res['ticker']} ({res['data_source']}) - Structure", expanded=(idx == 0)):
                        render_lightweight_chart_simple(res['df'], res['ticker'], height=250)
                        st.caption(f"Latest: {res['latest_price']} | Source: **{res['data_source']}**")


                # CRITICAL CHECK: PREVENT EMPTY API CALLS
                if not st.session_state.macro_etf_structures:
                    status.update(label="Aborted: No Data", state="error")
                    if mode == "Live":
                         st.error("❌ No Data received from Capital.com. Check Market Hours or Symbol Mapping.")
                    else:
                         st.error("❌ No Market Data found in DB (Core Indices). Aborting AI Call to save credits.")
                    st.stop()
                
                # DATA READY - Prompt building happens later
                st.session_state.step1_data_ready = True
                status.update(label="Data Fetch Complete", state="complete")
                st.rerun()

        # 2. MIDDLE SECTION (Verification & Prompt Construction)
        if st.session_state.step1_data_ready:
            
            # --- SHOW DATA ---
            st.markdown("### 📋 Step 1a Verification: Data")
            
            # Display Helper (Summary)
            st.info(f"Indices Scanned: {len(st.session_state.macro_index_data)}")

            st.dataframe(
                pd.DataFrame(st.session_state.macro_index_data),
                width="stretch"
            )

            # --- DYNAMIC PROMPT CONSTRUCTION (Step 1b Logic) ---
            # Reconstruct prompt every rerun using current News Input
            
            # Parse ETF Structures
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
                        "1_eod_context": st.session_state.glassbox_eod_card,
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

            prompt = f"""
            [SYSTEM]
            {prompt_debug_data['system_role']}
            
            [INPUTS]
            1. PREVIOUS CLOSING CONTEXT (EOD): {json.dumps(st.session_state.glassbox_eod_card)}
            2. CORE INDICES STRUCTURE (Pre-Market): 
                (Analysis of SPY, QQQ, IWM, VIX etc. - Look for Migration & Rejections)
                {st.session_state.macro_etf_structures}
            3. OVERNIGHT NEWS: {pm_news}
            
            [TASK]
            {chr(10).join(['- ' + t for t in prompt_debug_data['task_instructions']])}
            """
            st.session_state.glassbox_prompt = prompt 
            
            with st.expander("Review AI Prompt (Copy for Manual Use)", expanded=False):
                    st.code(st.session_state.glassbox_prompt, language="text")

            st.divider()
        

        # --- STEP 1b: AI SYNTHESIS (ALWAYS VISIBLE) ---
        st.header("Step 1b: AI Synthesis")
        st.caption("Generate the Market Narrative using the fetched data.")
        st.write("") # Vertical Spacer
        
        # --- ACTION COLUMNS ---
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.markdown("#### 🤖 Auto Mode")
            if st.button("✨ Run Gemini Analysis (Step 1b)", type="primary"):
                # VALIDATION: Check if Step 1a ran
                if not st.session_state.step1_data_ready:
                    st.warning("⚠️ Please run **Step 1a: Fetch Market Data** first.")
                    st.stop()
                
                with st.spinner("Running AI Analysis..."):
                    resp, error_msg = call_gemini_with_rotation(
                        st.session_state.glassbox_prompt, 
                        "You are a Macro Strategist.", 
                        logger, 
                        selected_model, 
                        st.session_state.key_manager_instance
                    )

                    if resp:
                        try:
                            clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
                            st.session_state.premarket_economy_card = json.loads(clean)
                            st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
                            st.success("Macro Context Generated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"JSON Parse Error: {e}")
                            with st.expander("Raw Output"):
                                st.code(resp)
                    else:
                        st.error(error_msg)

        with c2:
            st.markdown("#### 🛠️ Manual Fallback")
            with st.expander("Paste AI Response (Manual JSON)", expanded=False):
                manual_json = st.text_area("Paste the JSON output from an external LLM here:", height=200)
                if st.button("Process Manual JSON"):
                    if manual_json:
                        try:
                            clean = re.search(r"(\{.*\})", manual_json, re.DOTALL).group(1)
                            st.session_state.premarket_economy_card = json.loads(clean)
                            st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
                            st.success("Manual JSON Processed Successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Invalid JSON: {e}")
                    else:
                        st.warning("Please paste JSON first.")


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
                            st.plotly_chart(fig, use_container_width=True)
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
        st.header("Step 2: Stock Selection")
        
        # UI controls for both
        prox_col1, prox_col2 = st.columns([2, 1])
        with prox_col1:
            scan_threshold = st.slider("Proximity % (Strategic Level Check)", 0.1, 5.0, 2.5)
        
        # Display Table Here
        etf_placeholder = st.empty()
        if st.session_state.glassbox_etf_data:
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
                    "Migration Blocks": st.column_config.NumberColumn("Migration Steps"),
                    "Impact Levels": st.column_config.NumberColumn("Impact Zones"),
                },
            )
        else:
            etf_placeholder.info("Ready for Unified Selection Scan...")

        if st.button("Run Unified Selection Scan (Structure + Proximity)", type="primary"):
            if not st.session_state.premarket_economy_card:
                st.warning("⚠️ Please Generate Macro Context (Step 1) first.")
            else:
                st.session_state.glassbox_etf_data = []
                st.session_state.glassbox_raw_cards = {}
                st.session_state.proximity_scan_results = []
                etf_placeholder.empty()

                with st.status(f"Running Unified Selection Scan ({mode})...", expanded=True) as status:
                    # 1. Fetch Watchlist & Strategic Plans
                    watchlist = fetch_watchlist(turso, logger)
                    full_ticker_list = sorted(list(set(watchlist)))
                    
                    ref_date_dt = st.session_state.analysis_date
                    ref_date_str = ref_date_dt.strftime('%Y-%m-%d')
                    
                    status.write("1. Loading Strategic Plans for Proximity Check...")
                    db_plans = get_eod_card_data_for_screener(turso, tuple(full_ticker_list), ref_date_str, logger)
                    
                    def process_ticker_unified(ticker_to_scan):
                        """Unified worker for both Structure Analysis and Proximity Check."""
                        try:
                            # A. FETCH DATA
                            df = get_session_bars_routed(
                                turso, 
                                ticker_to_scan, 
                                benchmark_date_str, 
                                simulation_cutoff_str, 
                                mode, 
                                logger=None,
                                db_fallback=st.session_state.get('db_fallback', False),
                                premarket_only=False # Ensure latest for proximity
                            )
                            if df is None or df.empty: return None

                            latest_row = df.iloc[-1]
                            l_price = float(latest_row['Close'])
                            p_ts = latest_row['timestamp'] if 'timestamp' in df.columns else latest_row.get('dt_eastern')

                            # B. STRUCTURE ANALYSIS
                            ref_levels = get_previous_session_stats(turso, ticker_to_scan, benchmark_date_str, logger=None)
                            card = analyze_market_context(df, ref_levels, ticker=ticker_to_scan)
                            
                            mig_count = len(card.get('value_migration_log', []))
                            imp_count = len(card.get('key_level_rejections', []))
                            
                            freshness_score = 0.0
                            l_minutes = 0.0
                            if p_ts:
                                ts_clean = str(p_ts).replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: ts_obj = pytz_timezone('UTC').localize(ts_obj)
                                ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern'))
                                l_minutes = (simulation_cutoff_dt - ts_et).total_seconds() / 60.0
                                freshness_score = max(0.0, 1.0 - (l_minutes / 60.0))

                            # C. PROXIMITY CHECK
                            prox_alert = None
                            plan_data = db_plans.get(ticker_to_scan)
                            if plan_data:
                                s_levels = plan_data.get('s_levels', [])
                                r_levels = plan_data.get('r_levels', [])
                                levels = [(lvl, "SUPPORT") for lvl in s_levels] + [(lvl, "RESISTANCE") for lvl in r_levels]
                                
                                best_dist = float('inf')
                                for lvl, l_type in levels:
                                    dist_pct = abs(l_price - lvl) / l_price * 100
                                    if dist_pct <= scan_threshold and dist_pct < best_dist:
                                        best_dist = dist_pct
                                        prox_alert = {
                                            "Ticker": ticker_to_scan,
                                            "Price": f"${l_price:.2f}",
                                            "Type": l_type,
                                            "Level": lvl,
                                            "Dist %": round(dist_pct, 2),
                                            "Source": f"Plan {plan_data.get('plan_date', ref_date_str)}"
                                        }

                            return {
                                "ticker": ticker_to_scan,
                                "card": card,
                                "prox_alert": prox_alert,
                                "table_row": {
                                    "Ticker": ticker_to_scan,
                                    "Price": f"${l_price:.2f}",
                                    "Freshness": freshness_score,
                                    "Lag (m)": f"{l_minutes:.1f}" if p_ts else "N/A",
                                    "Audit: Date": f"{p_ts}",
                                    "Migration Blocks": mig_count,
                                    "Impact Levels": imp_count,
                                }
                            }
                        except Exception: return None

                    # 2. Parallel Execution
                    status.write(f"2. Analyzing {len(full_ticker_list)} assets (Parallel)...")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        future_to_ticker = {executor.submit(process_ticker_unified, t): t for t in full_ticker_list}
                        for future in concurrent.futures.as_completed(future_to_ticker):
                            res = future.result()
                            if res:
                                st.session_state.glassbox_raw_cards[res['ticker']] = res['card']
                                st.session_state.glassbox_etf_data.append(res['table_row'])
                                if res['prox_alert']:
                                    st.session_state.proximity_scan_results.append(res['prox_alert'])

                    status.update(label="✅ Unified Scan Complete!", state="complete")
                    st.rerun()

        # Proximity Alerts Display (If any)
        if st.session_state.proximity_scan_results:
            st.success(f"🎯 Found {len(st.session_state.proximity_scan_results)} Proximity Alerts")
            st.dataframe(pd.DataFrame(st.session_state.proximity_scan_results).sort_values("Dist %"), width="stretch")

        # VISUALIZATION
        if st.session_state.glassbox_raw_cards:
            with st.expander("🔍 View Company Structure Charts", expanded=False):
                companies = sorted(list(st.session_state.glassbox_raw_cards.keys()))
                for tkr in companies:
                    st.markdown(f"### {tkr}")
                    fig = render_market_structure_chart(st.session_state.glassbox_raw_cards[tkr])
                    if fig: st.plotly_chart(fig, use_container_width=True)
                    st.divider() 

    # ==============================================================================
    # TAB 3: STOCK RANKING (STEP 3)
    # ==============================================================================
    with tab3: 

        render_battle_commander()
        
        if not st.session_state.glassbox_raw_cards:
            st.info("ℹ️ run 'Context Engine (Step 1)' first to generate market data for ranking.")
        else:
            # 1. Prepare Data for Form
            available_tickers = sorted(list(st.session_state.glassbox_raw_cards.keys()))
            
            # AUTO-SELECT: Use Proximity Scan Results if available
            default_tickers = available_tickers[:3] if len(available_tickers) >= 3 else available_tickers
            if st.session_state.proximity_scan_results:
                prox_tickers = [x['Ticker'] for x in st.session_state.proximity_scan_results]
                valid_prox = [t for t in prox_tickers if t in available_tickers]
                if valid_prox:
                    default_tickers = valid_prox

            # 2. Head Trader Control Panel (Form)
            with st.form(key='head_trader_controls'):
                st.markdown("### 🎛️ Strategic Parameters")
                
                # Top: Selection
                selected_tickers = st.multiselect(
                    "Select Tickers", 
                    options=available_tickers,
                    default=default_tickers
                )
                
                # Middle: Ranking Factors
                p1, p2 = st.columns(2)
                with p1:
                    setup_type = st.selectbox("🎯 Setup Type", ["Any", "Gap & Go", "Reversal/Fade", "Breakout", "Dip Buy", "Range Bound"])
                with p2:
                    confluence_mode = st.selectbox("🏗️ Confluence", ["Flexible", "Strict"])

                st.divider()
                
                # Layout: Left = Model, Right = Controls (2x2)
                layout_c1, layout_c2 = st.columns([1, 1])
                
                with layout_c1:
                    ht_model = st.selectbox(
                        "Head Trader Model", 
                        options=AVAILABLE_MODELS, 
                        index=0,
                        format_func=lambda x: model_labels.get(x, x)
                    )

                with layout_c2:
                    # 2x2 Grid for Checkboxes
                    cb_c1, cb_c2 = st.columns(2)
                    with cb_c1:
                        prioritize_prox = st.checkbox("Prioritize Proximity", value=False, help="Rank stocks closest to Entry #1.")
                        use_full_context = st.checkbox("📖 Use Full Context", value=False, help="Sends raw JSON (High Token Cost)")
                    with cb_c2:
                        prioritize_rr = st.checkbox("Prioritize High R/R", value=False, help="Rank High Risk/Reward Ratios #1.")
                        dry_run_mode = st.checkbox("📋 Dry Run (Prompt Only)", value=False)
                
                submitted = st.form_submit_button("🧠 Run Head Trader Analysis", type="primary", use_container_width=True)

            if submitted:
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
                    def fetch_plan_safe(client_obj, ticker, full_context_mode=False):
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
                                
                                if full_context_mode:
                                     return card_data # Return Full JSON
                                
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
                            result = fetch_plan_safe(turso, tkr, use_full_context)
                            
                            if isinstance(result, Exception):
                                error_msg = str(result)
                                print(f"DEBUG: Initial fetch failed for {tkr}: {error_msg}")
                                # Retry
                                try: 
                                    from libsql_client import create_client_sync
                                    fresh_url = db_url.replace("libsql://", "https://") 
                                    if not fresh_url.startswith("https://"): fresh_url = f"https://{fresh_url}"
                                    fresh_db = create_client_sync(url=fresh_url, auth_token=auth_token)
                                    retry_res = fetch_plan_safe(fresh_db, tkr, use_full_context)
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
                    
                    # Logic for overrides
                    rr_instruction = ""
                    if prioritize_rr:
                        rr_instruction = "\n                    - **OVERRIDE: HIGH R/R**: YES. Rank opportunities with the best Risk/Reward ratio #1. Penalize low R/R."
                    
                    prox_instruction = ""
                    if prioritize_prox:
                        prox_instruction = "\n                    - **OVERRIDE: PROXIMITY**: YES. Prioritize stocks CLOSEST to the Entry level. We need immediate fills."

                    prompt_part_3 = f"""
                    [TASK]
                    Rank the CANDIDATES from BEST to WORST.
                    Return ONLY the **TOP 5** setups that match the following criteria.
                    
                    **TRADING PARAMETERS**:
                    - **Target Setup**: {setup_type}
                    - **Confluence Filter**: {confluence_mode}{rr_instruction}{prox_instruction}
                    - **MANDATORY MINIMUM R/R**: 1.5:1. (CRITICAL: If Potential Reward is not at least 1.5x the Risk, DISCARD THE SETUP. It is not tradable.)
                    
                    **CRITICAL PHILOSOPHY**:
                    - **NO STATIC PREDICTIONS**: Markets are dynamic. Do not say "It will go up". Say "IF it holds X, THEN it goes up".
                    - **SCENARIO BASED**: You must define specific TRIGGER CONDITIONS. If these triggers are not hit, the trade is invalid.
                    - **The Edge**: We trade the **PARTICIPATION GAP** (the dislocation between the Pre-Market Move and the Open).
                    - *Ideal Setup*: A ticker has reacted to news, moved to a Strategic Support Level, and is now waiting for the Open to reverse.

                    **CONSTRAINTS**:
                    - **NO EXTERNAL DATA**: You must NOT browse the internet or use outside knowledge. Rank these tickers SOLELY based on the "STRATEGIC_PLAN" and "TACTICAL_REALITY" provided in the input.
                    - **OUTPUT FORMAT**: RAW JSON LIST ONLY. Just the JSON array.
                    
                    [JSON OUTPUT SCHEMA]
                    [
                        {{
                            "rank": 1,
                            "ticker": "XYZ",
                            "direction": "LONG/SHORT",
                            "setup_type": "Gap & Go",
                            "rationale": "Concise summary of the thesis.",
                            "trigger_condition": "IF price [ACTION] [LEVEL], THEN [EXPECTATION]. (e.g. IF price holds $150, THEN Long)",
                            "invalidation_logic": "Setup is INVALID IF [CONDITION]. (e.g. IF price closes below $149)",
                            "plan": {{
                                "entry": 150.50,
                                "stop": 149.80,
                                "target": 152.00
                            }}
                        }},
                        ...
                    ]
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
                    # ------------------------------------------------------------------
                    # EXECUTION (Only if NOT Dry Run)
                    # ------------------------------------------------------------------
                    if not dry_run_mode:
                        log_expander = st.expander("📝 Live Execution Logs", expanded=True)
                        ht_logger = AppLogger(log_expander.empty())
                        
                        with st.spinner(f"Head Trader ({ht_model}) is analyzing Market Structure..."):
                            ht_response, err = call_gemini_with_rotation(
                                head_trader_prompt, 
                                "You are a Head Trader.", 
                                ht_logger, 
                                ht_model, 
                                st.session_state.key_manager_instance
                            )
                            
                            if ht_response:
                                try:
                                    # 1. Attempt to parse JSON
                                    json_str = ht_response
                                    # Greedy Search for the outer-most list
                                    match = re.search(r"(\[[\s\S]*\])", ht_response)
                                    if match:
                                        json_str = match.group(1)
                                    
                                    recommendations = json.loads(json_str)
                                    
                                    st.markdown("### 🏆 Head Trader's Top 5")
                                    
                                    for item in recommendations:
                                        tkr = item.get('ticker')
                                        rank = item.get('rank')
                                        direction = item.get('direction', 'Unknown')
                                        rationale = item.get('rationale', 'N/A')
                                        plan = item.get('plan', {})
                                        
                                        trigger = item.get('trigger_condition', 'N/A')
                                        invalid = item.get('invalidation_logic', 'N/A')
                                        
                                        with st.container():
                                            st.subheader(f"#{rank} {tkr} ({direction})")
                                            
                                            # Scenario Logic Display
                                            st.info(f"✅ **TRIGGER:** {trigger}")
                                            if invalid != 'N/A':
                                                st.caption(f"❌ **INVALIDATION:** {invalid}")
                                                
                                            st.write(f"**Rationale:** {rationale}")
                                            
                                            # Plan Details
                                            c1, c2, c3 = st.columns(3)
                                            c1.metric("Entry", plan.get('entry', 'N/A'))
                                            c2.metric("Stop", plan.get('stop', 'N/A'))
                                            c3.metric("Target", plan.get('target', 'N/A'))
                                            
                                            # Chart Overlay
                                            # Interactive TradingView Chart (Routed)
                                            render_tradingview_chart(turso, tkr, simulation_cutoff_str, mode=mode, trade_plan=plan)
                                            st.divider()

                                except json.JSONDecodeError:
                                    st.warning("⚠️ AI Output was not valid JSON. Showing raw text instead.")
                                    st.markdown(ht_response)
                                except Exception as e:
                                    st.error(f"Error displaying results: {e}")
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
