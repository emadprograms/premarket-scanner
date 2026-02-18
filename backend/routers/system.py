from fastapi import APIRouter
from backend.services.context import context
from backend.engine.capital_api import create_capital_session_v2
from backend.engine.database import fetch_watchlist
from backend.routers.macro import load_cached_card, CACHE_FILE
import os
import json
import time
from datetime import datetime

router = APIRouter()

@router.get("/status")
async def get_system_status():
    km = context.get_km()
    
    # 1. Check Gemini Keys
    available_keys = len(km.available_keys)
    
    # 2. Check Capital.com Connectivity
    try:
        cst, xst = create_capital_session_v2()
        capital_connected = (cst is not None and xst is not None)
    except:
        capital_connected = False
    
    # 3. Check DB
    try:
        context.get_db().execute("SELECT 1")
        db_connected = True
    except:
        db_connected = False

    # 4. Check Economy Card Cache
    economy_card_cached = False
    economy_card_updated = "N/A"
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                cached_ts = cache_data.get('timestamp')
                if cached_ts:
                    # Check if it's still valid according to the same logic as load_cached_card
                    from backend.routers.macro import CACHE_VALIDITY_MINUTES
                    ts_dt = datetime.fromisoformat(cached_ts)
                    age_minutes = (datetime.now() - ts_dt).total_seconds() / 60
                    if age_minutes < CACHE_VALIDITY_MINUTES:
                        economy_card_cached = True
                        tz_name = time.tzname[time.daylight] if hasattr(time, 'tzname') else ""
                        economy_card_updated = f"{ts_dt.strftime('%H:%M:%S')} {tz_name}".strip()
    except:
        pass

    return {
        "status": "success",
        "data": {
            "gemini_keys_available": available_keys,
            "capital_connected": capital_connected,
            "db_connected": db_connected,
            "economy_card_status": {
                "active": economy_card_cached,
                "updated": economy_card_updated
            }
        }
    }

@router.post("/sync-keys")
async def sync_keys():
    """Manually triggers a sync from Infisical."""
    from backend.engine.infisical_manager import InfisicalManager
    km = context.get_km()
    try:
        mgr = InfisicalManager()
        km.sync_keys_from_infisical(mgr)
        return {"status": "success", "message": "Key sync triggered successfully."}
    except Exception as e:
        return {"status": "error", "message": f"Sync failed: {str(e)}"}

@router.get("/key-diagnostics")
async def key_diagnostics():
    """Returns detailed internal state of the KeyManager."""
    km = context.get_km()
    return {
        "status": "success",
        "data": {
            "available_count": len(km.available_keys),
            "cooldown_count": len(km.cooldown_keys),
            "dead_count": len(km.dead_keys),
            "strikes": km.key_failure_strikes,
            "name_map_size": len(km.name_to_key)
        }
    }

@router.get("/watchlist-status")
async def get_watchlist_status():
    """Returns company card coverage for all watchlist companies."""
    db = context.get_db()
    
    tickers = fetch_watchlist(db, None)
    if not tickers:
        return {"status": "error", "message": "No tickers in watchlist", "data": []}
    
    tickers = sorted(tickers)
    placeholders = ','.join(['?'] * len(tickers))
    
    # Live cards
    rs_live = db.execute(
        f"SELECT ticker, MAX(timestamp) as latest FROM deep_dive_cards WHERE ticker IN ({placeholders}) GROUP BY ticker",
        tickers
    )
    live_map = {row[0]: row[1] for row in rs_live.rows}
    
    # EOD cards
    rs_eod = db.execute(
        f"SELECT ticker, MAX(date) as latest_date, COUNT(*) as total FROM company_cards WHERE ticker IN ({placeholders}) GROUP BY ticker",
        tickers
    )
    eod_map = {row[0]: {"date": row[1], "total": row[2]} for row in rs_eod.rows}
    
    rows = []
    for t in tickers:
        if t in live_map:
            rows.append({
                "ticker": t,
                "status": "LIVE",
                "latest": live_map[t][:10] if live_map[t] else "N/A",
                "total_eod": eod_map.get(t, {}).get("total", 0)
            })
        elif t in eod_map:
            rows.append({
                "ticker": t,
                "status": "EOD",
                "latest": eod_map[t]["date"],
                "total_eod": eod_map[t]["total"]
            })
        else:
            rows.append({
                "ticker": t,
                "status": "MISSING",
                "latest": "N/A",
                "total_eod": 0
            })
    
    return {"status": "success", "data": rows}
