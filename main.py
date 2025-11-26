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
try:
    from key_manager import KeyManager
except ImportError:
    st.error("❌ CRITICAL MISSING FILE: 'key_manager.py' was not found in this directory.")
    st.stop()

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================

st.set_page_config(page_title="Pre-Market Analyst (Glass Box)", layout="wide")

US_EASTERN = pytz_timezone('US/Eastern')
MARKET_OPEN_TIME = dt_time(9, 30)

AVAILABLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash", 
    "gemini-2.5-pro"
]
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

CORE_INTERMARKET_TICKERS = [
    "BTCUSDT", "CL=F", "DIA", "EURUSDT", "IWM",
    "PAXGUSDT", "QQQ", "SMH", "SPY", "TLT",
    "UUP", "XLC", "XLF", "XLI", "XLP",
    "XLU", "XLV", "NDAQ", "^VIX"
]

# --- GLOBAL INITIALIZATION ---
KEY_MANAGER_INSTANCE = None
TURSO_DB_URL_HTTPS = None
TURSO_AUTH_TOKEN = None

try:
    turso_secrets = st.secrets.get("turso", {})
    raw_db_url = turso_secrets.get("db_url")
    TURSO_AUTH_TOKEN = turso_secrets.get("auth_token")

    if raw_db_url:
        TURSO_DB_URL_HTTPS = raw_db_url.replace("libsql://", "https://")
    
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
# 3. DATABASE UTILITIES
# ==============================================================================

@st.cache_resource(show_spinner="Connecting to Headquarters...")
def get_db_connection():
    if not TURSO_DB_URL_HTTPS or not TURSO_AUTH_TOKEN:
        return None
    try:
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
    try:
        cutoff_date_part = cutoff_str.split(" ")[0] 
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
# 4. DATA PROCESSING
# ==============================================================================

def get_latest_price_details(client, ticker: str, cutoff_str: str, logger: AppLogger) -> tuple[float | None, str | None]:
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

        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(str).str.replace('Z', '').str.replace(' ', 'T'))
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        
        df['dt_eastern'] = df['timestamp'].dt.tz_convert(US_EASTERN)
        time_eastern = df['dt_eastern'].dt.time
        df['session'] = np.where(time_eastern < MARKET_OPEN_TIME, 'PM', 'RTH')

        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        for col in ['Close', 'Volume', 'High', 'Low']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df.dropna(subset=['Close'], inplace=True) # Removed Volume drop dependency
        return df.reset_index(drop=True)
    except Exception as e:
        logger.log(f"Data Error ({epic}): {e}")
        return None

# --- NEW: GEOMETRY & TIME ENGINE ---

def calculate_geometry(df: pd.DataFrame) -> dict:
    """Calculates Slope and Pivot Structure."""
    if len(df) < 3:
        return {"Slope": 0, "Structure": "Insufficient Data"}
    
    # 1. Trajectory Slope (Linear Regression on Close)
    try:
        x = np.arange(len(df))
        y = df['Close'].values
        slope, _ = np.polyfit(x, y, 1)
        
        # Normalize slope relative to price to make it comparable across tickers
        # (Slope / Average Price) * 1000 to make readable integer-like numbers
        norm_slope = (slope / np.mean(y)) * 10000
    except:
        norm_slope = 0

    # 2. Pivot Structure (Higher Highs / Lower Lows)
    # Divide session into 3 chunks to see progression
    chunks = np.array_split(df, 3)
    if len(chunks) < 3:
        structure = "N/A"
    else:
        h1, h2, h3 = chunks[0]['High'].max(), chunks[1]['High'].max(), chunks[2]['High'].max()
        l1, l2, l3 = chunks[0]['Low'].min(), chunks[1]['Low'].min(), chunks[2]['Low'].min()
        
        if h3 > h2 > h1 and l3 > l2 > l1: structure = "Clear Bullish Staircase (HH/HL)"
        elif h3 < h2 < h1 and l3 < l2 < l1: structure = "Clear Bearish Staircase (LH/LL)"
        elif h3 > h1 and l3 < l1: structure = "Expanding/Volatile (Megaphone)"
        elif h3 < h1 and l3 > l1: structure = "Compressing/Coiling (Inside)"
        else: structure = "Mixed/Choppy"

    return {"Slope": norm_slope, "Structure": structure}

