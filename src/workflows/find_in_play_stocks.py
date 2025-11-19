# src/workflows/find_in_play_stocks.py

from src.external_services.database.connection import create_turso_client
from src.external_services.database.queries import (
    get_all_tickers_from_db,
    get_eod_card_data_for_screener,
)
from src.external_services.broker_api.market_data import get_capital_current_price
from src.config.constants import LOOP_DELAY
import time

def run_proximity_scan(
    benchmark_date: str,
    proximity_pct: float,
    logger,
    cst: str,
    xst: str
) -> list[dict]:
    """
    Scan all tickers and return only those within proximity_pct % of an S/R level.
    Returns a list of dicts:
    [
        {"Ticker": "AAPL", "Proximity (%)": "1.23", "Live Price": "$194.12"},
        ...
    ]
    """
    logger.log("Starting proximity scan for in-play stocks...")
    client = create_turso_client(logger)
    if not client:
        logger.log("No DB connection, abort.")
        return []

    all_tickers = get_all_tickers_from_db(client, logger)
    if not all_tickers:
        logger.log("No tickers found in DB.")
        return []

    eod_data_map = get_eod_card_data_for_screener(client, all_tickers, benchmark_date, logger)
    scan_results = []
    for i, ticker in enumerate(eod_data_map.keys()):
        logger.log(f"Scanning ticker: {ticker}")
        bid, offer = get_capital_current_price(ticker, cst, xst, logger)
        if not bid:
            logger.log(f"Warn: No live bid for {ticker}. Skipping.")
            continue
        live_price = (bid + offer) / 2
        eod_data = eod_data_map[ticker]
        all_levels = eod_data.get('s_levels', []) + eod_data.get('r_levels', [])
        all_levels = [lvl for lvl in all_levels if lvl != 0]
        if not all_levels:
            logger.log(f"Warn: {ticker} has no valid S/R levels. Skipping.")
            continue
        min_dist_pct = min([abs(live_price - level) / level for level in all_levels]) * 100
        if min_dist_pct <= proximity_pct:
            scan_results.append({
                "Ticker": ticker,
                "Proximity (%)": f"{min_dist_pct:.2f}",
                "Live Price": f"${live_price:.2f}"
            })
        if i < len(eod_data_map) - 1:
            time.sleep(LOOP_DELAY)
    logger.log(f"Scan complete. {len(scan_results)} tickers found in-play.")
    return sorted(scan_results, key=lambda x: float(x['Proximity (%)']))
