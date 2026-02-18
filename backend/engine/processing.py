import pandas as pd
import pytz
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import yfinance as yf
from backend.engine.time_utils import US_EASTERN, MARKET_OPEN_TIME, to_et, to_utc, now_et, get_staleness_score
from backend.engine.utils import AppLogger

# --- DB FETCHING UTILITIES ---

from typing import Tuple, Optional, Union

def get_latest_price_details(client, ticker: str, cutoff_str: str, logger: AppLogger) -> Tuple[Optional[float], Optional[str]]:
    query = "SELECT close, timestamp FROM market_data WHERE symbol = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
    try:
        rs = client.execute(query, [ticker, cutoff_str])
        if rs.rows:
            return rs.rows[0][0], rs.rows[0][1]
        return None, None
    except Exception as e:
        logger.log(f"DB Read Error {ticker}: {e}")
        return None, None

def get_session_bars_from_db(client, epic: str, benchmark_date: str, cutoff_str: str, logger: AppLogger, premarket_only: bool = True) -> Optional[pd.DataFrame]:
    try:
        # We need High/Low/Close for Impact logic. Volume is optional but good to have.
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
        
        # Standardize to UTC aware
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize(pytz.utc)
        
        # FIX: Database timestamps are UTC.
        # We must localize to UTC then CONVERT to Eastern.
        df['dt_eastern'] = df['timestamp'].apply(lambda x: to_et(x))
        
        # Filter for Pre-Market (04:00 - 09:30 ET) - OPTIONAL
        if premarket_only:
             time_eastern = df['dt_eastern'].dt.time
             df = df[time_eastern < MARKET_OPEN_TIME].copy()

        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['close'], inplace=True)
        
        # Normalize columns for the Engine
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
        df['source'] = 'Turso DB'
        return df.reset_index(drop=True)
    except Exception as e:
        logger.log(f"Data Error ({epic}): {e}")
        return None

def get_previous_session_stats(client, ticker: str, current_date_str: str, logger: AppLogger) -> dict:
    """
    Fetches Yesterday's High, Low, and Close for context.
    """
    try:
        # Find the latest date BEFORE the current analysis date
        date_query = "SELECT DISTINCT date(timestamp) as d FROM market_data WHERE symbol = ? AND date(timestamp) < ? ORDER BY d DESC LIMIT 1"
        rs_date = client.execute(date_query, [ticker, current_date_str])
        
        if not rs_date.rows:
            return {"yesterday_close": 0, "yesterday_high": 0, "yesterday_low": 0}
            
        prev_date = rs_date.rows[0][0]
        
        # Get Stats for that date
        stats_query = """
            SELECT MAX(high), MIN(low), 
                   (SELECT close FROM market_data WHERE symbol = ? AND date(timestamp) = ? ORDER BY timestamp DESC LIMIT 1)
            FROM market_data 
            WHERE symbol = ? AND date(timestamp) = ?
        """
        rs = client.execute(stats_query, [ticker, prev_date, ticker, prev_date])
        
        if rs.rows:
            r = rs.rows[0]
            return {
                "yesterday_high": r[0] if r[0] else 0,
                "yesterday_low": r[1] if r[1] else 0,
                "yesterday_close": r[2] if r[2] else 0,
                "date": prev_date
            }
        return {"yesterday_close": 0, "yesterday_high": 0, "yesterday_low": 0}
    except Exception:
        return {"yesterday_close": 0, "yesterday_high": 0, "yesterday_low": 0}

from backend.engine.capital_api import create_capital_session_v2, fetch_capital_data_range

# --- DATA SOURCE ROUTING ---

