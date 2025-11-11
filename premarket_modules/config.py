import streamlit as st
from pytz import timezone
import logging

# --- Load Gemini API Keys ---
try:
    gemini_secrets = st.secrets.get("gemini", {})
    API_KEYS = gemini_secrets.get("api_keys", [])
    if not API_KEYS or not isinstance(API_KEYS, list) or len(API_KEYS) == 0:
        st.error("Error: Gemini API keys not found in st.secrets.")
        st.info("Please add `[gemini]` section with `api_keys = [...]` to your .streamlit/secrets.toml file.")
        st.stop()
except Exception as e:
    st.error(f"Failed to load Gemini secrets: {e}")
    API_KEYS = []

# --- Load Turso Database Configuration ---
try:
    turso_secrets = st.secrets.get("turso", {})
    TURSO_DB_URL = turso_secrets.get("db_url")
    TURSO_AUTH_TOKEN = turso_secrets.get("auth_token")

    if not TURSO_DB_URL or not TURSO_AUTH_TOKEN:
        st.error("Error: Turso DB URL or Auth Token not found in st.secrets.")
        st.info("Please add `[turso]` section with `db_url` and `auth_token` to your .streamlit/secrets.toml file.")
        st.stop()
    
    # --- Apply the HTTPS URL Fix ---
    # This forces the client to use HTTPS instead of WSS (WebSocket)
    TURSO_DB_URL_HTTPS = TURSO_DB_URL.replace("libsql://", "https://")

except Exception as e:
    st.error(f"Failed to load Turso secrets. App cannot connect to DB. Error: {e}")
    TURSO_DB_URL = None
    TURSO_AUTH_TOKEN = None
    TURSO_DB_URL_HTTPS = None

# --- API Configuration ---
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# --- Capital.com API ---
CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"

# --- Timezone & Market Hours ---
US_EASTERN = timezone('US/Eastern')
PREMARKET_START_HOUR = 4  # 4:00 AM ET
PREMARKET_END_HOUR = 9    # 9:00 AM ET
PREMARKET_END_MINUTE = 30 # 9:30 AM ET

# --- Watchlists ---
CORE_INTERMARKET_EPICS = [
    "SPY_SPX", "QQQ_NDX", "IWM_RUT", "DIA_DJI", # Indices
    "XLF", "XLE", "XLK", "XLI", "XLP", "XLU", "XLV", # Sectors
    "TLT_US_20Y", "UUP_DXY", "Gold_GLD", "USO_WTI" # Inter-market
]

# --- App Settings ---
LOOP_DELAY = 0.33 # Delay (in seconds) between API calls