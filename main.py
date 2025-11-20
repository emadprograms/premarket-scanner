import streamlit as st
import pandas as pd
import requests
import json
import re
import time
import random
from datetime import datetime, timezone, timedelta
import libsql_client
from libsql_client import create_client_sync, LibsqlError
from pytz import timezone as pytz_timezone
import numpy as np

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================

# --- Page Config ---
st.set_page_config(page_title="Pre-Market Analyst (Glass Box)", layout="wide")

# --- Timezone & Market Hours ---
US_EASTERN = pytz_timezone('US/Eastern')
PREMARKET_START_HOUR = 4  # 4:00 AM ET
MARKET_OPEN_HOUR = 9      # 9:00 AM (Hour component)
MARKET_OPEN_MINUTE = 30   # 30 Minutes

# --- API Config ---
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"

# --- Watchlists ---
CORE_INTERMARKET_EPICS = [
    "SPY_SPX", "QQQ_NDX", "IWM_RUT", "DIA_DJI", # Indices
    "XLF", "XLE", "XLK", "XLI", "XLP", "XLU", "XLV", # Sectors
    "TLT_US_20Y", "UUP_DXY", "Gold_GLD", "USO_WTI" # Inter-market
]

# --- Load Secrets (Fail Fast if Missing) ---
try:
    gemini_secrets = st.secrets.get("gemini", {})
    API_KEYS = gemini_secrets.get("api_keys", [])
    
    turso_secrets = st.secrets.get("turso", {})
    TURSO_DB_URL = turso_secrets.get("db_url")
    TURSO_AUTH_TOKEN = turso_secrets.get("auth_token")
    
    capital_secrets = st.secrets.get("capital_com", {})
    CAP_API_KEY = capital_secrets.get("X_CAP_API_KEY")
    CAP_IDENTIFIER = capital_secrets.get("identifier")
    CAP_PASSWORD = capital_secrets.get("password")

    # Force HTTPS for Turso
    if TURSO_DB_URL:
        TURSO_DB_URL_HTTPS = TURSO_DB_URL.replace("libsql://", "https://")
    else:
        TURSO_DB_URL_HTTPS = None

except Exception as e:
    st.error(f"Critical Error loading secrets: {e}")
    st.stop()

# ==============================================================================
# 2. UI COMPONENTS & LOGGER
# ==============================================================================

class AppLogger:
    """A robust logger that writes to a Streamlit container and supports flushing."""
    def __init__(self, container):
        self.container = container
        self.log_messages = []

    def log(self, message: str):
        """Appends a new message to the log."""
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        new_msg = f"**{timestamp}Z:** {message}"
        self.log_messages.append(new_msg)
        
        if self.container:
            # Display logs in reverse chronological order (newest top)
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

    def log_code(self, data, language='json'):
        """Appends structured data/code to the log."""
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
        """Forces a refresh of the container content. Essential for startup logs."""
        if self.container:
            self.container.markdown("\n\n".join(self.log_messages[::-1]), unsafe_allow_html=True)

