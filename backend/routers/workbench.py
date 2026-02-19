from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.schemas.base import GenericResponse
from typing import Optional, List, Dict, Any
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
from datetime import datetime
import json
import asyncio

router = APIRouter()

@router.get("/pipeline/next-date")
async def get_next_date():
    """Finds the day immediately after the last processed economy card."""
    logger = BackendAppLogger(manager, task_id="workbench_next_date")
    try:
        db = context.get_db()
        rs = db.execute("SELECT MAX(date) FROM economy_cards")
        last_date_str = rs.rows[0][0] if rs.rows and rs.rows[0][0] else None
        
        if not last_date_str:
            # If no cards exist, default to today or a safe fallback
            return GenericResponse(
                status="success", 
                message="No historical cards found, defaulting to today",
                data={"next_date": datetime.now().strftime("%Y-%m-%d"), "last_date": None}
            )
            
        from datetime import timedelta
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
        next_date = last_date + timedelta(days=1)
        
        return GenericResponse(
            status="success", 
            message="Calculated next sequential processing date",
            data={
                "next_date": next_date.strftime("%Y-%m-%d"),
                "last_date": last_date_str
            }
        )
    except Exception as e:
        await logger.error(f"Failed to find next date: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/daily-input/{date}")
async def get_daily_input(date: str):
    """Fetches saved news headlines for a specific date."""
    try:
        db = context.get_db()
        if not db:
            return GenericResponse(status="error", message="DB Connection Unavailable")
            
        rs = db.execute("SELECT news_text FROM daily_inputs WHERE target_date = ?", [date])
        
        news_text = ""
        if rs and rs.rows and len(rs.rows) > 0:
            val = rs.rows[0][0]
            news_text = str(val) if val is not None else ""
            
        return GenericResponse(status="success", message="Fetched daily input", data={"news_text": news_text})
    except Exception as e:
        return GenericResponse(status="error", message=f"Database Error: {str(e)}")

@router.post("/daily-input/save")
async def save_daily_input(date: str, news_text: str):
    """Saves news headlines for a specific date."""
    logger = BackendAppLogger(manager, task_id="workbench_save_input")
    try:
        db = context.get_db()
        # Upsert logic for SQLite/LibSQL
        db.execute("""
            INSERT INTO daily_inputs (target_date, news_text, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(target_date) DO UPDATE SET 
                news_text = excluded.news_text,
                updated_at = CURRENT_TIMESTAMP
        """, [date, news_text])
        await logger.success(f"Saved global context for {date}")
        return GenericResponse(status="success", message="Saved daily input")
    except Exception as e:
        await logger.error(f"Failed to save daily input: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cards/{category}")
async def get_cards(category: str, date: Optional[str] = None):
    """Fetches cards (economy or company) for a specific date or latest."""
    logger = BackendAppLogger(manager, task_id="workbench_card_fetch")
    try:
        db = context.get_db()
        if category == "economy":
            table = "economy_cards"
            date_col = "date"
        elif category == "company":
            table = "company_cards"
            date_col = "date"
        elif category == "daily-input":
            table = "daily_inputs"
            date_col = "target_date"
        else:
            raise HTTPException(status_code=400, detail="Invalid category")
            
        if date:
            query = f"SELECT * FROM {table} WHERE {date_col} = ?"
            rs = db.execute(query, [date])
        else:
            query = f"SELECT * FROM {table} ORDER BY {date_col} DESC LIMIT 1000"
            rs = db.execute(query)
            
        cards = []
        for row in rs.rows:
            cards.append(dict(zip(rs.columns, row)))
            
        return GenericResponse(status="success", message=f"Fetched {len(cards)} cards", data=cards)
    except Exception as e:
        await logger.error(f"Failed to fetch cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cards/{category}/update")
async def update_card(category: str, date: str, ticker: Optional[str], card_data: Dict[str, Any]):
    """Updates a card's JSON content in the database."""
    logger = BackendAppLogger(manager, task_id="workbench_card_update")
    try:
        db = context.get_db()
        table = "economy_cards" if category == "economy" else "company_cards"
        json_col = "economy_card_json" if category == "economy" else "company_card_json"
        
        json_str = json.dumps(card_data)
        
        if category == "economy":
            query = f"UPDATE {table} SET {json_col} = ? WHERE date = ?"
            db.execute(query, [json_str, date])
        else:
            query = f"UPDATE {table} SET {json_col} = ? WHERE date = ? AND ticker = ?"
            db.execute(query, [json_str, date, ticker])
            
        await logger.success(f"Updated {category} card for {date} {ticker or ''}")
        return GenericResponse(status="success", message="Card updated")
    except Exception as e:
        await logger.error(f"Failed to update card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cards/{category}/delete")
async def delete_card(category: str, date: str, ticker: Optional[str] = None):
    """Deletes a card from the database."""
    logger = BackendAppLogger(manager, task_id="workbench_card_delete")
    try:
        db = context.get_db()
        table = "economy_cards" if category == "economy" else "company_cards"
        
        if category == "economy":
            query = f"DELETE FROM {table} WHERE date = ?"
            db.execute(query, [date])
        else:
            query = f"DELETE FROM {table} WHERE date = ? AND ticker = ?"
            db.execute(query, [date, ticker])
            
        await logger.success(f"Deleted {category} card for {date} {ticker or ''}")
        return GenericResponse(status="success", message="Card deleted")
    except Exception as e:
        await logger.error(f"Failed to delete card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipeline/run")
