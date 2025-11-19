# src/external_services/database/mutations.py

from datetime import datetime
from src.logging.app_logger import AppLogger

def save_screener_output(client, briefing_text: str, logger: AppLogger) -> bool:
    """
    Save the final AI briefing or any important output to the 'screener_log' table.
    """
    logger.log("DB: Saving Head Trader briefing to screener_log table...")
    try:
        # Ensure the table exists
        client.execute("""
            CREATE TABLE IF NOT EXISTS screener_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                briefing_text TEXT NOT NULL
            );
        """)
    except Exception as e:
        logger.log(f"DB Warn: Table create error (may exist): {e}")

    try:
        # Insert result
        client.execute(
            "INSERT INTO screener_log (timestamp, briefing_text) VALUES (?, ?)",
            (datetime.utcnow().isoformat(), briefing_text)
        )
        logger.log("DB: Save successful.")
        return True
    except Exception as e:
        logger.log(f"DB Error: Could not save screener output. {e}")
        return False

# You can add more "write" operations below, for example:

def upsert_eod_economy_card(client, date: str, card_json: str, logger: AppLogger) -> bool:
    """
    Update or insert an EOD Economy Card for a given date.
    """
    logger.log(f"DB: Upserting EOD Economy Card for date: {date}")
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS economy_cards (
                date TEXT PRIMARY KEY,
                economy_card_json TEXT NOT NULL
            );
        """)
        client.execute("""
            INSERT INTO economy_cards (date, economy_card_json)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET economy_card_json=excluded.economy_card_json;
        """, (date, card_json))
        logger.log("DB: Upsert successful.")
        return True
    except Exception as e:
        logger.log(f"DB Error: Could not upsert EOD economy card. {e}")
        return False

# Similarly, add more mutation helpers as your data model evolves.