def calculate_time_at_price(df: pd.DataFrame) -> dict:
    """Calculates where price spent the most time (Time at Price)."""
    if df.empty: return {"Zone": "N/A", "Duration": 0}
    
    try:
        # Binning: Create 10 price buckets across the day's range
        low = df['Low'].min()
        high = df['High'].max()
        
        if high == low: return {"Zone": f"${low}", "Duration": len(df)*5} # Flatline
        
        bins = np.linspace(low, high, 10)
        # Digitize returns the bin index for each Close price
        indices = np.digitize(df['Close'], bins)
        
        # Count frequency (Time)
        counts = np.bincount(indices)
        max_idx = counts.argmax()
        
        # Map back to Price
        # The indices correspond to bins. bins[i-1] to bins[i]
        if max_idx >= len(bins): max_idx = len(bins) - 1
        if max_idx == 0: max_idx = 1
            
        zone_low = bins[max_idx-1]
        zone_high = bins[max_idx] if max_idx < len(bins) else high
        
        duration_min = counts[max_idx] * 5 # Assuming 5m bars
        pct_time = (counts[max_idx] / len(df)) * 100
        
        return {
            "Zone": f"${zone_low:.2f}-${zone_high:.2f}",
            "Duration": f"{duration_min} mins ({pct_time:.0f}%)",
            "Raw_Pct": pct_time
        }
    except:
        return {"Zone": "Error", "Duration": "0m", "Raw_Pct": 0}

def analyze_level_defense(df: pd.DataFrame) -> dict:
    """Checks how many times HOD/LOD were tested."""
    if df.empty: return {"Support_Tests": 0, "Resistance_Tests": 0}
    
    hod = df['High'].max()
    lod = df['Low'].min()
    threshold = 0.0005 # 0.05% tolerance
    
    # Count bars touching near High
    res_tests = len(df[df['High'] >= hod * (1 - threshold)])
    
    # Count bars touching near Low
    sup_tests = len(df[df['Low'] <= lod * (1 + threshold)])
    
    return {"Support_Tests": sup_tests, "Resistance_Tests": res_tests}

