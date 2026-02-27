from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.schemas.base import ScannerRequest, GenericResponse
from typing import Optional, List, Dict, Any
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
from backend.services.capital_socket import capital_ws
from backend.engine.ranking_engine import ranking_engine
from backend.engine.database import fetch_watchlist, get_eod_card_data_for_screener
from backend.engine.processing import get_session_bars_routed, calculate_atr, ticker_to_epic
import asyncio
import json
import re
from datetime import datetime

router = APIRouter()

def extract_level_price(text: str) -> Optional[float]:
    """Helper to extract float price from plan level text."""
    if not text: return None
    match = re.search(r'[\d.]+', str(text))
    return float(match.group()) if match else None

@router.post("/scan", response_model=GenericResponse)
async def run_proximity_scan(request: ScannerRequest):
    """
    The new 'Proximity Engine' entry point.
    1. Fetches Plan A/B levels from Turso.
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

    # 1. Fetch Plan Levels from Turso
    db_plans = get_eod_card_data_for_screener(turso, tuple(watchlist), request.benchmark_date, logger)
    
    # 2. Fetch Historical Data for ATR & Setup WebSocket
    ranked_candidates = []
    
    # We update the WebSocket service with the current watchlist (non-fatal)
    try:
        capital_ws.set_tickers(watchlist)
        if not capital_ws.running:
            await capital_ws.start()
    except Exception as e:
        await logger.warn(f"⚠️ Capital.com WS unavailable: {e}. Using historical data.")

    async def process_ticker(ticker):
        try:
            # Get historical bars for ATR (3 days, 5m resolution)
            df, _ = get_session_bars_routed(
                turso, ticker, request.benchmark_date, request.simulation_cutoff,
                mode=request.mode, days=3, resolution="MINUTE_5"
            )
            
            atr = calculate_atr(df) if df is not None else 0.0
            
            plan_data = db_plans.get(ticker, {})
            sb_text = plan_data.get("screener_briefing_text", "{}")
            
            # Robust Plan A/B Extraction
            plan_a_val = None
            plan_b_val = None
            setup_bias = "Neutral"
            
            try:
                if sb_text.strip().startswith("{"):
                    sb_obj = json.loads(sb_text)
                    plan_a_val = extract_level_price(sb_obj.get("Plan_A_Level"))
                    plan_b_val = extract_level_price(sb_obj.get("Plan_B_Level"))
                    setup_bias = sb_obj.get("Setup_Bias", "Neutral")
                else:
                    # Regex fallback for legacy string-based cards
                    m_a = re.search(r'Plan_A_Level:\s*([\d.]+)', sb_text)
                    m_b = re.search(r'Plan_B_Level:\s*([\d.]+)', sb_text)
                    plan_a_val = float(m_a.group(1)) if m_a else None
                    plan_b_val = float(m_b.group(1)) if m_b else None
            except: pass

            # Get current price from WebSocket cache or fallback to last bar
            epic = ticker_to_epic(ticker)
            ws_data = capital_ws.prices.get(epic, {})
            current_price = ws_data.get("mid")
            
            if not current_price and df is not None and not df.empty:
                current_price = float(df['Close'].iloc[-1])

            # Allow tickers with no price — they'll show as "--" on frontend
            return {
                "ticker": ticker,
                "current_price": current_price,
                "atr": atr,
                "plan_a": plan_a_val,
                "plan_b": plan_b_val,
                "setup_bias": setup_bias,
                "s_levels": plan_data.get("s_levels", []),
                "r_levels": plan_data.get("r_levels", []),
                "card": json.loads(plan_data.get("raw_card_json", "{}")) if plan_data.get("raw_card_json") else None,
                "card_date": plan_data.get("card_date", "N/A")
            }
        except Exception as e:
            await logger.error(f"Error processing {ticker}: {e}")
            return None

    # Process all tickers in parallel
    tasks = [process_ticker(t) for t in watchlist]
    results = await asyncio.gather(*tasks)
    valid_results = [r for r in results if r is not None]

    # Helper: Determine what the PLAN classifies a level as (Support or Resistance)
    def _classify_plan_nature(level_val, s_levels, r_levels):
        """Check if the nearest level value appears in S_Levels or R_Levels."""
        if level_val is None:
            return "N/A"
        # Fuzzy match: levels may differ by a small amount due to float parsing
        for s in s_levels:
            if abs(s - level_val) < 0.02:
                return "SUPPORT"
        for r in r_levels:
            if abs(r - level_val) < 0.02:
                return "RESISTANCE"
        return "UNKNOWN"

    # 3. Calculate Proximity & Rank (only for tickers with a price)
    priced_results = [r for r in valid_results if r.get("current_price")]
    unpriced_results = [r for r in valid_results if not r.get("current_price")]
    
    ranked_results = ranking_engine.rank_cards(priced_results)

    # 4. Format for Frontend
    final_output = []
    for r in ranked_results:
        ticker = r["ticker"]
        level_val = r.get("nearest_level_value")
        level_type = r.get("nearest_level_type", "N/A")
        prox_score = r.get("proximity_score", 0)
        cur_price = r.get("current_price", 0)
        s_levels = r.get("s_levels", [])
        r_levels = r.get("r_levels", [])
        
        # Price-relative behavior (live price vs level)
        if level_val is not None and cur_price:
            price_nature = "SUPPORT" if level_val < cur_price else "RESISTANCE"
            level_display = f"{level_type} (${level_val:.2f})"
        else:
            price_nature = "N/A"
            level_display = f"{level_type} (N/A)"

        # Plan classification (what the analyst plan says)
        plan_nature = _classify_plan_nature(level_val, s_levels, r_levels)
        
        final_output.append({
            "ticker": ticker,
            "plan_a": r.get("plan_a"),
            "plan_b": r.get("plan_b"),
            "atr": r.get("atr", 0),
            "card_date": r.get("card_date", "N/A"),
            "prox_alert": {
                "Ticker": ticker,
                "Price": f"${cur_price:.2f}" if cur_price else "N/A",
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
                "Price": f"${cur_price:.2f}" if cur_price else "N/A",
                "Score": round(prox_score, 2) if prox_score else 0,
                "Level": level_display
            }
        })

    # Append unpriced tickers at the end (no ranking, no price)
    for r in unpriced_results:
        ticker = r["ticker"]
        # Still classify plan nature for unpriced tickers if possible
        plan_a = r.get("plan_a")
        s_levels = r.get("s_levels", [])
        r_levels_list = r.get("r_levels", [])
        plan_nature = _classify_plan_nature(plan_a, s_levels, r_levels_list)

        final_output.append({
            "ticker": ticker,
            "plan_a": plan_a,
            "plan_b": r.get("plan_b"),
            "atr": r.get("atr", 0),
            "card_date": r.get("card_date", "N/A"),
            "prox_alert": {
                "Ticker": ticker,
                "Price": "N/A",
                "Type": "N/A",
                "Level": None,
                "Dist %": 0,
                "Bias": r.get("setup_bias", "Neutral"),
                "Nature": "N/A",
                "PlanNature": plan_nature
            },
            "card": r.get("card"),
            "table_row": {
                "Ticker": ticker,
                "Price": "N/A",
                "Score": 0,
                "Level": "N/A"
            }
        })

    await logger.success(f"✅ Proximity Rank Complete. {len(final_output)} tickers active.")
    
    return GenericResponse(
        status="success",
        message="Proximity scan complete",
        data={
            "results": final_output,
            "summary": {"total": len(watchlist), "active": len(final_output)}
        }
    )

