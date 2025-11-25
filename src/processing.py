import pandas as pd
import numpy as np
from datetime import time as dt_time
from pytz import timezone as pytz_timezone
from .utils import AppLogger

US_EASTERN = pytz_timezone('US/Eastern')
MARKET_OPEN_TIME = dt_time(9, 30) # 09:30 AM ET

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