def ticker_to_epic(ticker: str, client=None, logger=None) -> str:
    """
    Maps database tickers to Capital.com Epics.
    Priority: 1. Explicit Map, 2. DB Lookup, 3. Raw Ticker.
    """
    normalized = ticker.upper().strip()
    
    # 1. EXPLICIT MAPPING (Based on database symbols)
    EXPLICIT_MAP = {
        "BTCUSDT": "BTCUSD",
        "CL=F": "OIL_CRUDE",
        "EURUSDT": "EURUSD",
        "PAXGUSDT": "GOLD",
        "QQQ": "US100",    # CHANGED: Use US100 (Nasdaq CFD) for 24/5 Live Data
        "SPY": "US500",    # CHANGED: Use US500 (S&P CFD) for 24/5 Live Data
        "^VIX": "VIX",
        "NDAQ": "US100",
        # Major Indices
        "DIA": "US30",
        "IWM": "RTY",    # CHANGED: Use RTY (Russell 2000 CFD) for 24/5 Live Data
        "US30": "US30",
        "RTY": "RTY",
        
        # Sector ETFs (Direct Mapping)
        "XLC": "XLCP", # Proxy: UCITS Version (No US ETF)
        "XLF": "XLF",
        "XLI": "XLI",
        "XLP": "XLP",
        "XLU": "XLU",
        "XLV": "XLV",
        "XLE": "XLEP", # Energy Proxy
        "XLK": "XLK",
        "XLY": "XLYP", # Cons Discretionary Proxy
        "XLB": "XLB",
        "SMH": "SOXX", # Proxy (SMH not on Cap, SOXX is)
        "TLT": "TLT",
        "UUP": "DXY"   # Proxy: US Dollar Index
    }

    if normalized in EXPLICIT_MAP:
        return EXPLICIT_MAP[normalized]
    
    # 2. DB LOOKUP
    if client:
        try:
            # Attempt to find the Epic mapping from Turso symbol_map table
            rs = client.execute("SELECT capital_epic FROM symbol_map WHERE user_ticker = ?", [normalized])
            if rs.rows and rs.rows[0][0]:
                return rs.rows[0][0]
        except Exception:
            pass
            
    # 3. FINAL DEFAULT
    return normalized

def get_live_bars_from_capital(ticker: str, client=None, days: int = 5, logger: AppLogger = None, resolution: str = "MINUTE_5") -> Optional[pd.DataFrame]:
    """Fetches data from Capital.com for Live Mode."""
    cst, xst = create_capital_session_v2()
    if not cst or not xst:
        if logger: logger.log("   ❌ Capital.com Authentication Failed.")
        return None
        
    epic = ticker_to_epic(ticker, client=client, logger=logger)
    
    # Capital.com lookback depends on resolution.
    now_utc = datetime.now(pytz.utc)
    start_utc = now_utc - timedelta(days=days)
    
    df = fetch_capital_data_range(epic, cst, xst, start_utc, now_utc, logger, resolution=resolution)
    if df.empty:
        return None
        
    # Standardize columns for the engine (Title Case required for Analysis)
    # Extraction keys are already Title Case, so we just ensure consistency.
    # No rename needed if 'Open' is already 'Open'.
    
    # FIX: Rename SnapshotTime to timestamp (lowercase) for consistency with DB and Charting
    if 'SnapshotTime' in df.columns:
        df.rename(columns={'SnapshotTime': 'timestamp'}, inplace=True)
        
    df['source'] = 'Capital.com'
    return df

