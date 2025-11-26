import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta, time as dt_time
from pytz import timezone as pytz_timezone
from src.utils import AppLogger

US_EASTERN = pytz_timezone('US/Eastern')
MARKET_OPEN_TIME = dt_time(9, 30)

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
