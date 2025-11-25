import streamlit as st
import pandas as pd
import requests
import json
import re
import time
import random
import base64
import numpy as np
from datetime import datetime, timezone, timedelta, time as dt_time
from pytz import timezone as pytz_timezone
from libsql_client import create_client_sync, LibsqlError

# --- LOCAL IMPORT ---
# Assumes key_manager.py is in the same folder
try:
    from key_manager import KeyManager
except ImportError:
    st.error("❌ CRITICAL MISSING FILE: 'key_manager.py' was not found in this directory.")
    st.stop()

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================

# --- Page Config ---
st.set_page_config(page_title="Pre-Market Analyst (Glass Box)", layout="wide")

# --- Timezone & Market Hours ---
US_EASTERN = pytz_timezone('US/Eastern')
MARKET_OPEN_TIME = dt_time(9, 30) # 09:30 AM ET

# --- API Config ---
# We remove the hardcoded MODEL_NAME constant and replaced it with the list below
AVAILABLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash", 
    "gemini-2.5-pro"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# --- Watchlists ---
CORE_INTERMARKET_TICKERS = [
    "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
    "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "NDAQ", "^VIX"
]

# --- GLOBAL INITIALIZATION (SECRETS & KEY MANAGER) ---
KEY_MANAGER_INSTANCE = None
TURSO_DB_URL_HTTPS = None
TURSO_AUTH_TOKEN = None

try:
    # 1. Load Turso Secrets
    turso_secrets = st.secrets.get("turso", {})
    raw_db_url = turso_secrets.get("db_url")
    TURSO_AUTH_TOKEN = turso_secrets.get("auth_token")

    if raw_db_url:
        TURSO_DB_URL_HTTPS = raw_db_url.replace("libsql://", "https://")
    
    # 2. Initialize the Key Manager (The Brain)
    if TURSO_DB_URL_HTTPS and TURSO_AUTH_TOKEN:
        KEY_MANAGER_INSTANCE = KeyManager(
            db_url=TURSO_DB_URL_HTTPS, 
            auth_token=TURSO_AUTH_TOKEN
        )
    else:
        st.error("❌ Turso Database credentials missing in .streamlit/secrets.toml")
        st.stop()

except Exception as e:
    st.error(f"❌ Critical Initialization Error: {e}")
    st.stop()

# ==============================================================================
# 2. UI COMPONENTS & LOGGER
# ==============================================================================

class AppLogger:
    """A robust logger that writes to a Streamlit container."""
    def __init__(self, container):
        self.container = container
        self.log_messages = []

    def log(self, message: str):
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        new_msg = f"**{timestamp}Z:** {message}"
        self.log_messages.append(new_msg)
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

    def log_code(self, data, language='json'):
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        new_msg = f"**{timestamp}Z:** (See code block below)"
        self.log_messages.append(new_msg)
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)
            if language == 'json' and isinstance(data, dict):
                self.container.json(data)
            else:
                self.container.code(str(data), language=language)

    def flush(self):
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

# ==============================================================================
# 3. DATABASE UTILITIES (OPTIMIZED & TIME-TRAVEL READY)
# ==============================================================================

@st.cache_resource(show_spinner="Connecting to Headquarters...")
def get_db_connection():
    """
    Establishes a cached connection to Turso.
    This prevents reconnecting on every script rerun (Performance Fix).
    """
    if not TURSO_DB_URL_HTTPS or not TURSO_AUTH_TOKEN:
        return None
    try:
        # Using sync client as requested in original code structure
        return create_client_sync(url=TURSO_DB_URL_HTTPS, auth_token=TURSO_AUTH_TOKEN)
    except Exception as e:
        st.error(f"Failed to connect to DB: {e}")
        return None