def create_capital_session(logger: AppLogger) -> tuple[str | None, str | None]:
    """Creates a Capital.com session with explicit error logging."""
    # We use st.toast for less intrusive notifications during auth
    
    if not all([CAP_API_KEY, CAP_IDENTIFIER, CAP_PASSWORD]):
        logger.log("Error: Capital.com secrets missing.")
        st.error("Missing Capital.com secrets: API Key, Identifier, or Password.")
        return None, None
    
    session_url = f"{CAPITAL_API_URL_BASE}/session"
    headers = {'X-CAP-API-KEY': CAP_API_KEY, 'Content-Type': 'application/json'}
    payload = {"identifier": CAP_IDENTIFIER, "password": CAP_PASSWORD}
    
    try:
        response = requests.post(session_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        cst = response.headers.get('CST')
        xst = response.headers.get('X-SECURITY-TOKEN')
        
        if cst and xst:
            logger.log("Capital.com session created successfully.")
            return cst, xst
        else:
            logger.log("Error: Session created but CST/XST tokens missing.")
            return None, None
    except Exception as e:
        logger.log(f"Session creation failed: {e}")
        return None, None

# ==============================================================================
# 3. DATABASE UTILITIES (Turso / LibSQL)
# ==============================================================================

def create_turso_client(logger: AppLogger) -> libsql_client.Client | None:
    """
    Creates a Turso DB client using the PROVEN synchronous method (create_client_sync).
    """
    if not TURSO_DB_URL_HTTPS or not TURSO_AUTH_TOKEN:
        logger.log("DB Error: Turso URL or Auth Token missing from config.")
        return None
        
    try:
        client = create_client_sync(
            url=TURSO_DB_URL_HTTPS,
            auth_token=TURSO_AUTH_TOKEN
        )
        return client
    except Exception as e:
        logger.log(f"DB Error (Connection): {e}")
        return None

def init_db_schema(client, logger: AppLogger):
    """
    Initializes the database schema on app startup.
    Creates the 'premarket_snapshots' table if it doesn't exist.
    """
    try:
        # Create Table (Flight Recorder)
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
        logger.log("DB: Schema check complete. Table 'premarket_snapshots' verified.")
    except Exception as e:
        logger.log(f"DB Critical Error (Schema Init): {e}")

def get_latest_economy_card_date(client, logger: AppLogger) -> str | None:
    """Fetches the latest date from economy_cards."""
    try:
        rs = client.execute("SELECT MAX(date) FROM economy_cards")
        if rs.rows and rs.rows[0][0]:
            return rs.rows[0][0]
        return None
    except Exception as e:
        logger.log(f"DB Error (Latest Date): {e}")
        return None

def get_eod_economy_card(client, benchmark_date: str, logger: AppLogger) -> dict | None:
    """Fetches the EOD Economy Card for a specific date."""
    try:
        rs = client.execute("SELECT economy_card_json FROM economy_cards WHERE date = ?", (benchmark_date,))
        if rs.rows and rs.rows[0][0]:
            return json.loads(rs.rows[0][0])
        return None
    except Exception as e:
        logger.log(f"DB Error (Get Eco Card): {e}")
        return None

def get_all_tickers_from_db(client, logger: AppLogger) -> list[str]:
    """Fetches all tickers from the 'stocks' table."""
    try:
        rs = client.execute("SELECT ticker FROM stocks")
        tickers = [row[0] for row in rs.rows]
        logger.log(f"DB: Watchlist loaded. Found {len(tickers)} tickers in 'stocks'.")
        return tickers
    except Exception as e:
        logger.log(f"DB Error (Get Tickers): {e}")
        return []

def _parse_levels_from_json_blob(card_json_blob: str, logger: AppLogger) -> tuple[list[float], list[float]]:
    """Helper to parse S/R levels from the JSON blob, handling text or dict formats."""
    s_levels, r_levels = [], []
    try:
        card_data = json.loads(card_json_blob)
        briefing_data = card_data.get('screener_briefing')

        if isinstance(briefing_data, str):
            try:
                briefing_obj = json.loads(briefing_data)
            except json.JSONDecodeError:
                # Regex fallback for stringified JSON or markdown
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

        s_levels = [float(str(l).replace('$','')) for l in briefing_obj.get('S_Levels', []) if str(l).replace('$','').replace('.', '', 1).isdigit()]
        r_levels = [float(str(l).replace('$','')) for l in briefing_obj.get('R_Levels', []) if str(l).replace('$','').replace('.', '', 1).isdigit()]
    except Exception as e:
        logger.log(f"DB Warn (Level Parse): {e}")
        pass
    return s_levels, r_levels

def get_eod_card_data_for_screener(client, ticker_list: list, benchmark_date: str, logger: AppLogger) -> dict:
    """
    Fetches the LATEST company card data for each ticker that is 
    LESS THAN OR EQUAL TO the benchmark_date. This handles date misalignment.
    """
    logger.log(f"DB: Checking {len(ticker_list)} tickers for EOD data <= {benchmark_date}...")
    db_data = {}
    if not ticker_list or not client: return db_data

    # Use a Window Function to find the single latest card for each ticker
    query = f"""
        WITH RankedCards AS (
            SELECT 
                ticker, 
                company_card_json, 
                date,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
            FROM company_cards
            WHERE date <= ?
        )
        SELECT 
            ticker, 
            company_card_json 
        FROM RankedCards
        WHERE rn = 1
        AND ticker IN ({','.join(['?'] * len(ticker_list))})
    """
    
    try:
        args = [benchmark_date] + ticker_list
        rs = client.execute(query, args)
        
        for row in rs.rows:
            ticker = row[0]
            card_json_blob = row[1]
            if not card_json_blob: continue

            s_levels, r_levels = _parse_levels_from_json_blob(card_json_blob, logger)
            
            try:
                briefing_data = json.loads(card_json_blob).get('screener_briefing')
                briefing_text = json.dumps(briefing_data, indent=2) if isinstance(briefing_data, dict) else str(briefing_data)
            except:
                briefing_text = "Error parsing briefing."

            db_data[ticker] = {
                "screener_briefing_text": briefing_text,
                "s_levels": s_levels,
                "r_levels": r_levels
            }
        
        if not db_data:
            logger.log(f"DB: WARN: No historical EOD data found for any of the tickers <= {benchmark_date}.")
        else:
            logger.log(f"DB: Found {len(db_data)} tickers with aligned EOD data.")

        return db_data
    except Exception as e:
        logger.log(f"DB Error (Get EOD Data): {e}")
        return {}

def save_snapshot(client, news_input: str, eco_card: dict, live_stats: str, briefing: str, logger: AppLogger) -> bool:
    """
    Saves the 'Black Box' snapshot of the run.
    Uses the 'premarket_snapshots' table initialized at startup.
    """
    if not client: return False
    
    try:
        ts = datetime.now().isoformat()
        eco_json = json.dumps(eco_card)
        
        client.execute(
            """
            INSERT INTO premarket_snapshots 
            (run_timestamp, input_news_snapshot, economy_card_snapshot, live_stats_snapshot, final_briefing)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, news_input, eco_json, live_stats, briefing)
        )
        logger.log("DB: Snapshot saved successfully.")
        return True
    except Exception as e:
        logger.log(f"DB Error (Save Snapshot): {e}")
        return False

# ==============================================================================
# 4. DATA PROCESSING (DUAL SESSION LOGIC)
# ==============================================================================

def get_capital_current_price(epic: str, cst: str, xst: str, logger: AppLogger) -> tuple[float | None, float | None]:
    """Fetches live price snapshot. Logs 404s explicitly."""
    url = f"{CAPITAL_API_URL_BASE}/markets/{epic}"
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            snapshot = data.get('snapshot')
            if snapshot and 'bid' in snapshot:
                return snapshot['bid'], snapshot['offer']
        elif response.status_code == 404:
            logger.log(f"WARN: Market {epic} not found (404). Check EPIC name.")
        return None, None
    except Exception as e:
        logger.log(f"WARN: Error fetching price for {epic}: {e}")
        return None, None

def get_capital_price_bars(epic: str, cst: str, xst: str, resolution: str, logger: AppLogger) -> pd.DataFrame | None:
    """
    Fetches bars from 04:00 AM today until NOW.
    Supports 'Live Battle Mode' by NOT cutting off data at 9:30 AM.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=16) # Fetch enough history to definitely capture 4AM ET
    
    url = f"{CAPITAL_API_URL_BASE}/prices/{epic}"
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    params = {
        "resolution": resolution, 'max': 1000, 
        'from': start_date.strftime('%Y-%m-%dT%H:%M:%S'), 
        'to': end_date.strftime('%Y-%m-%dT%H:%M:%S')
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200: 
            logger.log(f"WARN: Bars fetch failed for {epic} (Status {response.status_code})")
            return pd.DataFrame()
        
        prices = response.json().get('prices', [])
        if not prices: return pd.DataFrame()

        data = {
            'SnapshotTime': [p.get('snapshotTime') for p in prices],
            'Open': [p.get('openPrice', {}).get('bid') for p in prices],
            'High': [p.get('highPrice', {}).get('bid') for p in prices],
            'Low': [p.get('lowPrice', {}).get('bid') for p in prices],
            'Close': [p.get('closePrice', {}).get('bid') for p in prices],
            'Volume': [p.get('lastTradedVolume') for p in prices]
        }
        df = pd.DataFrame(data)
        df['SnapshotTime'] = pd.to_datetime(df['SnapshotTime'], errors='coerce', utc=True)
        df.dropna(inplace=True)
        
        # Localize to ET
        df['ET_Time'] = df['SnapshotTime'].dt.tz_convert(US_EASTERN)
        today_et = datetime.now(US_EASTERN).date()
        
        # Filter: Anything after 04:00 AM Today
        day_start = US_EASTERN.localize(datetime.combine(today_et, datetime.min.time())) + timedelta(hours=PREMARKET_START_HOUR)
        
        df_session = df[df['ET_Time'] >= day_start].copy()
        
        if df_session.empty:
            logger.log(f"WARN: No session bars found for {epic} (since 4 AM today).")
            return pd.DataFrame()
            
        return df_session.reset_index(drop=True)

    except Exception as e:
        logger.log(f"Data Error ({epic}): {e}")
        return None

def calculate_vwap(df: pd.DataFrame) -> float:
    if df.empty or 'Volume' not in df.columns or df['Volume'].sum() == 0: return np.nan
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).sum() / df['Volume'].sum()

def calculate_volume_profile(df: pd.DataFrame) -> float:
    if df.empty or 'Volume' not in df.columns: return np.nan
    price_mid = (df['High'] + df['Low']) / 2
    try:
        # Dynamic binning based on data size
        bins = pd.cut(price_mid, bins=min(20, len(df)-1) if len(df) > 1 else 1)
        grouped = df.groupby(bins, observed=True)['Volume'].sum()
        return grouped.idxmax().mid
    except: return np.nan

def process_session_data_to_summary(ticker: str, df: pd.DataFrame, live_price: float, is_live_mode: bool, logger: AppLogger) -> dict:
    """
    The Brain of 'Live Battle Mode'.
    Returns a DICT now, not just a string, so we can display x-ray tables in the UI.
    
    ARG: is_live_mode (bool) -> Controlled by Sidebar. 
         If False, strictly enforce Pre-Market logic (ignore RTH data).
    """
    result = {
        "ticker": ticker,
        "price": live_price,
        "mode": "N/A",
        "pm_vwap": np.nan,
        "rth_vwap": np.nan,
        "divergence": "None",
        "summary_text": ""
    }

    if df.empty: 
        result["summary_text"] = f"Data Summary: {ticker} (No Data. Price: ${live_price:.2f})"
        return result
    
    # 1. Identify Key Time Marker (09:30 ET Today)
    today_et = df['ET_Time'].iloc[0].date() # Assuming df is already filtered to today
    rth_start = US_EASTERN.localize(datetime.combine(today_et, datetime.min.time())) + timedelta(hours=MARKET_OPEN_HOUR, minutes=MARKET_OPEN_MINUTE)
    
    # 2. Split Data
    df_pm = df[df['ET_Time'] < rth_start]
    df_rth = df[df['ET_Time'] >= rth_start]
    
    # 3. Calculate Pre-Market Context (Always exists if data exists)
    pm_high = df_pm['High'].max() if not df_pm.empty else np.nan
    pm_low = df_pm['Low'].min() if not df_pm.empty else np.nan
    pm_vwap = calculate_vwap(df_pm)
    pm_poc = calculate_volume_profile(df_pm)
    
    result["pm_vwap"] = pm_vwap
    pm_summary = f"PM Range: ${pm_low:.2f}-${pm_high:.2f} | PM VWAP: ${pm_vwap:.2f}"
    
    # 4. Determine Session Mode (Controlled by User Toggle)
    # If User selects "Pre-Market", we force the logic to behave as if RTH hasn't happened.
    
    if is_live_mode and not df_rth.empty:
        # === MODE: LIVE BATTLE (RTH OPEN + USER ENABLED) ===
        result["mode"] = "LIVE BATTLE"
        # Calculate RTH Reality (Anchored to 9:30)
        rth_vwap = calculate_vwap(df_rth)
        rth_poc = calculate_volume_profile(df_rth)
        rth_high = df_rth['High'].max()
        rth_low = df_rth['Low'].min()
        
        result["rth_vwap"] = rth_vwap
        
        # Dual Comparisons
        rth_rel = "ABOVE" if live_price > rth_vwap else "BELOW"
        pm_rel = "Above" if live_price > pm_vwap else "Below"
        
        # Divergence Check (The "Trap" Logic)
        divergence_text = "Analysis: "
        simple_signal = "Neutral"
        
        if (live_price > pm_vwap and live_price < rth_vwap):
            divergence_text += "**TRAP WARNING:** Price is Above PM VWAP (Bullish Context) but REJECTED RTH VWAP (Bearish Reality). Potential Long Trap."
            simple_signal = "Bearish Trap?"
        elif (live_price < pm_vwap and live_price > rth_vwap):
            divergence_text += "**REVERSAL WARNING:** Price is Below PM VWAP (Bearish Context) but RECLAIMED RTH VWAP (Bullish Reality). Potential Short Trap."
            simple_signal = "Bullish Reversal?"
        else:
            divergence_text += f"Convergence: Price is {rth_rel} both VWAPs."
            simple_signal = f"Converged ({rth_rel})"
            
        result["divergence"] = simple_signal
        
        result["summary_text"] = f"""
        TICKER: {ticker} | PRICE: ${live_price:.2f}
        [SESSION: LIVE BATTLE]
        {pm_summary}
        PM POC: ${pm_poc:.2f}
        -----------------------
        [RTH REALITY (Since 09:30)]
        RTH Range: ${rth_low:.2f}-${rth_high:.2f}
        RTH VWAP: ${rth_vwap:.2f} (Price is {rth_rel})
        RTH POC:  ${rth_poc:.2f}
        {divergence_text}
        """
    
    else:
        # === MODE: PRE-MARKET ONLY (FORCED OR NO RTH DATA) ===
        result["mode"] = "PRE-MARKET"
        vwap_rel = "Above" if live_price > pm_vwap else "Below"
        trend_msg = "Consolidating"
        if not pd.isna(pm_high) and not pd.isna(pm_low):
             rng = pm_high - pm_low
             pos = (live_price - pm_low) / rng if rng > 0 else 0.5
             trend_msg = "Trending High" if pos > 0.75 else "Trending Low" if pos < 0.25 else "Neutral"

        result["summary_text"] = f"""
        TICKER: {ticker} | PRICE: ${live_price:.2f}
        [SESSION: PRE-MARKET]
        {pm_summary}
        PM POC: ${pm_poc:.2f}
        Bias: {trend_msg}. Trading {vwap_rel} PM VWAP.
        """
        
    return result

# ==============================================================================
# 5. AI SERVICES (Gemini)
# ==============================================================================

def call_gemini_api(prompt: str, api_keys: list, system_prompt: str, logger: AppLogger) -> tuple[str | None, str | None]:
    """
    Calls Gemini API with KEY ROTATION (Robust to 403/Suspension).
    Rotates through the provided list of API keys up to 5 times if errors occur.
    
    RETURNS: (result_text, error_message)
    - If success: (text, None)
    - If failure: (None, error_message)
    """
    
    max_retries = 5
    last_error_msg = "Unknown Error"
    
    if not api_keys:
        return None, "No API keys provided in secrets."
    
    for attempt in range(max_retries):
        # 1. Pick a random key from the pool
        current_key = random.choice(api_keys)
        
        # Mask key for logging
        key_suffix = current_key[-4:] if len(current_key) > 4 else "XXXX"
        
        url = f"{GEMINI_API_URL}?key={current_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
        }
        
        try:
            response = requests.post(url, json=payload, timeout=90)
            
            if response.status_code == 200:
                # Success!
                return response.json()['candidates'][0]['content']['parts'][0]['text'].strip(), None
            else:
                # API Returned an Error (like 403, 500, 429)
                error_json = response.json()
                try:
                    # Try to extract a clean error message from Google's JSON
                    error_details = error_json.get('error', {})
                    code = error_details.get('code')
                    message = error_details.get('message')
                    last_error_msg = f"Error {code}: {message}"
                    
                    # Special Handling for Suspended/Quota Keys
                    if code == 403 or "suspended" in str(message).lower():
                        logger.log(f"⚠️ WARN: Key ending in ...{key_suffix} is SUSPENDED or INVALID. Rotating...")
                    else:
                        logger.log(f"⚠️ WARN: API Error ({code}). Rotating key... (Attempt {attempt+1}/{max_retries})")
                        
                except:
                    last_error_msg = f"Status {response.status_code} - {response.text[:200]}"
                    logger.log(f"⚠️ WARN: API Error. Rotating key... (Attempt {attempt+1}/{max_retries})")
                
                # Exponential Backoff (longer if it's just a retry, short if it's a rotation)
                time.sleep(1 + attempt) 
                
        except Exception as e:
            last_error_msg = f"Connection Failed: {str(e)}"
            logger.log(f"⚠️ WARN: Connection Error. Rotating key... (Attempt {attempt+1}/{max_retries})")
            time.sleep(1)
            
    return None, f"Failed after {max_retries} attempts. Last error: {last_error_msg}"

