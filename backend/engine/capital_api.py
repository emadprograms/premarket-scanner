import pandas as pd
import requests
from datetime import datetime, timedelta
import pytz
from backend.engine.infisical_manager import InfisicalManager

# Constants
CAPITAL_API_URL_BASE = "https://api-capital.backend-capital.com/api/v1"
BAHRAIN_TZ = pytz.timezone('Asia/Bahrain')
UTC = pytz.utc
US_EASTERN = pytz.timezone('US/Eastern')

def get_retry_session():
    """Simple requests session to mimic the user's helper."""
    s = requests.Session()
    return s

# Manual Singleton Cache for FastAPI/Non-Streamlit environments
_CAPITAL_SESSION_CACHE = {"cst": None, "xst": None, "expiry": None}

def create_capital_session_v2():
    """Creates a Capital.com session and caches tokens using Infisical."""
    global _CAPITAL_SESSION_CACHE
    
    # 1. Return cached session if valid (simple 10-min dummy expiry for now)
    if _CAPITAL_SESSION_CACHE["cst"] and _CAPITAL_SESSION_CACHE["xst"]:
        return _CAPITAL_SESSION_CACHE["cst"], _CAPITAL_SESSION_CACHE["xst"]

    print("📡 Infisical: Fetching Capital.com credentials...")
    mgr = InfisicalManager()
    if not mgr.is_connected:
        print("❌ Infisical: Not connected.")
        return None, None
        
    # Attempt variants (Prioritizing exact match from user dashboard)
    api_key = mgr.get_secret("capital_com_X_CAP_API_KEY")
    identifier = mgr.get_secret("capital_com_IDENTIFIER")
    password = mgr.get_secret("capital_com_PASSWORD")
    
    if not api_key or not identifier or not password:
        print(f"❌ AUTH DEBUG: Missing Keys. API_KEY={bool(api_key)}, ID={bool(identifier)}, PASS={bool(password)}")
        return None, None
        
    print(f"🚀 Capital: Attempting login for {identifier}...")
    session = get_retry_session()
    try:
        response = session.post(
            f"{CAPITAL_API_URL_BASE}/session", 
            headers={'X-CAP-API-KEY': api_key, 'Content-Type': 'application/json'}, 
            json={"identifier": identifier, "password": password}, 
            timeout=15
        )
        response.raise_for_status()
        
        cst = response.headers.get('CST')
        xst = response.headers.get('X-SECURITY-TOKEN')
        
        if cst and xst:
            print("✅ Capital: Session Established.")
            _CAPITAL_SESSION_CACHE["cst"] = cst
            _CAPITAL_SESSION_CACHE["xst"] = xst
            return cst, xst
        else:
            print("❌ Capital: Headers missing CST or X-SECURITY-TOKEN")
            return None, None
            
    except Exception as e:
        print(f"❌ Capital.com Session Failed: {e}")
        return None, None

def clear_capital_session():
    global _CAPITAL_SESSION_CACHE
    _CAPITAL_SESSION_CACHE = {"cst": None, "xst": None, "expiry": None}

def fetch_capital_data_range(epic: str, cst: str, xst: str, start_utc, end_utc, logger, resolution: str = "MINUTE") -> pd.DataFrame:
    """Fetches Capital.com data for a specific epic and UTC time window with custom resolution."""
    now_utc = datetime.now(UTC)
    
    # Capital.com Free API has lookback limits relative to granularity:
    # MINUTE: ~16h | HOUR: ~1 month | DAY: Years
    res_upper = resolution.upper()
    if res_upper == "MINUTE":
        limit_lookback = now_utc - timedelta(hours=16)
    elif res_upper == "MINUTE_5":
        limit_lookback = now_utc - timedelta(days=3) # ~864 bars
    elif res_upper == "MINUTE_15":
        limit_lookback = now_utc - timedelta(days=7) # ~672 bars
    elif res_upper == "MINUTE_30":
        limit_lookback = now_utc - timedelta(days=14) # ~672 bars
    elif res_upper == "HOUR":
        limit_lookback = now_utc - timedelta(days=31) # ~744 bars
    else: # DAY or others
        limit_lookback = now_utc - timedelta(days=365)
    
    if start_utc < limit_lookback:
        if logger: logger.log(f"   ⚠️ Start time clamped to {resolution} limit.")
        start_utc = limit_lookback + timedelta(minutes=1)
        
    if start_utc >= end_utc:
        return pd.DataFrame()
    
    price_params = {
        "resolution": resolution, 
        "max": 1000, 
        'from': start_utc.strftime('%Y-%m-%dT%H:%M:%S'), 
        'to': end_utc.strftime('%Y-%m-%dT%H:%M:%S')
    }
    
    session = get_retry_session()
    max_retries = 3
    import time
    
    for attempt in range(max_retries):
        try:
            response = session.get(
                f"{CAPITAL_API_URL_BASE}/prices/{epic}", 
                headers={'X-SECURITY-TOKEN': xst, 'CST': cst}, 
                params=price_params, 
                timeout=15
            )
            
            # SESSION SELF-HEALING: If we are unauthorized, clear the cache to force relogin
            if response.status_code == 401:
                if logger: logger.log(f"   ⚠️ 401 Unauthorized for {epic}. Clearing session cache.")
                clear_capital_session()
                return pd.DataFrame() # Caller should handle empty DF by checking auth again if needed

            response.raise_for_status()
            prices = response.json().get('prices', [])
            if not prices:
                return pd.DataFrame()
            
            extracted = [
                {
                    'SnapshotTime': p.get('snapshotTime'), 
                    'Open': p.get('openPrice', {}).get('bid'), 
                    'High': p.get('highPrice', {}).get('bid'), 
                    'Low': p.get('lowPrice', {}).get('bid'), 
                    'Close': p.get('closePrice', {}).get('bid'), 
                    'Volume': p.get('lastTradedVolume')
                } for p in prices
            ]
            df = pd.DataFrame(extracted)
            
            # Timezone Logic
            df['SnapshotTime'] = pd.to_datetime(df['SnapshotTime'])
            
            if df['SnapshotTime'].dt.tz is None:
                df['SnapshotTime'] = df['SnapshotTime'].dt.tz_localize(BAHRAIN_TZ)
            else:
                df['SnapshotTime'] = df['SnapshotTime'].dt.tz_convert(BAHRAIN_TZ)
            
            df['dt_utc'] = df['SnapshotTime'].dt.tz_convert(UTC)
            df['dt_eastern'] = df['SnapshotTime'].dt.tz_convert(US_EASTERN)
            df.rename(columns={'SnapshotTime': 'timestamp'}, inplace=True)
            return df

        except Exception as e:
            if attempt < max_retries - 1:
                if logger: logger.log(f"   🔄 Retry {attempt+1}/{max_retries} for {epic} due to: {e}")
                time.sleep(1)
                continue
            else:
                if logger: logger.log(f"   ❌ Final error fetching Capital data for {epic}: {e}")
                return pd.DataFrame()