def init_db_schema(client, logger: AppLogger):
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS premarket_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                input_news_snapshot TEXT,
                economy_card_snapshot TEXT,
                live_stats_snapshot TEXT,
                final_briefing TEXT
            );
        """)
        logger.log("DB: Schema verified.")
    except Exception as e:
        logger.log(f"DB Error: {e}")

def get_latest_economy_card_date(client, cutoff_str: str, logger: AppLogger) -> str | None:
    """
    Fetches the latest economy card date ON OR BEFORE the cutoff timestamp.
    """
    try:
        # We assume the 'date' column in economy_cards is YYYY-MM-DD.
        # We strictly want a card that existed before our simulation moment.
        cutoff_date_part = cutoff_str.split(" ")[0] # Extract YYYY-MM-DD from 'YYYY-MM-DD HH:MM:SS'
        
        rs = client.execute(
            "SELECT MAX(date) FROM economy_cards WHERE date <= ?", 
            [cutoff_date_part]
        )
        return rs.rows[0][0] if rs.rows and rs.rows[0][0] else None
    except Exception:
        return None

def get_eod_economy_card(client, benchmark_date: str, logger: AppLogger) -> dict | None:
    try:
        rs = client.execute("SELECT economy_card_json FROM economy_cards WHERE date = ?", (benchmark_date,))
        return json.loads(rs.rows[0][0]) if rs.rows and rs.rows[0][0] else None
    except Exception as e:
        logger.log(f"DB Error (EOD Card): {e}")
        return None

def _parse_levels_from_json_blob(card_json_blob: str, logger: AppLogger) -> tuple[list[float], list[float]]:
    s_levels, r_levels = [], []
    try:
        card_data = json.loads(card_json_blob)
        briefing_data = card_data.get('screener_briefing')
        if isinstance(briefing_data, str):
            try:
                briefing_obj = json.loads(briefing_data)
            except json.JSONDecodeError:
                s_match = re.search(r"S_Levels: \[(.*?)\]", briefing_data)
                r_match = re.search(r"R_Levels: \[(.*?)\]", briefing_data)
                s_str = s_match.group(1) if s_match else ""
                r_str = r_match.group(1) if r_match else ""
                s_levels = [float(x) for x in re.findall(r"[\d\.]+", s_str)]
                r_levels = [float(x) for x in re.findall(r"[\d\.]+", r_str)]
                return s_levels, r_levels
        elif isinstance(briefing_data, dict):
            briefing_obj = briefing_data
        else:
            return [], []

        s_levels = [
            float(str(l).replace('$', ''))
            for l in briefing_obj.get('S_Levels', [])
            if str(l).replace('$', '').replace('.', '', 1).isdigit()
        ]
        r_levels = [
            float(str(l).replace('$', ''))
            for l in briefing_obj.get('R_Levels', [])
            if str(l).replace('$', '').replace('.', '', 1).isdigit()
        ]
    except Exception:
        pass
    return s_levels, r_levels

def get_eod_card_data_for_screener(client, ticker_list: list, benchmark_date: str, logger: AppLogger) -> dict:
    db_data = {}
    if not ticker_list or not client:
        return db_data

    # This query fetches the latest card ON or BEFORE the benchmark_date (Time Travel Safe)
    query = f"""
        WITH RankedCards AS (
            SELECT ticker, company_card_json, date,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
            FROM company_cards WHERE date <= ?
        )
        SELECT ticker, company_card_json FROM RankedCards
        WHERE rn = 1 AND ticker IN ({','.join(['?'] * len(ticker_list))})
    """
    try:
        args = [benchmark_date] + ticker_list
        rs = client.execute(query, args)
        for row in rs.rows:
            ticker, card_json_blob = row[0], row[1]
            if not card_json_blob:
                continue
            s_levels, r_levels = _parse_levels_from_json_blob(card_json_blob, logger)
            try:
                briefing_data = json.loads(card_json_blob).get('screener_briefing')
                briefing_text = (
                    json.dumps(briefing_data, indent=2)
                    if isinstance(briefing_data, dict)
                    else str(briefing_data)
                )
            except Exception:
                briefing_text = "Error parsing."
            db_data[ticker] = {
                "screener_briefing_text": briefing_text,
                "s_levels": s_levels,
                "r_levels": r_levels,
            }
        return db_data
    except Exception as e:
        logger.log(f"DB Error (EOD Data): {e}")
        return {}

def get_all_tickers_from_db(client, logger: AppLogger) -> list[str]:
    try:
        rs = client.execute("SELECT user_ticker FROM symbol_map")
        return [row[0] for row in rs.rows]
    except Exception as e:
        logger.log(f"DB Error (Get Tickers): {e}")
        return []

def save_snapshot(client, news_input: str, eco_card: dict, live_stats: str, briefing: str, logger: AppLogger) -> bool:
    if not client:
        return False
    try:
        ts = datetime.now().isoformat()
        eco_json = json.dumps(eco_card)
        client.execute(
            """
            INSERT INTO premarket_snapshots
            (run_timestamp, input_news_snapshot, economy_card_snapshot, live_stats_snapshot, final_briefing)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, news_input, eco_json, live_stats, briefing),
        )
        logger.log("DB: Snapshot saved.")
        return True
    except Exception as e:
        logger.log(f"DB Error (Save Snapshot): {e}")
        return False

