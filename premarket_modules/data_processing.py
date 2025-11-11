import pandas as pd
import numpy as np
import re
import requests
import time
from datetime import datetime, timedelta

# Import config for constants
try:
    from . import config
except ImportError:
    import config

# ---
# --- "Stolen" Analytical Brain (Pandas/Numpy Analysis)
# ---

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculates the Volume Weighted Average Price (VWAP) series."""
    if 'Volume' not in df.columns or df['Volume'].sum() == 0:
        return pd.Series([np.nan] * len(df), index=df.index)
    
    if all(col in df.columns for col in ['High', 'Low', 'Close']):
        tp = (df['High'] + df['Low'] + df['Close']) / 3
    else:
        tp = df['Close']
        
    tpv = tp * df['Volume']
    
    if df['Volume'].cumsum().iloc[-1] == 0:
         return pd.Series([np.nan] * len(df), index=df.index)

    vwap_series = tpv.cumsum() / df['Volume'].cumsum()
    return vwap_series

def calculate_volume_profile(df: pd.DataFrame, bins: int = 20):
    """Calculates Volume Profile: POC, VAH, and VAL from a DataFrame."""
    if df.empty or 'Volume' not in df.columns or df['Volume'].sum() == 0:
        return np.nan, np.nan, np.nan
        
    if all(col in df.columns for col in ['High', 'Low']):
         price_mid = (df['High'] + df['Low']) / 2
    else:
         price_mid = df['Close']
         
    unique_prices = price_mid.nunique()
    if unique_prices < 2:
        if unique_prices == 1:
            price_val = price_mid.iloc[0]
            return price_val, price_val, price_val
        return np.nan, np.nan, np.nan

    actual_bins = min(bins, unique_prices - 1)
    
    try:
        price_bins = pd.cut(price_mid, bins=actual_bins)
    except Exception:
        return np.nan, np.nan, np.nan

    if price_bins.empty:
        return np.nan, np.nan, np.nan
        
    grouped = df.groupby(price_bins)['Volume'].sum()
    
    if grouped.empty:
        return np.nan, np.nan, np.nan
        
    poc_bin = grouped.idxmax()
    if not isinstance(poc_bin, pd.Interval):
         return np.nan, np.nan, np.nan
    poc_price = poc_bin.mid
    
    total_volume = grouped.sum()
    if total_volume == 0:
        return poc_price, np.nan, np.nan
        
    target_volume = total_volume * 0.70
    sorted_by_vol = grouped.sort_values(ascending=False)
    cumulative_vol = sorted_by_vol.cumsum()
    value_area_bins = sorted_by_vol[cumulative_vol <= target_volume]
    
    if value_area_bins.empty:
        return poc_price, np.nan, np.nan
        
    val_price = value_area_bins.index.min().left
    vah_price = value_area_bins.index.max().right
    
    return poc_price, vah_price, val_price

# ---
# --- Capital.com Data Fetching
# ---

def get_capital_current_price(epic: str, cst: str, xst: str, logger) -> tuple[float | None, float | None]:
    """Gets the live bid/offer for a single epic."""
    url = f"{config.CAPITAL_API_URL_BASE}/markets/{epic}"
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        snapshot = data.get('snapshot')
        if snapshot and 'bid' in snapshot and 'offer' in snapshot:
            return snapshot['bid'], snapshot['offer']
        else:
            logger.log(f"Ancillary...Warn ({epic}): Live price not in snapshot. {data}")
            return None, None
    except Exception as e:
        if hasattr(e, 'response') and e.response.status_code == 404:
            logger.log(f"Ancillary...Warn ({epic}): Market not found (404). Check EPIC name.")
        else:
            logger.log(f"Ancillary...Error fetching live price for {epic}: {e}")
        return None, None

def get_capital_price_bars(epic: str, cst: str, xst: str, resolution: str, logger) -> pd.DataFrame | None:
    """Fetches price bars for a given resolution, filtering for today's pre-market."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=18)
    
    price_params = {"resolution": resolution, 'max': 1000, 'from': start_date.strftime('%Y-%m-%dT%H:%M:%S'), 'to': end_date.strftime('%Y-%m-%dT%H:%M:%S')}
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    price_history_url = f"{config.CAPITAL_API_URL_BASE}/prices/{epic}"
    
    try:
        response = requests.get(price_history_url, headers=headers, params=price_params, timeout=10)
        response.raise_for_status()
        price_data = response.json()
        prices = price_data.get('prices', [])
        if not prices:
            logger.log(f"Ancillary...No price bars returned for {epic} (resolution: {resolution}).")
            return pd.DataFrame()
            
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
        df.dropna(subset=['SnapshotTime', 'Close', 'Open', 'High', 'Low', 'Volume'], inplace=True)
        
        if df.empty:
            logger.log(f"Ancillary...Price bars for {epic} were empty after cleaning.")
            return pd.DataFrame()
            
        df['ET_Time'] = df['SnapshotTime'].dt.tz_convert(config.US_EASTERN)
        today_et = datetime.now(config.US_EASTERN).date()
        pm_start = config.US_EASTERN.localize(datetime(today_et.year, today_et.month, today_et.day, config.PREMARKET_START_HOUR, 0))
        pm_end = config.US_EASTERN.localize(datetime(today_et.year, today_et.month, today_et.day, config.PREMARKET_END_HOUR, config.PREMARKET_END_MINUTE))
        
        df_premarket = df[(df['ET_Time'] >= pm_start) & (df['ET_Time'] < pm_end)].copy()
        
        if df_premarket.empty:
            logger.log(f"Ancillary...No bars found for {epic} within today's pre-market window.")
            return pd.DataFrame()
            
        logger.log(f"Ancillary...Successfully extracted {len(df_premarket)} pre-market bars for {epic}.")
        df_premarket.reset_index(drop=True, inplace=True)
        return df_premarket

    except Exception as e:
        logger.log(f"Ancillary...Error fetching/processing price bars for {epic}: {e}")
        return None

