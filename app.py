import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
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
from modules.analysis.detail_engine import update_company_card # GLOBAL IMPORT for Worker Scope
from modules.analysis.macro_engine import generate_economy_card_prompt # GLOBAL IMPORT
from modules.gemini import call_gemini_with_rotation # GLOBAL IMPORT

if 'detailed_premarket_cards' not in st.session_state:
    st.session_state.detailed_premarket_cards = {}

if 'db_plans' not in st.session_state:
    st.session_state.db_plans = {}

st.set_page_config(
    page_title="Context Engine",
    page_icon="🧠",
    layout="wide"
)

# Global Timezone Init
if 'market_timezone' not in st.session_state:
    st.session_state.market_timezone = pytz_timezone('US/Eastern')

# PERSISTENT GAP TRACKING
if 'macro_missing_tickers' not in st.session_state:
    st.session_state.macro_missing_tickers = []
if 'unified_missing_tickers' not in st.session_state:
    st.session_state.unified_missing_tickers = []
if 'macro_analysis_failures' not in st.session_state:
    st.session_state.macro_analysis_failures = []
if 'unified_analysis_failures' not in st.session_state:
    st.session_state.unified_analysis_failures = []
if 'macro_audit_log' not in st.session_state:
    st.session_state.macro_audit_log = []
if 'unified_audit_log' not in st.session_state:
    st.session_state.unified_audit_log = []

# ==============================================================================
# HELPER: VISUALIZE STRUCTURE FOR USER
# ==============================================================================
def escape_markdown(text):
    """Escapes special Markdown characters in a string for safe rendering."""
    if not isinstance(text, str):
        return text
    # Escape $ and ~
    return text.replace('$', '\\$').replace('~', '\\~')

# --- ECONOMY CARD (VIEW) ---
def display_view_economy_card(card_data, key_prefix="eco_view", edit_mode_key="edit_mode_economy"):
    """
    Displays the Economy card data in a read-only, formatted Markdown view.
    Renovated for Narrative Nuance (Phase 8a).
    """
    data = card_data
    
    with st.expander("🌍 Global Economy Narrative", expanded=True):
        # 1. Header & Narrative
        title_col, button_col = st.columns([0.9, 0.1])
        with title_col:
            st.markdown(f"### {escape_markdown(data.get('marketNarrative', 'Initializing Narrative...'))}")
        
        with button_col:
            def _enter_econ_edit_mode():
                st.session_state[edit_mode_key] = True
                try: st.rerun()
                except: pass
            st.button("✏️", key=f"{key_prefix}_edit_narrative", help="Edit narrative", on_click=_enter_econ_edit_mode)

        st.markdown(f"**Market Bias:** {escape_markdown(data.get('marketBias', 'N/A'))}")
        st.markdown("---")

        # 2. Key Data Columns
        col1, col2 = st.columns(2)

        # Column 1: Key Economic Events and Index Analysis
        with col1:
            with st.container():
                st.markdown("##### Key Economic Events")
                events = data.get("keyEconomicEvents", {})
                st.markdown("**Last 24h:**")
                st.info(escape_markdown(events.get('last_24h', 'N/A')))
                st.markdown("**Next 24h:**")
                st.warning(escape_markdown(events.get('next_24h', 'N/A')))

            with st.container():
                st.markdown("##### Index Analysis")
                indices = data.get("indexAnalysis", {})
                st.markdown(f"**Pattern:** {escape_markdown(indices.get('pattern', 'N/A'))}")
                for index, analysis in indices.items():
                    if index != 'pattern' and analysis and analysis.strip():
                        st.markdown(f"**{index}:** {escape_markdown(analysis)}")

        # Column 2: Sector Rotation and Inter-Market Analysis
        with col2:
            with st.container():
                st.markdown("##### Sector Rotation")
                rotation = data.get("sectorRotation", {})
                st.markdown(f"**Leading:** {escape_markdown(', '.join(rotation.get('leadingSectors', [])) or 'N/A')}")
                st.markdown(f"**Lagging:** {escape_markdown(', '.join(rotation.get('laggingSectors', [])) or 'N/A')}")
                st.write(escape_markdown(rotation.get('rotationAnalysis', 'N/A')))

            with st.container():
                st.markdown("##### Inter-Market Analysis")
                intermarket = data.get("interMarketAnalysis", {})
                for asset, analysis in intermarket.items():
                    if analysis and analysis.strip():
                        st.markdown(f"**{asset.replace('_', ' ')}**")
                        st.write(escape_markdown(analysis))

            with st.container():
                st.markdown("##### Market Internals")
                internals = data.get("marketInternals", {})
                for key, analysis in internals.items():
                    if analysis and analysis.strip():
                        st.markdown(f"**{key.capitalize()}:**")
                        st.write(escape_markdown(analysis))

        st.markdown("---")
        
        # 3. Log
        st.markdown("##### Market Key Action Log")
        key_log = data.get('keyActionLog', [])
        if isinstance(key_log, list) and key_log:
            with st.expander("Show Full Market Action Log..."):
                for entry in reversed(key_log): 
                    if isinstance(entry, dict):
                        st.markdown(f"**{entry.get('date', 'N/A')}:** {escape_markdown(entry.get('action', 'N/A'))}")
        
        st.write(f"*Note: {data.get('todaysAction', 'No summary available.')}*")

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
    "PAXGUSDT", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "XLK", "XLE", "GLD", "NDAQ", "^VIX"
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
        get_eod_economy_card,
        get_eod_card_data_for_screener,
        save_snapshot,
        save_deep_dive_card,
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
        if logger: logger.log(f"Watchlist Fetch Error: {e}")
        return []

class AuditLogger:
    """Helper to capture internal API logs into Streamlit Session State for persistence."""
    def __init__(self, session_state_key: str):
        self.key = session_state_key
        self.error_key = f"{session_state_key}_has_errors"
        if self.error_key not in st.session_state:
            st.session_state[self.error_key] = False

    def log(self, message: str):
        if self.key in st.session_state:
            st.session_state[self.key].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        if "❌" in message or "Worker Error" in message or "Failed" in message:
            st.session_state[self.error_key] = True
        print(message)