# ==============================================================================
# 6. MAIN APPLICATION LOGIC
# ==============================================================================

def main():
    st.title("Pre-Market & Live Analyst Workbench")

    # --- Initialize Session State ---
    if 'capital_session' not in st.session_state: st.session_state.capital_session = {"cst": None, "xst": None}
    if 'premarket_economy_card' not in st.session_state: st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state: st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state: st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state: st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state: st.session_state.final_briefing = None
    
    # --- Persistence for X-Ray Table ---
    if 'xray_snapshot' not in st.session_state: st.session_state.xray_snapshot = None
    
    # --- FIX: Robust Logger Initialization ---
    if 'app_logger' not in st.session_state or not hasattr(st.session_state.app_logger, 'flush'):
        st.session_state.app_logger = AppLogger(None)

    # --- Startup Phase: Schema Check ---
    # We run this immediately before UI rendering to ensure DB is ready.
    if TURSO_DB_URL_HTTPS and TURSO_AUTH_TOKEN:
        startup_logger = st.session_state.app_logger
        startup_client = create_turso_client(startup_logger)
        if startup_client:
            init_db_schema(startup_client, startup_logger)

    # --- Authentication ---
    if not st.session_state.capital_session.get("cst"):
        st.warning("Please login to Capital.com to continue.")
        auth_logger_container = st.expander("Auth Logs", True)
        logger = AppLogger(auth_logger_container)
        if st.button("Login to Capital.com"):
            cst, xst = create_capital_session(logger)
            if cst and xst:
                st.session_state.capital_session = {"cst": cst, "xst": xst}
                st.rerun()
        st.stop()

    # --- SIDEBAR CONFIGURATION (MANUAL OVERRIDE) ---
    with st.sidebar:
        st.header("⚙️ Mission Config")
        session_mode = st.radio(
            "Trading Session:",
            ["Pre-Market Prep", "Live Battle Mode"],
            index=0,
            help="Switching to 'Pre-Market' forces the system to ignore RTH data (open market data), allowing you to view the clean setup."
        )
        st.info(f"Active Mode: **{session_mode}**")
    
    # Logic Flag
    is_live_mode = (session_mode == "Live Battle Mode")

    # --- Tab Structure ---
    tab1_title = "Step 1: Live Market Monitor" if is_live_mode else "Step 1: Pre-Flight & Logs"
    tab2_title = "Step 2: Battle Commander" if is_live_mode else "Step 2: Head Trader"

    tab1, tab2 = st.tabs([tab1_title, tab2_title])
    logger = st.session_state.app_logger

    # === TAB 1: Pre-Flight / Monitor ===
    with tab1:
        st.header("A. Macro Context (Step 0)")
        
        pm_news = st.text_area("News Input", height=100, key="pm_news_input")
        
        if st.button("Generate Economy Card (Step 0)", key="btn_step0", type="primary"):
            
            # --- Prerequisite Checks ---
            if not API_KEYS: st.error("Missing Gemini API Keys in secrets."); st.stop()
            if not TURSO_DB_URL_HTTPS: st.error("Missing Turso DB details."); st.stop()

            # Multirun Check
            if st.session_state.premarket_economy_card and \
               st.session_state.premarket_economy_card.get('date') == datetime.now(US_EASTERN).date().isoformat():
                st.warning("Card already generated for today.")
                st.stop()
            
            turso = create_turso_client(logger)
            cst, xst = st.session_state.capital_session['cst'], st.session_state.capital_session['xst']
            
            if not turso: st.error("Critical: Failed to connect to the Turso database."); st.stop()
            
            with st.status("Generating Macro Context...", expanded=True) as status:
                status.write("Fetching Latest Database Date...")
                latest_date = get_latest_economy_card_date(turso, logger)
                
                status.write(f"Fetching EOD Card for {latest_date}...")
                eod_card = get_eod_economy_card(turso, latest_date, logger) if latest_date else {}
                
                status.write("Fetching Live Intermarket Data (SPY, QQQ, Yields)...")
                etf_summaries = []
                for epic in CORE_INTERMARKET_EPICS:
                    bid, offer = get_capital_current_price(epic, cst, xst, logger)
                    if bid:
                        df = get_capital_price_bars(epic, cst, xst, "MINUTE_5", logger)
                        if df is not None:
                            # Pass is_live_mode to respect the toggle
                            etf_summaries.append(process_session_data_to_summary(epic, df, (bid+offer)/2, is_live_mode, logger)["summary_text"])
                
                status.write("Synthesizing with AI Strategist...")
                # --- FIDELITY PROMPT: MACRO ANALYST ---
                mode_str = "LIVE TRADING" if is_live_mode else "PRE-MARKET PREP"
                prompt = f"""
                [INPUTS]
                EOD Context: {json.dumps(eod_card)}
                Live Intermarket Data: {etf_summaries}
                News: {pm_news}
                Mode: {mode_str}

                [TASK]
                Act as a Macro-Economic Strategist. Synthesize EOD Context + Live Data + News.

                **CRITICAL ANALYSIS RULES:**
                1. **Inter-Market Confirmation:** Do NOT just look at Stocks. Check the Correlations.
                   - If Stocks are down, are Yields (TLT) or Dollar (UUP) UP? (Real Selling).
                   - If Stocks are down but Yields/Dollar are flat? (Noise/Rotation).
                2. **Participant State:** Who is driving the move?
                   - "Waiting/Hedged" (Low Vol ahead of news).
                   - "Liquidation" (Broad selling across sectors).
                   - "Rotation" (Tech buying, Energy selling).

                [OUTPUT JSON KEYS]
                - marketNarrative (string): A detailed, nuanced paragraph explaining the "Why". Explicitly mention the relationship between Indices and Inter-market assets (Yields/USD). Do NOT be brief.
                - marketBias (string): "Bullish", "Bearish", or "Neutral/Chop".
                - sectorRotation (string): Specific flow description (e.g. "Money flowing out of XLF into XLK").
                """
                
                system_prompt = "You are an expert Macro Strategist. Output valid JSON only."
                
                # === KEY ROTATION CALL ===
                resp, error_msg = call_gemini_api(prompt, API_KEYS, system_prompt, logger)
                
                if resp:
                    try:
                        json_match = re.search(r"(\{.*\})", resp, re.DOTALL)
                        json_str = json_match.group(1) if json_match else resp
                        new_card = json.loads(json_str)
                        new_card['date'] = datetime.now(US_EASTERN).date().isoformat()
                        st.session_state.premarket_economy_card = new_card
                        st.session_state.latest_macro_date = new_card['date']
                        status.update(label="Success: Macro Card Generated", state="complete", expanded=False)
                        logger.log("Success: Macro Card Generated.")
                        st.rerun()
                    except Exception as e:
                        status.update(label="Error Parsing AI", state="error")
                        st.error(f"Error parsing AI JSON response: {e}")
                        logger.log(f"Error parsing AI response: {e}")
                else:
                    status.update(label="AI Generation Failed", state="error")
                    st.error(f"AI Error: {error_msg}") # Show specific API error to user

        if st.session_state.premarket_economy_card:
            st.success(f"Macro Card Loaded for: {st.session_state.latest_macro_date}")
            with st.expander("View Economy Card"):
                st.json(st.session_state.premarket_economy_card)

        st.markdown("---")
        st.header("B. Proximity Scan (Step 1)")
        
        pct_threshold = st.slider("Proximity %", 0.1, 5.0, 2.5)
        
        if st.button("Run Proximity Scan"):
            if not st.session_state.latest_macro_date: st.error("Error: Generate Macro Card first."); st.stop()
            
            logger = st.session_state.app_logger
            turso = create_turso_client(logger)
            if not turso: st.error("Critical: Failed to connect to Turso."); st.stop()
            
            cst, xst = st.session_state.capital_session['cst'], st.session_state.capital_session['xst']
            benchmark_date = st.session_state.latest_macro_date
                
            with st.status("Scanning Market...", expanded=True) as status:
                status.write("Fetching Watchlist...")
                tickers = get_all_tickers_from_db(turso, logger)
                status.write(f"Fetching EOD Data for {len(tickers)} tickers...")
                eod_data = get_eod_card_data_for_screener(turso, tickers, benchmark_date, logger)
                
                results = []
                if not eod_data: 
                    status.update(label="Error: No EOD Data Found", state="error")
                    st.warning("No EOD data found aligned to benchmark date."); st.stop()
                    
                status.write("Checking Live Prices vs Levels...")
                for tkr, data in eod_data.items():
                    bid, offer = get_capital_current_price(tkr, cst, xst, logger)
                    if not bid: continue
                    
                    price = (bid+offer)/2
                    levels = data['s_levels'] + data['r_levels']
                    levels = [l for l in levels if l > 0]
                    if not levels: continue
                    
                    dist = min([abs(price - l)/l for l in levels]) * 100
                    if dist <= pct_threshold:
                        results.append({"Ticker": tkr, "Price": f"${price:.2f}", "Dist%": f"{dist:.2f}"})
                
                st.session_state.proximity_scan_results = sorted(results, key=lambda x: float(x['Dist%']))
                status.update(label="Scan Complete", state="complete", expanded=False)
                st.rerun()

        if st.session_state.proximity_scan_results:
            df_res = pd.DataFrame(st.session_state.proximity_scan_results)
            st.dataframe(df_res, use_container_width=True)
            opts = [r['Ticker'] for r in st.session_state.proximity_scan_results]
            st.session_state.curated_tickers = st.multiselect("Curate List for Head Trader", opts, default=opts)
        
        # === LOGS CONTAINER ===
        st.markdown("---")
        st.subheader("Live Execution Logs")
        log_container = st.container(height=300)
        st.session_state.app_logger.container = log_container
        # Force flush to show startup messages
        st.session_state.app_logger.flush()

    # === TAB 2: Head Trader ===
    with tab2:
        st.header("Step 2: Head Trader Synthesis")
        
        if not st.session_state.curated_tickers: st.warning("Complete Step 1 first."); st.stop()
        focus_input = st.text_area("Executor's Focus (Sentiment)", height=80)
        
        if st.button("Run Synthesis (Freeze Snapshot)", type="primary"):
            if not API_KEYS: st.error("Missing API Keys."); st.stop()
            
            logger = st.session_state.app_logger
            turso = create_turso_client(logger)
            cst, xst = st.session_state.capital_session['cst'], st.session_state.capital_session['xst']
            benchmark_date = st.session_state.latest_macro_date
            
            if not turso: st.error("Critical: DB Connection Failed."); st.stop()
            
            # Variables to hold data for visual x-ray
            xray_data = []
            dossiers = []
            live_stats_log = []
            
            # Use st.status for the "Glass Box" Effect
            with st.status("Processing Head Trader Logic...", expanded=True) as status:
                
                status.write("Fetching EOD Strategy Data...")
                eod_map = get_eod_card_data_for_screener(turso, st.session_state.curated_tickers, benchmark_date, logger)
                
                status.write("Fetching & Splitting Live Session Data (PM vs RTH)...")
                for tkr in st.session_state.curated_tickers:
                    if tkr not in eod_map: continue
                    strat = eod_map.get(tkr, {}).get('screener_briefing_text', 'N/A')
                    
                    bid, offer = get_capital_current_price(tkr, cst, xst, logger)
                    
                    if bid:
                        price = (bid+offer)/2
                        df = get_capital_price_bars(tkr, cst, xst, "MINUTE_5", logger)
                        
                        if df is not None:
                            # Returns a DICT now for X-Ray
                            processed_data = process_session_data_to_summary(tkr, df, price, is_live_mode, logger)
                            
                            # Add to X-Ray Table
                            xray_data.append({
                                "Ticker": tkr,
                                "Mode": processed_data["mode"],
                                "Price": f"${price:.2f}",
                                "PM VWAP": f"${processed_data['pm_vwap']:.2f}" if not pd.isna(processed_data['pm_vwap']) else "-",
                                "RTH VWAP": f"${processed_data['rth_vwap']:.2f}" if not pd.isna(processed_data['rth_vwap']) else "-",
                                "Signal": processed_data["divergence"]
                            })
                            
                            live_summary = processed_data["summary_text"]
                            dossier = f"TICKER: {tkr}\n[STRATEGY - EOD]:\n{strat}\n[TACTICS - LIVE]:\n{live_summary}\n---"
                            dossiers.append(dossier)
                            live_stats_log.append(live_summary)
                
                status.write("Synthesizing... (See X-Ray below)")
                
                # --- PERSIST X-RAY DATA ---
                st.session_state.xray_snapshot = xray_data
                
                status.update(label="Data Gathering Complete", state="complete", expanded=False)

            # --- X-RAY VISUALIZATION (Ephemeral for loading) ---
            if xray_data:
                st.info("🔍 **Tactical X-Ray (Brain Scan):** Verify the data below before the AI verdict.")
                st.dataframe(pd.DataFrame(xray_data), use_container_width=True)

            # 2. Call AI with TIERED SYSTEM PROMPT
            with st.spinner("Head Trader Thinking (Categorizing)..."):
                
                mode_instruction = ""
                if is_live_mode:
                    mode_instruction = """
                    **CRITICAL: MARKET IS OPEN (LIVE BATTLE MODE)**
                    You must look for DIVERGENCES between the Pre-Market Context (PM VWAP) and the RTH Reality (RTH VWAP).
                    - If Price is above PM VWAP but below RTH VWAP, is this a 'Trap' for pre-market bulls?
                    - If Price is below PM VWAP but reclaimed RTH VWAP, is this a 'Reversal' or 'Short Squeeze'?
                    """
                else:
                    mode_instruction = "**MARKET IS CLOSED (PRE-MARKET PREP)**. Focus on the setup and the key levels for the open."

                prompt = f"""
                [INPUTS]
                Macro Context: {json.dumps(st.session_state.premarket_economy_card)}
                Executor Focus: {focus_input}
                Time Mode: {mode_instruction}
                
                [CANDIDATE DOSSIERS]
                {"\n".join(dossiers)}
                
                [TASK]
                Act as an Elite Head Trader. Analyze the Dossiers and the "Dual Session" Data.
                Your goal is to TRIAGE these opportunities based on CONVICTION LEVEL.

                **Conviction Hierarchy:**
                1. **Highest Conviction:** Where "Desperate Participants" (Trapped Longs or Puking Shorts) are creating an immediate, high-velocity opportunity.
                2. **Structural:** Where "Committed Participants" are patiently defending a level.
                3. **Neutral/Contra:** Stocks fighting the trend.

                [OUTPUT FORMAT - MANDATORY]
                Output your analysis in this EXACT structure:

                # HEAD TRADER BRIEFING: [Date]
                **MACRO THESIS:** [One sentence summary of the market context]

                ## TIER 1: HIGHEST CONVICTION [BEARISH/BULLISH] - DESPERATE [SELLERS/BUYERS]
                *Stocks with severe structural damage or massive traps. The "Pain Trade".*

                | Ticker | Price | Bias | Motivation & Story | Tactical Implication |
                | :--- | :--- | :--- | :--- | :--- |
                | MSFT | $491 | Bearish | **Desperate Sellers** causing breakdown of $506. PM is holding below VWAP. | Plan A: Short Retest of $506. |

                ## TIER 2: [BEARISH/BULLISH] - COMMITTED [SELLERS/BUYERS]
                *Stocks where control is established, patience required.*

                | Ticker | Price | Bias | Motivation & Story | Tactical Implication |
                | :--- | :--- | :--- | :--- | :--- |
                | ... | ... | ... | ... | ... |

                ## TIER 3: NEUTRAL/CONTRARIAN LEAN
                *Stocks showing relative strength/weakness against the tide.*

                | Ticker | Price | Bias | Motivation & Story | Tactical Implication |
                | :--- | :--- | :--- | :--- | :--- |
                | ... | ... | ... | ... | ... |

                ## SUMMARY & FOCUS
                * **Primary Bias:** ...
                * **Top Watch:** ...
                """
                
                sys_prompt = "You are an elite Head Trader. You focus on Order Flow, Participant Psychology, and Trap Scenarios. Be decisive."
                
                # === KEY ROTATION CALL ===
                briefing, error_msg = call_gemini_api(prompt, API_KEYS, sys_prompt, logger)
                
                if briefing:
                    st.session_state.final_briefing = briefing
                    
                    # 3. SAVE SNAPSHOT
                    news_in = st.session_state.get("pm_news_input", "")
                    save_snapshot(
                        client=turso,
                        news_input=str(news_in) + " | Focus: " + focus_input,
                        eco_card=st.session_state.premarket_economy_card,
                        live_stats=json.dumps(live_stats_log),
                        briefing=briefing,
                        logger=logger
                    )
                    st.success("Briefing Generated & Snapshot Saved!")
                    st.rerun()
                else:
                    st.error(f"AI Synthesis Failed: {error_msg}")

        if st.session_state.final_briefing:
            # --- PERSISTENT RENDER OF X-RAY TABLE ---
            if st.session_state.get('xray_snapshot'):
                 st.info("🔍 **Tactical X-Ray (Brain Scan) - Preserved Context:**")
                 st.dataframe(pd.DataFrame(st.session_state.xray_snapshot), use_container_width=True)
            
            st.markdown(st.session_state.final_briefing)

if __name__ == "__main__":
    main()