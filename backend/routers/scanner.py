from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.schemas.base import ScannerRequest, DeepDiveRequest, GenericResponse
from typing import Optional, List, Dict, Any
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
import concurrent.futures
import json
import asyncio
import re
from datetime import datetime, timedelta
import pandas as pd
from backend.engine.time_utils import get_staleness_score
from backend.engine.database import fetch_watchlist, get_eod_card_data_for_screener, upsert_live_card
from backend.engine.processing import get_session_bars_routed, get_previous_session_stats, analyze_market_context

router = APIRouter()

# --- Scanner Routers ---


def extract_plan_price(text: str) -> Optional[float]:
    """Extracts first float price from a string like '$140.50' or '140'."""
    if not text:
        return None
    import re
    match = re.search(r'[\d.]+', text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

def fetch_and_analyze_ticker(ticker, turso, benchmark_date_str, simulation_cutoff_str, mode, cutoff_dt, scan_threshold, db_plans, plan_only=False):
    """
    Always fetches live price bars AND runs full card analysis for every ticker.
    Returns a rich result dict with price, bar count, migration log, card, and freshness.
    The caller decides whether to upsert the card to DB based on refresh_tickers.
    """
    try:
        df, staleness = get_session_bars_routed(
            turso, ticker, benchmark_date_str, simulation_cutoff_str,
            mode=mode, logger=None, db_fallback=False,
            premarket_only=False, days=2.9, resolution="MINUTE_5"
        )

        bar_count = len(df)
        latest_row = df.iloc[-1]
        
        # ROBUST COLUMN SELECTION: Handles cases where df['Close'] might return a Series due to duplicate names
        def get_val(row, col):
            val = row[col]
            if isinstance(val, pd.Series):
                return float(val.iloc[0])
            return float(val)

        l_price = get_val(latest_row, 'Close')
        p_ts = latest_row.get('timestamp') or latest_row.get('dt_eastern')
        if isinstance(p_ts, pd.Series): p_ts = p_ts.iloc[0]

        ts_u = str(df['dt_utc'].iloc[-1]) if 'dt_utc' in df.columns else str(p_ts)

        l_minutes = 999.0
        freshness_p = 0.0
        if p_ts:
            l_minutes = get_staleness_score(p_ts)
            freshness_p = max(0.0, 1.0 - (l_minutes / 60.0))

        # Always run full card analysis — migration blocks needed for ranking + display
        ref_levels = get_previous_session_stats(turso, ticker, benchmark_date_str, logger=None)
        card = analyze_market_context(
            df, ref_levels, ticker=ticker,
            session_start_dt=cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0)
        )

        migration_log = card.get("value_migration_log", []) if card else []
        migration_count = len(migration_log)

        fetch_log = (
            f"✅ {ticker}: Fetched {bar_count} bars | "
            f"Latest price ${l_price:.2f} | "
            f"Lag {l_minutes:.1f}m | "
            f"{migration_count} migration block{'s' if migration_count != 1 else ''}"
        )

        # Proximity check using DB plan levels
        prox_alert = None
        plan_data = db_plans.get(ticker)
        if plan_data:
            # INJECT SCREENER BRIEFING FOR FRONTEND MODAL
            # (Logic ensures screener_briefing is available for chart and proximity)
            sb_obj = {}
            if card:
                try:
                    # Try to parse the stored briefing text (which is JSON)
                    sb_text = plan_data.get("screener_briefing_text", "{}")
                    if sb_text.strip().startswith("{"):
                        sb_obj = json.loads(sb_text)
                    else:
                        sb_obj = {"narrative": sb_text}
                    
                    # Ensure S/R levels are attached for badges
                    if "S_Levels" not in sb_obj:
                        sb_obj["S_Levels"] = plan_data.get("s_levels", [])
                    if "R_Levels" not in sb_obj:
                        sb_obj["R_Levels"] = plan_data.get("r_levels", [])
                        
                    card["screener_briefing"] = sb_obj
                except Exception:
                    # Fallback construction
                    sb_obj = {
                        "S_Levels": plan_data.get("s_levels", []),
                        "R_Levels": plan_data.get("r_levels", []),
                        "narrative": plan_data.get("screener_briefing_text", "Briefing unavailable")
                    }
                    card["screener_briefing"] = sb_obj

            # --- PROXIMITY LEVELS SELECTION ---
            target_levels = []
            
            if plan_only:
                # STRICT MODE: Only Plan A and Plan B prices
                p_level_a = sb_obj.get("Plan_A_Level")
                p_level_b = sb_obj.get("Plan_B_Level")
                
                # Robust fallback: check narrative text if specific fields are missing
                narrative = sb_obj.get("narrative", "")
                if not p_level_a and narrative:
                    m_a = re.search(r'Plan_A_Level:\s*(.*?)(?:\n|$)', narrative)
                    if m_a: p_level_a = m_a.group(1).strip()
                if not p_level_b and narrative:
                    m_b = re.search(r'Plan_B_Level:\s*(.*?)(?:\n|$)', narrative)
                    if m_b: p_level_b = m_b.group(1).strip()
                
                # Also extract Bias for UI coloring
                bias_val = sb_obj.get("Setup_Bias", "")
                plan_a_text = sb_obj.get("Plan_A", "")
                plan_b_text = sb_obj.get("Plan_B", "")

                if narrative:
                    if not bias_val:
                        m_bias = re.search(r'Setup_Bias:\s*(.*?)(?:\n|$)', narrative)
                        if m_bias: bias_val = m_bias.group(1).strip()
                    if not plan_a_text:
                        m_pa = re.search(r'Plan_A:\s*(.*?)(?:\n|$)', narrative)
                        if m_pa: plan_a_text = m_pa.group(1).strip()
                    if not plan_b_text:
                        m_pb = re.search(r'Plan_B:\s*(.*?)(?:\n|$)', narrative)
                        if m_pb: plan_b_text = m_pb.group(1).strip()

                sb_obj["Setup_Bias"] = bias_val
                sb_obj["Plan_A"] = plan_a_text
                sb_obj["Plan_B"] = plan_b_text

                def get_plan_bias(text, default_bias):
                    if not text: return default_bias
                    t = text.lower()
                    if any(k in t for k in ["short", "bear", "sell", "put", "below", "failure", "resistance", "rejection", "reject", "fade"]): return "Bearish"
                    if any(k in t for k in ["long", "bull", "buy", "call", "above", "support", "bounce", "break", "cross"]): return "Bullish"
                    return default_bias

                plan_a_bias = get_plan_bias(plan_a_text, bias_val)
                plan_b_bias = get_plan_bias(plan_b_text, bias_val)

                p_a = extract_plan_price(p_level_a)
                p_b = extract_plan_price(p_level_b)
                
                if p_a: target_levels.append((p_a, "PLAN A", plan_a_bias))
                if p_b: target_levels.append((p_b, "PLAN B", plan_b_bias))
            else:
                # STANDARD MODE: All S/R Levels
                target_levels = (
                    [(lvl, "SUPPORT") for lvl in plan_data.get('s_levels', [])] +
                    [(lvl, "RESISTANCE") for lvl in plan_data.get('r_levels', [])]
                )

            best_dist = float('inf')
            for best_lvl_data in target_levels:
                if len(best_lvl_data) == 3:
                    lvl, l_type, l_bias = best_lvl_data
                else:
                    lvl, l_type = best_lvl_data
                    l_bias = sb_obj.get("Setup_Bias", "Neutral")

                dist_pct = abs(l_price - lvl) / l_price * 100
                if dist_pct <= scan_threshold and dist_pct < best_dist:
                    best_dist = dist_pct
                    # Determine if it's support or resistance (Nature) for UI coloring
                    nature = l_type
                    if l_type.startswith("PLAN"):
                        if lvl in plan_data.get('s_levels', []): nature = "SUPPORT"
                        elif lvl in plan_data.get('r_levels', []): nature = "RESISTANCE"
                        else: nature = "SUPPORT" if lvl < l_price else "RESISTANCE"

                    prox_alert = {
                        "Ticker": ticker, "Price": f"${l_price:.2f}",
                        "Type": l_type, "Level": lvl,
                        "Dist %": round(dist_pct, 2),
                        "Source": f"Plan {plan_data.get('plan_date')}",
                        "Bias": l_bias,
                        "Nature": nature
                    }

        return {
            "ticker": ticker,
            "card": card,
            "prox_alert": prox_alert,
            "lag_min": l_minutes,
            "latest_ts_utc": ts_u,
            "bar_count": bar_count,
            "migration_count": migration_count,
            "source": "LIVE_CARD",   # always a full live card now
            "fetch_log": fetch_log,
            "table_row": {
                "Ticker": ticker,
                "Freshness": freshness_p,
                "Price": f"${l_price:.2f}",
                "Timestamp (UTC)": ts_u,
                "Lag (m)": f"{l_minutes:.1f}" if p_ts else "N/A",
                "Bars": bar_count,
                "Source": f"🔴 LIVE ({migration_count} blocks)"
            }
        }

    except Exception as e:
        return {
            "ticker": ticker,
            "error": str(e),
            "failed_analysis": True,
            "source": "LIVE_ERROR",
            "fetch_log": f"❌ {ticker}: Exception — {str(e)[:80]}"
        }