def run_macro_synthesis(status_obj, eod_card, news_text, bench_date, logger_obj, model_name):
    """
    Reusable block for Macro Integrity Lab Gemini Synthesis.
    """
    from modules.analysis.macro_engine import generate_economy_card_prompt
    
    status_obj.write("4. Synthesizing Macro Narrative (Gemini Masterclass)...")
    
    # Retrieve Rolling Log
    rolling_log = eod_card.get('keyActionLog', []) if eod_card else []

    # Semantic Summarization
    summarized_context = None
    if len(rolling_log) > 10:
        status_obj.write("   📜 Summarizing Long Market History...")
        summary_prompt = f"Summarize the following market log into a concise 'Macro Arc':\n{json.dumps(rolling_log, indent=2)}"
        try:
            sum_resp, _ = call_gemini_with_rotation(summary_prompt, "Summarize History", logger_obj, model_name, st.session_state.key_manager_instance)
            if sum_resp: summarized_context = sum_resp
        except: pass

    # Prompt Generation
    macro_prompt, macro_system = generate_economy_card_prompt(
        eod_card=eod_card,
        etf_structures=[json.loads(s) for s in st.session_state.macro_etf_structures],
        news_input=news_text,
        analysis_date_str=bench_date,
        logger=logger_obj,
        rolling_log=rolling_log,
        pre_summarized_context=summarized_context
    )
    st.session_state.glassbox_prompt = macro_prompt
    st.session_state.glassbox_prompt_system = macro_system

    # Gemini Call
    resp, error_msg = call_gemini_with_rotation(macro_prompt, macro_system, logger_obj, model_name, st.session_state.key_manager_instance)
    if resp:
        try:
            clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
            st.session_state.premarket_economy_card = json.loads(clean)
            st.session_state.latest_macro_date = st.session_state.analysis_date.isoformat()
            st.session_state.app_logger.log("✅ Step 1: Synthesis Complete.")
            status_obj.update(label="Step 1 Complete!", state="complete")
        except Exception as e:
            st.error(f"JSON Parse Error: {e}")
    else:
        st.error(error_msg)



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
    if 'macro_index_data' not in st.session_state:
        st.session_state.macro_index_data = []
    if 'macro_raw_dfs' not in st.session_state:
        st.session_state.macro_raw_dfs = {}
    if 'macro_context_alerts' not in st.session_state or not isinstance(st.session_state.macro_context_alerts, dict):
        st.session_state.macro_context_alerts = {}
    if 'macro_stale_alerts' not in st.session_state:
        st.session_state.macro_stale_alerts = []
    if 'macro_etf_structures' not in st.session_state:
        st.session_state.macro_etf_structures = [] # NEW: AI Data
    if 'utc_timezone' not in st.session_state: st.session_state.utc_timezone = timezone.utc
    if 'local_mode' not in st.session_state: st.session_state.local_mode = False
    if 'trigger_sync' not in st.session_state: st.session_state.trigger_sync = False
    if 'step1_data_ready' not in st.session_state: st.session_state.step1_data_ready = False # NEW: Workflow Split
    if 'unified_context_alerts' not in st.session_state or not isinstance(st.session_state.unified_context_alerts, dict):
        st.session_state.unified_context_alerts = {}
    if 'unified_stale_alerts' not in st.session_state: st.session_state.unified_stale_alerts = []
    if 'macro_audit_log' not in st.session_state: st.session_state.macro_audit_log = []
    if 'macro_audit_log_has_errors' not in st.session_state: st.session_state.macro_audit_log_has_errors = False
    if 'unified_audit_log_has_errors' not in st.session_state: st.session_state.unified_audit_log_has_errors = False
    if 'macro_missing_tickers' not in st.session_state: st.session_state.macro_missing_tickers = []
    if 'macro_analysis_failures' not in st.session_state: st.session_state.macro_analysis_failures = []

    # --- Startup ---
    startup_logger = st.session_state.app_logger
    db_url, auth_token = get_turso_credentials()
    
    # Handle Sync Trigger before connecting (need fresh connection for sync)
    if st.session_state.trigger_sync:
        with st.status("📥 Syncing Database...", expanded=True) as status:
            temp_conn = get_db_connection(db_url, auth_token, local_mode=False)
            if temp_conn:
                success = sync_turso_to_local(temp_conn, "data/local_turso.db", startup_logger)
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

    # --- FORCE RELOAD FOR BUGFIX (Gemini 3 Revert) ---
    if 'key_manager_gemini3_revert' not in st.session_state:
        if 'key_manager_instance' in st.session_state:
            del st.session_state.key_manager_instance
            st.toast("♻️ KeyManager Reloaded (Gemini 3.0 Fix)")
        st.session_state.key_manager_gemini3_revert = True

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
        st.header("Step 1: Macro Context Analysis")
        
        # News Input: Always Visible (User Request)
        st.caption("📝 Overnight News / Context")
        pm_news = st.text_area("Paste relevant headlines/catalysts here...", height=100, key="pm_news_input", label_visibility="collapsed")
        
        # UI IMPROVEMENT: Information for Step 1 Inputs
        st.info("ℹ️ **Engine Inputs**: Synthesis uses **Overnight News**, the latest **Strategic Plan** from DB, and structural scans of **20+ Indices** based on the current **Mission Clock**.")
        
        # 1. Action Button: FETCH DATA ONLY
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
            # State is already cleared by callback
            
            with st.status(f"Fetching Macro Data...", expanded=True) as status:
                a_logger = AuditLogger('macro_audit_log')
                a_logger.log("🚀 Starting Macro Scan 1a...")

                # A. FETCH EOD
                status.write("1. Retrieving End-of-Day Context...")
                # Use Simulation Cutoff directly (allows finding same-day plans if needed)
                lookup_cutoff = (simulation_cutoff_dt).strftime('%Y-%m-%d %H:%M:%S')
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
                        st.error("❌ Capital.com Authentication Failed. Check Infisical Secrets or enable **DB Fallback** in the Mission Config to proceed with historical data.")
                        st.stop()

                import time
                progress_bar = st.progress(0)
                
                # PHASE 1: SEQUENTIAL GATHERING (Rate Limit Compliant)
                status.write("2. Gathering Market Data (Sequential Fetches)...")
                raw_datafeeds = {}
                st.session_state.macro_missing_tickers = []
                for idx, t in enumerate(CORE_INTERMARKET_TICKERS):
                    status.write(f"   Fetching {t}...")
                    df = get_session_bars_routed(
                        turso, 
                        t, 
                        benchmark_date_str, 
                        simulation_cutoff_str, 
                        mode=mode, 
                        logger=a_logger, # Use AuditLogger
                        db_fallback=st.session_state.get('db_fallback', False),
                        days=2.9, # LOOSENED: Structural Context without clamping
                        resolution="MINUTE_5"
                    )
                    if df is not None and not df.empty:
                        raw_datafeeds[t] = df
                    else:
                        st.session_state.macro_missing_tickers.append(t)
                        a_logger.log(f"❌ {t}: Failed to fetch data (Check resolution or market hours).")
                    
                    # Respect Capital.com 1s Rate Limit (ONLY in Live mode without DB fallback)
                    if mode == "Live" and not st.session_state.get('db_fallback', False):
                        time.sleep(1)
                    
                    progress_bar.progress((idx + 1) / len(CORE_INTERMARKET_TICKERS))

                # GAP DETECTION WARNING (Status box visibility)
                if st.session_state.macro_missing_tickers:
                    status.write(f"⚠️ **Gaps detected**: {', '.join(st.session_state.macro_missing_tickers)}")

                # PHASE 2: PARALLEL ANALYSIS (CPU Bound)
                status.write("3. Analyzing Market Structure (Parallel Engine)...")
                
                # NARRATIVE PIVOT: Define Session Start (04:00 ET) for Anchor & Delta filtering
                session_start_dt = simulation_cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0)

                def analyze_macro_worker(ticker, df, session_start_dt=None):
                    """
                    Worker for Macro Indices.
                    """
                    try:
                        from modules.processing import analyze_market_context
                        latest_row = df.iloc[-1]
                        latest_price = latest_row['Close']
                        p_ts = latest_row['timestamp']
                        
                        # Get Previous Close Reference
                        ref_levels = get_previous_session_stats(turso, ticker, benchmark_date_str, logger=None)
                        card = analyze_market_context(df, ref_levels, ticker=ticker, session_start_dt=session_start_dt)
                        
                        mig_count = len(card.get('value_migration_log', []))
                        imp_count = len(card.get('key_level_rejections', []))
                        
                        freshness = 0.0
                        lag_min = 999.0
                        try:
                            if p_ts:
                                ts_clean = str(p_ts).replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: 
                                    ts_obj = pytz_timezone('UTC').localize(ts_obj)
                                ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern')).replace(tzinfo=None)
                                lag_min = (simulation_cutoff_dt.replace(tzinfo=None) - ts_et).total_seconds() / 60.0
                                freshness = max(0.0, 1.0 - (lag_min / 60.0))
                        except Exception as e: 
                            print(f"Freshness Calc Error for {ticker}: {e}")

                        data_source = df['source'].iloc[0] if 'source' in df.columns else ('Capital.com' if mode == 'Live' else 'DB')
                        
                        # Get UTC timestamp if available
                        ts_utc = "N/A"
                        if p_ts:
                            try:
                                # Ensure we have the UTC version
                                if 'dt_utc' in df.columns:
                                    ts_utc = str(df['dt_utc'].iloc[-1])
                                else:
                                    ts_utc = str(p_ts)
                            except: ts_utc = str(p_ts)

                        # FRESHNESS SCORE (0-1 scale, where 1.0 is < 5 mins and 0.0 is > 60 mins)
                        freshness_progress = max(0.0, 1.0 - (lag_min / 60.0))
                        
                        return {
                            "ticker": ticker,
                            "card": card,
                            "latest_price": latest_price,
                            "latest_ts_utc": ts_utc,
                            "data_source": data_source,
                            "mig_count": mig_count,
                            "imp_count": imp_count,
                            "freshness_score": freshness_progress,
                            "lag_min": lag_min,
                            "df": df
                        }
                    except Exception as e:
                        err_msg = f"Worker Error for {ticker}: {str(e)}"
                        print(err_msg)
                        # AuditLogger is not thread-safe for direct append from worker threads
                        # st.session_state.macro_audit_log.append(f"⚠️ {t}: Analysis Failure - {str(e)}")
                        return {"ticker": ticker, "error": str(e), "failed_analysis": True}

                macro_results = []
                st.session_state.macro_analysis_failures = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(analyze_macro_worker, t, df, session_start_dt) for t, df in raw_datafeeds.items()]
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        if res:
                            if res.get('failed_analysis'):
                                st.session_state.macro_analysis_failures.append(res['ticker'])
                                a_logger.log(f"⚠️ {res['ticker']}: Analysis Failure - {res['error']}")
                            else:
                                macro_results.append(res)
                
                # Sort alphabetically for consistency
                macro_results = sorted(macro_results, key=lambda x: x['ticker'])

                # STALE CHECK (Unified Date Check)
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
                    for dt, tks in context_map.items():
                        a_logger.log(f"⚠️ Context Alert ({dt}): {', '.join(tks)}")

                if st.session_state.macro_analysis_failures:
                    st.error(f"⚠️ **Analysis Error**: Failed to analyze {len(st.session_state.macro_analysis_failures)} symbols: {', '.join(st.session_state.macro_analysis_failures)}.")

                # STALE CHECK (>1h)
                stale_1h = [r['ticker'] for r in macro_results if r['lag_min'] > 60]
                if stale_1h:
                    st.session_state.macro_stale_alerts = stale_1h
                    a_logger.log(f"🚨 Stale Data Alert: {len(stale_1h)} symbols have data older than 1 HOUR: {', '.join(stale_1h)}.")

                stale_30m = [r['ticker'] for r in macro_results if 30 < r['lag_min'] <= 60]
                if stale_30m:
                    a_logger.log(f"⏰ Delayed Data: {len(stale_30m)} symbols have 30-60m lag: {', '.join(stale_30m)}.")

                # Final Processing & UI Rendering (Main Thread)
                for idx, res in enumerate(macro_results):
                    st.session_state.macro_etf_structures.append(json.dumps(res['card']))
                    st.session_state.macro_raw_dfs[res['ticker']] = res['df'] # SAVE FOR POST-REFRESH CHARTS
                    st.session_state.macro_index_data.append({
                        "Ticker": res['ticker'],
                        "Freshness": res['freshness_score'],
                        "Price": f"${res['latest_price']:.2f}",
                        "Timestamp (UTC)": res['latest_ts_utc'],
                        "Lag (m)": f"{res['lag_min']:.1f}",
                        "Source": res['data_source']
                    })

                # CRITICAL CHECK: PREVENT EMPTY API CALLS
                if not st.session_state.macro_etf_structures:
                    status.update(label="Aborted: No Data", state="error")
                    if mode == "Live":
                         st.error("❌ No Data received from Capital.com. Check Market Hours or enable **DB Fallback** in the Mission Config.")
                         a_logger.log("❌ No Data received from Capital.com.")
                    else:
                         st.error("❌ No Market Data found in DB (Core Indices). Aborting AI Call to save credits.")
                         a_logger.log("❌ No Market Data found in DB (Core Indices).")
                    st.stop()
                
                # DATA READY - Check for Gaps (Missing or Analysis Failures) or Stale Data (>1h)
                st.session_state.step1_data_ready = True
                
                # Check for critical gaps
                has_critical_gaps = bool(st.session_state.macro_missing_tickers) or bool(st.session_state.macro_analysis_failures)
                # Check for stale data (>1h)
                has_stale_data = bool(st.session_state.get('macro_stale_alerts'))
                
                if has_critical_gaps or has_stale_data:
                    # STOP: Gaps or Stale Data detected. Exit button logic.
                    if has_critical_gaps:
                        status.update(label="⚠️ Gaps Detected - Verification Required", state="error")
                        a_logger.log("⚠️ Gaps detected. Stopping for user confirmation.")
                    else:
                        status.update(label="⏰ Stale Data Detected - Confirmation Required", state="error")
                        a_logger.log("⏰ Stale data detected (>1h). Stopping for user confirmation.")
                    st.rerun()
                else:

                    st.session_state.macro_force_synthesis = False # Reset if we reached here naturally
                    
                    # --- AUTO-TRIGGER AI SYNTHESIS (Zero Gaps Path) ---
                    run_macro_synthesis(status, eod_card, pm_news, benchmark_date_str, logger, selected_model)
                    st.rerun()

        st.markdown("---") # RESTORED: Separator after Action Button


        # 2. MIDDLE SECTION (Verification & Prompt Construction)
        # --- RESULTS & VERIFICATION (Combined Step 1 Output) ---
        if st.session_state.step1_data_ready:
            
            # Dynamic Heading based on State
            if not st.session_state.premarket_economy_card:
                st.markdown("### 🔍 Data Integrity Verification")
            else:
                st.markdown("### ✅ Macro Context Results")

            # A. Verification Data (PRIORITIZED)
            if st.session_state.premarket_economy_card:
                st.subheader("1. Data Verification")
                # Display Helper (Summary)
                total_expected = len(CORE_INTERMARKET_TICKERS)
                st.caption(f"Indices Scanned: {len(st.session_state.macro_index_data)} / {total_expected}")

            
            # 1. CRITICAL GAP & STALE DATA GUARD UI
            has_critical_gaps = bool(st.session_state.macro_missing_tickers) or bool(st.session_state.macro_analysis_failures)
            has_stale_data = bool(st.session_state.get('macro_stale_alerts'))
            
            if (has_critical_gaps or has_stale_data) and not st.session_state.premarket_economy_card:
                if has_critical_gaps:
                    st.error("🚨 **Gaps Detected in Market Data**")
                    if st.session_state.macro_missing_tickers:
                        st.markdown(f"- **Missing Tickers**: {', '.join(st.session_state.macro_missing_tickers)}")
                    if st.session_state.macro_analysis_failures:
                        st.markdown(f"- **Analysis Failures**: {', '.join(st.session_state.macro_analysis_failures)}")
                
                if has_stale_data:
                    st.warning(f"⏰ **Stale Data Alert**: The following indices are older than 1 hour: **{', '.join(st.session_state.macro_stale_alerts or [])}**")
                
                st.info("💡 **Decision Required**: Are you sure you want to make the LLM call? Synthesis is paused to save credits.")

                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚀 Proceed Anyway (Use Credits)", type="primary", width="stretch"):
                        with st.status("Manual Synthesis Triggered...", expanded=True) as status_man:
                            eod_card = st.session_state.get('glassbox_eod_card', {})
                            news_in = st.session_state.get('pm_news_input', '')
                            run_macro_synthesis(status_man, eod_card, news_in, benchmark_date_str, logger, selected_model)
                            st.rerun()

                
                with c2:
                    if st.button("🔄 Clean & Retry Fetch", type="secondary", width="stretch"):
                        clear_step1_state()
                        st.rerun()

            # Alerts (Only show as supplementary info if the AI Narrative is already generated)
            if st.session_state.premarket_economy_card:
                if st.session_state.get('macro_context_alerts'):
                    for d, tks in st.session_state.macro_context_alerts.items():
                        st.warning(f"⚠️ **Context Alert ({d})**: Data for **{', '.join(tks)}** is from a previous session.")
                
                if st.session_state.get('macro_stale_alerts'):
                    st.error(f"🚨 **Stale Data Alert**: {len(st.session_state.macro_stale_alerts)} symbols have >1hr lag.")

                if st.session_state.macro_missing_tickers:
                    st.warning(f"⚠️ **Data Gaps**: **{', '.join(st.session_state.macro_missing_tickers)}** failed to fetch.")


            # Tables & Charts
            with st.expander("📝 Summary Table & Details", expanded=False):
                st.dataframe(pd.DataFrame(st.session_state.macro_index_data))
                if st.session_state.macro_raw_dfs:
                    st.markdown("#### Structural Charts")
                    for t, df in st.session_state.macro_raw_dfs.items():
                        st.markdown(f"**{t}**")
                        render_lightweight_chart_simple(df, t, height=200)

            # Audit Log
            if st.session_state.macro_audit_log and st.session_state.get('macro_audit_log_has_errors'):
                with st.expander("🛠️ Technical Audit Log", expanded=False):
                    for entry in st.session_state.macro_audit_log: st.write(entry)
                    
            # Prompt Review
            if st.session_state.get('glassbox_prompt'):
                with st.expander("🔍 Review AI Prompt", expanded=False):
                    st.code(st.session_state.glassbox_prompt, language="text")



            # B. AI Narrative (The Verdict)
            if st.session_state.premarket_economy_card:
                st.markdown("### 🤖 The Macro Narrative")
                display_view_economy_card(st.session_state.premarket_economy_card)
                
                with st.expander("View Full Card JSON", expanded=False):
                    st.json(st.session_state.premarket_economy_card)




    # ==============================================================================
    # TAB 2: STOCK SELECTION (STEP 2)
    # ==============================================================================
    with tab2:
        st.title("Step 2: Selection Hub")
        
        # A. Workflow Guide
        with st.container():
            g1, g2 = st.columns([3, 1])
            with g1:
                st.markdown("""
                ### 🎯 Selection Workflow
                1. **(Optional) Deep Prep**: Use the "Detailed Analysis" below if you need a fresh strategy card for specific stocks.
                2. **Execute Scan**: Run the **Unified Scanner** to find tickers near key structural levels from your watchlist.
                3. **Evaluate Results**: Check the table and proximity alerts to pick your final candidates for Step 3.
                """)
            with g2:
                if st.session_state.detailed_premarket_cards:
                    st.success(f"✅ {len(st.session_state.detailed_premarket_cards)} Detailed Cards Ready")
                else:
                    st.info("ℹ️ No Deep Dive cards generated yet.")

        st.divider()

        # B. Detailed Pre-Market Analysis (Moved to Expander)
        with st.expander("🧠 Deep Preparation: Masterclass Model (Optional)", expanded=False):
            st.markdown("#### Detailed Pre-Market Deep Dive")
            st.caption("Freshly analyze specific tickers using the 4-Participant Trading Model.")
            
            # Helper to check if we have detailed cards
            if 'detailed_premarket_cards' not in st.session_state:
                st.session_state.detailed_premarket_cards = {}

            # 1. Select Tickers
            if not st.session_state.get('watchlist_cache'):
                 st.session_state.watchlist_cache = fetch_watchlist(turso, logger)
            
            candidates = sorted(list(set(st.session_state.watchlist_cache))) if st.session_state.get('watchlist_cache') else []
            default_sel = list(st.session_state.detailed_premarket_cards.keys()) if st.session_state.detailed_premarket_cards else candidates[:3]
            
            selected_deep_dive = st.multiselect("Tickers for deep-dive Preparation:", candidates, default=default_sel, key="deep_dive_multiselect")
            
            if st.button("Generate Detailed Preparation Cards", type="secondary"):
                if not st.session_state.premarket_economy_card:
                    st.warning("⚠️ Please Generate Macro Context (Step 1) first.")
                    st.stop()
                
                deep_results = {}
                
                # PREPARE THREAD-SAFE OBJECTS
                km = st.session_state.get('key_manager_instance')
                
                # --- PRE-FETCH DATA IN MAIN THREAD (Sequential IO) ---
                # We fetch all necessary DB data here to avoid DB connections in threads.
                pre_fetched_data = {}
                
                from modules.analysis.impact_engine import get_or_compute_context
                
                with st.status("Fetching Data Context...", expanded=False) as status_io:
                    for ticker in selected_deep_dive:
                        status_io.write(f"Fetching context for {ticker}...")
                        try:
                            # 1. Fetch Impact Context (Price/Levels)
                            # Using main thread 'turso' client which is safe here
                            context_card = get_or_compute_context(turso, ticker, str(st.session_state.analysis_date), logger)
                            impact_json = json.dumps(context_card, indent=2)
                        except Exception as e:
                            logger.log(f"Pre-fetch Context Error {ticker}: {e}")
                            impact_json = json.dumps({"error": str(e), "note": "Pre-fetch failed"})
                        
                        # 2. Fetch Previous Card (Simulated/Placeholder for now as per original code)
                        # If we had a DB table for cards, we'd fetch it here.
                        prev_card_json = "{}" 
                        
                        pre_fetched_data[ticker] = {
                            "impact_context": impact_json,
                            "previous_card": prev_card_json
                        }
                    status_io.update(label="✅ Data Fetched! Starting AI Analysis...", state="complete")

                # Worker (PURE CPU/AI - NO DB)
                def process_deep_dive(ticker, key_mgr, macro_summary, date_obj, model, static_data, st_status, st_ctx):
                    import traceback
                    if st_ctx:
                        add_script_run_ctx(ctx=st_ctx)
                    # Thread-safe UI Logger for Streamlit
                    class StreamlitThreadLogger:
                        def __init__(self, ticker, status_container):
                            self.ticker = ticker
                            self.status = status_container
                        
                        def log(self, msg):
                            # Print to terminal for redundancy
                            print(f"[Worker-{self.ticker}] {msg}")
                            # Write to Streamlit container with ticker prefix
                            # Use colored markers for different tickers
                            colors = ["blue", "green", "orange", "red", "violet", "gray"]
                            t_color = colors[hash(self.ticker) % len(colors)]
                            self.status.write(f"**:{t_color}[{self.ticker}]** {msg}")
                    
                    local_logger = StreamlitThreadLogger(ticker, st_status)
                    
                    try:
                        # Unpack pre-fetched data
                        data = static_data.get(ticker, {})
                        impact_json = data.get("impact_context", "{}")
                        prev_card = data.get("previous_card", "{}")
                        
                        print(f"    [DEBUG] {ticker}: Context Len: {len(impact_json)}, Prev Card Len: {len(prev_card)}")

                        # Generate
                        json_result = update_company_card(
                            ticker=ticker,
                            previous_card_json=prev_card,
                            previous_card_date=str(date_obj - timedelta(days=1)), # Dummy
                            historical_notes="", 
                            new_eod_summary="", 
                            new_eod_date=date_obj,
                            model_name=model,
                            key_manager=key_mgr,
                            pre_fetched_context=impact_json, # PASS JSON STRING directly
                            market_context_summary=macro_summary,
                            logger=local_logger # Use ThreadSafe UI Version
                        )
                        
                        # PERSIST TO TURSO (Persistent Live Storage)
                        if json_result:
                            save_deep_dive_card(turso, ticker, str(date_obj), json_result, local_logger)
                            
                        return ticker, json_result
                    except Exception as e:
                        local_logger.log(f"❌ Worker EXCEPTION: {e}")
                        traceback.print_exc() # FORCE PRINT TO TERMINAL
                        return ticker, None

                # Parallel Run
                macro_context_summary = json.dumps(st.session_state.premarket_economy_card, indent=2)
                ctx = get_script_run_ctx()
                print(f"[DEBUG] Starting Parallel Execution. Workers: 20. Tickers: {len(selected_deep_dive)}")
                with st.status(f"Generating Masterclass Cards ({len(selected_deep_dive)})...", expanded=True) as status_deep:
                    # UTILIZE ALL KEYS: Increased workers to 20 to allow full parallel utilization of API rotation
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                        # Pass a copy of the key manager if it's mutable? It usually is thread-safe for reading.
                        futures = {executor.submit(process_deep_dive, t, km, macro_context_summary, st.session_state.analysis_date, selected_model, pre_fetched_data, status_deep, ctx): t for t in selected_deep_dive}
                        
                        for future in concurrent.futures.as_completed(futures):
                            tkr, res = future.result()
                            if res:
                                deep_results[tkr] = json.loads(res)
                            else:
                                status_deep.write(f"❌ **{tkr}**: Generation failed. See detailed logs above.")
                                
                    if deep_results:
                        st.session_state.detailed_premarket_cards.update(deep_results)
                        status_deep.update(label="✅ Deep Prep Complete!", state="complete")
                        st.rerun()

            # Display Deep Dive Cards
            if st.session_state.detailed_premarket_cards:
                st.markdown("---")
                for tkr, card in st.session_state.detailed_premarket_cards.items():
                    with st.container():
                        tk_c1, tk_c2 = st.columns([1, 2])
                        tk_c1.markdown(f"#### {tkr}")
                        tk_c1.info(f"**Confidence**: {card.get('confidence', 'N/A')}")
                        tk_c2.code(card.get('screener_briefing', 'N/A'), language='yaml')
                        with st.expander(f"View Full {tkr} Card JSON", expanded=False):
                            st.json(card)
                        st.divider()

        st.subheader("Unified Selection Scanner")
        st.caption("Find stocks from your watchlist nearing strategic levels for today's session.")
        
        # UI controls for both
        prox_col1, prox_col2 = st.columns([2, 1])
        with prox_col1:
            scan_threshold = st.slider("Proximity % (Strategic Level Check)", 0.1, 5.0, 2.5)
        with prox_col2:
            st.write("") # Spacer
            st.write("")
            run_btn = st.button("Run Unified Selection Scan (Structure + Proximity)", type="primary", width="stretch")

        # Display Table Here
        # --- SHOW ACTUAL VS EXPECTED --- (Refined)
        if st.session_state.glassbox_etf_data:
            watchlist_list = sorted(list(set(fetch_watchlist(turso, None))))
            watchlist_count = len(watchlist_list)
            st.info(f"Watchlist Assets Scanned: {len(st.session_state.glassbox_etf_data)} / {watchlist_count}")
        
        # --- PERSISTENT GAP WARNING (Outside) ---
        if st.session_state.get('unified_missing_tickers'):
            st.warning(f"⚠️ **Unified Scan Gaps**: Data missing for {', '.join(st.session_state.unified_missing_tickers)}.")

        if st.session_state.get('unified_context_alerts'):
            u_contexts = st.session_state.unified_context_alerts
            if isinstance(u_contexts, dict):
                for d, tks in u_contexts.items():
                    st.warning(f"⚠️ **Unified Context Alert ({d})**: Data for **{', '.join(tks)}** is from a previous session.")
            
        if st.session_state.get('unified_stale_alerts'):
            st.error(f"🚨 **Unified Stale Alert**: {len(st.session_state.unified_stale_alerts)} assets have data older than 1 HOUR: **{', '.join(st.session_state.unified_stale_alerts)}**.")

        if st.session_state.glassbox_etf_data:
            with st.expander("📝 View Selection Strategy Table", expanded=True):
                time_label = simulation_cutoff_dt.strftime('%H:%M')
                st.dataframe(
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
            st.info("Ready for Unified Selection Scan...")

        if run_btn:
            if not st.session_state.premarket_economy_card:
                st.warning("⚠️ Please Generate Macro Context (Step 1) first.")
            else:
                st.session_state.glassbox_etf_data = []
                st.session_state.glassbox_raw_cards = {}
                st.session_state.proximity_scan_results = []
                st.session_state.unified_missing_tickers = []
                st.session_state.unified_audit_log = [] # Clear audit log on new fetch
                st.session_state.unified_audit_log_has_errors = False
                st.session_state.unified_context_alerts = {}
                st.session_state.unified_stale_alerts = []
                st.session_state.db_plans = {}

                with st.status(f"Running Unified Selection Scan ({mode})...", expanded=True) as status:
                    u_logger = AuditLogger('unified_audit_log')
                    u_logger.log("🚀 Starting Unified Selection Scan...")
                    import time
                    # 1. Fetch Watchlist & Strategic Plans
                    watchlist = fetch_watchlist(turso, u_logger)
                    full_ticker_list = sorted(list(set(watchlist)))
                    
                    ref_date_dt = st.session_state.analysis_date
                    ref_date_str = ref_date_dt.strftime('%Y-%m-%d')
                    
                    status.write("1. Loading Strategic Plans for Proximity Check...")
                    st.session_state.db_plans = get_eod_card_data_for_screener(turso, tuple(full_ticker_list), ref_date_str, u_logger)
                    
                    # PHASE A+B: UNIFIED PARALLEL PIPELINE
                    u_session_start_dt = simulation_cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0)
                    
                    def analyze_ticker_unified_worker(ticker_to_scan, session_start_dt=None, st_ctx=None):
                        """
                        Unified Worker: Fetches AND analyzes data in parallel.
                        """
                        if st_ctx:
                            add_script_run_ctx(ctx=st_ctx)
                        
                        try:
                            # 1. FETCH DATA
                            df = get_session_bars_routed(
                                turso, 
                                ticker_to_scan, 
                                benchmark_date_str, 
                                simulation_cutoff_str, 
                                mode=mode, 
                                logger=None, # Don't flood audit log from threads
                                db_fallback=st.session_state.get('db_fallback', False),
                                premarket_only=False,
                                days=2.9,
                                resolution="MINUTE_5"
                            )
                            
                            if df is None or df.empty:
                                return {"ticker": ticker_to_scan, "error": "Fetch failed", "missing_data": True}

                            from modules.processing import analyze_market_context
                            # 2. ANALYZE PRICE ACTION
                            latest_row = df.iloc[-1]
                            l_price = float(latest_row['Close'])
                            p_ts = latest_row['timestamp'] if 'timestamp' in df.columns else latest_row.get('dt_eastern')

                            # B. STRUCTURE ANALYSIS
                            ref_levels = get_previous_session_stats(turso, ticker_to_scan, benchmark_date_str, logger=None)
                            card = analyze_market_context(df, ref_levels, ticker=ticker_to_scan, session_start_dt=session_start_dt)
                            
                            mig_count = len(card.get('value_migration_log', []))
                            imp_count = len(card.get('key_level_rejections', []))
                            
                            freshness_score = 0.0
                            l_minutes = 999.0
                            if p_ts:
                                ts_clean = str(p_ts).replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: ts_obj = pytz_timezone('UTC').localize(ts_obj)
                                ts_et = ts_obj.astimezone(pytz_timezone('US/Eastern')).replace(tzinfo=None)
                                l_minutes = (simulation_cutoff_dt.replace(tzinfo=None) - ts_et).total_seconds() / 60.0
                                freshness_score = max(0.0, 1.0 - (l_minutes / 60.0))

                            # C. PROXIMITY CHECK
                            prox_alert = None
                            plan_data = st.session_state.db_plans.get(ticker_to_scan)
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

                            # TIMESTAMP EXTRACTION (UTC)
                            ts_u = "N/A"
                            if p_ts:
                                try:
                                    if 'dt_utc' in df.columns: ts_u = str(df['dt_utc'].iloc[-1])
                                    else: ts_u = str(p_ts)
                                except: ts_u = str(p_ts)

                            # FRESHNESS SCORE
                            freshness_p = max(0.0, 1.0 - (l_minutes / 60.0))

                            return {
                                "ticker": ticker_to_scan,
                                "card": card,
                                "prox_alert": prox_alert,
                                "lag_min": l_minutes,
                                "latest_ts_utc": ts_u,
                                "table_row": {
                                    "Ticker": ticker_to_scan,
                                    "Freshness": freshness_p,
                                    "Price": f"${l_price:.2f}",
                                    "Timestamp (UTC)": ts_u,
                                    "Lag (m)": f"{l_minutes:.1f}" if p_ts else "N/A",
                                    "Migration Blocks": mig_count,
                                    "Impact Levels": imp_count,
                                }
                            }
                        except Exception as e: 
                            return {"ticker": ticker_to_scan, "error": str(e), "failed_analysis": True}

                    status.write(f"2. Processing {len(full_ticker_list)} assets (Parallel Fetch + Analysis)...")
                    prog_scan = st.progress(0)
                    
                    unified_results_list = []
                    st.session_state.unified_analysis_failures = []
                    st.session_state.unified_missing_tickers = []
                    
                    ctx = get_script_run_ctx()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        future_to_ticker = {executor.submit(analyze_ticker_unified_worker, t, u_session_start_dt, ctx): t for t in full_ticker_list}
                        
                        completed = 0
                        for future in concurrent.futures.as_completed(future_to_ticker):
                            res = future.result()
                            completed += 1
                            prog_scan.progress(completed / len(full_ticker_list))
                            
                            if res:
                                if res.get('missing_data'):
                                    st.session_state.unified_missing_tickers.append(res['ticker'])
                                    u_logger.log(f"❌ {res['ticker']}: Failed to fetch data.")
                                elif res.get('failed_analysis'):
                                    st.session_state.unified_analysis_failures.append(res['ticker'])
                                    u_logger.log(f"⚠️ {res['ticker']}: Analysis error: {res.get('error')}")
                                else:
                                    unified_results_list.append(res)
                                    st.session_state.glassbox_raw_cards[res['ticker']] = res['card']
                                    st.session_state.glassbox_etf_data.append(res['table_row'])
                                    if res['prox_alert']:
                                        st.session_state.proximity_scan_results.append(res['prox_alert'])

                    if st.session_state.unified_missing_tickers:
                        status.write(f"⚠️ **Watchlist Gaps**: {', '.join(st.session_state.unified_missing_tickers)}")

                    # Sort for consistent display
                    st.session_state.glassbox_etf_data = sorted(st.session_state.glassbox_etf_data, key=lambda x: x['Ticker'])

                    # STALE CHECK (Unified)
                    analysis_date_str = st.session_state.analysis_date.strftime('%Y-%m-%d')
                    u_context_map = {}
                    for r in unified_results_list:
                         if r['latest_ts_utc'] != "N/A":
                             d = r['latest_ts_utc'][:10]
                             if d != analysis_date_str:
                                 if d not in u_context_map: u_context_map[d] = []
                                 u_context_map[d].append(r['ticker'])
                    
                    if u_context_map:
                        st.session_state.unified_context_alerts = u_context_map
                        for dt, tks in u_context_map.items():
                            u_logger.log(f"⚠️ Context Alert ({dt}): {', '.join(tks)}")

                    if st.session_state.unified_analysis_failures:
                        u_logger.log(f"⚠️ Analysis Error: Failed to analyze symbols: {', '.join(st.session_state.unified_analysis_failures)}.")

                    stale_u_1h = [r['ticker'] for r in unified_results_list if r['lag_min'] > 60]
                    if stale_u_1h:
                        st.session_state.unified_stale_alerts = stale_u_1h
                        u_logger.log(f"🚨 Stale Watchlist Alert: {len(stale_u_1h)} assets have data older than 1 HOUR: {', '.join(stale_u_1h)}.")

                    stale_u_30m = [r['ticker'] for r in unified_results_list if 30 < r['lag_min'] <= 60]
                    if stale_u_30m:
                        u_logger.log(f"📊 Note: {len(stale_u_30m)} assets have 30-60m lag.")

                    # --- PERSISTENT AUDIT LOG (Conditional) ---
                    if st.session_state.unified_audit_log and st.session_state.get('unified_audit_log_has_errors'):
                        with st.expander("🛠️ Detailed Audit Log (Technical)", expanded=False):
                            for entry in st.session_state.unified_audit_log:
                                st.write(entry)

                    status.update(label="✅ Unified Scan Complete!", state="complete")
                    st.rerun()

        # Proximity Alerts Display (If any)
        if st.session_state.proximity_scan_results:
            st.success(f"🎯 Found {len(st.session_state.proximity_scan_results)} Proximity Alerts")
            st.dataframe(pd.DataFrame(st.session_state.proximity_scan_results).sort_values("Dist %"), width="stretch")

        # PERSISTENT ERROR VISIBILITY (Step 2 Failures)
        if st.session_state.get('unified_analysis_failures'):
            st.error(f"⚠️ **Analysis Failures**: The following symbols failed to analyze: {', '.join(st.session_state.unified_analysis_failures)}")
            if st.session_state.unified_audit_log:
                with st.expander("🛠️ View Detailed Audit Log for Failures", expanded=False):
                    for entry in st.session_state.unified_audit_log:
                        st.write(entry)

        # --- NEW: Card Intel Status Table ---
        if st.session_state.db_plans:
            with st.expander("📊 Card Intel (Tiered Lookup Details)", expanded=False):
                intel_df_list = []
                for tkr, info in st.session_state.db_plans.items():
                    # Use the source flags from the tiered lookup
                    source_label = "LIVE 🟢" if info.get('is_live') else "EOD 📜"
                    
                    # Format timestamp
                    raw_ts = info.get('timestamp', 'N/A')
                    if raw_ts and raw_ts != "Historical":
                        try:
                            # Extract just Time or Date+Time
                            gen_at = raw_ts[11:16] # HH:MM
                        except:
                            gen_at = raw_ts
                    else:
                        gen_at = "N/A"

                    intel_df_list.append({
                        "Ticker": tkr,
                        "Source": source_label,
                        "Market Version": info.get('plan_date'),
                        "Generated At": gen_at,
                        "Levels": f"S: {len(info.get('s_levels', []))} | R: {len(info.get('r_levels', []))}"
                    })
                st.dataframe(pd.DataFrame(intel_df_list).sort_values(["Source", "Ticker"], ascending=[False, True]), width="stretch")

        # VISUALIZATION
        if st.session_state.glassbox_raw_cards:
            with st.expander("🔍 View Company Structure Charts", expanded=False):
                companies = sorted(list(st.session_state.glassbox_raw_cards.keys()))
                for tkr in companies:
                    st.markdown(f"### {tkr}")
                    fig = render_market_structure_chart(st.session_state.glassbox_raw_cards[tkr])
                    if fig: st.plotly_chart(fig, width="stretch")
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
                
                submitted = st.form_submit_button("🧠 Run Head Trader Analysis", type="primary", width="stretch")

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
                            # Use the updated tiered fetch in database.py
                            print(f"DEBUG: Fetching Strategic Plan for {tkr} (Tiered lookup)...") 
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
                            "THE_ANCHOR (Strategic Plan)": strategic_plans.get(t, "No Plan Found"),
                            "THE_DELTA (Live Tape)": {
                                "current_price": card['reference_levels']['current_price'],
                                "session_delta_structure": pm_migration,
                                "new_impact_zones_detected": card['key_level_rejections']
                            }
                        }
                        context_packet.append(evidence)
                    
                    # ------------------------------------------------------------------
                    # 4. CONSTRUCT PROMPT (MODULAR)
                    # ------------------------------------------------------------------
                    
                    # PART 1: CONTEXT & ROLE
                    prompt_part_1 = f"""
                    [ROLE]
                    You are the Head Trader of a proprietary trading desk. Your job is to analyze the "Narrative Momentum" using the **Anchor & Delta** method.
                    
                    [GLOBAL MACRO CONTEXT]
                    (The "Wind" - The Governing Anchor for the entire market)
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
                        For this batch of tickers, compare THE_ANCHOR with THE_DELTA.
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
                    
                    **CRITICAL PHILOSOPHY: ANCHOR & DELTA**
                    - **THE ANCHOR**: The "Strategic Plan" is the established story. Assume it holds the highest probability UNLESS the Delta shows a break.
                    - **THE DELTA**: The "Live Tape" contains ONLY developments since today's open.
                    - **NARRATIVE INTEGRITY**: CHECK THE [GLOBAL MACRO CONTEXT]. If the `narrativeStatus` is 'BREAKING ANCHOR', assume ALL individual stock 'Strategic Plans' are compromised. In this state, prioritize 'TIGHT TACTICALS' (price action only) or discard the setup as too ambiguous.
                    - **CONFIRMATION**: If the Delta structure respects the Anchor's levels and the Macro Context is 'HOLDING', conviction for the plan INCREASES.
                    
                    **NO STATIC PREDICTIONS**: Markets are dynamic. Do not say "It will go up". Say "IF it holds X (Delta confirms Anchor), THEN it goes up".
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