def process_session_data_to_summary(ticker: str, df: pd.DataFrame, live_price: float, logger: AppLogger) -> dict:
    """
    Generates a Time & Geometry focused summary.
    """
    result = {
        "ticker": ticker,
        "price": live_price,
        "slope": 0,
        "time_zone": "N/A",
        "summary_text": f"Data Extraction Summary: {ticker} (Insufficient Data)",
    }

    if df is None or df.empty:
        return result

    # 1. Basic Stats
    open_px = df.iloc[0]['Open']
    high_px = df['High'].max()
    low_px = df['Low'].min()
    
    # 2. Geometry
    geo = calculate_geometry(df)
    slope_val = geo['Slope']
    slope_desc = "Flat"
    if slope_val > 5: slope_desc = "Strong Ascent"
    elif slope_val > 1: slope_desc = "Gradual Grind Up"
    elif slope_val < -5: slope_desc = "Steep Decline"
    elif slope_val < -1: slope_desc = "Drifting Lower"
    
    result["slope"] = f"{slope_val:.1f}"

    # 3. Time at Price
    tap = calculate_time_at_price(df)
    result["time_zone"] = tap["Zone"] # For X-Ray Table

    # 4. Defense
    defense = analyze_level_defense(df)

    # 5. Opening Range Time Analysis
    start_time = df['dt_eastern'].min()
    end_or_time = start_time + timedelta(minutes=30)
    df_or = df[df['dt_eastern'] <= end_or_time]
    
    or_narrative = "N/A"
    if not df_or.empty:
        or_high = df_or['High'].max()
        or_low = df_or['Low'].min()
        
        # Calculate TIME spent above/below OR
        bars_above = len(df[df['Close'] > or_high])
        bars_below = len(df[df['Close'] < or_low])
        bars_inside = len(df) - bars_above - bars_below
        
        total_bars = len(df)
        pct_above = (bars_above / total_bars) * 100
        pct_below = (bars_below / total_bars) * 100
        pct_inside = (bars_inside / total_bars) * 100
        
        if pct_above > 60: or_narrative = f"Acceptance Higher ({pct_above:.0f}% time > ORH)"
        elif pct_below > 60: or_narrative = f"Acceptance Lower ({pct_below:.0f}% time < ORL)"
        elif pct_inside > 60: or_narrative = f"Range Bound ({pct_inside:.0f}% time inside OR)"
        else: or_narrative = "Volatile / No Acceptance"
    
    # 6. CONSTRUCT REPORT
    date_str = df.iloc[0]['timestamp'].strftime('%Y-%m-%d')
    
    summary_report = f"""Data Extraction Summary: {ticker} | {date_str}
==================================================
1. SESSION GEOMETRY & PATH
   - Trajectory Slope: {slope_val:.2f} ({slope_desc})
   - Structure: {geo['Structure']}
   - Price vs Open: {'Green' if live_price > open_px else 'Red'} (${live_price:.2f} vs ${open_px:.2f})

2. TIME AT PRICE (VALUE ACCEPTANCE)
   - High Dwell Zone: {tap['Duration']} spent at {tap['Zone']}
   - Implication: This zone represents the market's agreed 'Fair Value' for the session.

3. KEY LEVEL DEFENSE (TESTS)
   - Resistance Tests (HOD): Tested {defense['Resistance_Tests']} times.
   - Support Tests (LOD): Tested {defense['Support_Tests']} times.

4. OPENING RANGE INTERACTION (TIME WEIGHTED)
   - Range: ${or_low:.2f} - ${or_high:.2f}
   - Behavior: {or_narrative}
"""
    result["summary_text"] = summary_report
    return result

# ==============================================================================
# 5. AI SERVICES
# ==============================================================================

