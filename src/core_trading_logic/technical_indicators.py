# src/core_trading_logic/technical_indicators.py

import pandas as pd
import numpy as np
import re
from datetime import datetime

from src.config.constants import US_EASTERN
from src.logging.app_logger import AppLogger


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate VWAP for the given DataFrame of OHLCV data.
    Assumes columns: ['Open', 'High', 'Low', 'Close', 'Volume'] (or at least 'Close' + 'Volume').
    """
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
    """
    Calculate a basic volume profile over the given bars:
    - POC (Point of Control): price level with the most volume
    - VAH (Value Area High)
    - VAL (Value Area Low)

    Returns (poc_price, vah_price, val_price).
    """
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
    if not hasattr(poc_bin, "mid"):
        return np.nan, np.nan, np.nan
    poc_price = poc_bin.mid

    total_volume = grouped.sum()
    if total_volume == 0:
        return poc_price, np.nan, np.nan

    # Build value area around the POC containing ~70% of volume
    target_volume = total_volume * 0.70
    sorted_by_vol = grouped.sort_values(ascending=False)
    cumulative_vol = sorted_by_vol.cumsum()
    value_area_bins = sorted_by_vol[cumulative_vol <= target_volume]

    if value_area_bins.empty:
        return poc_price, np.nan, np.nan

    val_price = value_area_bins.index.min().left
    vah_price = value_area_bins.index.max().right

    return poc_price, vah_price, val_price


def process_premarket_bars_to_summary(
    ticker: str,
    df_pm: pd.DataFrame,
    live_price: float,
    logger: AppLogger
) -> str:
    """
    Turn pre-market bars for a ticker into a compact textual summary
    used by the Macro and Head Trader workflows.
    """
    logger.log(f"Processing {len(df_pm)} pre-market bars for {ticker}...")
    try:
        today_str = datetime.now(US_EASTERN).date().isoformat()

        if df_pm.empty:
            return (
                f"Data Extraction Summary: {ticker} | {today_str} "
                f"(No pre-market bars. Current price is ${live_price:.2f})"
            )

        pm_open = df_pm['Open'].iloc[0]
        pm_high = df_pm['High'].max()
        pm_low = df_pm['Low'].min()
        pm_close = live_price
        total_volume = df_pm['Volume'].sum()

        # VWAP
        vwap_series = calculate_vwap(df_pm)
        pm_vwap = (
            vwap_series.iloc[-1]
            if not vwap_series.empty and not pd.isna(vwap_series.iloc[-1])
            else pm_close
        )

        # Volume profile
        pm_poc, pm_vah, pm_val = calculate_volume_profile(df_pm, bins=20)

        poc_str = f"${pm_poc:.2f}" if not pd.isna(pm_poc) else "N/A"
        vah_str = f"${pm_vah:.2f}" if not pd.isna(pm_vah) else "N/A"
        val_str = f"${pm_val:.2f}" if not pd.isna(pm_val) else "N/A"
        vwap_str = f"${pm_vwap:.2f}" if not pd.isna(pm_vwap) else "N/A"

        # Trend description based on where close is in the PM range
        trend_desc = "Consolidating."
        price_range = pm_high - pm_low
        if price_range > 0.001:
            percent_of_range = (pm_close - pm_low) / price_range
            if percent_of_range > 0.7:
                trend_desc = "Trending higher near PM High."
            elif percent_of_range < 0.3:
                trend_desc = "Trending lower near PM Low."

        close_vs_vwap = "Above" if pm_close > pm_vwap else "Below"

        summary_text = f"""
Data Extraction Summary: {ticker} | {today_str}
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
        # Collapse multiple spaces / newlines so the LLM gets a compact string
        return re.sub(r"\s+", " ", summary_text).strip()

    except Exception as e:
        logger.log(f"Error in process_premarket_bars_to_summary for {ticker}: {e}")
        today_str = datetime.now(US_EASTERN).date().isoformat()
        return (
            f"Data Extraction Summary: {ticker} | {today_str} "
            f"(Live Price: ${live_price:.2f}. Error processing bars.)"
        )
