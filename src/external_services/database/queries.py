# src/external_services/database/queries.py

import json
from src.logging.app_logger import AppLogger

def get_latest_economy_card_date(client, logger: AppLogger):
    logger.log("DB: Fetching latest economy card date...")
    try:
        rs = client.execute("SELECT MAX(date) FROM economy_cards")
        return rs.rows[0][0] if rs.rows and rs.rows[0][0] else None
    except Exception as e:
        logger.log(f"DB Error: Could not fetch latest macro date. {e}")
        return None

def get_eod_economy_card(client, date, logger: AppLogger):
    logger.log(f"DB: Fetching EOD Economy Card for {date}...")
    try:
        rs = client.execute("SELECT economy_card_json FROM economy_cards WHERE date = ?", (date,))
        return json.loads(rs.rows[0][0]) if rs.rows and rs.rows[0][0] else None
    except Exception as e:
        logger.log(f"DB Error: Could not fetch card for {date}. {e}")
        return None

def get_all_tickers_from_db(client, logger: AppLogger):
    logger.log("DB: Fetching all tickers from 'stocks'...")
    try:
        rs = client.execute("SELECT ticker FROM stocks")
        return [row[0] for row in rs.rows]
    except Exception as e:
        logger.log(f"DB Error fetching tickers: {e}")
        return []

def _parse_levels_from_json_blob(card_json_blob: str, logger: AppLogger):
    import re
    s_levels, r_levels = [], []
    try:
        card_data = json.loads(card_json_blob)
        briefing_data = card_data.get('screener_briefing')

        if not briefing_data:
            logger.log("DB Warn: No screener_briefing key.")
            return [], []

        if isinstance(briefing_data, str):
            try:
                briefing_obj = json.loads(briefing_data)
            except json.JSONDecodeError:
                s_match = re.search(r"S_Levels: \[(.*?)\]", briefing_data)
                r_match = re.search(r"R_Levels: \[(.*?)\]", briefing_data)
                s_levels_raw = re.findall(r"\$([\d\.]+)", s_match.group(1)) if s_match else []
                r_levels_raw = re.findall(r"\$([\d\.]+)", r_match.group(1)) if r_match else []
                return [float(lvl) for lvl in s_levels_raw], [float(lvl) for lvl in r_levels_raw]
        elif isinstance(briefing_data, dict):
            briefing_obj = briefing_data
        else:
            logger.log("DB Warn: screener_briefing not recognized format.")
            return [], []

        s_levels_raw = briefing_obj.get('S_Levels', [])
        r_levels_raw = briefing_obj.get('R_Levels', [])
        s_levels = [float(str(lvl).replace("$", "")) for lvl in s_levels_raw if str(lvl)]
        r_levels = [float(str(lvl).replace("$", "")) for lvl in r_levels_raw if str(lvl)]
    except Exception as e:
        logger.log(f"DB Error parsing S/R levels: {e}")
    return s_levels, r_levels


def get_eod_card_data_for_screener(client, tickers, benchmark_date, logger: AppLogger):
    logger.log(f"DB: Fetching EOD card data for {len(tickers)} tickers ({benchmark_date})...")
    if not tickers or not client:
        return {}

    placeholders = ','.join('?' * len(tickers))
    query = f"""
        SELECT ticker, company_card_json
        FROM company_cards
        WHERE date = ? AND ticker IN ({placeholders})
    """

    db_data = {}
    try:
        args = [benchmark_date] + tickers
        rs = client.execute(query, args)
        found_tickers = set()
        for row in rs.rows:
            ticker, card_json_blob = row
            found_tickers.add(ticker)
            if not card_json_blob:
                logger.log(f"DB Warn: {ticker} has no data.")
                continue
            s_levels, r_levels = _parse_levels_from_json_blob(card_json_blob, logger)
            try:
                briefing = json.loads(card_json_blob).get('screener_briefing')
                briefing_text = json.dumps(briefing, indent=2) if isinstance(briefing, dict) else str(briefing)
            except Exception:
                briefing_text = "Parse briefing error"
            db_data[ticker] = {
                "screener_briefing_text": briefing_text,
                "s_levels": s_levels,
                "r_levels": r_levels
            }
        # Optionally warn/skipped for missing_tickers
        return db_data
    except Exception as e:
        logger.log(f"DB Error: Could not fetch EOD card data. {e}")
        return {}
