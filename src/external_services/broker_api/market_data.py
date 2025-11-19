# src/external_services/broker_api/market_data.py

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Callable

# Correctly import from your project structure
from src.config.constants import (
    CAPITAL_API_URL_BASE,
    US_EASTERN,
    PREMARKET_START_HOUR,
    PREMARKET_END_HOUR,
    PREMARKET_END_MINUTE,
)

def get_capital_current_price(
    epic: str,
    cst: str,
    xst: str,
    log_func: Callable[[str], None]  # The missing parameter is now correctly added
) -> tuple[float | None, float | None]:
    """Fetches the current bid/offer price for a given epic."""
    url = f"{CAPITAL_API_URL_BASE}/markets/{epic}"
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        bid = data.get("snapshot", {}).get("bid")
        offer = data.get("snapshot", {}).get("offer")
        return bid, offer
    except requests.exceptions.RequestException as e:
        # Now 'log_func' is defined because it was passed in as a parameter
        log_func(f"Error fetching price for {epic}: {e}")
        return None, None

def get_capital_price_bars(
    epic: str,
    cst: str,
    xst: str,
    resolution: str,
    log_func: Callable[[str], None]  # The missing parameter is now correctly added
) -> pd.DataFrame | None:
    """Fetches and processes pre-market price bars for a given epic."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=18)
    price_params = {
        "resolution": resolution,
        "max": 1000,
        "from": start_date.strftime('%Y-%m-%dT%H:%M:%S'),
        "to": end_date.strftime('%Y-%m-%dT%H:%M:%S')
    }
    headers = {'X-SECURITY-TOKEN': xst, 'CST': cst}
    try:
        url = f"{CAPITAL_API_URL_BASE}/prices/{epic}"
        response = requests.get(url, headers=headers, params=price_params, timeout=10)
        response.raise_for_status()
        price_data = response.json()
        prices = price_data.get('prices', [])
        if not prices:
            log_func(f"No price bars received for {epic}.")
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
            log_func(f"Price bar data for {epic} was empty after cleaning.")
            return pd.DataFrame()
            
        df['ET_Time'] = df['SnapshotTime'].dt.tz_convert(US_EASTERN)
        today_et = datetime.now(US_EASTERN).date()
        pm_start = US_EASTERN.localize(datetime(today_et.year, today_et.month, today_et.day, PREMARKET_START_HOUR, 0))
        pm_end = US_EASTERN.localize(datetime(today_et.year, today_et.month, today_et.day, PREMARKET_END_HOUR, PREMARKET_END_MINUTE))
        
        df_premarket = df[(df['ET_Time'] >= pm_start) & (df['ET_Time'] < pm_end)].copy()
        
        if df_premarket.empty:
            log_func(f"No PM bars for {epic} within today's pre-market window.")
            return pd.DataFrame()
            
        df_premarket.reset_index(drop=True, inplace=True)
        return df_premarket

    except requests.exceptions.RequestException as e:
        # Now 'log_func' is defined because it was passed in as a parameter
        log_func(f"Error fetching price bars for {epic}: {e}")
        return None