# ==============================================================================
# 4. DATA PROCESSING (TIME TRAVEL ENABLED)
# ==============================================================================

def get_latest_price_details(client, ticker: str, cutoff_str: str, logger: AppLogger) -> tuple[float | None, str | None]:
    """
    Fetches price AND timestamp respecting the simulation cutoff.
    Uses String comparison on 'YYYY-MM-DD HH:MM:SS' format for reliability.
    """
    # We filter by timestamp <= cutoff_str
    query = "SELECT close, timestamp FROM market_data WHERE symbol = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
    try:
        rs = client.execute(query, [ticker, cutoff_str])
        if rs.rows:
            return rs.rows[0][0], rs.rows[0][1]
        return None, None
    except Exception as e:
        logger.log(f"DB Read Error {ticker}: {e}")
        return None, None

def get_session_bars_from_db(client, epic: str, benchmark_date: str, cutoff_str: str, logger: AppLogger) -> pd.DataFrame | None:
    """
    Fetches bars for the specific date, capped at cutoff.
    FIXED: Automatically determines 'PM' vs 'RTH' session based on timestamp,
    ignoring unreliable DB labels to prevent NaN VWAP.
    """
    try:
        query = """
            SELECT timestamp, open, high, low, close, volume, session
            FROM market_data
            WHERE symbol = ? AND date(timestamp) = ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """
        rs = client.execute(query, [epic, benchmark_date, cutoff_str])
        if not rs.rows:
            return None
        df = pd.DataFrame(
            rs.rows,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'session_db'],
        )

        # 1. Convert timestamp to Datetime (Handling space or T separator)
        # We strip 'Z' if present and coerce to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(str).str.replace('Z', '').str.replace(' ', 'T'))

        # 2. Localize to UTC (if naive) then Convert to US/Eastern
        # If timestamps are naive, assume they are UTC (standard for crypto/market data)
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        
        # Convert to Eastern for Session Logic
        df['dt_eastern'] = df['timestamp'].dt.tz_convert(US_EASTERN)

        # 3. Auto-Calculate Session (Robustness Fix)
        # PM = Time < 09:30
        # RTH = Time >= 09:30
        # We create a boolean mask
        time_eastern = df['dt_eastern'].dt.time
        df['session'] = np.where(time_eastern < MARKET_OPEN_TIME, 'PM', 'RTH')

        df.rename(
            columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
            },
            inplace=True,
        )
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
        df.dropna(subset=['Close', 'Volume'], inplace=True)
        return df.reset_index(drop=True)
    except Exception as e:
        logger.log(f"Data Error ({epic}): {e}")
        return None

def calculate_vwap(df: pd.DataFrame) -> float:
    if df.empty or 'Volume' not in df.columns or df['Volume'].sum() == 0:
        return np.nan
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).sum() / df['Volume'].sum()

def calculate_volume_profile(df: pd.DataFrame) -> float:
    if df.empty or 'Volume' not in df.columns:
        return np.nan
    price_mid = (df['High'] + df['Low']) / 2
    try:
        bins = pd.cut(price_mid, bins=min(20, len(df) - 1) if len(df) > 1 else 1)
        grouped = df.groupby(bins, observed=True)['Volume'].sum()
        return grouped.idxmax().mid
    except Exception:
        return np.nan

