from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio
from backend.schemas.base import MacroRequest, GenericResponse
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
import concurrent.futures
import json
import re
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from backend.engine.time_utils import get_staleness_score
from backend.engine.database import get_latest_economy_card_date, get_eod_economy_card
from backend.engine.processing import get_session_bars_routed, get_previous_session_stats
from backend.engine.sentiment_engine import analyze_headline_sentiment
from backend.engine.gemini import call_gemini_with_rotation

router = APIRouter()

# STANDARDIZED TICKERS + DATABASE FALLBACKS
RAW_FETCH_LIST = ["SPY", "QQQ", "NDAQ", "IWM", "PAXGUSDT", "BTCUSDT", "EURUSDT", "CL=F", "UUP", "TLT", "SMH", "^VIX", "XLF", "XLK", "XLV", "XLE", "XLI", "XLP", "XLY", "XLC", "XLU"]

# CACHE CONFIGURATION
CACHE_FILE = "data/economy_card_cache.json"
CACHE_VALIDITY_MINUTES = 150  # 2.5 Hours

def load_cached_card(logger=None):
    """Loads the economy card from cache if it's still valid."""
    try:
        if not os.path.exists(CACHE_FILE):
            return None
        
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
            
        cached_ts = datetime.fromisoformat(cache_data.get('timestamp'))
        now = datetime.now()
        
        age_minutes = (now - cached_ts).total_seconds() / 60
        
        if age_minutes < CACHE_VALIDITY_MINUTES:
            if logger:
                # We can't await here easily without making this async, so we'll just return
                pass
            return cache_data.get('data')
        else:
            return None
            
    except Exception as e:
        print(f"Cache Load Error: {e}")
        return None