# ---
# --- "Engine" Function (Core Request)
# ---

def process_premarket_bars_to_summary(ticker: str, df_pm: pd.DataFrame, live_price: float, logger) -> str:
    """
    Analyzes the 5-min pre-market DataFrame using advanced logic
    and creates a detailed text summary for the AI.
    """
    logger.log(f"Ancillary...Processing {len(df_pm)} pre-market bars for {ticker}...")
    try:
        if df_pm.empty:
            return f"Data Extraction Summary: {ticker} | {datetime.now(config.US_EASTERN).date().isoformat()} (No pre-market bars. Current price is ${live_price:.2f})"

        pm_open = df_pm['Open'].iloc[0]
        pm_high = df_pm['High'].max()
        pm_low = df_pm['Low'].min()
        pm_close = live_price
        total_volume = df_pm['Volume'].sum()
        
        vwap_series = calculate_vwap(df_pm)
        pm_vwap = vwap_series.iloc[-1] if not vwap_series.empty and not pd.isna(vwap_series.iloc[-1]) else pm_close
        
        pm_poc, pm_vah, pm_val = calculate_volume_profile(df_pm, bins=20)
        
        poc_str = f"${pm_poc:.2f}" if not pd.isna(pm_poc) else "N/A"
        vah_str = f"${pm_vah:.2f}" if not pd.isna(pm_vah) else "N/A"
        val_str = f"${pm_val:.2f}" if not pd.isna(pm_val) else "N/A"
        vwap_str = f"${pm_vwap:.2f}" if not pd.isna(pm_vwap) else "N/A"

        trend_desc = "Consolidating."
        price_range = pm_high - pm_low
        if price_range > 0.001: 
            percent_of_range = (pm_close - pm_low) / price_range
            if percent_of_range > 0.7: trend_desc = "Trending higher near PM High."
            elif percent_of_range < 0.3: trend_desc = "Trending lower near PM Low."
        
        close_vs_vwap = "Above" if pm_close > pm_vwap else "Below"

        summary_text = f"""
Data Extraction Summary: {ticker} | {datetime.now(config.US_EASTERN).date().isoformat()}
==================================================
1. Session Extremes:
   - PM Open: ${pm_open:.2f}
   - PM High (PMH): ${pm_high:.2f}
   - PM Low (PML): ${pm_low:.2f}
   - Current Price: ${pm_close:.2f}
2. Volume Profile (Pre-Market):
   - Point of Control (POC): {poc_str}
   - Value Area High (VAH): {vah_str}
   - Value Area Low (VAL): {val_str}
3. VWAP Relationship (Pre-Market):
   - Session VWAP: {vwap_str}
   - Current Price vs. VWAP: {close_vs_vwap}
4. Key Action:
   - Price set a PM range between ${pm_low:.2f} and ${pm_high:.2f}.
   - {trend_desc} Currently trading at ${pm_close:.2f} ({close_vs_vwap} PM VWAP).
   - Total Volume (PM): {total_volume:,.0f}
"""
        return re.sub(r'\s+', ' ', summary_text).strip()
    
    except Exception as e:
        logger.log(f"Ancillary...Error in process_premarket_bars_to_summary for {ticker}: {e}")
        return f"Data Extraction Summary: {ticker} | {datetime.now(config.US_EASTERN).date().isoformat()} (Live Price: ${live_price:.2f}. Error processing bars.)"