def process_session_data_to_summary(
    ticker: str,
    df: pd.DataFrame,
    live_price: float,
    logger: AppLogger,
) -> dict:
    """
    Pre-market only: uses PM session data to generate summary text and basic bias.
    """
    result = {
        "ticker": ticker,
        "price": live_price,
        "mode": "PRE-MARKET",
        "pm_vwap": np.nan,
        "rth_vwap": np.nan,
        "divergence": "None",
        "summary_text": "",
    }

    if df is None or df.empty:
        result["summary_text"] = (
            f"Data Summary: {ticker} (No Session Bars. Price: ${live_price:.2f})"
        )
        return result

    # Uses the robust 'session' column calculated in get_session_bars_from_db
    df_pm = df[df['session'] == 'PM']

    pm_high = df_pm['High'].max() if not df_pm.empty else np.nan
    pm_low = df_pm['Low'].min() if not df_pm.empty else np.nan
    pm_vwap = calculate_vwap(df_pm)
    pm_poc = calculate_volume_profile(df_pm)

    result["pm_vwap"] = pm_vwap
    pm_summary = f"PM Range: ${pm_low:.2f}-${pm_high:.2f} | PM VWAP: ${pm_vwap:.2f}"

    vwap_rel = "Above" if live_price > pm_vwap else "Below"
    trend_msg = "Consolidating"

    if not pd.isna(pm_high) and not pd.isna(pm_low):
        rng = pm_high - pm_low
        pos = (live_price - pm_low) / rng if rng > 0 else 0.5
        if pos > 0.75:
            trend_msg = "Trending High"
        elif pos < 0.25:
            trend_msg = "Trending Low"
        else:
            trend_msg = "Neutral"

    result["summary_text"] = (
        f"TICKER: {ticker} | PRICE: ${live_price:.2f}\n"
        "[SESSION: PRE-MARKET]\n"
        f"{pm_summary}\n"
        f"PM POC: ${pm_poc:.2f}\n"
        f"Bias: {trend_msg}. Trading {vwap_rel} PM VWAP."
    )

    return result

# ==============================================================================
# 5. AI SERVICES (UPDATED WITH ROTATION & KEY MANAGER)
# ==============================================================================

def call_gemini_with_rotation(
    prompt: str, 
    system_prompt: str, 
    logger: AppLogger, 
    model_name: str, 
    max_retries=5
) -> tuple[str | None, str | None]:
    """
    Calls the Gemini API using the KeyManager's Acquire-Use-Report loop.
    Replaces the old 'call_gemini_api' function.
    """
    if not KEY_MANAGER_INSTANCE:
        logger.log("❌ ERROR: KeyManager not initialized. Check database credentials.")
        return None, "System Configuration Error"
    
    for i in range(max_retries):
        current_api_key = None
        key_name = "Unknown"

        try:
            # 1. ACQUIRE: Get Key from Manager (Checking specific model bucket)
            key_name, current_api_key, wait_time = KEY_MANAGER_INSTANCE.get_key(target_model=model_name)
            
            # Handle global cooldown (all keys exhausted)
            if not current_api_key:
                logger.log(f"⏳ All keys exhausted for {model_name}. Waiting {wait_time:.0f}s... (Attempt {i+1})")
                if wait_time > 0 and i < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    return None, f"Global Rate Limit for {model_name}"
            
            # Log the Key Name (Glass Box)
            logger.log(f"🔑 Acquired '{key_name}' | Model: {model_name} (Attempt {i+1})")
            
            # 2. EXECUTE: Make the Request
            # Construct URL dynamically based on selected model
            gemini_url = f"{API_BASE_URL}/{model_name}:generateContent?key={current_api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}], 
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
            }
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            
            # 3. REPORT: Feedback Loop
            if response.status_code == 200:
                # Report Success to specific model bucket
                KEY_MANAGER_INSTANCE.report_success(current_api_key, model_id=model_name)
                
                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    return text, None
                except (KeyError, IndexError):
                    logger.log(f"⚠️ Invalid JSON response from Google.")
                    # Malformed JSON is technically a server/protocol error, don't penalize key heavily
                    KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)
                    continue 

            elif response.status_code == 429:
                logger.log(f"⛔ 429 Rate Limit on '{key_name}'. Adding Strike.")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=False)
            
            elif response.status_code >= 500:
                logger.log(f"☁️ {response.status_code} Server Error on '{key_name}'. No Penalty.")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)
            
            else:
                logger.log(f"⚠️ API Error {response.status_code}: {response.text}")
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)

        except Exception as e:
            logger.log(f"💥 Exception using '{key_name}': {str(e)}")
            if current_api_key:
                KEY_MANAGER_INSTANCE.report_failure(current_api_key, is_server_error=True)
        
        if i < max_retries - 1:
            time.sleep(2 ** i)

    return None, "Max Retries Exhausted"

# ==============================================================================
# 6. MAIN APPLICATION LOGIC
# ==============================================================================