def save_cached_card(data):
    """Saves the economy card to cache with a timestamp."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        cache_structure = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_structure, f, indent=2)
    except Exception as e:
        print(f"Cache Save Error: {e}")

def analyze_macro_worker(ticker, df: pd.DataFrame, turso, benchmark_date_str, simulation_cutoff_dt, mode, session_start_dt=None):
    try:
        from backend.engine.processing import analyze_market_context
        
        # Diagnostic Audit
        first_bar = df['timestamp'].iloc[0]
        last_bar = df['timestamp'].iloc[-1]
        nat_count = df['timestamp'].isna().sum()
        
        ref_levels = get_previous_session_stats(turso, ticker, benchmark_date_str, logger=None)
        card = analyze_market_context(df, ref_levels, ticker=ticker, session_start_dt=session_start_dt)
        
        mig_log = card.get('value_migration_log', [])
        mig_count = len(mig_log)
        rej_count = len(card.get('key_level_rejections', []))
        acc_count = len(card.get('time_based_acceptance', []))
        
        ts_sample = "N/A"
        if mig_log: ts_sample = mig_log[0].get('time_window', 'N/A')

        res_summary = f"{mig_count} Migs (1st: {ts_sample}), {rej_count} Rejs, {acc_count} Accs"
        audit_note = f"Range: {first_bar} to {last_bar} | NaT: {nat_count}"
        
        return {
            "ticker": ticker, 
            "card": card, 
            "res_summary": res_summary,
            "audit_note": audit_note,
            "status": "SUCCESS"
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "failed_analysis": True, "status": "FAILED"}

@router.post("/run", response_model=GenericResponse)
async def run_macro(request: MacroRequest, background_tasks: BackgroundTasks):
    logger = BackendAppLogger(manager, task_id="macro_scan")
    await logger.info(f"🔍 [0/4] MACRO ENGINE INITIALIZING...")
    
    # CHECK CACHE FIRST
    if not request.force_execution:
        cached_card = load_cached_card()
        if cached_card:
            await logger.info(f"⚡ CACHE HIT: Using valid Economy Card (Strategy Persisted).")
            await logger.success("🏁 MACRO CONTEXT RESTORED FROM CACHE.")
            return GenericResponse(status="success", message="Restored from cache", data=cached_card)
    else:
        await logger.info(f"🔄 FORCE REFRESH: Ignoring cache, regenerating context...")

    turso = context.get_db()
    km = context.get_km()
    
    # 1. Anchor Check
    latest_date = get_latest_economy_card_date(turso, request.simulation_cutoff, None)
    if not latest_date:
        await logger.error("MISSING ANCHOR: No strategic plan found in DB. Mission aborted.")
        raise HTTPException(status_code=404, detail="Anchor Strategic Plan required.")
        
    eod_card = get_eod_economy_card(turso, latest_date, None)
    await logger.info(f"⚓ ANCHOR RETRIEVED: Strategic Plan from {latest_date}")

    # 2. Gather Market Data (Parallel)
    raw_datafeeds = {}
    from backend.engine.time_utils import to_utc
    cutoff_dt = to_utc(datetime.strptime(request.simulation_cutoff, '%Y-%m-%d %H:%M:%S'))
    
    await logger.info(f"📡 [1/4] INGESTION: Querying {len(RAW_FETCH_LIST)} symbols...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        loop = asyncio.get_event_loop()
        fetch_tasks = []
        for t in RAW_FETCH_LIST:
            fetch_tasks.append(loop.run_in_executor(executor, get_session_bars_routed, turso, t, request.benchmark_date, request.simulation_cutoff, request.mode, None, request.db_fallback, True, 3, "MINUTE_5"))
            
        results = await asyncio.gather(*fetch_tasks)
        for i, (df, staleness) in enumerate(results):
            ticker = RAW_FETCH_LIST[i]
            if df is not None and not df.empty:
                raw_datafeeds[ticker] = df
            elif df is not None and df.empty:
                await logger.warn(f"   ⚠️ {ticker}: No data bars found.")
            else:
                await logger.error(f"   ❌ {ticker}: Fetch failure.")
        
    # Alias NDAQ to QQQ for AI consistency
    if "NDAQ" in raw_datafeeds and "QQQ" not in raw_datafeeds:
        await logger.info("💡 COMPATIBILITY: Mapping NDAQ data to QQQ for AI synthesis.")
        raw_datafeeds["QQQ"] = raw_datafeeds["NDAQ"]

    await logger.info(f"📡 INGESTION COMPLETE: {len(raw_datafeeds)} datasets ready for computation.")

    # 3. Structural Analysis
    session_start_dt = cutoff_dt.replace(hour=4, minute=0, second=0, microsecond=0)
    await logger.info(f"📐 [2/4] ANALYSIS: Computing patterns (Mask: >= {session_start_dt})")
    
    analysis_results = []
    # Gemini targets
    target_list = [t for t in RAW_FETCH_LIST if t in raw_datafeeds and t != "NDAQ"]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        analysis_tasks = [loop.run_in_executor(executor, analyze_macro_worker, t, raw_datafeeds[t], turso, request.benchmark_date, cutoff_dt, request.mode, session_start_dt) for t in target_list]
        analysis_results = await asyncio.gather(*analysis_tasks)

    valid_results = [r for r in analysis_results if r.get('status') == "SUCCESS"]
    
    for r in analysis_results:
        if r.get('status') == "SUCCESS":
            await logger.info(f"   📊 {r['ticker']}: {r['res_summary']}")
            print(f"AUDIT {r['ticker']}: {r['audit_note']}")
        else:
            await logger.error(f"   ❌ {r['ticker']}: Logic error - {r.get('error')}")

    etf_structures = [r['card'] for r in valid_results if r.get('card')]
    total_migs = sum(len(c.get('value_migration_log', [])) for c in etf_structures)
    total_rejs = sum(len(c.get('key_level_rejections', [])) for c in etf_structures)
    
    await logger.info(f"📊 EVIDENCE PACKAGE COMPLETE: {len(etf_structures)} symbols | {total_migs} Migs | {total_rejs} Rejs.")

    # 4. AI Synthesis
    from backend.engine.analysis.macro_engine import generate_economy_card_prompt
    await logger.info(f"🧠 [3/4] AI SYNTHESIS: Cross-examining evidence...")
    
    analysis_dt_obj = cutoff_dt
    
    # GAP GUARD IMPLEMENTATION
    warnings = []
    
    # 1. Critical Ticker Check
    critical_tickers = ["SPY", "QQQ"]
    missing_critical = [t for t in critical_tickers if t not in raw_datafeeds or raw_datafeeds[t].empty]
    
    if missing_critical:
        warnings.append(f"CRITICAL: Missing data for {', '.join(missing_critical)}")
        
    # 2. Activity Check
    if total_migs == 0 and total_rejs == 0:
        warnings.append("Low Activity: 0 Migration Blocks and 0 Rejections detected across all assets.")
        
    # 3. Staleness Check (aggregated)
    stale_assets = [t for t in raw_datafeeds if raw_datafeeds[t] is not None and not raw_datafeeds[t].empty and (analysis_dt_obj - raw_datafeeds[t]['timestamp'].iloc[-1]).total_seconds()/60 > 60]
    if len(stale_assets) > 0:
        warnings.append(f"Data Stale: {len(stale_assets)} assets ({', '.join(stale_assets)}) are >1 hour old.")

    if warnings and not request.force_execution:
        await logger.warn(f"✋ GAP GUARD TRIGGERED: {len(warnings)} issues detected. Pausing for user confirmation.")
        for w in warnings:
             await logger.warn(f"   ⚠️ {w}")
             
        return GenericResponse(
            status="warning", 
            message="Data Gaps Detected", 
            data={
                "warnings": warnings, 
                "card_coverage": [], # specific coverage not needed for this prompt
                "summary": "AI Synthesis Paused"
            }
        )

    if total_migs == 0 and total_rejs == 0:
        await logger.error("🚨 CRITICAL: No price-action findings (Migs/Rejs) to synthesize. Result will be empty.")

    macro_prompt, macro_system = generate_economy_card_prompt(
        eod_card=eod_card,
        etf_structures=etf_structures,
        news_input=request.news_text,
        analysis_date_str=request.benchmark_date,
        logger=None,
        rolling_log=eod_card.get('keyActionLog', []),
        sentiment_data=None 
    )
    
    await logger.info(f"🛰️ [4/4] SHIP TO GEMINI... (Payload: {len(macro_prompt)} chars)")
    
    resp, error_msg = call_gemini_with_rotation(macro_prompt, macro_system, None, request.model_name, km)
    
    if resp:
        try:
            clean = re.search(r"(\{.*\})", resp, re.DOTALL).group(1)
            final_card = json.loads(clean)
            
            leads = len(final_card.get('sectorRotation', {}).get('leadingSectors', []))
            lags = len(final_card.get('sectorRotation', {}).get('laggingSectors', []))
            bias = final_card.get('marketBias', 'Unknown')
            
            # --- CACHE THE RESULT ---
            save_cached_card(final_card)
            # ------------------------
            
            await logger.info(f"🤖 AI VERDICT: {bias} | {leads} Leads | {lags} Lags.")
            await logger.success("🏁 FULL CYCLE MISSION ACCOMPLISHED.")
            return GenericResponse(status="success", message="Analysis complete", data=final_card)
        except Exception as e:
            await logger.error(f"❌ RESULT CORRUPTION: Failed to parse AI JSON - {e}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response.")
    else:
        await logger.error(f"❌ AI COMMS FAILURE: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
