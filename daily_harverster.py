import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import altair as alt
from libsql_client import create_client_sync, Statement
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, time as dt_time, timedelta
from pytz import timezone
import time
import os

# --- Configuration & Constants ---
st.set_page_config(page_title="Market Data Harvester", layout="wide")

CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"
US_EASTERN = timezone('US/Eastern')
BAHRAIN_TZ = timezone('Asia/Bahrain')
UTC = timezone('UTC')

SCHEMA_COLS = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'session']

# --- 🛡️ PILLAR 1: RESILIENCE (Retry Logic) ---
def get_retry_session(retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 504)):
    """Creates a requests session with automatic retries."""
    session = requests.Session()
    retry = Retry(
        total=retries, read=retries, connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

# --- Turso Database Functions ---
@st.cache_resource
def get_db_connection():
    """Establishes a synchronous connection to the Turso database."""
    try:
        if "turso" not in st.secrets:
            st.error("Missing 'turso' section in secrets.toml")
            return None
        url = st.secrets["turso"]["db_url"]
        token = st.secrets["turso"]["auth_token"]
        # Force HTTPS for reliability in serverless environments
        http_url = url.replace("libsql://", "https://")
        config = {"url": http_url, "auth_token": token}
        return create_client_sync(**config)
    except Exception as e:
        st.error(f"Failed to create Turso client: {e}")
        return None

def init_db():
    """Initializes the database, creating tables if they don't exist."""
    client = get_db_connection()
    if not client: return
    try:
        # Table for managing symbol rules
        client.execute("""
            CREATE TABLE IF NOT EXISTS symbol_map (
                user_ticker TEXT PRIMARY KEY,
                capital_epic TEXT NOT NULL,
                source_strategy TEXT DEFAULT 'HYBRID' 
            )
        """)
        # Table for storing all market data
        client.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume REAL, session TEXT,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        # Seed the database if the symbol map is empty
        res = client.execute("SELECT count(*) FROM symbol_map")
        if res.rows and res.rows[0][0] == 0:
            hybrid_tickers = [
                "AMD", "AMZN", "AAPL", "AVGO", "BABA", "GOOGL", "LRCX", "META", 
                "MSFT", "MU", "NVDA", "ORCL", "PANW", "QCOM", "SHOP", "TSLA", "TSM",
                "SPY", "QQQ", "IWM", "DIA"
            ]
            seed_data = [(t, t, "HYBRID") for t in hybrid_tickers]
            for ticker, epic, strategy in seed_data:
                client.execute(
                    "INSERT INTO symbol_map (user_ticker, capital_epic, source_strategy) VALUES (?, ?, ?)", 
                    [ticker, epic, strategy]
                )
            st.toast("Database initialized with default symbols.", icon="💾")
    except Exception as e:
        st.error(f"DB Init Error: {e}")

def get_symbol_map_from_db():
    """Fetches the complete symbol inventory from Turso."""
    client = get_db_connection()
    if not client: return {}
    try:
        res = client.execute("SELECT user_ticker, capital_epic, source_strategy FROM symbol_map ORDER BY user_ticker")
        return {row[0]: {'epic': row[1], 'strategy': row[2]} for row in res.rows}
    except Exception as e:
        st.error(f"Error fetching inventory: {e}")
        return {}

def upsert_symbol_mapping(ticker, epic, strategy):
    """Adds or updates a symbol's rules in the database."""
    client = get_db_connection()
    if not client: return False
    try:
        client.execute(
            """INSERT INTO symbol_map (user_ticker, capital_epic, source_strategy) 
               VALUES (?, ?, ?) 
               ON CONFLICT(user_ticker) DO UPDATE SET 
                 capital_epic=excluded.capital_epic, 
                 source_strategy=excluded.source_strategy""",
            [ticker, epic, strategy]
        )
        return True
    except Exception as e:
        st.error(f"Error saving symbol: {e}")
        return False

def delete_symbol_mapping(ticker):
    """Deletes a symbol from the inventory."""
    client = get_db_connection()
    if not client: return False
    try:
        client.execute("DELETE FROM symbol_map WHERE user_ticker = ?", [ticker])
        return True
    except Exception as e:
        st.error(f"Error deleting symbol: {e}")
        return False

def save_data_to_turso(df: pd.DataFrame, logger=None):
    """Saves a DataFrame of market data to Turso using a batch INSERT OR REPLACE."""
    client = get_db_connection()
    if not client or df.empty: return False
    try:
        statements = []
        for _, row in df.iterrows():
            ts_str = row['timestamp'].isoformat()
            stmt = Statement(
                """INSERT OR REPLACE INTO market_data 
                   (timestamp, symbol, open, high, low, close, volume, session) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [ts_str, row['symbol'], row['open'], row['high'], row['low'], row['close'], row['volume'], row['session']]
            )
            statements.append(stmt)
        if logger: logger.log(f"   💾 Committing {len(statements)} records to Turso...")
        client.batch(statements)
        return True
    except Exception as e:
        err_msg = f"Batch Commit Failed: {e}"
        if logger: logger.log(f"   ❌ {err_msg}")
        else: st.error(err_msg)
        return False

def fetch_data_health_matrix(tickers: list, start_date, end_date, session_filter="Total"):
    """
    Fetches a matrix of candle counts for the data health dashboard.
    Can filter by session ('PRE', 'REG', or 'Total').
    """
    client = get_db_connection()
    if not client: return pd.DataFrame()

    start_str = f"{start_date}T00:00:00"
    end_str = f"{end_date}T23:59:59"
    placeholders = ",".join("?" * len(tickers))

    # Base query
    query = f"""
        SELECT 
            symbol, 
            date(timestamp) as day, 
            COUNT(*) as candle_count
        FROM market_data 
        WHERE symbol IN ({placeholders}) 
          AND timestamp >= ? 
          AND timestamp <= ? 
    """
    params = tickers + [start_str, end_str]
    
    # --- Session Filter Logic ---
    if session_filter != "Total":
        query += " AND session = ? "
        params.append(session_filter)
        
    query += " GROUP BY symbol, day ORDER BY symbol, day"
    
    try:
        res = client.execute(query, params)
        if not res.rows: return pd.DataFrame()
        cols = ['symbol', 'day', 'candle_count']
        df = pd.DataFrame([list(row) for row in res.rows], columns=cols)
        
        # Pivot to create the matrix
        pivot_df = df.pivot(index='symbol', columns='day', values='candle_count')
        return pivot_df
    except Exception as e:
        st.error(f"Error fetching data health: {e}")
        return pd.DataFrame()

class StreamlitLogger:
    """A simple logger that writes to a Streamlit container."""
    def __init__(self, container): self.container = container
    def log(self, message): self.container.write(f"🔹 {message}"); print(message) 

# --- Normalization Functions ---
def normalize_capital_df(df: pd.DataFrame, symbol: str, session_label: str) -> pd.DataFrame:
    """Normalizes Capital.com data to target schema."""
    if df.empty: return pd.DataFrame(columns=SCHEMA_COLS)
    df_norm = df.copy()
    df_norm.rename(columns={'SnapshotTime': 'timestamp', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    df_norm['symbol'] = symbol; df_norm['session'] = session_label
    return df_norm[SCHEMA_COLS]

def normalize_yahoo_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalizes Yahoo Finance data to target schema."""
    if df.empty: return pd.DataFrame(columns=SCHEMA_COLS)
    df_norm = df.copy()
    if isinstance(df_norm.columns, pd.MultiIndex): df_norm.columns = df_norm.columns.get_level_values(0)
    df_norm.reset_index(inplace=True)
    df_norm.rename(columns={'Datetime': 'timestamp', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    if df_norm['timestamp'].dt.tz is not None: df_norm['timestamp'] = df_norm['timestamp'].dt.tz_convert('UTC')
    else: df_norm['timestamp'] = df_norm['timestamp'].dt.tz_localize('US/Eastern').dt.tz_convert('UTC')
    df_norm['symbol'] = symbol; df_norm['session'] = 'REG'
    df_norm.columns = [c.lower() for c in df_norm.columns]
    return df_norm[SCHEMA_COLS]

# --- API Functions ---
@st.cache_resource(ttl=600)
def create_capital_session():
    """Creates a Capital.com session and caches tokens."""
    if "capital_com" not in st.secrets: return None, None
    secrets = st.secrets["capital_com"]
    session = get_retry_session()
    try:
        response = session.post(
            f"{CAPITAL_API_URL_BASE}/session", 
            headers={'X-CAP-API-KEY': secrets["X_CAP_API_KEY"], 'Content-Type': 'application/json'}, 
            json={"identifier": secrets["identifier"], "password": secrets["password"]}, timeout=15
        )
        response.raise_for_status()
        return response.headers.get('CST'), response.headers.get('X-SECURITY-TOKEN')
    except Exception: return None, None

def fetch_capital_data_range(epic: str, cst: str, xst: str, start_utc, end_utc, logger) -> pd.DataFrame:
    """Fetches 1-min Capital.com data for a specific epic and UTC time window."""
    now_utc = datetime.now(UTC)
    limit_16h_ago = now_utc - timedelta(hours=16)
    
    # Clamp start time to the 16-hour wall
    if start_utc < limit_16h_ago: 
        logger.log(f"   ⚠️ Start time clamped to 16h limit.")
        start_utc = limit_16h_ago + timedelta(minutes=1)
        
    if start_utc >= end_utc: return pd.DataFrame()
    if end_utc > now_utc: end_utc = now_utc
    
    price_params = {
        "resolution": "MINUTE", "max": 1000, # max: 1000 is CRITICAL
        'from': start_utc.strftime('%Y-%m-%dT%H:%M:%S'), 
        'to': end_utc.strftime('%Y-%m-%dT%H:%M:%S')
    }
    session = get_retry_session()
    try:
        response = session.get(f"{CAPITAL_API_URL_BASE}/prices/{epic}", headers={'X-SECURITY-TOKEN': xst, 'CST': cst}, params=price_params, timeout=15)
        response.raise_for_status()
        prices = response.json().get('prices', [])
        if not prices: return pd.DataFrame()
        
        extracted = [{'SnapshotTime': p.get('snapshotTime'), 'Open': p.get('openPrice', {}).get('bid'), 'High': p.get('highPrice', {}).get('bid'), 'Low': p.get('lowPrice', {}).get('bid'), 'Close': p.get('closePrice', {}).get('bid'), 'Volume': p.get('lastTradedVolume')} for p in prices]
        df = pd.DataFrame(extracted)
        
        # Normalize timestamps
        df['SnapshotTime'] = pd.to_datetime(df['SnapshotTime'])
        if df['SnapshotTime'].dt.tz is None: df['SnapshotTime'] = df['SnapshotTime'].dt.tz_localize(BAHRAIN_TZ)
        else: df['SnapshotTime'] = df['SnapshotTime'].dt.tz_convert(BAHRAIN_TZ)
        df['SnapshotTime'] = df['SnapshotTime'].dt.tz_convert(UTC)
        return df
    except Exception as e:
        logger.log(f"   ❌ Error fetching Capital data for {epic}: {e}")
        return pd.DataFrame()

def fetch_yahoo_market_data(ticker: str, target_date_et, logger) -> pd.DataFrame:
    """Fetches 1-min Yahoo Finance data for the regular session."""
    try:
        start = target_date_et
        end = start + pd.Timedelta(days=1)
        df = yf.download(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), interval="1m", progress=False)
        if df.empty: return pd.DataFrame()
        
        # Ensure timezone-aware index
        if df.index.tz is None: df.index = df.index.tz_localize('UTC')
        
        df_est = df.tz_convert(US_EASTERN)
        # Filter to market hours
        df_market = df_est.between_time("09:30", "16:00")
        if df_market.empty:
            logger.log(f"   ⚠️ Yahoo returned data, but none in 9:30-16:00 window.")
        return df_market
    except Exception as e:
        logger.log(f"   ❌ Error fetching Yahoo data: {e}")
        return pd.DataFrame() # Return empty on error

# =========================================
#       CORE HARVESTING LOGIC (Refactored)
# =========================================
def run_harvest_logic(tickers_to_harvest, target_date, db_map, logger, harvest_mode="🚀 Full Day"):
    """
    Core logic for fetching data from APIs.
    This is now separate from the UI.
    """
    cst, xst = create_capital_session()
    need_capital = "Regular Session Only" not in harvest_mode or any(db_map[t]['strategy'] == 'CAPITAL_ONLY' for t in tickers_to_harvest if t in db_map)
    
    if need_capital and not cst:
        logger.log("❌ Capital.com Auth Failed. Cannot proceed.")
        return pd.DataFrame(), pd.DataFrame()

    all_data = []
    report_cards = [] 
    
    # Define time windows
    pm_start = US_EASTERN.localize(datetime.combine(target_date, dt_time(4, 0))).astimezone(UTC)
    pm_end   = US_EASTERN.localize(datetime.combine(target_date, dt_time(9, 30))).astimezone(UTC)
    reg_start = pm_end 
    reg_end   = US_EASTERN.localize(datetime.combine(target_date, dt_time(16, 0))).astimezone(UTC)

    for ticker in tickers_to_harvest:
        if ticker not in db_map:
            logger.log(f"⚠️ Skipping **{ticker}**: Not in inventory.")
            continue
            
        logger.log(f"Processing **{ticker}**...")
        rules = db_map[ticker]
        epic, strategy = rules['epic'], rules['strategy']
        
        df_pre, df_reg = pd.DataFrame(), pd.DataFrame()
        mode_str = strategy # Default

        # --- A. Pre-Market ---
        if "Regular Session Only" not in harvest_mode:
            if cst:
                time.sleep(0.2) # Small delay to be nice
                raw_pre = fetch_capital_data_range(epic, cst, xst, pm_start, pm_end, logger)
                df_pre = normalize_capital_df(raw_pre, ticker, "PRE")

        # --- B. Regular Session (with Fallback) ---
        if "Pre-Market Only" not in harvest_mode:
            if strategy == 'CAPITAL_ONLY':
                mode_str = "CAPITAL_ONLY"
                if cst:
                    time.sleep(0.2)
                    raw_reg = fetch_capital_data_range(epic, cst, xst, reg_start, reg_end, logger)
                    df_reg = normalize_capital_df(raw_reg, ticker, "REG")
            else: # HYBRID
                logger.log(f"   -> Primary Source: Yahoo Finance")
                raw_yahoo = fetch_yahoo_market_data(ticker, target_date, logger)
                
                if not raw_yahoo.empty:
                    logger.log(f"   -> Success (Yahoo): {len(raw_yahoo)} rows.")
                    df_reg = normalize_yahoo_df(raw_yahoo, ticker)
                    mode_str = "HYBRID (Yahoo)"
                else:
                    # --- FALLBACK ---
                    logger.log(f"   ⚠️ Yahoo failed. Trying Fallback: Capital.com ({epic})")
                    if cst: # Check if we have a Capital session
                        time.sleep(0.2)
                        raw_capital_fallback = fetch_capital_data_range(epic, cst, xst, reg_start, reg_end, logger)
                        
                        if not raw_capital_fallback.empty:
                            logger.log(f"   -> Success (Capital Fallback): {len(raw_capital_fallback)} rows.")
                            df_reg = normalize_capital_df(raw_capital_fallback, ticker, "REG") # Note: We label it 'REG'
                            mode_str = "HYBRID (Fallback)"
                        else:
                            logger.log(f"   ❌ Fallback failed. No regular session data for {ticker}.")
                            df_reg = pd.DataFrame() # Ensure it's an empty DF
                            mode_str = "HYBRID (Failed)"
                    else:
                        logger.log(f"   ❌ Fallback skipped (No Capital session).")
                        df_reg = pd.DataFrame()
                        mode_str = "HYBRID (Failed)"

        # --- C. Merge & Report ---
        dfs = [d for d in [df_pre, df_reg] if not d.empty]
        total_rows = 0
        if dfs:
            combined = pd.concat(dfs).sort_values('timestamp').drop_duplicates('timestamp', keep='last')
            all_data.append(combined)
            total_rows = len(combined)
        
        # --- 🛡️ PILLAR 2: QUALITY (Gap Detection) ---
        expected_pre = 330 # 5.5 hours * 60
        expected_reg = 390 # 6.5 hours * 60
        pre_rows, reg_rows = len(df_pre), len(df_reg)
        
        gaps = []
        status_icon = "✅ Complete"
        
        if harvest_mode in ["🚀 Full Day", "🌙 Pre-Market Only"]:
            if pre_rows < (expected_pre * 0.9):
                gaps.append("Pre")
        
        if harvest_mode in ["🚀 Full Day", "☀️ Regular Session Only"]:
            if reg_rows < (expected_reg * 0.9):
                gaps.append("Reg")

        if total_rows == 0:
            status_icon = "❌ Failed"
        elif gaps:
            status_icon = f"⚠️ Gappy ({', '.join(gaps)})"
        
        if "Fallback" in mode_str and status_icon == "✅ Complete":
             status_icon = "✅ (Fallback)"

        report_cards.append({"Ticker": ticker, "Mode": mode_str, "Pre": pre_rows, "Reg": reg_rows, "Total": total_rows, "Status": status_icon})

    if not all_data:
        return pd.DataFrame(), pd.DataFrame(report_cards)
        
    final_df = pd.concat(all_data).reset_index(drop=True)
    report_df = pd.DataFrame(report_cards)
    return final_df, report_df

# =========================================
#               UI SECTIONS
# =========================================

def render_harvester_ui(inventory_list, db_map):
    st.subheader("🌱 Data Harvester")
    
    # Initialize session state keys
    if 'harvest_report' not in st.session_state:
        st.session_state['harvest_report'] = None
    if 'harvested_data' not in st.session_state:
        st.session_state['harvested_data'] = None
    if 'harvest_target_date' not in st.session_state:
        st.session_state['harvest_target_date'] = datetime.now(US_EASTERN).date()
    
    c1, c2 = st.columns([1, 2])
    with c1:
        harvest_mode = st.radio("Harvest Mode", ["🚀 Full Day", "🌙 Pre-Market Only", "☀️ Regular Session Only"])
        target_date = st.date_input("Target Date", st.session_state['harvest_target_date'])
    with c2:
        st.write("**Select Symbols to Harvest**")
        selected_tickers = st.multiselect("Tickers", options=inventory_list, default=inventory_list[:2] if inventory_list else None, label_visibility="collapsed")
        st.caption(f"Selected: {len(selected_tickers)}")
        
        if st.button("Start Harvest", type="primary", disabled=(len(selected_tickers) == 0)):
            status_container = st.status("Harvesting Data...", expanded=True)
            logger = StreamlitLogger(status_container)
            
            final_df, report_df = run_harvest_logic(selected_tickers, target_date, db_map, logger, harvest_mode)
            
            status_container.update(label="Harvest Complete!", state="complete", expanded=False)
            
            st.session_state['harvest_report'] = report_df
            st.session_state['harvest_target_date'] = target_date 
            
            if not final_df.empty:
                st.session_state['harvested_data'] = final_df
            else:
                st.session_state['harvested_data'] = None
                st.warning("No data collected.")
            
            # --- Explicit Fallback Warning ---
            if not report_df.empty:
                fallback_tickers = report_df[report_df['Mode'].str.contains("Fallback")]['Ticker'].tolist()
                if fallback_tickers:
                    st.warning(f"**Fallback Alert:** {', '.join(fallback_tickers)} failed to fetch from Yahoo Finance and used Capital.com as a fallback. Volume data for these symbols may be inaccurate.", icon="📡")


    if st.session_state.get('harvest_report') is not None:
        st.divider()
        col_report, col_viz = st.columns([1, 1])
        
        report_df = st.session_state['harvest_report']
        final_df = st.session_state.get('harvested_data')
        
        target_date_obj = st.session_state.get('harvest_target_date')
        if not target_date_obj:
            target_date_obj = datetime.now(US_EASTERN).date() # Fallback
        
        with col_report:
            st.write("### 📋 Harvest Report Card")
            
            if final_df is not None:
                total_rows_collected = len(final_df)
                st.metric("Total Rows Collected", f"{total_rows_collected:,}")
            else:
                st.metric("Total Rows Collected", "0")

            st.dataframe(report_df, use_container_width=True)
            
            if final_df is not None:
                csv_backup = final_df.to_csv(index=False).encode('utf-8')
                st.download_button("💾 Download Backup CSV", csv_backup, f"backup_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
                
                btn_label = f"☁️ Commit Data for {target_date_obj}"
                if st.button(btn_label, type="primary"):
                    with st.spinner("Saving..."):
                        if save_data_to_turso(final_df):
                            st.success("Saved Successfully!"); st.balloons()
        with col_viz:
            if final_df is not None:
                st.write("### 👁️ Visual Check")
                t_sel = st.selectbox("Preview Ticker", final_df['symbol'].unique())
                if t_sel:
                    sub = final_df[final_df['symbol'] == t_sel]
                    chart = alt.Chart(sub).mark_line().encode(x='timestamp:T', y=alt.Y('close:Q', scale=alt.Scale(zero=False)), color='session:N').interactive()
                    st.altair_chart(chart, use_container_width=True)

def render_inventory_ui(db_map, inventory_list):
    st.subheader("📦 Inventory Manager")
    
    with st.container(border=True):
        st.write("### ➕ Add New Symbol")
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1: new_ticker = st.text_input("Ticker", placeholder="e.g. AAPL").upper()
        with c2: new_epic = st.text_input("Epic", placeholder="e.g. AAPL").upper()
        with c3: new_strat = st.selectbox("Strategy", ["HYBRID (Stock/ETF)", "CAPITAL_ONLY (Index/CFD)"], key="add_strat")
        if st.button("Save New Symbol", type="primary") and new_ticker:
            code = "CAPITAL_ONLY" if "CAPITAL" in new_strat else "HYBRID"
            epic_val = new_epic if new_epic else new_ticker
            if upsert_symbol_mapping(new_ticker, epic_val, code):
                st.success(f"Saved {new_ticker}"); time.sleep(0.5); st.rerun()

    with st.container(border=True):
        st.write("### ⚡ Edit Existing Symbol")
        if not inventory_list: st.info("No symbols in inventory yet.")
        else:
            STRAT_HYBRID = "HYBRID (Stock/ETF)"
            STRAT_CAPITAL = "CAPITAL_ONLY (Index/CFD)"
            STRAT_OPTIONS = [STRAT_HYBRID, STRAT_CAPITAL]
            
            # --- State initialization remains the same ---
            if 'edit_select' not in st.session_state:
                st.session_state.edit_select = "" 
            if 'edit_ticker_val' not in st.session_state:
                 st.session_state.edit_ticker_val = ""
            if 'edit_epic_val' not in st.session_state:
                st.session_state.edit_epic_val = ""
            if 'edit_strat_sel' not in st.session_state:
                st.session_state.edit_strat_sel = STRAT_HYBRID

            # --- NEW: Define the callback function BEFORE the button ---
            def handle_update():
                # 1. Read all values from session_state
                original_ticker = st.session_state.edit_select
                new_ticker_val = st.session_state.edit_ticker_val
                new_epic_val = st.session_state.edit_epic_val
                new_strategy_sel = st.session_state.edit_strat_sel
                
                code = "CAPITAL_ONLY" if "CAPITAL" in new_strategy_sel else "HYBRID"
                
                # 2. Perform DB logic
                if original_ticker and new_ticker_val and original_ticker != new_ticker_val:
                    st.info(f"Renaming {original_ticker} to {new_ticker_val}...")
                    delete_symbol_mapping(original_ticker)
                
                if new_ticker_val:
                    if upsert_symbol_mapping(new_ticker_val, new_epic_val, code):
                        st.success(f"Updated {new_ticker_val}")
                        
                        # 3. --- THIS IS THE FIX ---
                        # Set the state for the *next* run. This is safe
                        # because it runs inside the callback.
                        st.session_state.edit_select = ""
                        st.session_state.edit_ticker_val = "" 
                        st.session_state.edit_epic_val = "" 
                        st.session_state.edit_strat_sel = STRAT_HYBRID 
                    else:
                        st.error("Failed to update symbol.")
                else:
                    st.error("Ticker field cannot be empty.")

            # --- This section draws the top selectbox ---
            c_edit1, c_edit_spacer = st.columns([1.5, 2.5])
            with c_edit1: 
                st.selectbox("Select Ticker to Edit", 
                             options=[""] + inventory_list, 
                             key="edit_select") # No callback needed here
            
            # --- This declarative logic syncs the form to the selectbox ---
            current_selection = st.session_state.edit_select
            if current_selection != st.session_state.edit_ticker_val:
                if current_selection in db_map:
                    selected_data = db_map[current_selection]
                    st.session_state.edit_ticker_val = current_selection
                    st.session_state.edit_epic_val = selected_data['epic']
                    st.session_state.edit_strat_sel = STRAT_HYBRID if "HYBRID" in selected_data['strategy'] else STRAT_CAPITAL
                else:
                    st.session_state.edit_ticker_val = "" 
                    st.session_state.edit_epic_val = ""
                    st.session_state.edit_strat_sel = STRAT_HYBRID
            
            # --- This section draws the form fields ---
            c_edit_fields1, c_edit_fields2, c_edit_fields3, c_edit_fields4 = st.columns([1.5, 1.5, 1.5, 1])
            
            with c_edit_fields1:
                new_ticker_val = st.text_input("Ticker (Yahoo/PK)", key="edit_ticker_val")
            with c_edit_fields2: 
                new_epic_val = st.text_input("Epic (Capital)", key="edit_epic_val")
            with c_edit_fields3: 
                new_strategy_sel = st.selectbox("Strategy", STRAT_OPTIONS, key="edit_strat_sel")
            with c_edit_fields4:
                st.write(""); st.write("")
                
                # --- MODIFIED: The button now just calls the callback ---
                is_disabled = (st.session_state.edit_select == "")
                st.button("Update Symbol", 
                          disabled=is_disabled, 
                          on_click=handle_update) # Attach the callback here
                
                # All logic that was here is now in handle_update()
    
    # --- Rest of the function is unchanged ---
    st.write("### 📋 Current Inventory")
    if db_map:
        data = [{"Ticker": k, "Epic": v['epic'], "Strategy": v['strategy']} for k, v in db_map.items()]
        st.dataframe(pd.DataFrame(data), use_container_width=True)
        st.write("#### 🗑️ Delete Symbol")
        c_del1, c_del2 = st.columns([3, 1])
        with c_del1: d_t = st.selectbox("Select Symbol to Delete", [""] + inventory_list, key="del_select")
        with c_del2:
            st.write(""); st.write("")
            if st.button("Confirm Delete", type="primary", disabled=(not d_t)):
                delete_symbol_mapping(d_t); st.success(f"Deleted {d_t}"); time.sleep(0.5); st.rerun()

                
# --- Data Health Dashboard UI ---
def render_health_dashboard(inventory_list):
    st.subheader("🗓️ Data Health Dashboard")
    st.info("Check the completeness of your data library. Cells show the number of candles collected.")
    
    # --- Session Filter ---
    session_mode = st.radio(
        "Select Session to Inspect", 
        ["Full Day (Total)", "🌙 Pre-Market", "☀️ Regular Session"], 
        horizontal=True
    )
    
    today = datetime.now(US_EASTERN).date()
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("Start Date", today - timedelta(days=7))
    with c2:
        end_date = st.date_input("End Date", today)
    
    selected_tickers = st.multiselect("Select Symbols", inventory_list, default=inventory_list)
    
    if st.button("🔍 Generate Health Report", type="primary") and selected_tickers:
        
        # --- Map radio to filter ---
        if session_mode == "🌙 Pre-Market":
            session_filter = "PRE"
        elif session_mode == "☀️ Regular Session":
            session_filter = "REG"
        else:
            session_filter = "Total"
            
        with st.spinner(f"Querying {session_mode} data health..."):
            health_pivot_df = fetch_data_health_matrix(selected_tickers, start_date, end_date, session_filter)
            
            if not health_pivot_df.empty:
                # --- Dynamic Heatmap Logic ---
                def style_heatmap(val, mode="Total"):
                    if pd.isna(val):
                        return 'background-color: #262626' # Dark grey for NaN
                    
                    if mode == "Total":
                        if val > 700: return 'background-color: #285E28' # Dark Green (Full Day)
                        elif val > 330: return 'background-color: #5E5B28' # Dark Yellow (Full RTH + some PM)
                        elif val > 300: return 'background-color: #5E4228' # Dark Orange (Just PM)
                    elif mode == "PRE":
                        if val > 300: return 'background-color: #285E28' # Dark Green (Full PM)
                        elif val > 100: return 'background-color: #5E5B28' # Dark Yellow (Partial PM)
                    elif mode == "REG":
                        if val > 350: return 'background-color: #285E28' # Dark Green (Full RTH)
                        elif val > 100: return 'background-color: #5E5B28' # Dark Yellow (Partial RTH)
                    
                    return 'background-color: #5E2828' # Dark Red (Gappy/Failed)

                
                # Calculate dynamic height
                base_height = 40  # Base height for header
                row_height = 35   # Height per row
                dynamic_height = base_height + (row_height * len(health_pivot_df))

                st.dataframe(
                    health_pivot_df.style.apply(lambda x: x.map(lambda val: style_heatmap(val, mode=session_filter))).format("{:.0f}", na_rep=""), 
                    use_container_width=True,
                    height=dynamic_height
                )
            else:
                st.warning("No data found for the selected symbols and date range.")

# --- Main App ---
def main():
    init_db()
    with st.sidebar:
        st.title("🦁 Market Lion")
        # --- NEW Sidebar Order ---
        app_mode = st.selectbox("Select App Mode", [
            "⚙️ Inventory Manager",
            "🌱 Data Harvester", 
            "🗓️ Data Health Dashboard"
        ])
        st.divider()
    
    db_map = get_symbol_map_from_db()
    inventory_list = list(db_map.keys())

    if app_mode == "⚙️ Inventory Manager":
        render_inventory_ui(db_map, inventory_list)
    elif app_mode == "🌱 Data Harvester":
        render_harvester_ui(inventory_list, db_map)
    elif app_mode == "🗓️ Data Health Dashboard":
        render_health_dashboard(inventory_list)

if __name__ == "__main__":
    main()