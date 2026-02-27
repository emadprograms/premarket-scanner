from fastapi import APIRouter, HTTPException
from backend.services.context import context
import asyncio
import json
import logging
import traceback

router = APIRouter()
log = logging.getLogger(__name__)


def _safe_execute(query, params=None):
    """Run a sync DB query with detailed error handling."""
    db = context.get_db()
    try:
        if params:
            return db.execute(query, params)
        return db.execute(query)
    except KeyError as e:
        # libsql_client v0.3.1 throws KeyError('result') when the Turso server
        # returns an error response (e.g., table not found). Convert to a clear message.
        log.error(f"DB KeyError (likely missing table): query={query}, error={e}")
        log.error(traceback.format_exc())
        raise RuntimeError(f"Database query failed (table may not exist): {query.split('FROM')[-1].split('WHERE')[0].strip() if 'FROM' in query else query}")
    except Exception as e:
        log.error(f"DB error: query={query}, error={e}")
        raise


@router.get("/cards/{category}")
async def get_cards(category: str, date: str = None):
    try:
        if category == "economy":
            query = "SELECT date, economy_card_json FROM aw_economy_cards"
            if date:
                query += " WHERE date = ?"
                rs = await asyncio.to_thread(_safe_execute, query, [date])
            else:
                query += " ORDER BY date DESC"
                rs = await asyncio.to_thread(_safe_execute, query)
            
            return {
                "status": "success",
                "data": [
                    {"date": r[0], "economy_card_json": json.loads(r[1]) if r[1] else {}}
                    for r in rs.rows
                ]
            }
        
        elif category == "company":
            query = "SELECT ticker, date, company_card_json FROM aw_company_cards"
            if date:
                query += " WHERE date = ?"
                rs = await asyncio.to_thread(_safe_execute, query, [date])
            else:
                query += " ORDER BY date DESC, ticker ASC"
                rs = await asyncio.to_thread(_safe_execute, query)
                
            return {
                "status": "success",
                "data": [
                    {"ticker": r[0], "date": r[1], "company_card_json": json.loads(r[2]) if r[2] else {}}
                    for r in rs.rows
                ]
            }
            
        return {"status": "error", "message": "Invalid category"}
    except Exception as e:
        log.error(f"Archive cards error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/cards/{category}/update")
async def update_card(category: str, card_data: dict, date: str, ticker: str = None):
    try:
        card_json = json.dumps(card_data)
        if category == "economy":
            await asyncio.to_thread(
                _safe_execute,
                "UPDATE aw_economy_cards SET economy_card_json = ? WHERE date = ?",
                [card_json, date]
            )
        elif category == "company" and ticker:
            await asyncio.to_thread(
                _safe_execute,
                "UPDATE aw_company_cards SET company_card_json = ? WHERE date = ? AND ticker = ?",
                [card_json, date, ticker]
            )
        else:
            return {"status": "error", "message": "Invalid parameters"}
            
        return {"status": "success", "message": "Card updated"}
    except Exception as e:
        log.error(f"Archive update error: {e}")
        return {"status": "error", "message": str(e)}

@router.delete("/cards/{category}/delete")
async def delete_card(category: str, date: str, ticker: str = None):
    try:
        if category == "economy":
            await asyncio.to_thread(
                _safe_execute,
                "DELETE FROM aw_economy_cards WHERE date = ?",
                [date]
            )
        elif category == "company" and ticker:
            await asyncio.to_thread(
                _safe_execute,
                "DELETE FROM aw_company_cards WHERE date = ? AND ticker = ?",
                [date, ticker]
            )
        else:
            return {"status": "error", "message": "Invalid parameters"}
            
        return {"status": "success", "message": "Card deleted"}
    except Exception as e:
        log.error(f"Archive delete error: {e}")
        return {"status": "error", "message": str(e)}
