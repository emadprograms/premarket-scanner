import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from pytz import timezone as pytz_timezone
from modules.utils import AppLogger

US_EASTERN = pytz_timezone('US/Eastern')
MARKET_OPEN_TIME = dt_time(9, 30)

# --- DB FETCHING UTILITIES ---

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
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')

        df['dt_eastern'] = df['timestamp'].dt.tz_convert(US_EASTERN)
        
        # Filter for Pre-Market (04:00 - 09:30 ET)
        time_eastern = df['dt_eastern'].dt.time
        df = df[time_eastern < MARKET_OPEN_TIME].copy()

        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['close'], inplace=True)
        
        # Normalize columns for the Engine
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
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

# ==========================================
# THE IMPACT CONTEXT ENGINE (UPDATED FROM ENGINE LAB)
# ==========================================

def detect_impact_levels(df):
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

        # SCORE CALCULATION
        score = magnitude * np.log1p(duration_mins)

        if magnitude > (avg_price * 0.001): 
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

        score = magnitude * np.log1p(duration_mins)

        if magnitude > (avg_price * 0.001):
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

def analyze_market_context(df, ref_levels, ticker="UNKNOWN") -> dict:
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
        value_migration_log.append(log_entry)
        block_id += 1

    # 3. IMPACT-BASED REJECTION SYSTEM (Rank 1 Priority)
    ranked_rejections = detect_impact_levels(df.copy())

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