def main():
    st.title("Pre-Market Analyst Workbench (Glass Box)")

    # --- Session State Init ---
    if 'premarket_economy_card' not in st.session_state:
        st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state:
        st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state:
        st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state:
        st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state:
        st.session_state.final_briefing = None
    if 'xray_snapshot' not in st.session_state:
        st.session_state.xray_snapshot = None
    if 'app_logger' not in st.session_state or not hasattr(st.session_state.app_logger, 'flush'):
        st.session_state.app_logger = AppLogger(None)

    # --- Glass Box State ---
    if 'glassbox_eod_card' not in st.session_state:
        st.session_state.glassbox_eod_card = None
    if 'glassbox_etf_data' not in st.session_state:
        st.session_state.glassbox_etf_data = []
    if 'glassbox_prompt' not in st.session_state:
        st.session_state.glassbox_prompt = None
    if 'audit_logs' not in st.session_state:
        st.session_state.audit_logs = []

    # --- Startup ---
    startup_logger = st.session_state.app_logger
    turso = get_db_connection() # Uses Cached Connection
    
    if turso:
        init_db_schema(turso, startup_logger)
    else:
        st.error("DB Connection Failed.")
        st.stop()

    # --- Sidebar Configuration (Live vs Simulation) ---
    with st.sidebar:
        st.header("⚙️ Mission Config")
        
        # --- KEY MANAGER STATUS ---
        if KEY_MANAGER_INSTANCE:
            st.success("✅ Key Manager: Active")
        else:
            st.error("❌ Key Manager: Failed")

        # --- MODEL SELECTION (NEW) ---
        selected_model = st.selectbox(
            "AI Model", 
            AVAILABLE_MODELS, 
            index=0,
            help="Select the specific model to use for generation. This determines which Key Quota bucket is checked."
        )
        
        mode = st.radio("Operation Mode", ["Live", "Simulation"], index=0)
        
        if mode == "Live":
            # In Live mode, the cutoff is essentially "Now"
            simulation_cutoff_dt = datetime.now(timezone.utc)
            st.success(f"🟢 Live Mode Active")
            
        else:
            st.warning(f"🟠 Simulation Mode")
            sim_date = st.date_input("Simulation Date")
            # CHANGED: Time input label now explicitly says UTC
            sim_time = st.time_input("Simulation Time (UTC)", value=datetime.strptime("13:00", "%H:%M").time())
            
            # Construct the cutoff timestamp - PURE UTC
            # 1. Combine date and time
            # 2. Replace tzinfo with UTC directly
            simulation_cutoff_dt = datetime.combine(sim_date, sim_time).replace(tzinfo=timezone.utc)
            
            st.info(f"Time Travel To: {simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        # --- DATE FORMAT FIX FOR SQLITE COMPARISON ---
        simulation_cutoff_str = simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Determine Analysis Date (for fetching bars)
        # Since we are in UTC mode, the market date IS the selected date
        analysis_date = sim_date if mode == "Simulation" else simulation_cutoff_dt.date()
        
        st.write(f"Analysis Market Date: {analysis_date}")
        st.session_state.analysis_date = analysis_date

    tab1, tab2 = st.tabs(["Step 1: Live Market Monitor", "Step 2: Battle Commander"])
    logger = st.session_state.app_logger

    # === TAB 1: Pre-Flight / Monitor ===
    with tab1:
        st.header("A. Macro Context (Step 0)")
        pm_news = st.text_area("News Input", height=100, key="pm_news_input")

        # --- GLASS BOX MONITOR ---
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
                    key="glassbox_prompt_view"  # Added Unique Key
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
                        format=" ",  # Hides the text overlay
                        min_value=0,
                        max_value=1,
                        width="small",  # Compact width
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
            
            # Clear previous run data
            st.session_state.glassbox_etf_data = []
            st.session_state.audit_logs = []
            etf_placeholder.empty()

            with st.status(f"Running Macro Scan ({mode})...", expanded=True) as status:
                status.write("Fetching EOD Card...")
                
                # --- SIMULATION EOD LOGIC ---
                if mode == "Simulation":
                    # Shift back 1 day to ensure we don't read "future" EOD cards
                    eod_search_date = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    eod_search_date = simulation_cutoff_dt.strftime('%Y-%m-%d')
                    
                latest_date = get_latest_economy_card_date(turso, simulation_cutoff_str, logger)
                eod_card = get_eod_economy_card(turso, latest_date, logger) if latest_date else {}
                
                st.session_state.glassbox_eod_card = eod_card
                eod_placeholder.json(eod_card, expanded=False)

                status.write("Scanning Intermarket Tickers...")
                etf_summaries = []
                benchmark_date_str = st.session_state.analysis_date.isoformat()

                for epic in CORE_INTERMARKET_TICKERS:
                    # TRACEABLE DATA FETCHING (X-RAY LOGIC)
                    # NOW USING CUTOFF_STR (Fixed Format)
                    latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)

                    if latest_price:
                        # FETCH BARS CAPPED AT CUTOFF
                        df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                        bar_count = len(df) if df is not None else 0

                        # --- FRESHNESS LOGIC (Relativity Check) ---
                        # PRESERVED EXACTLY AS REQUESTED
                        freshness_score = 0.0
                        try:
                            if price_ts:
                                # Ensure DB timestamp is parsed correctly even if space separated
                                ts_clean = price_ts.replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None:
                                    ts_obj = ts_obj.replace(tzinfo=timezone.utc)

                                # Compare data timestamp vs SIMULATION timestamp
                                lag_minutes = (simulation_cutoff_dt - ts_obj).total_seconds() / 60.0
                                # 100% at 0 lag, 0% at 60m lag
                                freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                        except Exception:
                            freshness_score = 0.0
                        # ----------------------------------

                        if df is not None:
                            processed_data = process_session_data_to_summary(
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

                            # Render updated DataFrame
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
                            # Tiny sleep for visual effect of "scanning"
                            time.sleep(0.02)

                # --- GUARDRAIL: STOP IF NO DATA ---
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
                # Added Unique Key to resolve duplicate ID error
                prompt_placeholder.text_area("Prompt Preview", prompt, height=150, key="glassbox_prompt_preview")

                status.write(f"Calling Gemini ({selected_model})...")
                system_prompt = (
                    "You are an expert Macro Strategist. Output valid JSON only with "
                    "keys: marketNarrative, marketBias, sectorRotation."
                )
                
                # --- UPDATED: Use the new Rotation Function ---
                resp, error_msg = call_gemini_with_rotation(
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
                        # Tag the card with the analysis date
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
            logger = st.session_state.app_logger
            # Use the date from the generated card
            benchmark_date_for_scan = st.session_state.latest_macro_date
            
            with st.status(f"Scanning Market ({mode})...", expanded=True) as status:
                tickers = get_all_tickers_from_db(turso, logger)
                
                # Fetch EOD cards respecting simulation logic (already handled by getting latest_macro_date)
                # But for LEVELS, we need to check the date relative to cutoff
                eod_data = get_eod_card_data_for_screener(
                    turso,
                    tickers,
                    benchmark_date_for_scan, # This is the date of the macro card we just made/found
                    logger,
                )
                results = []
                for tkr, data in eod_data.items():
                    # Fetch Price Capped at Cutoff
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    
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

        st.markdown("---")
        st.subheader("Live Logs")
        log_container = st.container(height=200)
        st.session_state.app_logger.container = log_container
        st.session_state.app_logger.flush()

    # === TAB 2: Head Trader ===
    with tab2:
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
                eod_map = get_eod_card_data_for_screener(
                    turso,
                    st.session_state.curated_tickers,
                    benchmark_date_str,
                    logger,
                )

                for tkr in st.session_state.curated_tickers:
                    if tkr not in eod_map:
                        continue

                    strat = eod_map.get(tkr, {}).get("screener_briefing_text", "N/A")
                    
                    # Fetch Price Capped at Cutoff
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    
                    if price:
                        # Fetch Bars Capped at Cutoff
                        df = get_session_bars_from_db(
                            turso,
                            tkr,
                            benchmark_date_str,
                            simulation_cutoff_str,
                            logger,
                        )
                        if df is not None:
                            processed_data = process_session_data_to_summary(
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

                # --- UPDATED: Use the new Rotation Function ---
                briefing, error_msg = call_gemini_with_rotation(
                    prompt,
                    "You are an elite Head Trader.",
                    logger,
                    selected_model
                )

                if briefing:
                    st.session_state.final_briefing = briefing

                    save_snapshot(
                        turso,
                        str(pm_news),
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


if __name__ == "__main__":
    main()