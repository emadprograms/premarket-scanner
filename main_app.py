import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import altair as alt
from libsql_client import create_client_sync
from datetime import datetime, time as dt_time, timedelta
from pytz import timezone
import time
import json

# --- Configuration & Constants ---
st.set_page_config(page_title="Market Data Harvester", layout="wide")

CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"
US_EASTERN = timezone('US/Eastern')
BAHRAIN_TZ = timezone('Asia/Bahrain')
UTC = timezone('UTC')

# Schema Definition
SCHEMA_COLS = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'session']

# --- Turso Database Functions (Updated for libsql-client) ---

@st.cache_resource
def get_db_connection():
    """
    Helper function to create a database connection to Turso.
    Uses create_client_sync and forces HTTPS for stability.
    """
    try:
        if "turso" not in st.secrets:
            st.error("Missing 'turso' section in secrets.toml")
            return None

        url = st.secrets["turso"]["db_url"]
        token = st.secrets["turso"]["auth_token"]
        
        # --- FIX: Force HTTPS connection ---
        # This is more reliable than libsql:// or wss:// in Streamlit
        http_url = url.replace("libsql://", "https://")
        
        config = {
            "url": http_url,
            "auth_token": token
        }
        
        # --- FIX: Use create_client_sync ---
        client = create_client_sync(**config)
        return client
        
    except Exception as e:
        st.error(f"Failed to create Turso client: {e}")
        return None

def init_db():
    """Creates the symbol_map table if it doesn't exist and seeds default values."""
    client = get_db_connection()
    if not client:
        return

    try:
        # Create Table
        client.execute("""
            CREATE TABLE IF NOT EXISTS symbol_map (
                user_ticker TEXT PRIMARY KEY,
                capital_epic TEXT NOT NULL,
                source_strategy TEXT DEFAULT 'HYBRID' 
            )
        """)
        
        # Check if empty
        res = client.execute("SELECT count(*) FROM symbol_map")
        count = res.rows[0][0] if res.rows else 0
        
        if count == 0:
            # Seed Defaults
            seed_data = [
                ("DIA", "US30", "CAPITAL_ONLY"),
                ("QQQ", "US100", "CAPITAL_ONLY"),
                ("SPY", "US500", "CAPITAL_ONLY"),
                ("IWM", "US2000", "CAPITAL_ONLY"),
                ("NDQ", "US100", "CAPITAL_ONLY")
            ]
            
            # Batch insert for speed
            for ticker, epic, strategy in seed_data:
                client.execute(
                    "INSERT INTO symbol_map (user_ticker, capital_epic, source_strategy) VALUES (?, ?, ?)", 
                    [ticker, epic, strategy]
                )
            
            st.toast("Database initialized with default maps.", icon="💾")
    except Exception as e:
        st.error(f"DB Init Error: {e}")

def get_symbol_map_from_db():
    """Fetches the mapping dictionary from Turso."""
    client = get_db_connection()
    if not client: 
        return {}
    
    try:
        res = client.execute("SELECT user_ticker, capital_epic, source_strategy FROM symbol_map")
        # Row format is typically tuple-like in the sync client: (ticker, epic, strat)
        return {row[0]: {'epic': row[1], 'strategy': row[2]} for row in res.rows}
    except Exception as e:
        st.error(f"Error fetching symbol map: {e}")
        return {}

def upsert_symbol_mapping(ticker, epic, strategy):
    """Adds or updates a mapping in Turso."""
    client = get_db_connection()
    if client:
        try:
            client.execute(
                "INSERT INTO symbol_map (user_ticker, capital_epic, source_strategy) VALUES (?, ?, ?) ON CONFLICT(user_ticker) DO UPDATE SET capital_epic=excluded.capital_epic, source_strategy=excluded.source_strategy",
                [ticker, epic, strategy]
            )
        except Exception as e:
            st.error(f"Error saving mapping: {e}")

