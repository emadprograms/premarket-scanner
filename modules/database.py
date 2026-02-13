import streamlit as st
import json
import re
import sqlite3
from datetime import datetime
from libsql_client import create_client_sync, LibsqlError
from modules.utils import AppLogger

class LocalDBClient:
    """Wrapper to make sqlite3 look like libsql_client"""
    def __init__(self, path):
        self.path = path
    
    def execute(self, query, params=None):
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        if params:
            cursor.execute(query.replace('?', '?'), params) # sqlite3 uses ? too
        else:
            cursor.execute(query)
        
        rows = cursor.fetchall()
        cols = [description[0] for description in cursor.description] if cursor.description else []
        conn.close()
        
        # Mocking the ResultSet object
        class ResultSet:
            def __init__(self, rows, columns):
                self.rows = rows
                self.columns = columns
        return ResultSet(rows, cols)

@st.cache_resource(show_spinner="Connecting to Headquarters...")
def get_db_connection(db_url: str, auth_token: str, local_mode=False, local_path="data/local_cache.db"):
    if local_mode:
        import os
        if not os.path.exists(local_path):
            st.warning("Local database not found. Please Sync first.")
            return None
        return LocalDBClient(local_path)
        
    if not db_url or not auth_token:
        return None
    try:
        return create_client_sync(url=db_url, auth_token=auth_token)
    except Exception as e:
        st.error(f"Failed to connect to DB: {e}")
        return None

def init_db_schema(client, logger: AppLogger):
    if isinstance(client, LocalDBClient):
        return # Assume local schema is synced from Turso
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS premarket_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                input_news_snapshot TEXT,
                economy_card_snapshot TEXT,
                live_stats_snapshot TEXT,
                final_briefing TEXT
            );
        """)
        logger.log("DB: Schema verified.")
    except Exception as e:
        logger.log(f"DB Error: {e}")

# @st.cache_data(ttl=3600, show_spinner=False) # REMOVED: User requested no caching in Live Mode
def get_latest_economy_card_date(_client, cutoff_str: str, _logger: AppLogger) -> str:
    try:
        cutoff_date_part = cutoff_str.split(" ")[0]
        rs = _client.execute(
            "SELECT MAX(date) FROM economy_cards WHERE date <= ?",
            [cutoff_date_part]
        )
        return rs.rows[0][0] if rs.rows and rs.rows[0][0] else None
    except Exception:
        return None

# @st.cache_data(ttl=3600, show_spinner=False) # REMOVED: User requested no caching in Live Mode
def get_eod_economy_card(_client, benchmark_date: str, _logger: AppLogger) -> dict:
    try:
        rs = _client.execute("SELECT economy_card_json FROM economy_cards WHERE date = ?", (benchmark_date,))
        return json.loads(rs.rows[0][0]) if rs.rows and rs.rows[0][0] else None
    except Exception as e:
        _logger.log(f"DB Error (EOD Card): {e}")
        return None

def _parse_levels_from_json_blob(card_json_blob: str, logger: AppLogger) -> tuple[list[float], list[float]]:
    s_levels, r_levels = [], []
    try:
        card_data = json.loads(card_json_blob)
        briefing_data = card_data.get('screener_briefing')
        if isinstance(briefing_data, str):
            try:
                briefing_obj = json.loads(briefing_data)
            except json.JSONDecodeError:
                s_match = re.search(r"S_Levels: \[(.*?)\]", briefing_data)
                r_match = re.search(r"R_Levels: \[(.*?)\]", briefing_data)
                s_str = s_match.group(1) if s_match else ""
                r_str = r_match.group(1) if r_match else ""
                s_levels = [float(x) for x in re.findall(r"[\d\.]+", s_str)]
                r_levels = [float(x) for x in re.findall(r"[\d\.]+", r_str)]
                return s_levels, r_levels
        elif isinstance(briefing_data, dict):
            briefing_obj = briefing_data
        else:
            return [], []

        s_levels = [
            float(str(l).replace('$', ''))
            for l in briefing_obj.get('S_Levels', [])
            if str(l).replace('$', '').replace('.', '', 1).isdigit()
        ]
        r_levels = [
            float(str(l).replace('$', ''))
            for l in briefing_obj.get('R_Levels', [])
            if str(l).replace('$', '').replace('.', '', 1).isdigit()
        ]
    except Exception:
        pass
    return s_levels, r_levels

# @st.cache_data(ttl=3600, show_spinner=False) # REMOVED: User requested no caching in Live Mode
def get_eod_card_data_for_screener(_client, ticker_tuple: tuple, benchmark_date: str, _logger: AppLogger) -> dict:
    # Use ticker_tuple for caching compatibility (lists are unhashable)
    ticker_list = list(ticker_tuple)
    db_data = {}
    if not ticker_list or not _client:
        return db_data

    # ROBUST FIX: Fetch the latest plan PER TICKER individually.
    # This handles cases where some tickers have plans for Today, and others only for Yesterday.
    try:
        # Use a Window Function (Supported by Turso/Modern SQLite) to find the latest record for EACH ticker.
        placeholders = ','.join(['?'] * len(ticker_list))
        query = f"""
            WITH LatestCards AS (
                SELECT 
                    ticker, 
                    company_card_json, 
                    date,
                    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                FROM company_cards
                WHERE date <= ? AND ticker IN ({placeholders})
            )
            SELECT ticker, company_card_json, date
            FROM LatestCards
            WHERE rn = 1
        """
        args = [benchmark_date] + ticker_list
        rs = _client.execute(query, args)

        for row in rs.rows:
            ticker, card_json_blob, actual_date = row[0], row[1], row[2]
            if not card_json_blob:
                continue
            s_levels, r_levels = _parse_levels_from_json_blob(card_json_blob, _logger)
            try:
                card_data = json.loads(card_json_blob)
                briefing_data = card_data.get('screener_briefing')
                briefing_text = (
                    json.dumps(briefing_data, indent=2)
                    if isinstance(briefing_data, dict)
                    else str(briefing_data)
                )
            except Exception:
                briefing_text = "Error parsing."
            db_data[ticker] = {
                "screener_briefing_text": briefing_text,
                "s_levels": s_levels,
                "r_levels": r_levels,
                "plan_date": actual_date
            }
        return db_data
    except Exception as e:
        _logger.log(f"DB Error (EOD Data Refactored): {e}")
        return {}

# @st.cache_data(ttl=86400, show_spinner=False) # REMOVED: User requested no caching in Live Mode
def get_all_tickers_from_db(_client, _logger: AppLogger) -> list[str]:
    try:
        rs = _client.execute("SELECT user_ticker FROM symbol_map")
        return [row[0] for row in rs.rows]
    except Exception as e:
        _logger.log(f"DB Error (Get Tickers): {e}")
        return []

def save_snapshot(client, news_input: str, eco_card: dict, live_stats: str, briefing: str, logger: AppLogger) -> bool:
    if not client or isinstance(client, LocalDBClient):
        return False # Don't save snapshots to local cache
    try:
        ts = datetime.now().isoformat()
        eco_json = json.dumps(eco_card)
        client.execute(
            """
            INSERT INTO premarket_snapshots
            (run_timestamp, input_news_snapshot, economy_card_snapshot, live_stats_snapshot, final_briefing)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, news_input, eco_json, live_stats, briefing),
        )
        logger.log("DB: Snapshot saved.")
        return True
    except Exception as e:
        logger.log(f"DB Error (Save Snapshot): {e}")
        return False
