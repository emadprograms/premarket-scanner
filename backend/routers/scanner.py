from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.schemas.base import ScannerRequest, GenericResponse
from typing import Optional, List, Dict, Any
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
from backend.services.capital_socket import capital_ws
from backend.engine.ranking_engine import ranking_engine
from backend.engine.database import fetch_watchlist, get_eod_card_data_for_screener
from backend.engine.card_extractor import extract_screener_briefing
from backend.engine.processing import get_live_bars_from_yahoo, get_live_bars_from_capital, calculate_atr, ticker_to_epic
import asyncio
import json
from datetime import datetime

router = APIRouter()

@router.post("/scan", response_model=GenericResponse)
async def run_proximity_scan(request: ScannerRequest):
    """
    The 'Proximity Engine' entry point.
    1. Fetches Plan A/B levels from Turso via card_extractor.
    2. Fetches 3 days of historical data to calculate ATR for normalization.
    3. Initializes/Updates the WebSocket feed for real-time prices.
    4. Calculates initial proximity and returns ranked results.
    """
    logger = BackendAppLogger(manager, task_id="proximity_scan")
    await logger.info("🚀 Initializing Proximity Engine...")

    turso = context.get_db()
    watchlist = fetch_watchlist(turso, logger)
    if not watchlist:
        return GenericResponse(status="error", message="Watchlist is empty.")

    # 1. Fetch card data from Turso (aw_company_cards only)
    db_plans = get_eod_card_data_for_screener(turso, tuple(watchlist), request.benchmark_date, logger)
    
    # 2. Setup WebSocket (non-fatal)
    try:
        capital_ws.set_tickers(watchlist)
        if not capital_ws.running:
            await capital_ws.start()
    except Exception as e:
        await logger.warn(f"⚠️ Capital.com WS unavailable: {e}. Using historical data.")

    async def process_ticker(ticker):
        try:
            # Get bars from Yahoo Finance (fast) — only needed for ATR, not charting
            df = get_live_bars_from_yahoo(ticker, days=3, resolution="MINUTE_5")
            atr = calculate_atr(df) if df is not None else 0.0
            
            plan_data = db_plans.get(ticker, {})
            raw_card_json = plan_data.get("raw_card_json", "{}")

            # Use the dedicated card_extractor for robust extraction
            extracted = extract_screener_briefing(raw_card_json)

            # Get current price from WebSocket cache or fallback to last bar
            epic = ticker_to_epic(ticker)
            ws_data = capital_ws.prices.get(epic, {})
            current_price = ws_data.get("mid")
            
            if not current_price and df is not None and not df.empty:
                current_price = float(df['Close'].iloc[-1])

            return {
                "ticker": ticker,
                "current_price": current_price,
                "atr": atr,
                "plan_a": extracted["plan_a_level"],
                "plan_b": extracted["plan_b_level"],
                "plan_a_text": extracted["plan_a_text"],
                "plan_b_text": extracted["plan_b_text"],
                "plan_a_nature": extracted["plan_a_nature"],
                "plan_b_nature": extracted["plan_b_nature"],
                "setup_bias": extracted["setup_bias"],
                "card": json.loads(raw_card_json) if raw_card_json and raw_card_json != "{}" else None,
                "card_date": plan_data.get("card_date", "N/A")
            }
        except Exception as e:
            await logger.error(f"Error processing {ticker}: {e}")
            return None

    # Process all tickers in parallel
    tasks = [process_ticker(t) for t in watchlist]
    results = await asyncio.gather(*tasks)
    valid_results = [r for r in results if r is not None]

    # 3. Calculate Proximity & Rank (only for tickers with a price)
    priced_results = [r for r in valid_results if r.get("current_price")]
    unpriced_results = [r for r in valid_results if not r.get("current_price")]
    
    ranked_results = ranking_engine.rank_cards(priced_results)

    # 4. Format for Frontend
    def _format_ticker(r, has_price=True):
        ticker = r["ticker"]
        level_val = r.get("nearest_level_value")
        level_type = r.get("nearest_level_type", "N/A")
        prox_score = r.get("proximity_score", 0)
        cur_price = r.get("current_price", 0)

        # Price-relative behavior
        if has_price and level_val is not None and cur_price:
            price_nature = "SUPPORT" if level_val < cur_price else "RESISTANCE"
            level_display = f"{level_type} (${level_val:.2f})"
        else:
            price_nature = "N/A"
            level_display = f"{level_type} (N/A)" if has_price else "N/A"

        # Plan nature — determined by which plan is nearest
        if level_type == "PLAN A":
            plan_nature = r.get("plan_a_nature", "UNKNOWN")
        elif level_type == "PLAN B":
            plan_nature = r.get("plan_b_nature", "UNKNOWN")
        else:
            plan_nature = "UNKNOWN"

        return {
            "ticker": ticker,
            "plan_a": r.get("plan_a"),
            "plan_b": r.get("plan_b"),
            "plan_a_text": r.get("plan_a_text", ""),
            "plan_b_text": r.get("plan_b_text", ""),
            "plan_a_nature": r.get("plan_a_nature", "UNKNOWN"),
            "plan_b_nature": r.get("plan_b_nature", "UNKNOWN"),
            "atr": r.get("atr", 0),
            "card_date": r.get("card_date", "N/A"),
            "prox_alert": {
                "Ticker": ticker,
                "Price": f"${cur_price:.2f}" if (has_price and cur_price) else "N/A",
                "Type": level_type,
                "Level": level_val,
                "Dist %": round(prox_score, 2) if prox_score else 0,
                "Bias": r.get("setup_bias", "Neutral"),
                "Nature": price_nature,
                "PlanNature": plan_nature
            },
            "card": r.get("card"),
            "table_row": {
                "Ticker": ticker,
                "Price": f"${cur_price:.2f}" if (has_price and cur_price) else "N/A",
                "Score": round(prox_score, 2) if prox_score else 0,
                "Level": level_display
            }
        }

    final_output = [_format_ticker(r, has_price=True) for r in ranked_results]
    
    # Unpriced tickers appended at end with no ranking
    for r in unpriced_results:
        r["nearest_level_value"] = None
        r["nearest_level_type"] = "N/A"
        r["proximity_score"] = 0
        final_output.append(_format_ticker(r, has_price=False))

    await logger.success(f"✅ Proximity Rank Complete. {len(final_output)} tickers active.")
    
    return GenericResponse(
        status="success",
        message="Proximity scan complete",
        data={
            "results": final_output,
            "summary": {"total": len(watchlist), "active": len(final_output)}
        }
    )


