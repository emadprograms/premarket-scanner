from __future__ import annotations
import json
import pandas as pd
from datetime import datetime, timedelta
from backend.engine.processing import analyze_market_context, get_session_bars_from_db, get_previous_session_stats
from backend.engine.utils import AppLogger

def get_or_compute_context(conn, ticker, trade_date_str, logger: AppLogger):
    """
    Retrieves the 'Impact Context Card' (Value Migration Log, etc.) for a ticker/date.
    Tries to fetch from DB cache first (if we had a cache table, skipping for now).
    Computes it fresh if needed using processing logic.
    """
    # 1. Check if we can compute it
    # We need bars for the trade_date
    # Since this is "Pre-Market", we usually look at the *previous* full day for context?
    # Or is 'trade_date_str' today?
    # The prompt says: "Today's New Price Action Summary (IMPACT CONTEXT CARD)"
    # If we are running this in Pre-Market, 'Today's Action' is just the Pre-Market action so far.
    
    # We will fetch whatever bars are available for this date up to now.
    
    # For simplicity in this "Wrapper", we will just compute it fresh.
    # In a real system we might cache this JSON in a table to avoid re-computing 20 times.
    
    cutoff_time = f"{trade_date_str} 23:59:59" # End of day or current time
    # Check if we are in live mode or sim?
    # We'll just use the provided date.
    
    try:
        # Fetch bars from DB (Context Engine usually runs on recent data)
        # We need a client. 'conn' passed in is likely a sqlite3 connection or LocalDBClient.
        # analyze_market_context needs a DataFrame.
        
        # We need to construct a client-like object or use the conn directly?
        # get_session_bars_from_db expects a 'client' object with .execute()
        
        # We'll assume 'conn' works as the client (LocalDBClient has .execute)
        
        # 1. Fetch Bars
        df = get_session_bars_from_db(
            client=conn, 
            epic=ticker, 
            benchmark_date=trade_date_str, 
            cutoff_str=cutoff_time, 
            logger=logger, 
            premarket_only=False # We want everything available for this date
        )
        
        if df is None or df.empty:
            return {"error": "No price data found for date."}
            
        # 2. Fetch Reference Levels (Previous Day's VAH/VAL/POC)
        # We need the previous trading day.
        # This is tricky without a calendar. We'll just try date-1, date-2, date-3
        ref_levels = get_previous_session_stats(conn, ticker, trade_date_str, logger)
        
        # 3. Compute
        context_card = analyze_market_context(df, ref_levels, ticker=ticker)
        return context_card

    except Exception as e:
        logger.log(f"Error computing context: {e}")
        return {"error": str(e)}