def get_live_bars_from_yahoo(ticker: str, days: int = 5, resolution: str = "MINUTE_5", logger: AppLogger = None) -> Optional[pd.DataFrame]:
    """Fallback: Fetches data from Yahoo Finance."""
    try:
        # Map resolution to YF interval
        interval = "5m" if resolution == "MINUTE_5" else "1m" if resolution == "MINUTE_1" else "1h"
        
        # YFinance tickers for indices might differ (e.g. ^GSPC for SPY? No SPY is SPY).
        # VIX is ^VIX. 
        yf_ticker = ticker
        if ticker == "BTCUSDT": yf_ticker = "BTC-USD"
        elif ticker == "EURUSDT": yf_ticker = "EURUSD=X"
        elif ticker == "CL=F": yf_ticker = "CL=F"
        
        # Fetch data
        # Map requested days to valid YF period (1d, 5d, 1mo, etc.)
        # User requested 5d fallback for periods like 2.9d
        yf_period = "1d" if days <= 1 else "5d"
        
        # prepost=True is CRITICAL for early morning sector data (XLF, etc.)
        df = yf.download(yf_ticker, period=yf_period, interval=interval, progress=False, ignore_tz=False, prepost=True)
        
        if df.empty:
            if logger: logger.log(f"   ⚠️ Yahoo Finance: No data for {yf_ticker}")
            return None
            
        # Flatten MultiIndex columns if present (yfinance >= 0.2.0)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Reset index to get timestamp column
        df.reset_index(inplace=True)
        
        # Renaissance of Column Names
        # YF gives: Date/Datetime, Open, High, Low, Close, Adj Close, Volume
        rename_map = {
            'Datetime': 'timestamp', 
            'Date': 'timestamp',
            'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'
        }
        df.rename(columns=rename_map, inplace=True)
        
        # Ensure timestamp is UTC
        if 'timestamp' not in df.columns:
            # Should not happen with reset_index but just in case
            return None
            
        if df['timestamp'].dt.tz is None:
             # YF usually returns localized to exchange time (often ET) or UTC depending on params.
             # If naive, assume ET for US stocks? Or UTC? 
             # Safe bet: Localize to UTC if we can, or assume it's roughly correct.
             # Actually YF 'Datetime' is usually timezone-aware if interval < 1d.
             df['timestamp'] = df['timestamp'].dt.tz_localize('UTC') # Assumption
        else:
             df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')

        df['source'] = 'Yahoo Finance'
        
        # ENSURE UNIQUE COLUMNS: Sometimes YF returns duplicate names after MultiIndex flattening
        df = df.loc[:, ~df.columns.duplicated()].copy()
        
        return df
        
    except Exception as e:
        if logger: logger.log(f"   ❌ Yahoo Fallback Error ({ticker}): {e}")
        return None

