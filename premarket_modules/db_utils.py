# premarket_modules/db_utils.py

import libsql_client
# REMOVE: import httpx 
import re 
import json
import datetime

# --- Import from our own modules ---
try:
    from . import config
    from .ui_components import AppLogger
except ImportError:
    # This allows the file to be run directly if needed
    import config
    from ui_components import AppLogger
    
# Import the specific synchronous functions your old file uses
from libsql_client import create_client_sync, LibsqlError # <--- ADD THIS LINE
# The LibsqlError is good practice too!

# ---
# --- Turso Client Creator
# ---

def create_turso_client(logger: AppLogger) -> libsql_client.Client | None:
    """
    Creates and returns a Turso DB client using the synchronous client
    (create_client_sync) for guaranteed Streamlit compatibility.
    """
    if not config.TURSO_DB_URL_HTTPS or not config.TURSO_AUTH_TOKEN:
        logger.log("DB Error: Turso URL or Auth Token is missing from config.")
        return None
        
    try:
        # Use the HTTPS-fixed URL from the config (Gotcha #2)
        client = create_client_sync(
            url=config.TURSO_DB_URL_HTTPS,
            auth_token=config.TURSO_AUTH_TOKEN
        )
        
        logger.log("DB: Turso client created successfully (using create_client_sync).")
        return client
        
    except LibsqlError as e:
        logger.log(f"DB Error (Libsql): Failed to create Turso client: {e}")
        return None
    except Exception as e:
        logger.log(f"DB Error (General): Failed to create Turso client: {e}")
        return None
# ---
# --- Database Read/Write Functions (The rest of your file)
# ---

def get_latest_economy_card_date(client: libsql_client.Client, logger: AppLogger) -> str | None:
    """
    Fetches the latest date (as a TEXT string) from the economy_cards table.
    This is the benchmark date for the "Date Alignment" rule.
    """
    logger.log("DB: Fetching latest economy card date (Benchmark Date)...")
    if not client:
        logger.log("DB Error: No client provided.")
        return None
    try:
        # Query for the single most recent date
        rs = client.execute("SELECT MAX(date) FROM economy_cards")
        if rs.rows and rs.rows[0][0]:
            latest_date = rs.rows[0][0]
            logger.log(f"DB: Found latest macro benchmark date: {latest_date}")
            return latest_date
        else:
            logger.log("DB Warn: No dates found in economy_cards table.")
            return None
    except Exception as e:
        logger.log(f"DB Error: Could not fetch latest macro date. {e}")
        return None

def get_eod_economy_card(client: libsql_client.Client, latest_date: str, logger: AppLogger) -> dict | None:
    """
    Fetches the full EOD Economy Card JSON for the specified benchmark date.
    (Used by ai_services.py)
    """
    logger.log(f"DB: Fetching EOD Economy Card for date: {latest_date}...")
    if not client:
        logger.log("DB Error: No client provided.")
        return None
    try:
        # Fetch the card for that specific date
        rs = client.execute(
            "SELECT economy_card_json FROM economy_cards WHERE date = ?",
            (latest_date,)
        )
        if rs.rows and rs.rows[0][0]:
            return json.loads(rs.rows[0][0])
        else:
            logger.log(f"DB Warn: No EOD Economy Card found for date {latest_date}.")
            return None
    except Exception as e:
        logger.log(f"DB Error: Could not fetch EOD Economy Card for {latest_date}. {e}")
        return None

def get_all_tickers_from_db(client: libsql_client.Client, logger: AppLogger) -> list[str]:
    """Fetches all tickers from the 'stocks' table."""
    logger.log("DB: Fetching all tickers from 'stocks' watchlist...")
    if not client:
        logger.log("DB Error: No client provided.")
        return []
    try:
        rs = client.execute("SELECT ticker FROM stocks")
        return [row[0] for row in rs.rows]
    except Exception as e:
        logger.log(f"DB Error: Could not fetch tickers from 'stocks'. {e}")
        return []

