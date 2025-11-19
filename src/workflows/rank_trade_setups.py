# src/workflows/rank_trade_setups.py

import time
import json

from src.external_services.database.connection import create_turso_client
from src.external_services.database.queries import get_eod_card_data_for_screener
from src.external_services.broker_api.market_data import (
    get_capital_current_price, get_capital_price_bars
)
from src.core_trading_logic.technical_indicators import process_premarket_bars_to_summary
from src.external_services.ai_service.llm_calls import call_gemini_api
from src.external_services.database.mutations import save_screener_output
from src.config.constants import LOOP_DELAY

def run_head_trader_screener(
    curated_tickers: list,
    benchmark_date: str,
    economy_card: dict,
    executor_focus: str,
    logger,
    cst: str,
    xst: str,
    api_key: str
) -> tuple[str | None, str | None]:
    """
    Orchestrates:
    - Gathering dossiers,
    - Composing Head Trader prompt,
    - Sending to Gemini,
    - Saving briefing.
    """
    logger.log("Starting Head Trader Screener workflow...")
    client = create_turso_client(logger)
    if not client:
        logger.log("No DB connection.")
        return None, "No DB connection."
    eod_data_map = get_eod_card_data_for_screener(client, curated_tickers, benchmark_date, logger)
    candidate_dossiers = []

    for i, ticker in enumerate(curated_tickers):
        logger.log(f"Processing dossier for {ticker}...")
        if ticker not in eod_data_map:
            logger.log(f"  No EOD data for {ticker}. Skipping.")
            continue
        eod_briefing_text = eod_data_map[ticker].get('screener_briefing_text', 'N/A')
        bid, offer = get_capital_current_price(ticker, cst, xst, logger)
        if not bid:
            logger.log(f"  No live price for {ticker}. Skipping.")
            continue
        live_price = (bid + offer) / 2
        df_pm = get_capital_price_bars(ticker, cst, xst, "MINUTE_5", logger)
        live_pm_summary = (
            process_premarket_bars_to_summary(
                ticker=ticker,
                df_pm=df_pm,
                live_price=live_price,
                logger=logger
            ) if df_pm is not None else "Live PM data fetch failed or empty."
        )
        dossier = (
            f"\n**Ticker:** {ticker}\n"
            f"**EOD Briefing ({benchmark_date}):**\n{eod_briefing_text}\n"
            f"**Live Pre-Market Action:**\n{live_pm_summary}\n"
        )
        candidate_dossiers.append(dossier)
        if i < len(curated_tickers) - 1:
            time.sleep(LOOP_DELAY)

    if not candidate_dossiers:
        return None, "No candidate data was gathered for Head Trader step."

    macro_text = json.dumps(economy_card, indent=2) if economy_card else "Not available."

    prompt = f"""
[MACRO WHY]
{macro_text}

[EXECUTOR'S FOCUS]
"{executor_focus}"

[CANDIDATE DOSSIERS]
{chr(10).join(candidate_dossiers)}

[YOUR TASK]
Output a markdown Head Trader's Briefing grouping setups by alignment.
    """.strip()
    system_prompt = (
        "You are a 'Head Trader' for a proprietary trading desk. "
        "Synthesize the macro context, executor's focus, and all candidate dossiers into a markdown briefing, ordered by setup clarity."
    )
    ai_response = call_gemini_api(prompt, api_key, system_prompt, logger)
    if not ai_response:
        return None, "AI screener did not return a response."
    # Save to screener_log for record-keeping
    save_screener_output(client, ai_response, logger)
    logger.log("Head Trader's Briefing generated and saved.")
    return ai_response, None