@router.get("/bars/{ticker}")
async def get_chart_bars(ticker: str, days: int = 1):
    """
    Fetch Capital.com bars for chart plotting.
    Returns OHLC data for the requested ticker (default: last 16 hours / 1 day).
    """
    try:
        turso = context.get_db()
        df = get_live_bars_from_capital(ticker, client=turso, days=days, resolution="MINUTE_5")
        
        if df is None or df.empty:
            return GenericResponse(status="empty", message=f"No Capital.com data for {ticker}", data={"bars": []})
        
        # Convert to JSON-serializable list of dicts
        bars = []
        for _, row in df.iterrows():
            ts = row.get('timestamp')
            # Convert timestamp to unix seconds
            if hasattr(ts, 'timestamp'):
                time_val = int(ts.timestamp())
            else:
                time_val = 0
            bars.append({
                "time": time_val,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
            })
        
        return GenericResponse(
            status="success",
            message=f"{len(bars)} bars for {ticker}",
            data={"bars": bars, "ticker": ticker}
        )
    except Exception as e:
        return GenericResponse(status="error", message=str(e), data={"bars": []})


@router.get("/bars/yahoo/{ticker}")
async def get_yahoo_chart_bars(ticker: str, days: int = 3):
    """
    Fetch Yahoo Finance bars for chart plotting (Fallback/Weekend).
    Returns OHLC data for the requested ticker (default: last 3 days).
    """
    try:
        df = get_live_bars_from_yahoo(ticker, days=days, resolution="MINUTE_5")
        
        if df is None or df.empty:
            return GenericResponse(status="empty", message=f"No Yahoo Finance data for {ticker}", data={"bars": []})
        
        # Convert to JSON-serializable list of dicts formatted for lightweight-charts
        bars = []
        for _, row in df.iterrows():
            ts = row.get('timestamp') or row.name
            # Convert timestamp to unix seconds
            if hasattr(ts, 'timestamp'):
                time_val = int(ts.timestamp())
            else:
                try:
                    import pandas as pd
                    time_val = int(pd.to_datetime(ts).timestamp())
                except:
                    time_val = 0
            
            bars.append({
                "time": time_val,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
            })
        
        return GenericResponse(
            status="success",
            message=f"{len(bars)} bars for {ticker} (Yahoo)",
            data={"bars": bars, "ticker": ticker, "source": "yahoo"}
        )
    except Exception as e:
        return GenericResponse(status="error", message=str(e), data={"bars": []})