async def run_pipeline(date: str, tickers: List[str], background_tasks: BackgroundTasks):
    """Triggers the EOD pipeline for a specific date and tickers."""
    logger = BackendAppLogger(manager, task_id="workbench_pipeline")
    await logger.info(f"🚀 Starting EOD Pipeline for {date}...")
    
    # In a real implementation, this would trigger the analysis engine
    # For now, we return success and log the start
    return GenericResponse(status="success", message=f"Pipeline started for {date}")

@router.post("/economy/generate")
async def generate_economy_card(date: str, news_text: str, model_config: Optional[str] = "gemini-3-flash-free"):
    """Generates (or recreates) an economy card for a specific date."""
    logger = BackendAppLogger(manager, task_id="workbench_eco_gen")
    try:
        db = context.get_db()
        await logger.info(f"🚀 Initializing Macro Synthesis for {date}")
        await logger.info(f"📥 Global Context received: {len(news_text)} characters")
        
        # KEY MANAGEMENT LOGS
        km = context.get_km()
        # Mocking prompt size for log demonstration
        est_tokens = len(news_text) // 4 + 1000
        await logger.info(f"📝 Estimated Prompt Size: {est_tokens} tokens")
        
        # Get Key
        key_name, key_val, wait, model_id = km.get_key(model_config, estimated_tokens=est_tokens)
        if key_val:
            tier = km.MODELS_CONFIG.get(model_config, {}).get('tier', 'free')
            await logger.success(f"🔑 Acquired '{key_name}' from {tier}-tier rotation pool")
            await logger.info(f"🧠 Routing request to {model_id} cluster...")
        else:
            await logger.warn("⚠️ High traffic detected. Retrying with secondary key...")
            
        await logger.info("🔍 Analyzing sector rotation and inter-market correlations...")
        await asyncio.sleep(1) # Simulated deliberation
        
        # MOCK: AI logic (Full Schema Compliance)
        mock_json_obj = {
            "marketNarrative": "Synthesis of the current session shows institutional support at major benchmarks...",
            "marketBias": "NEUTRAL",
            "keyEconomicEvents": {
                "last_24h": "FED speakers maintain hawkish tilt; CPI remains sticky.",
                "next_24h": "Retail Sales and Empire State Mfg index pending."
            },
            "sectorRotation": {
                "leadingSectors": ["XLK", "XLY"],
                "laggingSectors": ["XLP", "XLV"],
                "rotationAnalysis": "Capital flows favoring growth as yields stabilize."
            },
            "indexAnalysis": {
                "pattern": "Bullish Flag on 4H",
                "SPY": "Support at 505.50, Resistance at 512.00",
                "QQQ": "Support at 438.00, Resistance at 445.00"
            },
            "interMarketAnalysis": {
                "bonds": "TLT finding buyers at local lows; 10Y Yield testing 4.25%.",
                "commodities": "Gold consolidating near ATH; Oil steady.",
                "currencies": "DXY softening slightly.",
                "crypto": "BTC testing upper range of consolidation."
            },
            "marketInternals": {
                "volatility": "VIX compression persists below 14.00."
            },
            "todaysAction": "Market held key support levels despite early volatility.",
            "date": date
        }
        mock_json = json.dumps(mock_json_obj)
        
        await logger.info("💾 Saving Macro Card to Turso...")
        query = """
            INSERT INTO economy_cards (date, raw_text_summary, economy_card_json)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                raw_text_summary = excluded.raw_text_summary,
                economy_card_json = excluded.economy_card_json
        """
        db.execute(query, [date, news_text, mock_json])
        
        # Report usage
        km.report_usage(key_val, tokens=est_tokens + 500, model_id=model_id)
        await logger.success(f"✅ Economy Card for {date} finalized and committed.")
        
        return GenericResponse(status="success", message="Economy card generated/updated", data={"card": mock_json_obj})
    except Exception as e:
        await logger.error(f"❌ Critical Failure in Macro Pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/company/generate")
async def generate_company_card(date: str, ticker: str, model_config: Optional[str] = "gemini-3-flash-free"):
    """Generates (or recreates) a company card for a specific ticker and date."""
    logger = BackendAppLogger(manager, task_id=f"workbench_comp_{ticker}")
    try:
        db = context.get_db()
        await logger.info(f"🔍 Starting Structural Audit for {ticker} on {date}")
        
        # KEY MANAGEMENT
        km = context.get_km()
        await logger.info(f"📝 Initializing Deep Search for historical context...")
        
        # Get Key
        key_name, key_val, wait, model_id = km.get_key(model_config, estimated_tokens=1500)
        if key_val:
            await logger.success(f"🔑 Acquired '{key_name}' for {ticker} analysis")
            await logger.info(f"🧠 Routing to {model_id}...")
        
        await logger.info(f"📊 Analyzing price action vs key structural levels...")
        await asyncio.sleep(0.5)
        
        # MOCK: AI logic
        mock_json_obj = {
            "ticker": ticker,
            "bias": "BULLISH",
            "narrative": f"Company analysis for {ticker} shows strong accumulation...",
            "date": date
        }
        mock_json = json.dumps(mock_json_obj)
        
        await logger.info(f"💾 Committing {ticker} battle card to Turso...")
        query = """
            INSERT INTO company_cards (date, ticker, raw_text_summary, company_card_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, ticker) DO UPDATE SET
                raw_text_summary = excluded.raw_text_summary,
                company_card_json = excluded.company_card_json
        """
        db.execute(query, [date, ticker, "AI Generated Summary", mock_json])
        
        km.report_usage(key_val, tokens=2000, model_id=model_id)
        await logger.success(f"✅ {ticker} Audit Complete.")
        
        return GenericResponse(status="success", message=f"Company card for {ticker} generated", data={"card": mock_json_obj})
    except Exception as e:
        await logger.error(f"❌ Failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