def call_gemini_with_rotation(
    prompt: str, 
    system_prompt: str, 
    logger: AppLogger, 
    model_name: str, 
    max_retries=5
) -> tuple[str | None, str | None]:
    
    if not KEY_MANAGER_INSTANCE:
        logger.log("❌ ERROR: KeyManager not initialized.")
        return None, "System Configuration Error"
    
    for i in range(max_retries):
        current_api_key = None
        key_name = "Unknown"

        try:
            key_name, current_api_key, wait_time = KEY_MANAGER_INSTANCE.get_key(target_model=model_name)
            
            if not current_api_key:
                logger.log(f"⏳ All keys exhausted for {model_name}. Waiting {wait_time:.0f}s...")
                if wait_time > 0 and i < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    return None, f"Global Rate Limit for {model_name}"
            
            logger.log(f"🔑 Acquired '{key_name}' | Model: {model_name} (Attempt {i+1})")
            
            gemini_url = f"{API_BASE_URL}/{model_name}:generateContent?key={current_api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}], 
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
            }
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(gemini_url, headers=headers, data=json.dumps(payload), timeout=90)
            
            if response.status_code == 200:
                KEY_MANAGER_INSTANCE.report_success(current_api_key, model_id=model_name)
                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    return text, None
                except (KeyError, IndexError):
                    logger.log(f"⚠️ Invalid JSON response from Google.")
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

    # --- Session State ---
    if 'premarket_economy_card' not in st.session_state: st.session_state.premarket_economy_card = None
    if 'latest_macro_date' not in st.session_state: st.session_state.latest_macro_date = None
    if 'proximity_scan_results' not in st.session_state: st.session_state.proximity_scan_results = []
    if 'curated_tickers' not in st.session_state: st.session_state.curated_tickers = []
    if 'final_briefing' not in st.session_state: st.session_state.final_briefing = None
    if 'xray_snapshot' not in st.session_state: st.session_state.xray_snapshot = None
    if 'app_logger' not in st.session_state or not hasattr(st.session_state.app_logger, 'flush'):
        st.session_state.app_logger = AppLogger(None)

    if 'glassbox_eod_card' not in st.session_state: st.session_state.glassbox_eod_card = None
    if 'glassbox_etf_data' not in st.session_state: st.session_state.glassbox_etf_data = []
    if 'glassbox_prompt' not in st.session_state: st.session_state.glassbox_prompt = None
    if 'audit_logs' not in st.session_state: st.session_state.audit_logs = []

    # --- Startup ---
    startup_logger = st.session_state.app_logger
    turso = get_db_connection()
    if turso: init_db_schema(turso, startup_logger)
    else: st.error("DB Connection Failed."); st.stop()

    # --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ Mission Config")
        if KEY_MANAGER_INSTANCE: st.success("✅ Key Manager: Active")
        else: st.error("❌ Key Manager: Failed")

        selected_model = st.selectbox("AI Model", AVAILABLE_MODELS, index=0)
        mode = st.radio("Operation Mode", ["Live", "Simulation"], index=0)
        
        if mode == "Live":
            simulation_cutoff_dt = datetime.now(timezone.utc)
            st.success(f"🟢 Live Mode Active")
        else:
            st.warning(f"🟠 Simulation Mode")
            sim_date = st.date_input("Simulation Date")
            sim_time = st.time_input("Simulation Time (UTC)", value=datetime.strptime("13:00", "%H:%M").time())
            simulation_cutoff_dt = datetime.combine(sim_date, sim_time).replace(tzinfo=timezone.utc)
            st.info(f"Time Travel To: {simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        simulation_cutoff_str = simulation_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
        analysis_date = sim_date if mode == "Simulation" else simulation_cutoff_dt.date()
        st.write(f"Analysis Market Date: {analysis_date}")
        st.session_state.analysis_date = analysis_date

    tab1, tab2 = st.tabs(["Step 1: Live Market Monitor", "Step 2: Battle Commander"])
    logger = st.session_state.app_logger

    # --- TAB 1 ---
    with tab1:
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
                eod_placeholder.info("Click **'Generate Economy Card'** below to fetch the latest End-of-Day context.")

        with col2:
            st.caption("3. Constructed AI Prompt")
            prompt_placeholder = st.empty()
            if st.session_state.glassbox_prompt:
                prompt_placeholder.text_area("Prompt Preview", st.session_state.glassbox_prompt, height=150, key="glassbox_prompt_view")
            else:
                prompt_placeholder.info("Click **'Generate Economy Card'** below to construct the AI prompt.")

        st.caption("2. Intermarket Data Build (Updating Live)")
        etf_placeholder = st.empty()
        if st.session_state.glassbox_etf_data:
            etf_placeholder.dataframe(
                pd.DataFrame(st.session_state.glassbox_etf_data), use_container_width=True,
                column_config={
                    "Freshness": st.column_config.ProgressColumn(f"Freshness (vs {simulation_cutoff_dt.strftime('%H:%M')})", format=" ", min_value=0, max_value=1, width="small"),
                    "Audit: Date": st.column_config.TextColumn("Data Timestamp (UTC)"),
                    "Audit: Bars": st.column_config.NumberColumn("Bars"),
                },
            )
        else:
            etf_placeholder.info("Ready to scan. Click **'Generate Economy Card (Step 0)'** to fetch live market data.")

        # --- GLASS BOX VISIBILITY: RAW ETF STRINGS ---
        if st.session_state.glassbox_etf_data:
            with st.expander("🔍 View Raw Data Strings sent to AI"):
                st.info("Check the Live Logs or 'Prompt Preview' above to see the full generated reports.")

        st.markdown("---")

        if st.button("Generate Economy Card (Step 0)", key="btn_step0", type="primary"):
            st.session_state.glassbox_etf_data = []
            etf_placeholder.empty()

            with st.status(f"Running Macro Scan ({mode})...", expanded=True) as status:
                status.write("Fetching EOD Card...")
                if mode == "Simulation":
                    eod_search_date = (simulation_cutoff_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    eod_search_date = simulation_cutoff_dt.strftime('%Y-%m-%d')
                    
                latest_date = get_latest_economy_card_date(turso, simulation_cutoff_str, logger)
                eod_card = {}
                if latest_date:
                    eod_card_data = get_eod_economy_card(turso, latest_date, logger)
                    if eod_card_data:
                        eod_card = eod_card_data
                        eod_placeholder.json(eod_card, expanded=False)
                    else:
                        eod_placeholder.warning(f"⚠️ Found record for {latest_date} but data was empty/corrupt.")
                else:
                    eod_placeholder.warning(f"⚠️ No EOD Economy Card found on or before {simulation_cutoff_str.split(' ')[0]}.")
                
                st.session_state.glassbox_eod_card = eod_card

                status.write("Scanning Intermarket Tickers...")
                etf_summaries = []
                benchmark_date_str = st.session_state.analysis_date.isoformat()

                for epic in CORE_INTERMARKET_TICKERS:
                    latest_price, price_ts = get_latest_price_details(turso, epic, simulation_cutoff_str, logger)

                    if latest_price:
                        df = get_session_bars_from_db(turso, epic, benchmark_date_str, simulation_cutoff_str, logger)
                        bar_count = len(df) if df is not None else 0

                        freshness_score = 0.0
                        try:
                            if price_ts:
                                ts_clean = price_ts.replace("Z", "+00:00").replace(" ", "T")
                                ts_obj = datetime.fromisoformat(ts_clean)
                                if ts_obj.tzinfo is None: ts_obj = ts_obj.replace(tzinfo=timezone.utc)
                                lag_minutes = (simulation_cutoff_dt - ts_obj).total_seconds() / 60.0
                                freshness_score = max(0.0, 1.0 - (lag_minutes / 60.0))
                        except Exception: freshness_score = 0.0

                        if df is not None:
                            processed_data = process_session_data_to_summary(epic, df, latest_price, logger)
                            summary_text = processed_data["summary_text"]
                            etf_summaries.append(summary_text)

                            new_row = {
                                "Ticker": epic,
                                "Price": f"${latest_price:.2f}",
                                "Freshness": freshness_score,
                                "Audit: Date": f"{price_ts} (UTC)",
                                "Audit: Bars": bar_count,
                                "Slope": processed_data["slope"],
                                "High Dwell": processed_data["time_zone"],
                            }
                            st.session_state.glassbox_etf_data.append(new_row)
                            
                            etf_placeholder.dataframe(pd.DataFrame(st.session_state.glassbox_etf_data), use_container_width=True)
                            time.sleep(0.02)

                if not etf_summaries:
                    status.update(label="Scan Aborted: No Data", state="error", expanded=True)
                    st.error("⚠️ **No Live Data Found:** Please run the **Data Harvester** to update market data, then click the button again.")
                    st.stop()

                status.write("Synthesizing AI Prompt...")
                mode_str = f"PRE-MARKET PREP ({mode})"
                prompt = f"""
                [INPUTS]
                EOD Context: {json.dumps(eod_card)}
                
                Live Intermarket Data (Price Action & Time Analysis): 
                {json.dumps(etf_summaries, indent=2)}
                
                News: {pm_news}
                Mode: {mode_str}
                [TASK] Act as Macro Strategist. Synthesize EOD Context + Live Data + News.
                """
                st.session_state.glassbox_prompt = prompt
                prompt_placeholder.text_area("Prompt Preview", prompt, height=150, key="glassbox_prompt_preview")

                status.write(f"Calling Gemini ({selected_model})...")
                system_prompt = "You are an expert Macro Strategist. Output valid JSON only with keys: marketNarrative, marketBias, sectorRotation."
                
                resp, error_msg = call_gemini_with_rotation(prompt, system_prompt, logger, selected_model)

                if resp:
                    try:
                        json_match = re.search(r"(\{.*\})", resp, re.DOTALL)
                        json_str = json_match.group(1) if json_match else resp
                        new_card = json.loads(json_str)
                        new_card['date'] = st.session_state.analysis_date.isoformat()
                        st.session_state.premarket_economy_card = new_card
                        st.session_state.latest_macro_date = new_card['date']
                        status.update(label="Macro Card Generated", state="complete", expanded=False)
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
            benchmark_date_for_scan = st.session_state.latest_macro_date
            
            with st.status(f"Scanning Market ({mode})...", expanded=True) as status:
                tickers = get_all_tickers_from_db(turso, logger)
                eod_data = get_eod_card_data_for_screener(turso, tickers, benchmark_date_for_scan, logger)
                results = []
                for tkr, data in eod_data.items():
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    if not price: continue
                    levels = [l for l in data['s_levels'] + data['r_levels'] if l > 0]
                    if not levels: continue
                    dist = min([abs(price - l) / l for l in levels]) * 100
                    if dist <= pct_threshold:
                        results.append({"Ticker": tkr, "Price": f"${price:.2f}", "Dist%": f"{dist:.2f}"})
                st.session_state.proximity_scan_results = sorted(results, key=lambda x: float(x['Dist%']))
                status.update(label="Scan Complete", state="complete", expanded=False)
                st.rerun()

        if st.session_state.proximity_scan_results:
            df_res = pd.DataFrame(st.session_state.proximity_scan_results)
            st.dataframe(df_res, use_container_width=True)
            opts = [r['Ticker'] for r in st.session_state.proximity_scan_results]
            st.session_state.curated_tickers = st.multiselect("Curate List", opts, default=opts)

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
                eod_map = get_eod_card_data_for_screener(turso, st.session_state.curated_tickers, benchmark_date_str, logger)

                for tkr in st.session_state.curated_tickers:
                    if tkr not in eod_map: continue
                    strat = eod_map.get(tkr, {}).get("screener_briefing_text", "N/A")
                    price, _ = get_latest_price_details(turso, tkr, simulation_cutoff_str, logger)
                    
                    if price:
                        df = get_session_bars_from_db(turso, tkr, benchmark_date_str, simulation_cutoff_str, logger)
                        if df is not None:
                            processed_data = process_session_data_to_summary(tkr, df, price, logger)
                            
                            xray_data.append({
                                "Ticker": tkr,
                                "Price": f"${price:.2f}",
                                "Slope": processed_data["slope"],
                                "High Dwell": processed_data["time_zone"],
                            })

                            dossiers.append(f"TICKER: {tkr}\n[STRATEGY]:\n{strat}\n[TACTICS]:\n{processed_data['summary_text']}\n---")
                            live_stats_log.append(processed_data["summary_text"])

                st.session_state.xray_snapshot = xray_data
                status.update(label="Data Gathered", state="complete")

            if xray_data:
                st.info("🔍 **Tactical X-Ray:**")
                st.dataframe(pd.DataFrame(xray_data), use_container_width=True)
            
            # --- GLASS BOX VISIBILITY: SHOW DOSSIERS ---
            if dossiers:
                with st.expander("📂 View Dossiers Sent to Head Trader"):
                    st.text("\n".join(dossiers))

            with st.spinner(f"Head Trader Categorizing ({selected_model})..."):
                prompt = (
                    "[INPUTS]\n"
                    f"Macro: {json.dumps(st.session_state.premarket_economy_card)}\n"
                    f"Focus: {focus_input}\n"
                    f"DOSSIERS:\n{''.join(dossiers)}\n"
                    "Task: Triage into Tiers 1/2/3."
                )

                briefing, error_msg = call_gemini_with_rotation(prompt, "You are an elite Head Trader.", logger, selected_model)

                if briefing:
                    st.session_state.final_briefing = briefing
                    save_snapshot(turso, str(pm_news), st.session_state.premarket_economy_card, json.dumps(live_stats_log), briefing, logger)
                    st.success("Briefing Saved!")
                    st.rerun()
                else:
                    st.error(f"AI Failed: {error_msg}")

        if st.session_state.final_briefing:
            st.markdown(st.session_state.final_briefing)

if __name__ == "__main__":
    main()