def get_historical_bars_for_chart(client, ticker: str, cutoff_str: str, days: int = 5, mode: str = "Simulation", logger: AppLogger = None) -> Optional[pd.DataFrame]:
    """
    Fetches multi-day price history.
    Simulation -> Turso DB
    Live -> Capital.com
    Returns: DataFrame with LOWERCASE columns ['open', 'close', ...] and 'timestamp'
    """
    if mode == "Live":
        df = get_live_bars_from_capital(ticker, client=client, days=days, logger=logger)
        if df is not None:
             # Normalize Capital (Title) to Chart (Lower)
             df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
             df['source'] = 'Capital.com'
        return df
    
    # --- SIMULATION (DB) LOGIC ---
    try:
        # Calculate start date
        clean_cutoff = cutoff_str.replace("Z", "").replace("T", " ")
        try:
             dt_cutoff = datetime.fromisoformat(clean_cutoff)
        except:
             # Fallback if isoformat fails on space
             dt_cutoff = datetime.strptime(clean_cutoff, "%Y-%m-%d %H:%M:%S")

        dt_start = dt_cutoff - timedelta(days=days)
        start_str = dt_start.strftime("%Y-%m-%d %H:%M:%S")
        
        query = """
            SELECT timestamp, open, high, low, close, volume 
            FROM market_data 
            WHERE symbol = ? AND timestamp >= ? AND timestamp <= ? 
            ORDER BY timestamp ASC
        """
        
        args = [ticker, start_str, cutoff_str]
        rs = client.execute(query, args)
        
        if not rs.rows:
            return None
            
        df = pd.DataFrame(rs.rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['source'] = 'Turso DB'
        
        # Convert timestamp to datetime objects for Pandas
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # If timestamps are naive, assume they are UTC (as per rest of app logic)
        if df['timestamp'].dt.tz is None:
             df['timestamp'] = df['timestamp'].dt.tz_localize(pytz.utc)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
             df[col] = pd.to_numeric(df[col], errors='coerce')
             
        return df

    except Exception as e:
        if logger: logger.log(f"Chart History DB Error ({ticker}): {e}")
        return None

def get_session_bars_routed(client, epic: str, benchmark_date_str: str, cutoff_str: str, mode: str = "Simulation", logger: AppLogger = None, db_fallback: bool = False, premarket_only: bool = True, days: int = 3, resolution: str = "MINUTE_5") -> Tuple[Optional[pd.DataFrame], Optional[float]]:
    """
    Routes data fetching for the Analysis Engine.
    Returns: (DataFrame with TITLE CASE columns, staleness_score_minutes or None)
    """
    df = None
    staleness = None

    if mode == "Live":
        # Strategy: Try Capital -> Fail? Try Yahoo -> Fail? Try DB Fallback if enabled -> Fail? Give Up.
        
        # 1. Capital.com
        df = get_live_bars_from_capital(epic, client=client, days=days, logger=logger, resolution=resolution)
        
        # STALENESS CHECK: If Capital returns "Yesterday's Close" (stale) during Pre-Market, TREAT AS EMPTY.
        if df is not None and not df.empty:
            last_ts = df['timestamp'].iloc[-1]
            age_mins = get_staleness_score(last_ts)
            
            # If data is > 60 mins old, it's stale (likely yesterday's data)
            if age_mins > 60:
                if logger: logger.warn(f"   ⚠️ Capital.com data for {epic} is STALE ({int(age_mins)}m old). Discarding...")
                df = None

        # 2. Yahoo Finance Fallback
        if df is None or df.empty:
             if logger: logger.warn(f"   ⚠️ Capital.com missing {epic}. Attempting Yahoo Finance Fallback...")
             # In macro.py, we pass 't' (e.g. "SPY") as epic. So epic IS the ticker.
             df = get_live_bars_from_yahoo(epic, days=days, resolution=resolution, logger=logger)
             
        # 3. DB Fallback (if requested and Live/Yahoo failed)
        if (df is None or df.empty) and db_fallback:
             if logger: logger.warn(f"   ⚠️ Live Fetch Failed for {epic}. Attempting DB Fallback...")
             df = get_session_bars_from_db(client, epic, benchmark_date_str, cutoff_str, logger, premarket_only=premarket_only)
        
        if df is not None and not df.empty:
            # ENSURE UNIQUE COLUMNS: Prevents "cannot convert series to float" errors
            df = df.loc[:, ~df.columns.duplicated()].copy()
            
            last_ts = df['timestamp'].iloc[-1]
            staleness = get_staleness_score(last_ts)
            
        return df, staleness
    else:
        df = get_session_bars_from_db(client, epic, benchmark_date_str, cutoff_str, logger, premarket_only=premarket_only)
        return df, None

def detect_impact_levels(df, session_start_dt=None):
    """
    Identifies Levels based on IMPACT (Depth & Duration).
    1. Find every pivot.
    2. Calculate Score = (How far price went away) * log(How long it stayed away).
    3. Rank by Score.
    4. De-duplicate (remove nearby weaker signals).
    """
    if df.empty: return []

    avg_price = df['Close'].mean()

    # Define "Nearby" for de-duplication (e.g. 0.15% of price)
    proximity_threshold = max(0.10, avg_price * 0.0015)

    # 1. Find ALL Pivots (Local Extremes)
    # We use a small window (3) because we want to catch the exact moment of rejection
    df['is_peak'] = df['High'][(df['High'].shift(1) <= df['High']) & (df['High'].shift(-1) < df['High'])]
    df['is_valley'] = df['Low'][(df['Low'].shift(1) >= df['Low']) & (df['Low'].shift(-1) > df['Low'])]

    potential_peaks = df[df['is_peak'].notna()]
    potential_valleys = df[df['is_valley'].notna()]

    scored_levels = []

    # 2. Score Every Pivot Individually

    # --- RESISTANCE SCORING ---
    for idx, row in potential_peaks.iterrows():
        pivot_price = row['High']
        pivot_time = idx # Index in df (RangeIndex in processing.py usually, need to check access)
        
        # NOTE: df in processing.py has RangeIndex. 
        # But wait, logic below uses df.loc[idx, 'timestamp'].
        # In Engine Lab, df has DateTimeIndex so idx IS timestamp.
        # Here df has RangeIndex, so idx is int.
        # We need to adapt logic to handle RangeIndex OR ensure we access timestamps correctly.

        # Look forward
        # If RangeIndex, loc_idx is just idx? 
        # df.index.get_loc(pivot_time) -> if pivot_time is int index, this works.
        
        # Adaptation: processing.py df is RangeIndex.
        # So pivot_time is an integer.
        
        if isinstance(df.index, pd.RangeIndex):
             loc_idx = idx
        else:
             loc_idx = df.index.get_loc(pivot_time)

        future_df = df.iloc[loc_idx+1:]

        if future_df.empty: continue

        # Did price ever return to this level?
        # Return condition: Price crosses ABOVE the pivot again
        recovery_mask = future_df['High'] >= pivot_price

        if recovery_mask.any():
            recovery_time = recovery_mask.idxmax() # This will be an Integer Index if RangeIndex
            interval_df = future_df.loc[:recovery_time]
            # Max Adverse Excursion
            lowest_point = interval_df['Low'].min()
            magnitude = pivot_price - lowest_point
            
            # Duration Calculation Adaptation
            if 'timestamp' in df.columns:
                 t1 = df.loc[idx]['timestamp'] # idx is integer
                 t2 = df.loc[recovery_time]['timestamp']
                 duration_mins = (t2 - t1).total_seconds() / 60
            else:
                 # Fallback if using DateTimeIndex (Engine Lab style)
                 duration_mins = (recovery_time - pivot_time).total_seconds() / 60
        else:
            # Price NEVER returned
            lowest_point = future_df['Low'].min()
            magnitude = pivot_price - lowest_point
            # Duration is rest of session
            if 'timestamp' in df.columns:
                 t_start = df.loc[idx]['timestamp']
                 t_end = df.iloc[-1]['timestamp']
                 duration_mins = (t_end - t_start).total_seconds() / 60
            else:
                 duration_mins = len(future_df) # Rough estimate or calc from index

        # SCORE CALCULATION (NORMALIZED)
        magnitude_pct = (magnitude / pivot_price) * 100
        score = magnitude_pct * np.log1p(duration_mins)

        # LOWERED THRESHOLD TO 0.00015 (0.015%) to catch more levels
        if magnitude > (avg_price * 0.00015): 
            scored_levels.append({
                "type": "RESISTANCE",
                "level": pivot_price,
                "score": score,
                "magnitude": magnitude,
                "duration": duration_mins,
                "time": pivot_time
            })

    # --- SUPPORT SCORING ---
    for idx, row in potential_valleys.iterrows():
        pivot_price = row['Low']
        
        if isinstance(df.index, pd.RangeIndex):
             loc_idx = idx
        else:
             loc_idx = df.index.get_loc(idx)

        future_df = df.iloc[loc_idx+1:]
        if future_df.empty: continue

        recovery_mask = future_df['Low'] <= pivot_price

        if recovery_mask.any():
            recovery_time = recovery_mask.idxmax()
            interval_df = future_df.loc[:recovery_time]
            highest_point = interval_df['High'].max()
            magnitude = highest_point - pivot_price
            
            if 'timestamp' in df.columns:
                 t1 = df.loc[idx]['timestamp']
                 t2 = df.loc[recovery_time]['timestamp']
                 duration_mins = (t2 - t1).total_seconds() / 60
            else:
                 duration_mins = (recovery_time - idx).total_seconds() / 60
        else:
            highest_point = future_df['High'].max()
            magnitude = highest_point - pivot_price
            if 'timestamp' in df.columns:
                 t_start = df.loc[idx]['timestamp']
                 t_end = df.iloc[-1]['timestamp']
                 duration_mins = (t_end - t_start).total_seconds() / 60
            else:
                 duration_mins = len(future_df)

        score = ((magnitude / pivot_price) * 100) * np.log1p(duration_mins)

        # LOWERED THRESHOLD TO 0.00015 (0.015%)
        if magnitude > (avg_price * 0.00015):
            scored_levels.append({
                "type": "SUPPORT",
                "level": pivot_price,
                "score": score,
                "magnitude": magnitude,
                "duration": duration_mins,
                "time": idx
            })

    # 3. Sort by Score (Impact)
    scored_levels.sort(key=lambda x: x['score'], reverse=True)

    # 4. De-Duplicate (Keep strongest signal in a zone)
    final_levels = []

    for candidate in scored_levels:
        is_duplicate = False
        for existing in final_levels:
            # If close to an existing (higher ranked) level of same type
            if (candidate['type'] == existing['type']) and \
               (abs(candidate['level'] - existing['level']) < proximity_threshold):
                is_duplicate = True
                break

        if not is_duplicate:
            # Anchor & Delta Filter: Only keep rejections that happened AFTER session start
            if session_start_dt:
                # Get the pivot timestamp
                if 'timestamp' in df.columns:
                    p_ts = df.loc[candidate['time']]['timestamp']
                else:
                    p_ts = candidate['time'] # DateTimeIndex
                
                # Ensure p_ts is naive or localized consistently for comparison
                # (Capital.com data is usually localized in processing.py calls)
                if p_ts < session_start_dt:
                    continue
            
            final_levels.append(candidate)

    # Return Top Results (separated)
    resistance = [x for x in final_levels if x['type'] == 'RESISTANCE'][:2]
    support = [x for x in final_levels if x['type'] == 'SUPPORT'][:2]

    # Format for JSON
    summary = []
    rank = 1
    for r in resistance:
        summary.append({
            "type": "RESISTANCE",
            "rank": rank,
            "level": r['level'],
            "strength_score": round(r['score'], 2),
            "reason": f"Rejected: Dropped ${r['magnitude']:.2f}, buyers absent for {int(r['duration'])} mins."
        })
        rank += 1

    rank = 1
    for s in support:
        summary.append({
            "type": "SUPPORT",
            "rank": rank,
            "level": s['level'],
            "strength_score": round(s['score'], 2),
            "reason": f"Bounced: Rallied ${s['magnitude']:.2f}, sellers absent for {int(s['duration'])} mins."
        })
        rank += 1

    return summary

def analyze_market_context(df, ref_levels, ticker="UNKNOWN", session_start_dt=None) -> dict:
    """
    The Master Function.
    Returns the JSON Observation Card (Migration Log + Impact Levels).
    """
    if df is None or df.empty:
        return {"status": "No Data", "meta": {"ticker": ticker}}

    # Pre-calc
    if 'timestamp' in df.columns:
        # Ensure correct resampling if index is not datetime
        # df index is RangeIndex, column 'timestamp' exists
        blocks = df.resample('30min', on='timestamp')
    else:
        # Fallback if DF has DateTimeIndex
        blocks = df.resample('30min')

    session_high = df['High'].max()
    session_low = df['Low'].min()
    current_price = df.iloc[-1]['Close']
    total_range = session_high - session_low

    value_migration_log = []
    block_id = 1

    # Helper to track POCs for Time-Based Support detection
    all_block_pocs = []

    for time_window, block_data in blocks:
        if len(block_data) == 0: continue

        price_counts = {}
        for _, row in block_data.iterrows():
            l = np.floor(row['Low'] * 20) / 20
            h = np.ceil(row['High'] * 20) / 20
            if h > l: ticks = np.arange(l, h + 0.05, 0.05)
            else: ticks = [l]
            for t in ticks:
                p = round(t, 2)
                price_counts[p] = price_counts.get(p, 0) + 1

        if not price_counts: poc = (block_data['High'].max() + block_data['Low'].min()) / 2
        else: poc = max(price_counts, key=price_counts.get)

        all_block_pocs.append(poc) # Collect POC for clustering later

        total_minutes = len(block_data)
        poc_hits = price_counts.get(poc, 0)
        time_at_poc_pct = round((poc_hits / total_minutes) * 100, 1) if total_minutes > 0 else 0

        block_h = block_data['High'].max()
        block_l = block_data['Low'].min()
        block_c = block_data['Close'].iloc[-1]
        block_o = block_data['Open'].iloc[0]
        range_val = block_h - block_l
        
        if total_range > 0: range_ratio = range_val / total_range
        else: range_ratio = 0

        if range_ratio < 0.15: vol_str = "Tight Compression"
        elif range_ratio < 0.35: vol_str = "Moderate Range"
        else: vol_str = "Wide Expansion"

        if range_val == 0: loc_str = "unchanged"
        else:
            pct_loc = (block_c - block_l) / range_val
            if pct_loc > 0.8: loc_str = "near highs"
            elif pct_loc < 0.2: loc_str = "near lows"
            else: loc_str = "mid-range"

        if block_c > block_o: dir_str = "Green"
        elif block_c < block_o: dir_str = "Red"
        else: dir_str = "Flat"

        nature_desc = f"{dir_str} candle, {vol_str} (${range_val:.2f}), closed {loc_str}"

        # Adaptation: Use column access safely
        log_entry = {
            "block_id": block_id,
            "time_window": time_window.strftime("%H:%M") + " - " + (time_window + timedelta(minutes=30)).strftime("%H:%M"),
            "observations": {
                "block_high": round(block_h, 2),
                "block_low": round(block_l, 2),
                "most_traded_price_level": round(poc, 2),
                "time_at_poc_percent": f"{min(time_at_poc_pct, 100)}%",
                "price_action_nature": nature_desc
            }
        }
        # Anchor & Delta Filter: Value Migrations must be from the current session
        if session_start_dt:
            if time_window < session_start_dt:
                block_id += 1
                continue

        value_migration_log.append(log_entry)
        block_id += 1

    # 3. IMPACT-BASED REJECTION SYSTEM (Rank 1 Priority)
    ranked_rejections = detect_impact_levels(df.copy(), session_start_dt=session_start_dt)

    # 4. TIME-BASED ACCEPTANCE (Stacked POCs - Rank 2 Priority)
    all_block_pocs.sort()
    time_based_levels = []
    if all_block_pocs:
        tolerance = max(0.05, df['Close'].mean() * 0.001)

        current_cluster = [all_block_pocs[0]]
        for i in range(1, len(all_block_pocs)):
            if all_block_pocs[i] - np.mean(current_cluster) <= tolerance:
                current_cluster.append(all_block_pocs[i])
            else:
                if len(current_cluster) >= 3:
                    time_based_levels.append({
                        "level": round(np.mean(current_cluster), 2),
                        "count": len(current_cluster),
                        "note": "Significant Time-Based Acceptance (Stacked POCs)"
                    })
                current_cluster = [all_block_pocs[i]]
        if len(current_cluster) >= 3:
            time_based_levels.append({
                "level": round(np.mean(current_cluster), 2),
                "count": len(current_cluster),
                "note": "Significant Time-Based Acceptance (Stacked POCs)"
            })

    time_based_levels.sort(key=lambda x: x['count'], reverse=True)

    # Safe Access to timestamp
    if 'timestamp' in df.columns:
        last_ts = df.iloc[-1]['timestamp'].strftime("%H:%M:%S")
        open_ts = df.iloc[0]['timestamp'].strftime("%H:%M:%S")
    else:
        last_ts = df.index[-1].strftime("%H:%M:%S")
        open_ts = df.index[0].strftime("%H:%M:%S")

    context_card = {
        "meta": {
            "ticker": ticker,
            "timestamp": last_ts,
            "pre_market_session_open": open_ts
        },
        "reference_levels": {
            "yesterday_close": ref_levels.get("yesterday_close", 0),
            "yesterday_high": ref_levels.get("yesterday_high", 0),
            "yesterday_low": ref_levels.get("yesterday_low", 0),
            "current_price": round(current_price, 2)
        },
        "session_extremes": {
            "pre_market_high": session_high,
            "pre_market_low": session_low,
            "total_range_dollars": round(total_range, 2)
        },
        "value_migration_log": value_migration_log,
        "key_level_rejections": ranked_rejections,
        "time_based_acceptance": time_based_levels
    }
    
    return context_card