# --- Helper Class for Logging to UI ---
class StreamlitLogger:
    def __init__(self, container):
        self.container = container

    def log(self, message):
        self.container.write(f"🔹 {message}")
        print(message) 

# --- Normalization Functions ---
def normalize_capital_df(df: pd.DataFrame, symbol: str, session_label: str) -> pd.DataFrame:
    """Normalizes Capital.com data to target schema."""
    if df.empty:
        return pd.DataFrame(columns=SCHEMA_COLS)
    
    df_norm = df.copy()
    df_norm.rename(columns={
        'SnapshotTime': 'timestamp', 
        'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'
    }, inplace=True)
    
    df_norm['symbol'] = symbol 
    df_norm['session'] = session_label
    return df_norm[SCHEMA_COLS]

def normalize_yahoo_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalizes Yahoo Finance data to target schema."""
    if df.empty:
        return pd.DataFrame(columns=SCHEMA_COLS)

    df_norm = df.copy()
    if isinstance(df_norm.columns, pd.MultiIndex):
        df_norm.columns = df_norm.columns.get_level_values(0)
    df_norm.reset_index(inplace=True)
    df_norm.rename(columns={
        'Datetime': 'timestamp', 
        'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'
    }, inplace=True)
    
    if df_norm['timestamp'].dt.tz is not None:
        df_norm['timestamp'] = df_norm['timestamp'].dt.tz_convert('UTC')
    else:
        df_norm['timestamp'] = df_norm['timestamp'].dt.tz_localize('US/Eastern').dt.tz_convert('UTC')

    df_norm['symbol'] = symbol
    df_norm['session'] = 'REG'
    df_norm.columns = [c.lower() for c in df_norm.columns]
    
    return df_norm[SCHEMA_COLS]

# --- Capital.com API Functions (Generic) ---
@st.cache_resource(ttl=600)
def create_capital_session():
    if "capital_com" not in st.secrets:
        st.error("Missing 'capital_com' in secrets.")
        return None, None

    secrets = st.secrets["capital_com"]
    try:
        response = requests.post(
            f"{CAPITAL_API_URL_BASE}/session", 
            headers={'X-CAP-API-KEY': secrets["X_CAP_API_KEY"], 'Content-Type': 'application/json'}, 
            json={"identifier": secrets["identifier"], "password": secrets["password"]}, 
            timeout=10
        )
        response.raise_for_status()
        return response.headers.get('CST'), response.headers.get('X-SECURITY-TOKEN')
    except Exception as e:
        st.error(f"Auth Failed: {e}")
        return None, None

def fetch_capital_data_range(epic: str, cst: str, xst: str, start_utc, end_utc, logger) -> pd.DataFrame:
    """Generic fetcher for Capital.com within a specific UTC window."""
    
    # Safety: Check 16-hour rolling limit
    now_utc = datetime.now(UTC)
    limit_16h_ago = now_utc - timedelta(hours=16)
    
    if start_utc < limit_16h_ago:
        logger.log(f"   ⚠️ Start time {start_utc.strftime('%H:%M')} is >16h old. Clamping.")
        start_utc = limit_16h_ago + timedelta(minutes=1)

    if start_utc >= end_utc:
        logger.log("   ❌ Time window expired (older than 16h).")
        return pd.DataFrame()

    if end_utc > now_utc:
        end_utc = now_utc

    price_params = {
        "resolution": "MINUTE", 
        'from': start_utc.strftime('%Y-%m-%dT%H:%M:%S'), 
        'to': end_utc.strftime('%Y-%m-%dT%H:%M:%S')
    }
    
    try:
        response = requests.get(f"{CAPITAL_API_URL_BASE}/prices/{epic}", headers={'X-SECURITY-TOKEN': xst, 'CST': cst}, params=price_params, timeout=10)
        response.raise_for_status()
        prices = response.json().get('prices', [])
        
        if not prices: return pd.DataFrame()

        extracted = [{
            'SnapshotTime': p.get('snapshotTime'),
            'Open': p.get('openPrice', {}).get('bid'),
            'High': p.get('highPrice', {}).get('bid'),
            'Low': p.get('lowPrice', {}).get('bid'),
            'Close': p.get('closePrice', {}).get('bid'),
            'Volume': p.get('lastTradedVolume')
        } for p in prices]
            
        df = pd.DataFrame(extracted)
        
        # Correct Bahrain Time to UTC
        df['SnapshotTime'] = pd.to_datetime(df['SnapshotTime'])
        if df['SnapshotTime'].dt.tz is None:
             df['SnapshotTime'] = df['SnapshotTime'].dt.tz_localize(BAHRAIN_TZ)
        else:
             df['SnapshotTime'] = df['SnapshotTime'].dt.tz_convert(BAHRAIN_TZ)
             
        df['SnapshotTime'] = df['SnapshotTime'].dt.tz_convert(UTC)
        return df

    except Exception as e:
        logger.log(f"   ❌ Error fetching Capital data for {epic}: {e}")
        return pd.DataFrame()

def fetch_yahoo_market_data(ticker: str, target_date_et, logger) -> pd.DataFrame:
    """Fetches 1-minute market data from Yahoo."""
    try:
        start = target_date_et
        end = start + pd.Timedelta(days=1)
        df = yf.download(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), interval="1m", progress=False)
        
        if df.empty: return pd.DataFrame()
        
        if df.index.tz is None: df.index = df.index.tz_localize('UTC')
        
        df_est = df.tz_convert(US_EASTERN)
        return df_est.between_time("09:30", "16:00")
    except Exception as e:
        logger.log(f"   ❌ Error fetching Yahoo data for {ticker}: {e}")
        return pd.DataFrame()

# --- Main App UI ---
def main():
    init_db() # Ensure DB is ready
    st.title("🦁 Market Data Harvester (Turso Edition)")

    if 'harvested_data' not in st.session_state:
        st.session_state['harvested_data'] = None

    # --- Sidebar ---
    with st.sidebar:
        st.header("Settings")
        harvest_mode = st.radio("Harvest Mode", ["🚀 Full Day", "🌙 Pre-Market Only", "☀️ Regular Session Only"])
        target_date = st.date_input("Select Date", datetime.now(US_EASTERN))
        
        # Ticker Input
        default_tickers = "NVDA, TSLA, DIA, QQQ"
        ticker_input = st.text_area("Tickers", default_tickers)
        tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
        
        # Symbol Mapping Management
        with st.expander("⚙️ Symbol Map (Turso)"):
            db_map = get_symbol_map_from_db()
            if db_map:
                # Convert to DataFrame for display
                map_display = []
                for k, v in db_map.items():
                    map_display.append({"Ticker": k, "Epic": v['epic'], "Strategy": v['strategy']})
                st.dataframe(pd.DataFrame(map_display), use_container_width=True, hide_index=True)
            else:
                st.warning("No mappings found or DB error.")
            
            # Add New Mapping
            st.caption("Add/Update Mapping")
            c1, c2, c3 = st.columns(3)
            new_ticker = c1.text_input("Ticker", "DIA").upper()
            new_epic = c2.text_input("Epic", "US30").upper()
            new_strat = c3.selectbox("Strategy", ["HYBRID", "CAPITAL_ONLY"], index=1)
            if st.button("Save Mapping"):
                upsert_symbol_mapping(new_ticker, new_epic, new_strat)
                st.toast(f"Saved {new_ticker} -> {new_epic}")
                time.sleep(1)
                st.rerun()

        run_btn = st.button("Start Harvest", type="primary")
        download_placeholder = st.empty()

    # --- Execution Logic ---
    if run_btn:
        status_container = st.status("Harvesting...", expanded=True)
        logger = StreamlitLogger(status_container)
        
        # 1. Auth Capital.com (Always needed for Indices now)
        cst, xst = create_capital_session()
        if not cst:
            st.stop()
        
        all_data = []
        progress_bar = st.progress(0)
        
        # Define Time Windows (UTC)
        pm_start = US_EASTERN.localize(datetime.combine(target_date, dt_time(4, 0))).astimezone(UTC)
        pm_end   = US_EASTERN.localize(datetime.combine(target_date, dt_time(9, 30))).astimezone(UTC)
        reg_start = pm_end # 9:30 ET
        reg_end   = US_EASTERN.localize(datetime.combine(target_date, dt_time(16, 0))).astimezone(UTC)

        for i, ticker in enumerate(tickers):
            logger.log(f"Processing **{ticker}**...")
            
            # Check Map
            mapping = db_map.get(ticker, {'epic': ticker, 'strategy': 'HYBRID'})
            epic = mapping['epic']
            strategy = mapping['strategy']
            
            if strategy == 'CAPITAL_ONLY':
                logger.log(f"   ℹ️ Strategy: **CAPITAL_ONLY** (Using {epic})")
            else:
                logger.log(f"   ℹ️ Strategy: **HYBRID** (Yahoo for Regular)")

            df_pre, df_reg = pd.DataFrame(), pd.DataFrame()

            # --- A. Pre-Market (Always Capital) ---
            if "Regular Session Only" not in harvest_mode:
                logger.log(f"   🌙 Fetching Pre-Market ({epic})...")
                raw_pre = fetch_capital_data_range(epic, cst, xst, pm_start, pm_end, logger)
                df_pre = normalize_capital_df(raw_pre, ticker, "PRE")
                logger.log(f"      ✅ Rows: {len(df_pre)}")

            # --- B. Regular Session ---
            if "Pre-Market Only" not in harvest_mode:
                logger.log(f"   ☀️ Fetching Regular Session...")
                
                if strategy == 'CAPITAL_ONLY':
                    # Fetch Regular from Capital
                    raw_reg = fetch_capital_data_range(epic, cst, xst, reg_start, reg_end, logger)
                    df_reg = normalize_capital_df(raw_reg, ticker, "REG")
                else:
                    # Fetch Regular from Yahoo
                    raw_reg = fetch_yahoo_market_data(ticker, target_date, logger)
                    df_reg = normalize_yahoo_df(raw_reg, ticker)
                
                logger.log(f"      ✅ Rows: {len(df_reg)}")

            # --- C. Merge ---
            dfs = [d for d in [df_pre, df_reg] if not d.empty]
            if dfs:
                combined = pd.concat(dfs).sort_values('timestamp').drop_duplicates('timestamp', keep='last')
                all_data.append(combined)
            
            progress_bar.progress((i + 1) / len(tickers))

        status_container.update(label="Harvest Complete!", state="complete", expanded=False)
        
        if all_data:
            final_df = pd.concat(all_data).reset_index(drop=True)
            st.session_state['harvested_data'] = final_df
            st.success(f"Collected {len(final_df)} rows.")
        else:
            st.warning("No data collected.")

    # --- Display ---
    if st.session_state['harvested_data'] is not None:
        final_df = st.session_state['harvested_data']
        
        with download_placeholder.container():
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download CSV", csv, "market_data.csv", "text/csv")

        tab1, tab2 = st.tabs(["Visual Check", "Data Table"])
        
        with tab1:
            t_list = final_df['symbol'].unique()
            sel_t = st.selectbox("Select Ticker", t_list)
            sub_df = final_df[final_df['symbol'] == sel_t]
            
            chart = alt.Chart(sub_df).mark_line().encode(
                x='timestamp:T',
                y=alt.Y('close:Q', scale=alt.Scale(zero=False)),
                color='session:N',
                tooltip=['timestamp', 'close', 'volume']
            ).interactive()
            st.altair_chart(chart, use_container_width=True)
        
        with tab2:
            st.dataframe(final_df, use_container_width=True)

if __name__ == "__main__":
    main()