def _parse_levels_from_json_blob(card_json_blob: str, logger: AppLogger) -> tuple[list[float], list[float]]:
    """
    Helper to parse the 'screener_briefing' object from inside
    the full 'company_card_json' blob.
    """
    s_levels, r_levels = [], []
    try:
        # 1. Parse the outer JSON blob
        card_data = json.loads(card_json_blob)
        
        # 2. Extract the 'screener_briefing' object
        #    This is the exact logic from our discussion:
        #    The screener_briefing is *inside* the main JSON.
        briefing_data = card_data.get('screener_briefing')

        if not briefing_data:
            logger.log("DB...Warn: 'screener_briefing' key not found in JSON blob.")
            return [], []

        # 3. If briefing_data is a string, parse *it* as JSON
        #    (Handling nested JSON strings)
        if isinstance(briefing_data, str):
            try:
                briefing_obj = json.loads(briefing_data)
            except json.JSONDecodeError:
                # Fallback for plain text briefing (older format)
                logger.log("DB...Warn: 'screener_briefing' is a text string, not JSON. Parsing with regex.")
                s_match = re.search(r"S_Levels: \[(.*?)\]", briefing_data)
                r_match = re.search(r"R_Levels: \[(.*?)\]", briefing_data)
                s_levels_raw = re.findall(r"\$([\d\.]+)", s_match.group(1)) if s_match else []
                r_levels_raw = re.findall(r"\$([\d\.]+)", r_match.group(1)) if r_match else []
                return [float(lvl) for lvl in s_levels_raw], [float(lvl) for lvl in r_levels_raw]

        # 4. If it's already an object/dict
        elif isinstance(briefing_data, dict):
            briefing_obj = briefing_data
        else:
            logger.log("DB...Warn: 'screener_briefing' is not a recognized format (string or object).")
            return [], []

        # 5. Extract levels from the briefing object
        s_levels_raw = briefing_obj.get('S_Levels', [])
        r_levels_raw = briefing_obj.get('R_Levels', [])
        
        # 6. Sanitize levels (they might be '$255.00' or 255.0)
        s_levels = [float(re.sub(r'[^\d\.]', '', str(lvl))) for lvl in s_levels_raw if str(lvl)]
        r_levels = [float(re.sub(r'[^\d\.]', '', str(lvl))) for lvl in r_levels_raw if str(lvl)]
        
    except Exception as e:
        logger.log(f"DB...Error parsing levels from card JSON: {e}")
    return s_levels, r_levels


def get_eod_card_data_for_screener(client: libsql_client.Client, ticker_list: list, benchmark_date: str, logger: AppLogger) -> dict:
    """
    Fetches the LATEST EOD card data for a list of tickers that
    MATCHES the benchmark_date. This implements the "Date Alignment" rule.
    
    Returns a dictionary:
    { "TICKER": {"screener_briefing_text": "...", "s_levels": [...], "r_levels": [...]}, ... }
    """
    logger.log(f"DB: Fetching EOD card data for {len(ticker_list)} tickers...")
    logger.log(f"DB: Aligning all company cards to Benchmark Date: {benchmark_date}")
    
    db_data = {}
    if not ticker_list or not client:
        return db_data
        
    # Build the query
    # We select all tickers and only those matching the latest date
    placeholders = ','.join('?' * len(ticker_list))
    query = f"""
        SELECT 
            ticker, 
            company_card_json 
        FROM company_cards
        WHERE 
            date = ? AND 
            ticker IN ({placeholders})
    """
    
    try:
        # The first arg is the date, the rest are the tickers
        args = [benchmark_date] + ticker_list
        rs = client.execute(query, args)
        
        found_tickers = set()
        for row in rs.rows:
            ticker = row[0]
            card_json_blob = row[1]
            found_tickers.add(ticker)

            if not card_json_blob:
                logger.log(f"DB Warn: Ticker {ticker} has no company_card_json for {benchmark_date}.")
                continue
            
            s_levels, r_levels = _parse_levels_from_json_blob(card_json_blob, logger)
            
            # Extract the screener_briefing text/object itself
            try:
                # Re-parse the blob to get the briefing
                briefing_data = json.loads(card_json_blob).get('screener_briefing')
                
                # The "Head Trader" AI needs a string. If the briefing
                # is an object, dump it back to a string.
                if isinstance(briefing_data, dict):
                    briefing_text = json.dumps(briefing_data, indent=2)
                else:
                    briefing_text = str(briefing_data) # Use as-is if it's already text

            except Exception:
                briefing_text = "Error parsing briefing from JSON blob."

            db_data[ticker] = {
                "screener_briefing_text": briefing_text,
                "s_levels": s_levels,
                "r_levels": r_levels
            }
        
        # Log any tickers that were *not* found for the benchmark date
        missing_tickers = set(ticker_list) - found_tickers
        for ticker in missing_tickers:
            logger.log(f"DB Warn: Ticker {ticker} is out of sync. No card found for {benchmark_date}. Skipping.")
            
        return db_data
        
    except Exception as e:
        logger.log(f"DB Error: Could not fetch EOD card data. {e}")
        return {}

def save_screener_output(client: libsql_client.Client, briefing_text: str, logger: AppLogger) -> bool:
    """Saves the final AI briefing to the screener_log table."""
    logger.log("DB: Saving final Head Trader briefing to log...")
    if not client:
        logger.log("DB Error: No client provided.")
        return False
        
    # We must ensure the table exists
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS screener_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                briefing_text TEXT NOT NULL
            );
        """)
    except Exception as e:
        logger.log(f"DB Warn: Could not create 'screener_log' table (may exist): {e}")

    try:
        client.execute(
            "INSERT INTO screener_log (timestamp, briefing_text) VALUES (?, ?)",
            (datetime.now().isoformat(), briefing_text)
        )
        logger.log("DB: Save successful.")
        return True
    except Exception as e:
        logger.log(f"DB Error: Could not save screener output. {e}")
        return False