def build_db_fallback_result(ticker, db_plans):
    """Used only when live fetch completely fails."""
    plan_data = db_plans.get(ticker)
    if not plan_data:
        return {
            "ticker": ticker,
            "error": "No DB card found",
            "missing_data": True,
            "source": "DB_MISS",
            "fetch_log": f"⚠️ {ticker}: No card in DB and live fetch failed"
        }

    card_source = "LIVE_DB" if plan_data.get("is_live") else "EOD_DB"
    return {
        "ticker": ticker,
        "card": None,
        "prox_alert": None,
        "lag_min": 9999,
        "latest_ts_utc": plan_data.get("timestamp", "Historical"),
        "bar_count": 0,
        "migration_count": 0,
        "source": card_source,
        "fetch_log": f"📋 {ticker}: Live fetch failed — using {card_source} card from {plan_data.get('plan_date', 'N/A')}",
        "table_row": {
            "Ticker": ticker,
            "Freshness": 0.0,
            "Price": "N/A",
            "Timestamp (UTC)": plan_data.get("timestamp", "Historical"),
            "Lag (m)": "N/A",
            "Bars": 0,
            "Source": f"📋 {card_source} ({plan_data.get('plan_date', 'N/A')})"
        }
    }


@router.post("/scan", response_model=GenericResponse)
async def run_scan(request: ScannerRequest):
    logger = BackendAppLogger(manager, task_id="selection_scan")
    await logger.info("🚀 Starting Unified Selection Scan — fetching + analyzing all tickers...")

    turso = context.get_db()
    watchlist = fetch_watchlist(turso, None)
    full_ticker_list = sorted(list(set(watchlist)))

    # refresh_tickers = tickers whose fresh cards get upserted to DB
    # ALL tickers always get live fetch + full card analysis (migration blocks needed for ranking)
    refresh_set = set(t.upper() for t in (request.refresh_tickers or []))
    await logger.info(
        f"📡 All {len(full_ticker_list)} tickers → live fetch + full analysis | "
        f"💾 {len(refresh_set)} tickers → card upserted to DB"
    )

    # Load DB plans for proximity level data
    db_plans = get_eod_card_data_for_screener(turso, tuple(full_ticker_list), request.benchmark_date, None)

    from backend.engine.time_utils import to_utc
    cutoff_dt = to_utc(datetime.strptime(request.simulation_cutoff, '%Y-%m-%d %H:%M:%S'))

    # --- LIVE FETCH + FULL ANALYSIS FOR ALL 19 TICKERS (parallel) ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=19) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                executor,
                fetch_and_analyze_ticker,
                t, turso, request.benchmark_date, request.simulation_cutoff,
                request.mode, cutoff_dt, request.threshold, db_plans, request.plan_only
            )
            for t in full_ticker_list
        ]
        all_results = await asyncio.gather(*tasks)

    # --- LOG RESULTS + SELECTIVELY UPSERT CARDS ---
    card_coverage = []
    final_results = []

    for r in all_results:
        ticker = r["ticker"]
        fetch_log = r.get("fetch_log", "")
        source = r.get("source", "UNKNOWN")

        # Emit per-ticker fetch log
        if fetch_log:
            await logger.info(fetch_log)

        # Upsert card to DB only for selected refresh tickers
        if r.get("card") and not r.get("failed_analysis") and ticker.upper() in refresh_set:
            upsert_live_card(turso, ticker, request.benchmark_date, json.dumps(r["card"]))
            await logger.info(f"💾 {ticker}: Card upserted to DB.")

        # If live fetch failed, fall back to DB card
        if r.get("failed_analysis") or r.get("missing_data"):
            r = build_db_fallback_result(ticker, db_plans)
            await logger.info(r.get("fetch_log", ""))

        card_coverage.append({
            "ticker": ticker,
            "source": r.get("source", "UNKNOWN"),
            "price": r.get("table_row", {}).get("Price", "N/A"),
            "bars": r.get("bar_count", 0),
            "lag_min": round(r.get("lag_min", 9999), 1),
            "card_date": r.get("latest_ts_utc", "N/A"),
            "migration_blocks": r.get("migration_count", 0)
        })

        final_results.append(r)

    # --- SUMMARY ---
    live_card_count = sum(1 for c in card_coverage if c["source"] == "LIVE_CARD")
    eod_count = sum(1 for c in card_coverage if "EOD" in c["source"] or "DB" in c["source"])
    miss_count = sum(1 for c in card_coverage if "MISS" in c["source"] or "ERROR" in c["source"])
    total_blocks = sum(c["migration_blocks"] for c in card_coverage)

    await logger.success(
        f"📊 Scan Complete: {live_card_count} live cards | {eod_count} DB fallbacks | "
        f"{miss_count} missing | {total_blocks} total migration blocks across watchlist"
    )

    valid_results = [r for r in final_results if not r.get("failed_analysis")]

    return GenericResponse(
        status="success",
        message="Scan complete",
        data={
            "results": valid_results,
            "card_coverage": card_coverage,
            "summary": {
                "total": len(full_ticker_list),
                "live_cards": live_card_count,
                "eod_db": eod_count,
                "missing": miss_count,
                "total_migration_blocks": total_blocks
            }
        }
    )


@router.post("/deep-dive", response_model=GenericResponse)
async def run_deep_dive(request: DeepDiveRequest, background_tasks: BackgroundTasks):
    return GenericResponse(status="success", message="Deep Dive feature port in progress")



